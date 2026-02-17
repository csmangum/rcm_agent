"""Integration tests: RAG tools against the real medicare_rag Chroma index.

Run only when the index exists (e.g. RCM_RAG_CHROMA_DIR or ~/medicare_rag/data/chroma).
Skip when index is missing or medicare_rag is not installed so CI without the index still passes.

Run with: pytest tests/test_rag_real_index.py -v
Run all including these: pytest tests/ -v
"""

import os
from pathlib import Path

import pytest

# Default location of medicare_rag Chroma index
_DEFAULT_CHROMA = Path.home() / "medicare_rag" / "data" / "chroma"


def _get_real_chroma_dir() -> Path | None:
    raw = os.environ.get("RCM_RAG_CHROMA_DIR", "").strip()
    path = Path(raw) if raw else _DEFAULT_CHROMA
    return path if path.exists() else None


def _medicare_rag_available() -> bool:
    try:
        import medicare_rag  # noqa: F401
        return True
    except ImportError:
        return False


_skip_if_no_real_index = pytest.mark.skipif(
    _get_real_chroma_dir() is None or not _medicare_rag_available(),
    reason="Real Chroma index not found or medicare_rag not installed (set RCM_RAG_CHROMA_DIR or create ~/medicare_rag/data/chroma, pip install -e medicare_rag)",
)


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_payer_policies_real_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_payer_policies with RAG backend returns non-empty snippets from real Chroma."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.rag import rag_search_payer_policies

    result = rag_search_payer_policies("UnitedHealthcare", "73721")
    assert isinstance(result, list), "expected list of snippets"
    assert len(result) > 0, "expected at least one snippet from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in result), "expected non-empty strings"


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_coding_guidelines_real_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_coding_guidelines with RAG backend returns non-empty snippets from real Chroma."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.rag import rag_search_coding_guidelines

    result = rag_search_coding_guidelines("E&M level selection time or MDM")
    assert isinstance(result, list), "expected list of snippets"
    assert len(result) > 0, "expected at least one snippet from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in result), "expected non-empty strings"


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_ncci_edits_real_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_ncci_edits with RAG backend returns snippets from real Chroma."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.rag import rag_search_ncci_edits

    result = rag_search_ncci_edits("27130", "99223")
    assert isinstance(result, list), "expected list of snippets"
    # Real index may or may not have NCCI-specific chunks; accept any non-error result
    assert all(isinstance(s, str) for s in result), "expected list of strings"
    if len(result) > 0:
        assert not result[0].startswith("No RAG") and "ChromaDB" not in result[0], "expected real snippets not error message"


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_cms_requirements_real_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """search_cms_requirements with RAG backend returns snippets from real Chroma."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.rag import rag_search_cms_requirements

    result = rag_search_cms_requirements("prior authorization")
    assert isinstance(result, list), "expected list of snippets"
    assert len(result) > 0, "expected at least one snippet from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in result), "expected non-empty strings"


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_prior_auth_crew_uses_real_rag_snippets(monkeypatch: pytest.MonkeyPatch, encounter_002) -> None:
    """Prior auth crew with RAG backend gets real policy snippets in auth packet."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.crews.prior_auth_crew import run_prior_auth_crew

    output = run_prior_auth_crew(encounter_002)
    policy_refs = output.raw_result.get("auth_packet", {}).get("policy_references", {})
    assert "73721" in policy_refs, "expected policy refs for procedure 73721"
    snippets = policy_refs["73721"]
    assert isinstance(snippets, list) and len(snippets) > 0, "expected non-empty snippets from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in snippets), "expected non-empty strings"


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_coding_crew_uses_real_rag_snippets(monkeypatch: pytest.MonkeyPatch, encounter_001) -> None:
    """Coding crew with RAG backend gets real guideline snippets in raw_result."""
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.crews.coding_crew import run_coding_crew

    output = run_coding_crew(encounter_001)
    snippets = output.raw_result.get("coding_guidelines_snippets", [])
    assert isinstance(snippets, list) and len(snippets) > 0, "expected non-empty coding guidelines from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in snippets), "expected non-empty strings"
