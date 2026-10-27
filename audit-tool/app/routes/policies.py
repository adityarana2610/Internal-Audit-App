"""
policies.py — FastAPI router for the PDF Policy Ingestion Service.

Endpoints
---------
POST /policies/upload
    Upload a PDF policy document. Triggers the full ingestion pipeline
    (parse → embed → Qdrant → AI analysis → YAML updates/drafts).

GET  /policies/clauses
    List all stored policy clauses from Qdrant (paginated).

GET  /policies/clauses/search
    Semantic search over policy clauses using a free-text query.

GET  /policies/rules/draft
    List all AI-generated draft rules waiting for review.

POST /policies/rules/draft/{rule_id}/approve
    Promote a draft rule to the live rules directory so the audit engine
    will pick it up on the next run.

DELETE /policies/rules/draft/{rule_id}/reject
    Delete a draft rule that has been reviewed and rejected.

GET  /policies/trace/{rule_id}
    Find which policy clause(s) back a given live audit rule.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, Request
from fastapi.responses import JSONResponse
import yaml

from app.engine import get_rules_dir, load_draft_rules
from app.policy_engine.orchestrator import process_policy_pdf
from app.policy_engine.vector_store import (
    list_all_clauses,
    search_clauses,
)

logger = logging.getLogger("audit_tool.routes.policies")

from app.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


_RULES_DIR = None
_DRAFT_DIR = None


def _get_rules_dir() -> Path:
    global _RULES_DIR
    if _RULES_DIR is None:
        _RULES_DIR = get_rules_dir()
    return _RULES_DIR


def _get_draft_dir() -> Path:
    global _DRAFT_DIR
    if _DRAFT_DIR is None:
        _DRAFT_DIR = _get_rules_dir() / "draft"
    return _DRAFT_DIR


# ---------------------------------------------------------------------------
# Upload & Ingest
# ---------------------------------------------------------------------------

@router.post("/upload", summary="Upload a PDF policy document and ingest it")
async def upload_policy(
    file: UploadFile = File(..., description="PDF policy document to ingest"),
):
    """
    Upload a PDF policy document.

    The service will:
    1. Extract text clauses from the PDF.
    2. Store clause embeddings in Qdrant for semantic search.
    3. Compare each clause against existing audit rules.
    4. Either update rule parameters (e.g. threshold_days) or write a new
       draft YAML rule to `rules/draft/` for human review.

    Returns a structured summary of all actions taken.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Enforce maximum 25MB file upload limit to prevent memory exhaustion
    MAX_POLICY_PDF_BYTES = 25 * 1024 * 1024
    file_bytes = await file.read(MAX_POLICY_PDF_BYTES + 1)
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > MAX_POLICY_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {MAX_POLICY_PDF_BYTES // (1024 * 1024)}MB."
        )

    logger.info(f"Received policy PDF '{file.filename}' ({len(file_bytes):,} bytes).")

    try:
        result = await process_policy_pdf(file_bytes, file.filename)
    except Exception as exc:
        logger.error(f"Policy ingestion failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Policy ingestion failed: {exc}",
        )

    # Serialise to a clean JSON-safe dict
    return JSONResponse(
        status_code=200,
        content={
            "ingestion_id": result.ingestion_id,
            "source_pdf": result.source_pdf,
            "policy_version": result.policy_version,
            "ingested_at": result.ingested_at.isoformat(),
            "summary": {
                "total_clauses": result.total_clauses,
                "auditable_clauses": result.auditable_clauses,
                "rules_updated": len(result.rules_updated),
                "rules_created": len(result.rules_created),
                "clauses_skipped": len(result.clauses_skipped),
            },
            "actions": {
                "updated": [
                    {
                        "clause_id": a.clause.clause_id,
                        "clause_title": a.clause.title,
                        "matched_rule_id": a.matched_rule_id,
                        "parameter_changes": [
                            {"field": c.field, "old": c.old_value, "new": c.new_value}
                            for c in (a.parameter_changes or [])
                        ],
                        "confidence": round(a.confidence, 3),
                        "reasoning": a.reasoning,
                    }
                    for a in result.rules_updated
                ],
                "created": [
                    {
                        "clause_id": a.clause.clause_id,
                        "clause_title": a.clause.title,
                        "draft_filename": a.draft_filename,
                        "confidence": round(a.confidence, 3),
                        "reasoning": a.reasoning,
                    }
                    for a in result.rules_created
                ],
                "skipped": [
                    {
                        "clause_id": a.clause.clause_id,
                        "clause_title": a.clause.title,
                        "reasoning": a.reasoning,
                    }
                    for a in result.clauses_skipped
                ],
            },
        },
    )


# ---------------------------------------------------------------------------
# Clause browsing
# ---------------------------------------------------------------------------

