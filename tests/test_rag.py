"""Tests for RAG adapters and backend selection."""

import pytest

from rcm_agent.rag import (
    get_coding_guidelines_backend,
    get_cms_requirements_backend,
    get_ncci_edits_backend,
    get_payer_policy_backend,
    rag_search_coding_guidelines,
    rag_search_cms_requirements,
    rag_search_ncci_edits,
    rag_search_payer_policies,
)


def test_get_payer_policy_backend_returns_none_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    monkeypatch.delenv("RCM_RAG_CHROMA_DIR", raising=False)
    # Reload config at call time
    assert get_payer_policy_backend() is None


def test_get_payer_policy_backend_returns_callable_when_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_payer_policy_backend()
    assert callable(backend)
    assert backend is not None
    # Call returns list (Chroma missing -> graceful message)
    result = backend("Aetna", "73721")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "ChromaDB" in result[0] or "not found" in result[0].lower()


def test_get_coding_guidelines_backend_returns_none_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    assert get_coding_guidelines_backend() is None


def test_get_coding_guidelines_backend_returns_callable_when_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_coding_guidelines_backend()
    assert callable(backend)
    result = backend("CPT E&M coding")
    assert isinstance(result, list)


def test_rag_search_payer_policies_when_backend_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    result = rag_search_payer_policies("UHC", "73721")
    assert result == ["No RAG backend enabled; use RCM_RAG_BACKEND=rag."]


def test_rag_search_coding_guidelines_when_backend_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    result = rag_search_coding_guidelines("e&m")
    assert result == ["No RAG backend enabled; use RCM_RAG_BACKEND=rag."]


def test_rag_search_payer_policies_when_chroma_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/path/chroma")
    result = rag_search_payer_policies("Aetna", "99213")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "ChromaDB" in result[0] or "not found" in result[0].lower()


def test_rag_search_coding_guidelines_when_chroma_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/path/chroma")
    result = rag_search_coding_guidelines("CPT modifiers")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "ChromaDB" in result[0] or "not found" in result[0].lower()


def test_payer_policy_backend_callable_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returned backend has signature (payer, procedure_code) -> list[str]."""
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_payer_policy_backend()
    assert backend is not None
    out = backend("Payer", "99213")
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)


def test_coding_guidelines_backend_callable_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returned backend has signature (query) -> list[str]."""
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_coding_guidelines_backend()
    assert backend is not None
    out = backend("guidelines")
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)


def test_rag_search_ncci_edits_when_backend_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    result = rag_search_ncci_edits("27130", "99223")
    assert result == ["No RAG backend enabled; use RCM_RAG_BACKEND=rag."]


def test_rag_search_cms_requirements_when_backend_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    result = rag_search_cms_requirements("prior auth")
    assert result == ["No RAG backend enabled; use RCM_RAG_BACKEND=rag."]


def test_get_ncci_edits_backend_returns_none_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    assert get_ncci_edits_backend() is None


def test_get_ncci_edits_backend_returns_callable_when_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_ncci_edits_backend()
    assert callable(backend)
    out = backend("27130", "99223")
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)


def test_get_cms_requirements_backend_returns_none_when_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "mock")
    assert get_cms_requirements_backend() is None


def test_get_cms_requirements_backend_returns_callable_when_rag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", "/nonexistent/chroma")
    backend = get_cms_requirements_backend()
    assert callable(backend)
    out = backend("interoperability")
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)
