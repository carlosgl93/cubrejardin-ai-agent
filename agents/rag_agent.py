"""RAG agent implementation."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from config.prompts import rag_prompt
from models.schemas import RAGResponse
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from utils import logger
from utils.helpers import build_response_message


_QUERY_REWRITE_PROMPT = (
    "Reescribe la última pregunta del cliente como una consulta de búsqueda "
    "independiente y específica en español, resolviendo pronombres o referencias "
    "usando el historial de conversación. Responde SOLO con la consulta reescrita, "
    "sin comillas ni explicaciones."
)

_RERANK_PROMPT = (
    "Eres un evaluador de relevancia para búsqueda documental. "
    "Dada la consulta del cliente y una lista numerada de fragmentos, "
    "ordena los índices de los fragmentos más relevantes para responder la consulta. "
    'Responde SOLO con JSON: {"ranked_indices": [0, 2, ...]}.'
)

_ANSWER_JSON_PROMPT = (
    "Responde usando únicamente la información de las fuentes proporcionadas. "
    'Devuelve SOLO un JSON válido con este formato: '
    '{"answer": "respuesta clara en español para el cliente", '
    '"answerable": true, "confidence": 0.9}. '
    "Si las fuentes no contienen información suficiente para responder con certeza, "
    'usa "answerable": false y "confidence" menor a 0.45.'
)

_HYBRID_CANDIDATES_K = 12
_RERANK_FINAL_K = 4


class RAGAgent:
    """Agent responsible for retrieving and answering queries."""

    def __init__(
        self,
        openai_service: OpenAIService,
        vector_store: VectorStoreService,
        system_prompt: str | None = None,
        business_name: str = "el negocio",
    ) -> None:
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.business_name = business_name
        self.system_prompt = rag_prompt(
            system_prompt=system_prompt, business_name=business_name
        )

    def _rewrite_query(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Rewrite an ambiguous follow-up query into a standalone Spanish search query."""

        cleaned_query = query.strip()
        if not cleaned_query or not history:
            return cleaned_query

        recent_turns = [
            f"{turn.get('role', 'user')}: {turn.get('content', '').strip()}"
            for turn in history[-6:]
            if turn.get("content", "").strip()
        ]
        if not recent_turns:
            return cleaned_query

        history_block = "\n".join(recent_turns)
        try:
            response = self.openai_service.chat_completion(
                messages=[
                    {"role": "system", "content": _QUERY_REWRITE_PROMPT},
                    {
                        "role": "user",
                        "content": f"Historial:\n{history_block}\n\nPregunta actual: {cleaned_query}",
                    },
                ]
            )
            rewritten = response["choices"][0]["message"]["content"].strip().strip('"').strip("'")
            if rewritten:
                logger.info(
                    "rag_query_rewritten",
                    extra={"original": cleaned_query, "rewritten": rewritten},
                )
                return rewritten
        except Exception as exc:
            logger.warning("rag_query_rewrite_failed", extra={"error": str(exc)})
        return cleaned_query

    def _chat_json(self, messages: List[Dict[str, str]]) -> str:
        """Call chat_completion requesting JSON, falling back if a stub omits response_format."""

        try:
            response = self.openai_service.chat_completion(
                messages=messages,
                response_format={"type": "json_object"},
            )
        except TypeError:
            response = self.openai_service.chat_completion(messages=messages)
        return str(response["choices"][0]["message"]["content"]).strip()

    def _rerank_candidates(
        self,
        query: str,
        candidates: List[Tuple[float, Dict[str, Any]]],
        *,
        top_k: int = _RERANK_FINAL_K,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Rerank hybrid search candidates down to top_k using an LLM JSON pass."""

        if len(candidates) <= top_k:
            return candidates

        numbered = "\n\n".join(
            f"[{idx}] {item[1].get('title', '')}\n{str(item[1].get('content', ''))[:400]}"
            for idx, item in enumerate(candidates)
        )
        try:
            raw = self._chat_json(
                [
                    {"role": "system", "content": _RERANK_PROMPT},
                    {"role": "user", "content": f"Consulta: {query}\n\nFragmentos:\n{numbered}"},
                ]
            )
            parsed = json.loads(raw)
            ranked_indices = parsed.get("ranked_indices")
            if not isinstance(ranked_indices, list) or not ranked_indices:
                return candidates[:top_k]

            selected: List[int] = []
            seen: set[int] = set()
            for idx in ranked_indices:
                if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                    seen.add(idx)
                    selected.append(idx)
            for idx in range(len(candidates)):
                if len(selected) >= top_k:
                    break
                if idx not in seen:
                    seen.add(idx)
                    selected.append(idx)
            if selected:
                return [candidates[idx] for idx in selected[:top_k]]
        except Exception as exc:
            logger.warning("rag_rerank_failed", extra={"error": str(exc)})
        return candidates[:top_k]

    def _search_documents(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        *,
        top_k: int = _RERANK_FINAL_K,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        """Rewrite query if needed, embed, run hybrid search, and rerank to top_k."""

        search_query = self._rewrite_query(query, history)
        embedding_response = self.openai_service.embed(input_texts=[search_query])
        embedding = embedding_response["data"][0]["embedding"]
        candidate_k = max(top_k, _HYBRID_CANDIDATES_K)
        if hasattr(self.vector_store, "search_hybrid"):
            candidates = self.vector_store.search_hybrid(embedding, search_query, top_k=candidate_k)
        else:
            candidates = self.vector_store.search(embedding, top_k=candidate_k)
        return self._rerank_candidates(search_query, candidates, top_k=top_k)

    def retrieve_context(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        *,
        top_k: int = 5,
    ) -> Tuple[str, List[Dict[str, str]], float]:
        """Retrieve plain context text, source metadata, and best score for downstream agents."""

        search_results = self._search_documents(query, history, top_k=top_k)
        chunks: List[str] = []
        sources: List[Dict[str, str]] = []
        best_score = 0.0
        for score, metadata in search_results:
            content = str(metadata.get("content", "")).strip()
            if content:
                chunks.append(content)
            sources.append({"title": metadata.get("title", "unknown"), "score": f"{score:.2f}"})
            best_score = max(best_score, float(score))
        return "\n\n".join(chunks), sources, best_score

    def _build_context(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        *,
        top_k: int = 5,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], float]:
        """Retrieve relevant documents for query."""

        search_results = self._search_documents(query, history, top_k=top_k)
        documents: List[Dict[str, str]] = []
        sources: List[Dict[str, str]] = []
        best_score = 0.0
        for score, metadata in search_results:
            documents.append({"role": "system", "content": f"Fuente: {metadata['title']}\n{metadata['content']}"})
            sources.append({"title": metadata.get("title", ""), "score": f"{score:.2f}"})
            best_score = max(best_score, float(score))
        return documents, sources, best_score

    def answer(self, query: str, history: Optional[List[Dict[str, str]]] = None) -> RAGResponse:
        """Answer query using retrieved documents and calibrated answerability confidence."""

        context_messages, sources, best_score = self._build_context(query, history, top_k=_RERANK_FINAL_K)
        messages = context_messages + [
            {"role": "system", "content": f"{self.system_prompt}\n\n{_ANSWER_JSON_PROMPT}"},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": query})

        raw_content = self._chat_json(messages)
        answer = raw_content
        confidence = float(best_score)

        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict) and isinstance(parsed.get("answer"), str) and parsed["answer"].strip():
                answer = parsed["answer"].strip()
                answerable = bool(parsed.get("answerable", True))
                raw_conf = float(parsed.get("confidence", best_score))
                clamped_conf = max(0.0, min(1.0, raw_conf))
                confidence = clamped_conf if answerable else min(clamped_conf, 0.45)
            elif isinstance(parsed, dict):
                fallback_messages = context_messages + [{"role": "system", "content": self.system_prompt}]
                if history:
                    fallback_messages.extend(history)
                fallback_messages.append({"role": "user", "content": query})
                fallback_resp = self.openai_service.chat_completion(messages=fallback_messages)
                answer = str(fallback_resp["choices"][0]["message"]["content"]).strip()
        except (ValueError, TypeError):
            pass

        disclaimer = None
        if confidence < 0.5:
            disclaimer = "Estoy reenviando tu consulta a un agente humano para brindarte la mejor respuesta."
        elif confidence < 0.75:
            disclaimer = "La información puede no ser exacta; si necesitas confirmación házmelo saber."
        answer_text = build_response_message(answer, disclaimer if confidence < 0.75 and disclaimer else None)
        return RAGResponse(answer=answer_text, confidence=confidence, sources=sources, disclaimer=disclaimer)
