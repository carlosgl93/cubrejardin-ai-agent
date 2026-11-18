"""Tests for RAGAgent."""

from __future__ import annotations

import json

from agents.rag_agent import RAGAgent
from models.schemas import RAGResponse


class DummyOpenAIService:
    """Stub OpenAI service."""

    def __init__(
        self,
        *,
        rewrite_text: str = "Costo de envío a Las Condes",
        fail_rewrite: bool = False,
        rerank_order: list[int] | None = None,
        answer_payload: dict | None = None,
    ) -> None:
        self.embed_called = False
        self.embedded_queries: list[str] = []
        self.chat_called = False
        self.chat_calls: int = 0
        self.rewrite_text = rewrite_text
        self.fail_rewrite = fail_rewrite
        self.rerank_order = rerank_order
        self.answer_payload = answer_payload

    def embed(self, *, input_texts):  # type: ignore[override]
        self.embed_called = True
        self.embedded_queries.extend(input_texts)
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    def chat_completion(self, *, messages, response_format=None):  # type: ignore[override]
        self.chat_called = True
        self.chat_calls += 1
        system_msg = messages[0]["content"] if messages else ""
        if "Reescribe la última pregunta" in system_msg:
            if self.fail_rewrite:
                raise RuntimeError("LLM unavailable")
            return {"choices": [{"message": {"content": self.rewrite_text}}]}
        if "evaluador de relevancia" in system_msg and self.rerank_order is not None:
            return {"choices": [{"message": {"content": json.dumps({"ranked_indices": self.rerank_order})}}]}
        if self.answer_payload is not None:
            return {"choices": [{"message": {"content": json.dumps(self.answer_payload)}}]}
        return {"choices": [{"message": {"content": "Respuesta"}}]}


class DummyVectorStore:
    """Stub vector store returning fixed score."""

    def search(self, embedding, top_k=5):  # type: ignore[override]
        return [(0.9, {"title": "Doc", "content": "Contenido"})]


class HybridDummyVectorStore:
    """Stub hybrid vector store recording query_text passed to search_hybrid."""

    def __init__(self) -> None:
        self.hybrid_queries: list[str] = []

    def search_hybrid(self, embedding, query_text: str, top_k: int = 5):
        self.hybrid_queries.append(query_text)
        return [(0.85, {"title": "Despacho", "content": "Envío a Las Condes: $4.990"})]


def test_rag_answer() -> None:
    """RAG agent should respond with high confidence."""

    openai_service = DummyOpenAIService()
    vector_store = DummyVectorStore()
    agent = RAGAgent(openai_service, vector_store)
    response = agent.answer("Pregunta")
    assert isinstance(response, RAGResponse)
    assert response.confidence == 0.9
    assert "Doc" in response.sources[0]["title"]
    assert openai_service.chat_calls == 1


def test_rag_rewrites_query_with_history_and_uses_hybrid_search() -> None:
    """Follow-up queries with history should be rewritten before embedding and hybrid search."""

    openai_service = DummyOpenAIService(rewrite_text="Precio de despacho a Las Condes")
    vector_store = HybridDummyVectorStore()
    agent = RAGAgent(openai_service, vector_store)  # type: ignore[arg-type]
    history = [
        {"role": "user", "content": "¿Hacen envíos a Providencia?"},
        {"role": "assistant", "content": "Sí, el despacho a Providencia cuesta $3.990."},
    ]

    context_text, sources, best_score = agent.retrieve_context("¿y a Las Condes?", history, top_k=3)

    assert openai_service.embedded_queries == ["Precio de despacho a Las Condes"]
    assert vector_store.hybrid_queries == ["Precio de despacho a Las Condes"]
    assert "Las Condes" in context_text
    assert sources == [{"title": "Despacho", "score": "0.85"}]
    assert best_score == 0.85


def test_rag_rewrite_falls_back_to_original_query_on_error() -> None:
    """If query rewriting fails, RAGAgent must fall back to the original user query."""

    openai_service = DummyOpenAIService(fail_rewrite=True)
    vector_store = HybridDummyVectorStore()
    agent = RAGAgent(openai_service, vector_store)  # type: ignore[arg-type]
    history = [{"role": "user", "content": "Hola"}]

    agent.retrieve_context("¿y a Las Condes?", history)

    assert openai_service.embedded_queries == ["¿y a Las Condes?"]
    assert vector_store.hybrid_queries == ["¿y a Las Condes?"]


def test_rag_reranks_12_candidates_down_to_4() -> None:
    """Hybrid search fetches 12 candidates and reranks them down to 4."""

    class ManyCandidatesStore:
        def __init__(self) -> None:
            self.requested_top_k: int | None = None

        def search_hybrid(self, embedding, query_text: str, top_k: int = 12):
            self.requested_top_k = top_k
            return [
                (0.5, {"title": f"Doc-{i}", "content": f"Contenido {i}"})
                for i in range(12)
            ]

    openai_service = DummyOpenAIService(rerank_order=[9, 4, 1, 0])
    vector_store = ManyCandidatesStore()
    agent = RAGAgent(openai_service, vector_store)  # type: ignore[arg-type]

    _, sources, _ = agent.retrieve_context("SKU-9", top_k=4)

    assert vector_store.requested_top_k == 12
    assert [s["title"] for s in sources] == ["Doc-9", "Doc-4", "Doc-1", "Doc-0"]


def test_rag_answer_uses_calibrated_answerability_confidence() -> None:
    """Answerable JSON overrides low cosine score; unanswerable caps confidence below 0.5."""

    class LowCosineStore:
        def search_hybrid(self, embedding, query_text: str, top_k: int = 12):
            return [(0.38, {"title": "Catalogo", "content": "SKU-402 cuesta $19.990"})]

    answerable_agent = RAGAgent(
        DummyOpenAIService(
            answer_payload={"answer": "El SKU-402 cuesta $19.990.", "answerable": True, "confidence": 0.92}
        ),
        LowCosineStore(),  # type: ignore[arg-type]
    )
    ok_resp = answerable_agent.answer("Precio SKU-402")
    assert ok_resp.confidence == 0.92
    assert ok_resp.disclaimer is None

    unanswerable_agent = RAGAgent(
        DummyOpenAIService(
            answer_payload={"answer": "No tengo esa información.", "answerable": False, "confidence": 0.8}
        ),
        LowCosineStore(),  # type: ignore[arg-type]
    )
    low_resp = unanswerable_agent.answer("Tienen tienda en Marte?")
    assert low_resp.confidence <= 0.45
    assert low_resp.disclaimer is not None