@router.get("/clauses", summary="List all stored policy clauses")
def list_clauses(
    limit: int = Query(50, ge=1, le=500, description="Max clauses to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    Returns stored policy clauses from Qdrant.
    Results are not ordered (Qdrant scroll does not guarantee order).
    """
    try:
        clauses = list_all_clauses(limit=limit, offset=offset)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Qdrant: {exc}",
        )
    return {"count": len(clauses), "clauses": clauses}


@router.get("/clauses/search", summary="Semantic search over policy clauses")
def search_policy_clauses(
    q: str = Query(..., description="Free-text search query"),
    top_k: int = Query(5, ge=1, le=20, description="Number of results"),
    source_pdf: str | None = Query(None, description="Filter by source PDF filename"),
):
    """
    Performs a semantic (embedding-based) search over all stored policy clauses.

    Example: `GET /policies/clauses/search?q=inactive accounts 30 days`
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query string 'q' cannot be empty.")

    try:
        results = search_clauses(q, top_k=top_k, source_pdf=source_pdf)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )
    return {"query": q, "count": len(results), "results": results}


# ---------------------------------------------------------------------------
# Draft rule management
# ---------------------------------------------------------------------------

@router.get("/rules/draft", summary="List AI-generated draft rules pending review")
def list_draft_rules():
    """
    Returns all YAML rules in `rules/draft/` that were generated by the
    policy ingestion service and are awaiting human review.
    """
    drafts = load_draft_rules()
    # Strip internal fields before sending to client
    clean = []
    for rule in drafts:
        r = {k: v for k, v in rule.items() if not k.startswith("_")}
        r["_filename"] = Path(rule["_file_path"]).name
        clean.append(r)
    return {"count": len(clean), "draft_rules": clean}


@router.put("/rules/draft/{rule_id}", summary="Update a draft rule by its ID")
async def update_draft_rule(rule_id: str, request: Request):
    drafts = load_draft_rules()
    target = next((r for r in drafts if r.get("id") == rule_id), None)

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Draft rule with id '{rule_id}' not found.",
        )

    try:
        updated_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    file_path = Path(target["_file_path"])

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current_data = yaml.safe_load(f)
    except Exception:
        current_data = {}

    # Remove keys that were deleted by the user (ignore internal keys)
    keys_to_remove = [k for k in current_data.keys() if not k.startswith('_') and k not in updated_data]
    for k in keys_to_remove:
        del current_data[k]

    current_data.update(updated_data)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(current_data, f, default_flow_style=False, sort_keys=False)
        logger.info(f"Draft rule '{rule_id}' updated: {file_path}")
    except Exception as exc:
        logger.error(f"Failed to update draft rule file '{file_path}': {exc}")
        raise HTTPException(status_code=500, detail=f"Could not update draft rule file: {exc}")

    return {
        "status": "updated",
        "rule_id": rule_id,
        "message": f"Draft rule '{rule_id}' has been successfully updated.",
    }


@router.post(
    "/rules/draft/{rule_id}/approve",
    summary="Approve a draft rule and promote it to the live rules directory",
)
def approve_draft_rule(rule_id: str):
    """
    Moves the draft YAML file from `rules/draft/` to `rules/`.

    After approval the audit engine will include this rule on its next run.
    The rule_id must match the `id` field inside the YAML (not the filename).
    """
    drafts = load_draft_rules()
    target = next((r for r in drafts if r.get("id") == rule_id), None)

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Draft rule with id '{rule_id}' not found.",
        )

    src_path  = Path(target["_file_path"])
    dest_path = _get_rules_dir() / src_path.name

    if dest_path.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                f"A rule file '{src_path.name}' already exists in the live rules "
                "directory. Rename the draft or delete the existing file first."
            ),
        )

    shutil.move(str(src_path), str(dest_path))
    logger.info(f"Draft rule '{rule_id}' promoted: {src_path} → {dest_path}")

    return {
        "status": "approved",
        "rule_id": rule_id,
        "message": f"Rule '{rule_id}' is now live and will run on the next audit.",
        "live_path": str(dest_path),
    }


@router.delete(
    "/rules/draft/{rule_id}/reject",
    summary="Reject and delete a draft rule",
)
def reject_draft_rule(rule_id: str):
    """
    Deletes the draft YAML file from `rules/draft/`.

    Use this to discard AI-generated rules that are incorrect or out of scope.
    """
    drafts = load_draft_rules()
    target = next((r for r in drafts if r.get("id") == rule_id), None)

    if not target:
        raise HTTPException(
            status_code=404,
            detail=f"Draft rule with id '{rule_id}' not found.",
        )

    src_path = Path(target["_file_path"])
    src_path.unlink()
    logger.info(f"Draft rule '{rule_id}' rejected and deleted: {src_path}")

    return {
        "status": "rejected",
        "rule_id": rule_id,
        "message": f"Draft rule '{rule_id}' has been deleted.",
    }


# ---------------------------------------------------------------------------
# Policy traceability
# ---------------------------------------------------------------------------

@router.get(
    "/trace/{rule_id}",
    summary="Find the policy clause(s) that back a live audit rule",
)
def trace_rule_to_policy(
    rule_id: str,
    top_k: int = Query(3, ge=1, le=10, description="Max matching clauses to return"),
):
    """
    Uses semantic search to find which stored policy clauses most likely
    motivated the audit rule with the given *rule_id*.

    Useful for compliance reports: "Rule X was derived from Policy Y, clause Z."
    """
    import yaml as _yaml

    # Load the rule to get its title + remediation text
    rules_dir = _get_rules_dir()
    rule_text: str | None = None

    for yaml_path in rules_dir.glob("*.yaml"):
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = _yaml.safe_load(f)
            if isinstance(data, dict) and data.get("id") == rule_id:
                rule_text = f"{data.get('title', '')}. {data.get('remediation', '')}"
                break
        except Exception:
            continue

    if not rule_text:
        raise HTTPException(
            status_code=404,
            detail=f"Live rule with id '{rule_id}' not found.",
        )

    try:
        results = search_clauses(rule_text, top_k=top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "rule_id": rule_id,
        "query_used": rule_text[:200],
        "matching_clauses": results,
    }
