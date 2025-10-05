"""Tests for RAGAgent."""

from __future__ import annotations

from agents.rag_agent import RAGAgent
from models.schemas import RAGResponse


class DummyOpenAIService:
    """Stub OpenAI service."""

    def __init__(self) -> None:
        self.embed_called = False
        self.chat_called = False

    def embed(self, *, input_texts):  # type: ignore[override]
        self.embed_called = True
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    def chat_completion(self, *, messages):  # type: ignore[override]
        self.chat_called = True
        return {"choices": [{"message": {"content": "Respuesta"}}]}


class DummyVectorStore:
    """Stub vector store returning fixed score."""

    def search(self, embedding, top_k=5):  # type: ignore[override]
        return [(0.9, {"title": "Doc", "content": "Contenido"})]


def test_rag_answer() -> None:
    """RAG agent should respond with high confidence."""

    openai_service = DummyOpenAIService()
    vector_store = DummyVectorStore()
    agent = RAGAgent(openai_service, vector_store)
    response = agent.answer("Pregunta")
    assert isinstance(response, RAGResponse)
    assert response.confidence == 0.9
    assert "Doc" in response.sources[0]["title"]
