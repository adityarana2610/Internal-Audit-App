"""
vector_store.py — Manages all interactions with Qdrant and the Jina AI
embedding API.

Responsibilities
----------------
* Initialise the Qdrant collection on first use.
* Generate text embeddings via the Jina AI REST API (jina-embeddings-v3).
* Upsert PolicyClause objects as Qdrant points (vector + payload).
* Search for semantically similar clauses using cosine similarity.
* Retrieve all clauses from a specific source document.
* Match a text snippet (e.g. an audit rule title) against stored clauses.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings
from app.policy_engine.models import PolicyClause

logger = logging.getLogger("audit_tool.policy_engine.vector_store")

# ── Jina AI REST endpoint ────────────────────────────────────────────────────
JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"

# ── Singleton Qdrant client ──────────────────────────────────────────────────
_qdrant_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Return a verified Qdrant client.
    - If settings.qdrant_host is ':memory:', returns an in-memory client.
    - Otherwise connects to the real Qdrant cluster.
    - If connection fails, raises RuntimeError without silent fallback to prevent data loss.
    - Leaves client uncached on failure so recovery on subsequent requests is immediate.
    """
    global _qdrant_client
    if _qdrant_client is None:
        if settings.qdrant_host == ":memory:":
            logger.info("Using configured in-memory Qdrant instance.")
            _qdrant_client = QdrantClient(":memory:")
            return _qdrant_client

        try:
            client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=4.0,
            )
            # Verify connectivity to the Qdrant cluster
            client.get_collections()
            logger.info(f"Connected to Qdrant vector database at {settings.qdrant_host}:{settings.qdrant_port}")
            _qdrant_client = client
        except Exception as exc:
            logger.error(f"Failed to connect to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}: {exc}")
            raise RuntimeError(
                f"Qdrant vector database is unavailable at {settings.qdrant_host}:{settings.qdrant_port}. "
                "Ensure the Qdrant service is running and healthy."
            ) from exc

    return _qdrant_client
# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------

def ensure_collection() -> None:
    """
    Create the Qdrant collection if it does not already exist.
    Uses cosine distance with the configured embedding dimension (default 1024).
    """
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    try:
        client.get_collection(collection_name)
        logger.debug(f"Qdrant collection '{collection_name}' already exists.")
    except (UnexpectedResponse, Exception):
        logger.info(f"Creating Qdrant collection '{collection_name}'...")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=settings.jina_embedding_dimensions,
                distance=qdrant_models.Distance.COSINE,
            ),
        )
        logger.info(f"Collection '{collection_name}' created successfully.")


