import os
import math
import yaml
import logging
from pathlib import Path
from sqlalchemy import text, Connection

logger = logging.getLogger("audit_tool.engine")

def get_rules_dir() -> Path:
    """Resolve the path to the rules directory."""
    current_dir = Path(__file__).parent.resolve()
    rules_dir = current_dir.parent / "rules"
    if not rules_dir.exists():
        rules_dir = Path("rules").resolve()
    return rules_dir

def get_draft_rules_dir() -> Path:
    """Resolve the path to the draft rules directory (AI-generated, pending review)."""
    return get_rules_dir() / "draft"

def load_rules() -> list[dict]:
    """Loads and returns all YAML rules from the rules directory."""
    rules_dir = get_rules_dir()
    logger.info(f"Loading rules from {rules_dir}...")
    rules = []
    
    if not rules_dir.exists():
        logger.warning(f"Rules directory {rules_dir} does not exist.")
        return rules

    for file_path in rules_dir.glob("*.yaml"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                rule_data = yaml.safe_load(f)
                if isinstance(rule_data, dict) and "id" in rule_data:
                    # Store filename/path for debugging
                    rule_data["_file_path"] = str(file_path)
                    rules.append(rule_data)
        except Exception as e:
            logger.error(f"Error loading rule file {file_path}: {str(e)}")
            
    # Sort rules for consistent execution order
    rules.sort(key=lambda x: x.get("id", ""))
    return rules

def load_draft_rules() -> list[dict]:
    """
    Loads all AI-generated draft YAML rules from rules/draft/.
    These are NOT executed by the audit engine until promoted to rules/.
    """
    draft_dir = get_draft_rules_dir()
    logger.info(f"Loading draft rules from {draft_dir}...")
    rules = []

    if not draft_dir.exists():
        return rules

    for file_path in draft_dir.glob("*.yaml"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                rule_data = yaml.safe_load(f)
                if isinstance(rule_data, dict) and "id" in rule_data:
                    rule_data["_file_path"] = str(file_path)
                    rule_data["_is_draft"] = True
                    rules.append(rule_data)
        except Exception as e:
            logger.error(f"Error loading draft rule file {file_path}: {str(e)}")

    rules.sort(key=lambda x: x.get("id", ""))
    return rules

def build_sql_query(rule: dict) -> str:
    """Formats and prepares the SQL query from a rule, injecting configuration parameters."""
    query_template = rule.get("query", "")
    rule_id = rule.get("id")

    # Special handling for Segregation of Duties (SoD)
    if rule_id == "segregation_of_duties" and "conflict_pairs" in rule:
        conflict_pairs = rule.get("conflict_pairs", [])
        union_parts = []
        for pair in conflict_pairs:
            app = pair.get("app")
            roles = pair.get("roles", [])
            if len(roles) >= 2:
                role1 = roles[0]
                role2 = roles[1]
                part = f"""
                SELECT 
                  ap1.employee_id, 
                  ap1.app_name, 
                  ap1.permission_name AS role_1, 
                  ap2.permission_name AS role_2,
                  e.full_name,
                  e.department
                FROM app_security.application_permissions ap1
                JOIN app_security.application_permissions ap2 ON ap1.employee_id = ap2.employee_id
                JOIN hr_schema.employees e ON ap1.employee_id = e.id
                WHERE ap1.app_name = '{app}' AND ap1.permission_name = '{role1}'
                  AND ap2.app_name = '{app}' AND ap2.permission_name = '{role2}'
                """
                union_parts.append(part)
        
        if union_parts:
            # Join the query parts
            return "\nUNION\n".join(union_parts)
        else:
            # Fallback that returns schema columns but no rows
            return """
            SELECT 
              employee_id, 
              app_name, 
              permission_name AS role_1, 
              permission_name AS role_2,
              NULL::text AS full_name,
              NULL::text AS department
            FROM app_security.application_permissions LIMIT 0
            """

    # For other queries, perform string formatting with defaults if keys are found
    try:
        formatted_query = query_template.format(
            threshold_days=rule.get("threshold_days", 10),
            window_minutes=rule.get("window_minutes", 30),
            bytes_threshold=rule.get("bytes_threshold", 1073741824)
        )
        logger.debug("Formatted query: "+formatted_query)
        return formatted_query
    except Exception as e:
        logger.error(f"Failed formatting query template for rule {rule_id}: {str(e)}")
        return query_template

def execute_rule(rule: dict, connection: Connection) -> dict:
    """Executes a single rule against the database and returns structured findings."""
    rule_id = rule.get("id")
    title = rule.get("title", rule_id)
    severity = rule.get("severity", "medium")
    remediation = rule.get("remediation", "")
    
    sql_to_run = build_sql_query(rule)
    logger.info(f"Running query for rule: {rule_id}")
    
    findings = []
    finding_count = 0
    error_message = None

    try:
        result = connection.execute(text(sql_to_run))
        # Convert rows to dictionaries
        # logger.info(sql_to_run)
        for row in result:
            findings.append(dict(row._mapping))
            # logger.debug("Result: "+str(row))
        finding_count = len(findings)
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error executing rule {rule_id}: {error_message}")
        
    result_dict = rule.copy()
    
    # Strip internal server-side keys before sending to frontend
    keys_to_remove = [k for k in result_dict.keys() if k.startswith('_')]
    for k in keys_to_remove:
        del result_dict[k]
        
    result_dict.update({
        "rule_id": rule_id,
        "query_run": sql_to_run,
        "finding_count": finding_count,
        "findings": findings,
        "error": error_message
    })
    
    # Ensure fallback values for UI
    result_dict.setdefault("title", rule_id)
    result_dict.setdefault("severity", severity)
    result_dict.setdefault("remediation", remediation)
    
    return result_dict
