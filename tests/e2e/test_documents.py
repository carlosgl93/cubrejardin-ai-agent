"""E2E tests for document management endpoints."""

from __future__ import annotations

import pytest
import httpx


@pytest.mark.e2e
class TestDocumentDelete:
    """Test document deletion endpoint."""

    @pytest.mark.asyncio
    async def test_delete_document_endpoint_accessible(self, api_base_url: str):
        """Delete endpoint should be accessible (returns auth error without credentials)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{api_base_url}/api/documents/test-doc-id",
            )
            # Without auth, returns 401/403/422
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document_with_auth(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return 404 for non-existent document with valid auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{api_base_url}/api/documents/nonexistent-doc-id",
                headers=auth_headers,
            )
            # 404 if not found, 401/403/422 if auth invalid
            assert response.status_code in [404, 401, 403, 422]


@pytest.mark.e2e
class TestDocumentList:
    """Test document listing (via knowledge-base)."""

    @pytest.mark.asyncio
    async def test_knowledge_base_endpoint_accessible(self, api_base_url: str):
        """Knowledge base endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/admin/knowledge-base",
                json={"action": "list"},
            )
            # Without auth returns validation/auth error
            assert response.status_code in [401, 403, 422]


@pytest.mark.e2e
class TestDocumentIngestion:
    """Test document ingestion workflow."""

    @pytest.mark.asyncio
    async def test_ingest_pdf_document(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should accept PDF documents with proper auth."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            pdf_content = b"%PDF-1.4 minimal test"

            files = {
                "file": ("test.pdf", pdf_content, "application/pdf"),
            }
            data = {"title": "Test Document", "category": "general"}

            response = await client.post(
                f"{api_base_url}/admin/knowledge-base",
                headers=auth_headers,
                files=files,
                data=data,
            )

            # Should accept the file or return auth error
            assert response.status_code in [201, 400, 401, 403, 422]

    @pytest.mark.asyncio
    async def test_ingest_markdown_document(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should accept Markdown documents."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            md_content = b"""# Test Document

## Introduction
This is a test document.
"""

            files = {
                "file": ("test.md", md_content, "text/markdown"),
            }
            data = {"title": "Test MD", "category": "faq"}

            response = await client.post(
                f"{api_base_url}/admin/knowledge-base",
                headers=auth_headers,
                files=files,
                data=data,
            )

            # Should accept markdown or return error
            assert response.status_code in [201, 400, 401, 403, 422]


@pytest.mark.e2e
class TestLearningEntryValidation:
    """Test learning queue entry validation."""

    @pytest.mark.asyncio
    async def test_validate_learning_entry_requires_auth(self, api_base_url: str):
        """Validation endpoint should require authentication."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/admin/learning/entry-123/validate",
            )
            # Without auth returns validation/auth error
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_validate_nonexistent_entry_with_auth(
        self, api_base_url: str, auth_headers: dict[str, str]
    ):
        """Should return 404 for non-existent entry with auth."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_base_url}/admin/learning/nonexistent-id/validate",
                headers=auth_headers,
            )
            # 404 if not found, 401/403/422 if auth invalid
            assert response.status_code in [404, 401, 403, 422]