# ---------------------------------------------------------------------------
# Jina AI embeddings
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], task: str = "retrieval.passage") -> list[list[float]]:
    """
    Generate embeddings for a list of texts using the Jina AI REST API.

    Parameters
    ----------
    texts :
        List of strings to embed. Batched in a single request.
    task :
        Jina task type. Use ``"retrieval.passage"`` when storing and
        ``"retrieval.query"`` when searching.

    Returns
    -------
    list[list[float]]
        One float vector per input text, ordered to match *texts*.

    Raises
    ------
    RuntimeError
        If the Jina API key is missing or the request fails.
    """
    if not settings.jina_api_key:
        raise RuntimeError(
            "JINA_API_KEY is not set. Add it to audit-tool/.env to enable embeddings."
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.jina_api_key}",
    }
    payload = {
        "input": texts,
        "model": settings.jina_embedding_model,
        "dimensions": settings.jina_embedding_dimensions,
        "task": task,
    }

    try:
        response = httpx.post(JINA_EMBED_URL, json=payload, headers=headers, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        # Jina returns embeddings in the same order as the input
        return [item["embedding"] for item in data["data"]]
    except httpx.HTTPStatusError as exc:
        logger.error(f"Jina API error {exc.response.status_code}: {exc.response.text}")
        raise RuntimeError(f"Jina embedding request failed: {exc}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error calling Jina API: {exc}")
        raise RuntimeError(f"Jina embedding request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_clauses(clauses: list[PolicyClause]) -> int:
    """
    Embed and upsert a list of PolicyClause objects into Qdrant.

    Each clause is stored as a Qdrant point with:
    - ``id``: a deterministic UUID derived from ``source_pdf + clause_id``
    - ``vector``: the Jina embedding of ``title + " " + full_text``
    - ``payload``: all PolicyClause fields as JSON-serialisable dict

    Returns the number of successfully upserted points.
    """
    if not clauses:
        return 0

    ensure_collection()
    client = get_qdrant_client()

    # Build texts to embed (title + body gives richer signal)
    texts = [f"{c.title}. {c.full_text}" for c in clauses]
    logger.info(f"Generating embeddings for {len(texts)} clause(s) via Jina...")
    vectors = embed_texts(texts, task="retrieval.passage")

    points: list[qdrant_models.PointStruct] = []
    for clause, vector in zip(clauses, vectors):
        # Deterministic ID so re-uploading the same PDF is idempotent
        point_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{clause.source_pdf}/{clause.clause_id}")
        )
        payload = {
            "clause_id": clause.clause_id,
            "title": clause.title,
            "full_text": clause.full_text,
            "page_number": clause.page_number,
            "section_path": clause.section_path,
            "source_pdf": clause.source_pdf,
            "policy_version": clause.policy_version,
            "upload_timestamp": clause.upload_timestamp.isoformat(),
        }
        points.append(
            qdrant_models.PointStruct(id=point_id, vector=vector, payload=payload)
        )

    client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info(f"Upserted {len(points)} clauses into Qdrant.")
    return len(points)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_clauses(
    query: str,
    top_k: int = 5,
    source_pdf: str | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic search over stored policy clauses.

    Parameters
    ----------
    query :
        Free-text search query.
    top_k :
        Maximum number of results to return.
    source_pdf :
        If provided, restrict results to clauses from this PDF file.

    Returns
    -------
    list[dict]
        Each dict contains ``score`` (float) and ``payload`` (clause data).
    """
    ensure_collection()
    client = get_qdrant_client()

    query_vector = embed_texts([query], task="retrieval.query")[0]

    # Optional filter by source document
    query_filter = None
    if source_pdf:
        query_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="source_pdf",
                    match=qdrant_models.MatchValue(value=source_pdf),
                )
            ]
        )

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {"score": hit.score, "payload": hit.payload, "id": str(hit.id)}
        for hit in results.points
    ]


def find_matching_clause(
    rule_text: str,
    similarity_threshold: float = 0.75,
) -> dict[str, Any] | None:
    """
    Check whether any stored clause is semantically similar to *rule_text*.

    Used during policy ingestion to detect duplicates / overlaps with
    already-existing audit rules.

    Returns the top hit's payload if similarity exceeds *similarity_threshold*,
    otherwise None.
    """
    results = search_clauses(rule_text, top_k=1)
    if results and results[0]["score"] >= similarity_threshold:
        return results[0]
    return None


# ---------------------------------------------------------------------------
# Retrieval by document
# ---------------------------------------------------------------------------

def list_clauses_by_pdf(source_pdf: str) -> list[dict[str, Any]]:
    """Return all stored clauses that originated from *source_pdf*."""
    ensure_collection()
    client = get_qdrant_client()

    scroll_filter = qdrant_models.Filter(
        must=[
            qdrant_models.FieldCondition(
                key="source_pdf",
                match=qdrant_models.MatchValue(value=source_pdf),
            )
        ]
    )

    results, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=scroll_filter,
        limit=500,
        with_payload=True,
        with_vectors=False,
    )

    return [{"id": str(r.id), "payload": r.payload} for r in results]


def list_all_clauses(limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
    """Return up to *limit* stored clauses, ordered by upload timestamp."""
    ensure_collection()
    client = get_qdrant_client()

    results, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        limit=limit,
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )

    return [{"id": str(r.id), "payload": r.payload} for r in results]
