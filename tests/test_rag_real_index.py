"""Integration tests: RAG tools against the real insurance_rag Chroma index.

Run only when the index exists (e.g. RCM_RAG_CHROMA_DIR or ~/insurance_rag/data/chroma).
Skip when index is missing or insurance_rag is not installed so CI without the index still passes.
Skip when index exists but Chroma cannot connect (version mismatch, rust panic, or tenant error).

Run with: pytest tests/test_rag_real_index.py -v
Run all including these: pytest tests/ -v
"""

import os
from pathlib import Path

import pytest

# Default location of insurance_rag Chroma index
_DEFAULT_CHROMA = Path.home() / "insurance_rag" / "data" / "chroma"


def _get_real_chroma_dir() -> Path | None:
    raw = os.environ.get("RCM_RAG_CHROMA_DIR", "").strip()
    path = Path(raw).expanduser() if raw else _DEFAULT_CHROMA
    return path if path.exists() else None


def _insurance_rag_available() -> bool:
    try:
        import insurance_rag  # noqa: F401

        return True
    except ImportError:
        return False


def _probe_chroma_connection(chroma_dir: Path) -> tuple[bool, str]:
    """Try to create a retriever and run one query. Return (True, '') if OK, (False, reason) otherwise."""
    prev_data_dir = os.environ.get("DATA_DIR")
    try:
        os.environ["DATA_DIR"] = str(chroma_dir.parent)
        from insurance_rag.query.retriever import get_retriever

        retriever = get_retriever(k=5)
        retriever.invoke("test")
        return (True, "")
    except BaseException as e:
        # PanicException (Chroma rust panic) does not inherit from Exception
        err = f"{type(e).__name__}: {e}"
        if "default_tenant" in err or "PanicException" in type(e).__name__:
            hint = " (upgrade chromadb, run 'chromadb utils vacuum' on the index, or recreate with insurance_rag)"
        else:
            hint = ""
        return (False, err + hint)
    finally:
        if prev_data_dir is not None:
            os.environ["DATA_DIR"] = prev_data_dir
        else:
            os.environ.pop("DATA_DIR", None)


# Cached result of connection probe (lazy, set when first test runs)
_chroma_connection_ok: bool | None = None
_chroma_connection_reason: str = ""


def _chroma_connection_works() -> tuple[bool, str]:
    """Return (ok, reason). Probe once and cache."""
    global _chroma_connection_ok, _chroma_connection_reason
    if _chroma_connection_ok is not None:
        return (_chroma_connection_ok, _chroma_connection_reason)
    chroma_dir = _get_real_chroma_dir()
    if not chroma_dir or not _insurance_rag_available():
        _chroma_connection_ok = False
        _chroma_connection_reason = "Real Chroma index not found or insurance_rag not installed"
        return (_chroma_connection_ok, _chroma_connection_reason)
    _chroma_connection_ok, _chroma_connection_reason = _probe_chroma_connection(chroma_dir)
    return (_chroma_connection_ok, _chroma_connection_reason)


_skip_if_no_real_index = pytest.mark.skipif(
    _get_real_chroma_dir() is None or not _insurance_rag_available(),
    reason="Real Chroma index not found or insurance_rag not installed (set RCM_RAG_CHROMA_DIR or create ~/insurance_rag/data/chroma, pip install -e insurance_rag)",
)


@pytest.fixture(scope="module")
def chroma_connection() -> tuple[bool, str]:
    """Probe Chroma once per module. (ok, reason); if not ok, tests should skip with reason."""
    return _chroma_connection_works()


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_payer_policies_real_index(
    chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """search_payer_policies with RAG backend returns non-empty snippets from real Chroma."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
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
def test_rag_search_coding_guidelines_real_index(
    chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """search_coding_guidelines with RAG backend returns non-empty snippets from real Chroma."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
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
def test_rag_search_ncci_edits_real_index(chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """search_ncci_edits with RAG backend returns snippets from real Chroma."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
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
        assert not result[0].startswith("No RAG") and "ChromaDB" not in result[0], (
            "expected real snippets not error message"
        )


@_skip_if_no_real_index
@pytest.mark.integration
@pytest.mark.slow
def test_rag_search_cms_requirements_real_index(
    chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """search_cms_requirements with RAG backend returns snippets from real Chroma."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
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
def test_prior_auth_crew_uses_real_rag_snippets(
    chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch, encounter_002
) -> None:
    """Prior auth crew with RAG backend gets real policy snippets in auth packet."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
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
def test_coding_crew_uses_real_rag_snippets(
    chroma_connection: tuple[bool, str], monkeypatch: pytest.MonkeyPatch, encounter_001
) -> None:
    """Coding crew with RAG backend gets real guideline snippets in raw_result."""
    if not chroma_connection[0]:
        pytest.skip(chroma_connection[1])
    chroma_dir = _get_real_chroma_dir()
    assert chroma_dir is not None
    monkeypatch.setenv("RCM_RAG_BACKEND", "rag")
    monkeypatch.setenv("RCM_RAG_CHROMA_DIR", str(chroma_dir))

    from rcm_agent.crews.coding_crew import run_coding_crew

    output = run_coding_crew(encounter_001)
    snippets = output.raw_result.get("coding_guidelines_snippets", [])
    assert isinstance(snippets, list) and len(snippets) > 0, "expected non-empty coding guidelines from real index"
    assert all(isinstance(s, str) and len(s) > 0 for s in snippets), "expected non-empty strings"
