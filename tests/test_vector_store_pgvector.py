"""Tests for the pgvector-backed vector store."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from services.vector_store import VectorStoreService


class FakeResponse:
    """Small response object matching Supabase's `.execute()` contract."""

    def __init__(self, data: Optional[List[Dict[str, Any]]] = None) -> None:
        self.data = data or []


class FakeRPCQuery:
    """Record RPC calls and return canned data."""

    def __init__(self, client: "FakeSupabaseClient", name: str, params: Dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> FakeResponse:
        self.client.rpc_calls.append((self.name, self.params))
        return FakeResponse(self.client.rpc_results)


class FakeTableQuery:
    """Support the subset of the Supabase table API used by the vector store."""

    def __init__(self, client: "FakeSupabaseClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self._mode = "select"
        self._rows: List[Dict[str, Any]] = []
        self._filters: Dict[str, Any] = {}
        self._contains: Dict[str, Any] = {}

    def insert(self, rows: List[Dict[str, Any]]) -> "FakeTableQuery":
        self._mode = "insert"
        self._rows = rows
        return self

    def delete(self) -> "FakeTableQuery":
        self._mode = "delete"
        return self

    def eq(self, key: str, value: Any) -> "FakeTableQuery":
        self._filters[key] = value
        return self

    def contains(self, key: str, value: Dict[str, Any]) -> "FakeTableQuery":
        self._contains[key] = value
        return self

    def execute(self) -> FakeResponse:
        if self._mode == "insert":
            inserted_rows: List[Dict[str, Any]] = []
            for index, row in enumerate(self._rows, start=1):
                stored = dict(row)
                stored["id"] = f"doc-{len(self.client.documents) + index}"
                inserted_rows.append(stored)
            self.client.documents.extend(inserted_rows)
            self.client.insert_calls.append(inserted_rows)
            return FakeResponse(inserted_rows)

        if self._mode == "delete":
            remaining: List[Dict[str, Any]] = []
            deleted: List[Dict[str, Any]] = []
            for row in self.client.documents:
                matches_eq = all(row.get(key) == value for key, value in self._filters.items())
                matches_contains = True
                for key, expected in self._contains.items():
                    payload = row.get(key) or {}
                    if not isinstance(payload, dict) or not all(payload.get(k) == v for k, v in expected.items()):
                        matches_contains = False
                        break
                if matches_eq and matches_contains:
                    deleted.append(row)
                    continue
                remaining.append(row)
            self.client.documents = remaining
            self.client.delete_calls.append(
                {
                    "filters": dict(self._filters),
                    "contains": dict(self._contains),
                    "deleted": deleted,
                }
            )
            return FakeResponse(deleted)

        raise AssertionError(f"Unsupported fake mode: {self._mode}")


class FakeSupabaseClient:
    """Capture vector store interactions without a real Supabase project."""

    def __init__(self) -> None:
        self.rpc_results: List[Dict[str, Any]] = []
        self.rpc_calls: List[Any] = []
        self.documents: List[Dict[str, Any]] = []
        self.insert_calls: List[List[Dict[str, Any]]] = []
        self.delete_calls: List[Dict[str, Any]] = []

    def rpc(self, name: str, params: Dict[str, Any]) -> FakeRPCQuery:
        return FakeRPCQuery(self, name, params)

    def table(self, table_name: str) -> FakeTableQuery:
        return FakeTableQuery(self, table_name)


def test_pgvector_search_calls_rpc_with_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenant searches must go through the match_documents RPC."""

    client = FakeSupabaseClient()
    client.rpc_results = [
        {
            "id": "doc-1",
            "title": "Guia A",
            "content": "Contenido A",
            "metadata": {"source_title": "Guia A"},
            "similarity": 0.91,
        },
        {
            "id": "doc-2",
            "title": "Guia B",
            "content": "Contenido B",
            "metadata": {"source_title": "Guia B"},
            "similarity": 0.84,
        },
    ]
    monkeypatch.setattr("services.vector_store.get_supabase_client", lambda: client)

    service = VectorStoreService(tenant_id="tenant-a", backend="pgvector")
    results = service.search([0.1, 0.2, 0.3], top_k=2, min_similarity=0.8)

    assert [item[1]["title"] for item in results] == ["Guia A", "Guia B"]
    assert client.rpc_calls == [
        (
            "match_documents",
            {
                "query_embedding": [0.1, 0.2, 0.3],
                "match_count": 2,
                "p_tenant_id": "tenant-a",
                "min_similarity": 0.8,
            },
        )
    ]


def test_pgvector_add_embeddings_inserts_rows_with_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """pgvector writes should normalize each document row before inserting."""

    client = FakeSupabaseClient()
    monkeypatch.setattr("services.vector_store.get_supabase_client", lambda: client)

    service = VectorStoreService(tenant_id="tenant-a", backend="pgvector")
    inserted_ids = service.add_embeddings(
        [[0.42, 0.24]],
        [
            {
                "title": "Manual de soporte",
                "content": "Contenido principal",
                "file_type": "markdown",
                "metadata": {"source_title": "Manual de soporte"},
                "question": "Como instalar",
                "source": "load_documents",
            }
        ],
    )

    assert inserted_ids == ["doc-1"]
    inserted_row = client.insert_calls[0][0]
    assert inserted_row["tenant_id"] == "tenant-a"
    assert inserted_row["title"] == "Manual de soporte"
    assert inserted_row["metadata"]["source_title"] == "Manual de soporte"
    assert inserted_row["metadata"]["question"] == "Como instalar"
    assert inserted_row["metadata"]["source"] == "load_documents"


def test_pgvector_delete_documents_by_source_title_is_tenant_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deletes must only remove chunks for the requested tenant/source pair."""

    client = FakeSupabaseClient()
    client.documents = [
        {
            "id": "doc-1",
            "tenant_id": "tenant-a",
            "title": "Manual A",
            "content": "A1",
            "metadata": {"source_title": "Manual A"},
        },
        {
            "id": "doc-2",
            "tenant_id": "tenant-b",
            "title": "Manual A",
            "content": "B1",
            "metadata": {"source_title": "Manual A"},
        },
    ]
    monkeypatch.setattr("services.vector_store.get_supabase_client", lambda: client)

    service = VectorStoreService(tenant_id="tenant-a", backend="pgvector")
    deleted = service.delete_documents_by_source_title("Manual A")

    assert deleted == 1
    assert [row["tenant_id"] for row in client.documents] == ["tenant-b"]
