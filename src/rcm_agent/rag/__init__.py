"""RAG infrastructure for payer policies and coding guidelines.

Wires medicare_rag ChromaDB retriever into rcm_agent tools via callable backends.
DATA_DIR is set for medicare_rag at each RAG call; once set it persists for the process.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path

from rcm_agent.config import get_rag_config

logger = logging.getLogger(__name__)


def _rag_search_helper(query: str, metadata_filter: dict[str, str] | None = None) -> list[str]:
    """
    Common RAG search implementation for all search functions.
    Returns list of page_content strings from ChromaDB retrieval.
    """
    cfg = get_rag_config()
    if cfg["backend"] != "rag":
        return ["No RAG backend enabled; use RCM_RAG_BACKEND=rag."]
    chroma_dir = Path(cfg["chroma_dir"])
    if not chroma_dir.exists():
        logger.warning("RAG chroma dir %s does not exist; returning empty snippets.", chroma_dir)
        return ["ChromaDB directory not found; run medicare_rag ingest first."]
    try:
        os.environ["DATA_DIR"] = str(chroma_dir.parent)
        from medicare_rag.query.retriever import get_retriever

        retriever = get_retriever(k=5, metadata_filter=metadata_filter) if metadata_filter else get_retriever(k=5)
        docs = retriever.invoke(query)
        return [d.page_content for d in docs] if docs else []
    except OSError as e:
        logger.warning(
            "medicare_rag Chroma/data path or I/O error %s: %s; fallback to empty list.",
            type(e).__name__,
            e,
        )
        return []
    except Exception as e:
        logger.warning(
            "medicare_rag retrieval failed: %s: %s; fallback to empty list.",
            type(e).__name__,
            e,
        )
        return []


def rag_search_payer_policies(payer: str, procedure_code: str) -> list[str]:
    """
    Retrieve policy snippets for (payer, procedure_code) from medicare_rag ChromaDB.
    Uses IOM source filter. Returns list of page_content strings.
    """
    query = f"{payer} {procedure_code} coverage policy prior authorization"
    return _rag_search_helper(query, metadata_filter={"source": "iom"})


def rag_search_coding_guidelines(query: str) -> list[str]:
    """
    Retrieve coding guideline snippets for query from medicare_rag ChromaDB.
    No source filter (IOM + codes). Returns list of page_content strings.
    """
    return _rag_search_helper(query)


def get_payer_policy_backend() -> Callable[[str, str], list[str]] | None:
    """Return the RAG callable for search_payer_policies when backend is 'rag', else None (use mock)."""
    if get_rag_config()["backend"] != "rag":
        return None
    return rag_search_payer_policies


def get_coding_guidelines_backend() -> Callable[[str], list[str]] | None:
    """Return the RAG callable for search_coding_guidelines when backend is 'rag', else None (use mock)."""
    if get_rag_config()["backend"] != "rag":
        return None
    return rag_search_coding_guidelines


def rag_search_ncci_edits(cpt_code_1: str, cpt_code_2: str) -> list[str]:
    """
    Retrieve NCCI edit snippets for a CPT pair from medicare_rag ChromaDB.
    Uses coding/policy sources. Returns list of page_content strings.
    """
    query = f"NCCI PTP edit CPT {cpt_code_1} {cpt_code_2} bundling modifier"
    return _rag_search_helper(query)


def rag_search_cms_requirements(topic: str) -> list[str]:
    """
    Retrieve CMS regulation/requirement snippets for a topic from medicare_rag ChromaDB.
    Uses IOM and MCD sources. Returns list of page_content strings.
    """
    query = f"CMS requirements {topic} coverage prior authorization"
    return _rag_search_helper(query)


def get_ncci_edits_backend() -> Callable[[str, str], list[str]] | None:
    """Return the RAG callable for search_ncci_edits when backend is 'rag', else None (use mock)."""
    if get_rag_config()["backend"] != "rag":
        return None
    return rag_search_ncci_edits


def get_cms_requirements_backend() -> Callable[[str], list[str]] | None:
    """Return the RAG callable for search_cms_requirements when backend is 'rag', else None (use mock)."""
    if get_rag_config()["backend"] != "rag":
        return None
    return rag_search_cms_requirements
