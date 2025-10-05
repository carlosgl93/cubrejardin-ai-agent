"""RAG agent implementation."""

from __future__ import annotations

from typing import Dict, List, Tuple

from config.prompts import rag_prompt
from models.schemas import RAGResponse
from services.openai_service import OpenAIService
from services.vector_store import VectorStoreService
from utils.helpers import build_response_message


class RAGAgent:
    """Agent responsible for retrieving and answering queries."""

    def __init__(self, openai_service: OpenAIService, vector_store: VectorStoreService) -> None:
        self.openai_service = openai_service
        self.vector_store = vector_store
        self.system_prompt = rag_prompt()

    def _build_context(self, query: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], float]:
        """Retrieve relevant documents for query."""

        embedding_response = self.openai_service.embed(input_texts=[query])
        embedding = embedding_response["data"][0]["embedding"]
        search_results = self.vector_store.search(embedding, top_k=5)
        documents: List[Dict[str, str]] = []
        sources: List[Dict[str, str]] = []
        best_score = 0.0
        for score, metadata in search_results:
            documents.append({"role": "system", "content": f"Fuente: {metadata['title']}\n{metadata['content']}"})
            sources.append({"title": metadata.get("title", ""), "score": f"{score:.2f}"})
            best_score = max(best_score, score)
        return documents, sources, best_score

    def answer(self, query: str) -> RAGResponse:
        """Answer query using retrieved documents."""

        context_messages, sources, best_score = self._build_context(query)
        messages = context_messages + [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        response = self.openai_service.chat_completion(messages=messages)
        answer = response["choices"][0]["message"]["content"].strip()
        confidence = float(best_score)
        disclaimer = None
        if confidence < 0.5:
            disclaimer = "Estoy reenviando tu consulta a un agente humano para brindarte la mejor respuesta."
        elif confidence < 0.75:
            disclaimer = "La información puede no ser exacta; si necesitas confirmación házmelo saber."
        answer_text = build_response_message(answer, disclaimer if confidence < 0.75 and disclaimer else None)
        return RAGResponse(answer=answer_text, confidence=confidence, sources=sources, disclaimer=disclaimer)
