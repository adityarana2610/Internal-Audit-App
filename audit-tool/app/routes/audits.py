import datetime
import logging
import yaml
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import Connection

from app.db import get_connection
from app.engine import load_rules, execute_rule, get_rules_dir
from app.narrator import generate_narrative
from app.config import settings

logger = logging.getLogger("audit_tool.routes")

from app.auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


# Resolve templates directory relative to this file
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get("/run")
def run_all_audits(connection: Connection = Depends(get_connection)):
    """Runs all registered YAML audit rules and returns raw findings in JSON format."""
    rules = load_rules()
    if not rules:
        return {
            "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "results": [],
            "message": "No rules found to execute."
        }

    results = []
    for rule in rules:
        res = execute_rule(rule, connection)
        results.append(res)

    return {
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "results": results
    }

@router.get("/report", response_class=HTMLResponse)
def get_audit_report(
    request: Request,
    format: str = Query("html", pattern="^(html|json)$"),
    connection: Connection = Depends(get_connection)
):
    """
    Runs all audit rules, invokes Ollama for findings narration,
    and returns either an HTML report or raw JSON.
    """
    rules = load_rules()
    results = []
    for rule in rules:
        res = execute_rule(rule, connection)
        results.append(res)

    # Invoke narrative generation
    # It must run after SQL rules execute, on their structured output
    # Fallback to None if Ollama is offline (handled gracefully in UI)
    narrative = generate_narrative(results)

    report_data = {
        "executed_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "results": results,
        "narrative": narrative,
        "ai_provider": settings.ai_provider,
        "narrative_model": settings.gemini_model if settings.ai_provider.lower() == "gemini" else settings.ollama_model
    }

    if format == "json":
        from fastapi.encoders import jsonable_encoder
        return JSONResponse(content=jsonable_encoder(report_data))

    # Return HTML response using Jinja2
    return templates.TemplateResponse(
        request=request,
        name="audit_report.html",
        context={"report": report_data}
    )

class SettingsUpdate(BaseModel):
    ai_provider: str
    gemini_api_key: str
    gemini_model: str
    ollama_base_url: str
    ollama_model: str

def mask_secret(val: str) -> str:
    # Completely obscures secret: returns empty or placeholder without leaking any characters
    if not val:
        return ""
    return "••••••••••••••••"

@router.get("/settings")
def get_system_settings():
    return {
        "ai_provider": settings.ai_provider,
        "gemini_api_key": mask_secret(settings.gemini_api_key),
        "gemini_api_key_configured": bool(settings.gemini_api_key),
        "gemini_model": settings.gemini_model,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_model": settings.ollama_model,
    }

@router.post("/settings")
def update_system_settings(update: SettingsUpdate):
    settings.ai_provider = update.ai_provider
    new_key_supplied = update.gemini_api_key and not update.gemini_api_key.startswith("****") and "..." not in update.gemini_api_key
    if new_key_supplied:
        settings.gemini_api_key = update.gemini_api_key
    settings.gemini_model = update.gemini_model
    settings.ollama_base_url = update.ollama_base_url
    settings.ollama_model = update.ollama_model

    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            lines = f.readlines()
        
        def update_line(key, val):
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}\n"
                    return
            lines.append(f"{key}={val}\n")

        update_line("AI_PROVIDER", update.ai_provider)
        if new_key_supplied:
            update_line("GEMINI_API_KEY", update.gemini_api_key)
        update_line("GEMINI_MODEL", update.gemini_model)
        update_line("OLLAMA_BASE_URL", update.ollama_base_url)
        update_line("OLLAMA_MODEL", update.ollama_model)

        with open(env_path, "w") as f:
            f.writelines(lines)
            
    return {"status": "success"}

@router.delete("/rules/{rule_id}", summary="Delete a live audit rule by its ID")
def delete_rule(rule_id: str):
    """
    Permanently deletes the YAML rule file for the given rule_id from the
    live rules directory. This rule will no longer be evaluated on subsequent
    audit runs.
    """
    rules = load_rules()
    target_rule = next((r for r in rules if r.get("id") == rule_id), None)

    if not target_rule:
        raise HTTPException(status_code=404, detail=f"Rule with ID '{rule_id}' not found.")

    file_path = Path(target_rule["_file_path"])
    try:
        file_path.unlink()
        logger.info(f"Rule '{rule_id}' deleted: {file_path}")
    except Exception as exc:
        logger.error(f"Failed to delete rule file '{file_path}': {exc}")
        raise HTTPException(status_code=500, detail=f"Could not delete rule file: {exc}")

    return {
        "status": "deleted",
        "rule_id": rule_id,
        "message": f"Rule '{rule_id}' has been permanently deleted.",
    }


@router.put("/rules/{rule_id}", summary="Update a live audit rule by its ID")
async def update_rule(rule_id: str, request: Request):
    """
    Updates the YAML rule file for the given rule_id in the live rules directory.
    """
    rules = load_rules()
    target_rule = next((r for r in rules if r.get("id") == rule_id), None)

    if not target_rule:
        raise HTTPException(status_code=404, detail=f"Rule with ID '{rule_id}' not found.")

    try:
        updated_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    file_path = Path(target_rule["_file_path"])
    
    # Merge existing rule with updated data (preserving fields not sent, overriding sent fields)
    # We load the existing file text to preserve structure if possible, but dumping dict is safer for arbitrary edits.
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
        logger.info(f"Rule '{rule_id}' updated: {file_path}")
    except Exception as exc:
        logger.error(f"Failed to update rule file '{file_path}': {exc}")
        raise HTTPException(status_code=500, detail=f"Could not update rule file: {exc}")

    return {
        "status": "updated",
        "rule_id": rule_id,
        "message": f"Rule '{rule_id}' has been successfully updated.",
    }


@router.post("/rules", summary="Create a new live audit rule")
async def create_rule(request: Request):
    """
    Creates a new YAML rule file in the live rules directory.
    """
    try:
        new_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    rule_id = new_data.get("id")
    if not rule_id:
        raise HTTPException(status_code=400, detail="Rule ID is required to create a new rule.")

    # Validate valid characters in rule ID for filename safety
    import re
    if not re.match(r'^[a-zA-Z0-9_\-]+$', rule_id):
        raise HTTPException(status_code=400, detail="Rule ID can only contain letters, numbers, underscores, and dashes.")

    # Check if a rule with this ID already exists
    rules = load_rules()
    if any(r.get("id") == rule_id for r in rules):
        raise HTTPException(status_code=409, detail=f"A rule with ID '{rule_id}' already exists.")

    # Save to a new YAML file
    file_path = get_rules_dir() / f"{rule_id}.yaml"
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(new_data, f, default_flow_style=False, sort_keys=False)
        logger.info(f"New rule '{rule_id}' created at: {file_path}")
    except Exception as exc:
        logger.error(f"Failed to create rule file '{file_path}': {exc}")
        raise HTTPException(status_code=500, detail=f"Could not create rule file: {exc}")

    return {
        "status": "created",
        "rule_id": rule_id,
        "message": f"Rule '{rule_id}' has been successfully created.",
    }


@router.get("/{rule_id}")
def run_single_audit(rule_id: str, connection: Connection = Depends(get_connection)):
    """Runs a single YAML audit rule matching the specified rule ID."""
    rules = load_rules()
    target_rule = None
    for rule in rules:
        if rule.get("id") == rule_id:
            target_rule = rule
            break

    if not target_rule:
        raise HTTPException(status_code=404, detail=f"Rule with ID '{rule_id}' not found.")

    res = execute_rule(target_rule, connection)
    return {
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "result": res
    }
