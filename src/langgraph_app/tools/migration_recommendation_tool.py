"""Migration recommendation tools — scores CSV, inventory CSV, and recommendation JSON."""

from __future__ import annotations

import copy
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_core.tools import tool

from ..config import settings

_AA_CODE_PATTERN = re.compile(r"^AA\d{5}$")
_SKILL_DIR = "skills/migration-recommendation"
_SCORES_TEMPLATE = "migration-scores.template.csv"
_INVENTORY_TEMPLATE = "target-inventory.template.csv"
_SCORES_DIR = "scores"
_DEFAULT_MIN_SCORE = 0.7
_EXCEL_ENGINE = "openpyxl"

_SCORE_COLUMNS = ("EntityType", "EntityId", "EntityName", "Score", "Notes")
_INVENTORY_COLUMNS = (
    "Region",
    "Environment",
    "ClusterName",
    "NodePool",
    "Capacity",
    "CpuCores",
    "MemoryGb",
    "StorageGb",
    "PreferredRuntimes",
    "Notes",
)


def _skill_root() -> Path:
    return Path(settings.workspace_dir) / _SKILL_DIR


def _validate_aa_code(aa_code: str) -> str | None:
    normalised = aa_code.strip().upper()
    if not _AA_CODE_PATTERN.match(normalised):
        return (
            f"Invalid AA number '{aa_code}'. Expected format: AA followed by "
            "exactly 5 digits (e.g. AA12345)."
        )
    return None


def _parse_json_input(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} must be a JSON object.")
        return parsed
    raise ValueError(f"{field_name} must be a dict or JSON string.")


def _ensure_scores_csv(aa_code: str | None = None) -> Path | dict[str, Any]:
    template = _skill_root() / _SCORES_TEMPLATE
    if not template.is_file():
        return {"error": f"Scores template not found at {template}."}

    if aa_code:
        dest = _skill_root() / _SCORES_DIR / f"{aa_code}.csv"
    else:
        dest = _skill_root() / "migration-scores.csv"

    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file():
        shutil.copy2(template, dest)
    return dest


def _ensure_inventory_csv() -> Path | dict[str, Any]:
    dest = _skill_root() / "target-inventory.csv"
    template = _skill_root() / _INVENTORY_TEMPLATE
    if not dest.is_file():
        if not template.is_file():
            return {"error": f"Inventory template not found at {template}."}
        shutil.copy2(template, dest)
    return dest


def _load_csv(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[list(columns)].fillna("")


def _parse_score(raw: Any) -> float | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        score = float(str(raw).strip())
    except ValueError:
        return None
    if score < 0.0 or score > 1.0:
        return None
    return score


def _scores_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        entity_type = str(row["EntityType"]).strip().lower()
        entity_id = str(row["EntityId"]).strip()
        if not entity_type or not entity_id:
            continue
        score = _parse_score(row["Score"])
        records.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": str(row["EntityName"]).strip(),
                "score": score,
                "notes": str(row["Notes"]).strip(),
                "score_valid": score is not None,
            }
        )
    return records


def _inventory_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        cluster = str(row["ClusterName"]).strip()
        if not cluster:
            continue
        records.append(
            {
                "region": str(row["Region"]).strip(),
                "environment": str(row["Environment"]).strip(),
                "cluster_name": cluster,
                "node_pool": str(row["NodePool"]).strip(),
                "capacity": str(row["Capacity"]).strip().lower(),
                "cpu_cores": str(row["CpuCores"]).strip(),
                "memory_gb": str(row["MemoryGb"]).strip(),
                "storage_gb": str(row["StorageGb"]).strip(),
                "preferred_runtimes": [
                    r.strip()
                    for r in str(row["PreferredRuntimes"]).split(",")
                    if r.strip()
                ],
                "notes": str(row["Notes"]).strip(),
            }
        )
    return records


def _score_index(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["entity_type"], record["entity_id"])
        index[key] = record
    return index


def _match_inventory(
    *,
    region: str,
    environment: str,
    runtime: str,
    inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    runtime_lower = runtime.lower()
    for row in inventory:
        if row["capacity"] == "unavailable":
            continue
        region_match = not region or row["region"].lower() == region.lower()
        env_match = not environment or row["environment"].lower() == environment.lower()
        runtime_match = (
            not runtime
            or not row["preferred_runtimes"]
            or any(runtime_lower in pref.lower() for pref in row["preferred_runtimes"])
        )
        if region_match and env_match and runtime_match:
            matches.append(row)
    if not matches and region:
        for row in inventory:
            if row["capacity"] != "unavailable" and row["region"].lower() == region.lower():
                matches.append(row)
    if not matches:
        matches = [r for r in inventory if r["capacity"] != "unavailable"]
    return matches[:3]


@tool
def load_migration_scores(aa_code: str | None = None) -> dict[str, Any]:
    """Load migration suitability scores (0–1) from the skill CSV.

    Reads ``scores/{aa_code}.csv`` when ``aa_code`` is provided, otherwise
    ``migration-scores.csv``. Creates the file from the template on first use.

    Args:
        aa_code: Optional AA number to load per-application scores workbook path.

    Returns:
        Dict with ``records``, counts, and ``file_path``, or an ``error`` key.
    """
    normalised: str | None = None
    if aa_code:
        if err := _validate_aa_code(aa_code):
            return {"error": err}
        normalised = aa_code.strip().upper()

    path_or_error = _ensure_scores_csv(normalised)
    if isinstance(path_or_error, dict):
        return path_or_error

    try:
        df = _load_csv(path_or_error, _SCORE_COLUMNS)
        records = _scores_to_records(df)
    except Exception as exc:
        return {"error": f"Failed to read migration scores: {exc!s}"}

    valid = [r for r in records if r["score_valid"]]
    invalid = [r for r in records if not r["score_valid"]]
    return {
        "aa_code": normalised,
        "file_path": str(path_or_error),
        "records": records,
        "total": len(records),
        "valid_score_count": len(valid),
        "invalid_score_count": len(invalid),
    }


@tool
def load_target_inventory() -> dict[str, Any]:
    """Load the AKS target inventory CSV from the migration-recommendation skill folder.

    Creates ``target-inventory.csv`` from the template on first use.

    Returns:
        Dict with ``records``, counts, and ``file_path``, or an ``error`` key.
    """
    path_or_error = _ensure_inventory_csv()
    if isinstance(path_or_error, dict):
        return path_or_error

    try:
        df = _load_csv(path_or_error, _INVENTORY_COLUMNS)
        records = _inventory_to_records(df)
    except Exception as exc:
        return {"error": f"Failed to read target inventory: {exc!s}"}

    available = [r for r in records if r["capacity"] != "unavailable"]
    return {
        "file_path": str(path_or_error),
        "records": records,
        "total": len(records),
        "available_count": len(available),
    }


@tool
def build_migration_recommendation(
    discovery: dict[str, Any] | str,
    scores: list[dict[str, Any]] | str,
    inventory: list[dict[str, Any]] | str,
    min_score: float = _DEFAULT_MIN_SCORE,
) -> dict[str, Any]:
    """Build a migration recommendation JSON from discovery, scores, and inventory.

    Joins the application-discovery artifact with migration scores (0–1). Entities
    at or above ``min_score`` receive target cluster recommendations from the
    inventory CSV (matched by region, environment, and runtime).

    Args:
        discovery: Parsed ``discovery-artifact.json`` object or JSON string.
        scores: List of score records from ``load_migration_scores``, or JSON string.
        inventory: List of inventory records from ``load_target_inventory``, or JSON string.
        min_score: Minimum score (0–1) required to recommend migration. Default 0.7.

    Returns:
        Dict with ``recommendation``, ``recommendation_json``, and summary counts.
    """
    if min_score < 0.0 or min_score > 1.0:
        return {"error": "min_score must be between 0 and 1."}

    try:
        discovery_obj = _parse_json_input(discovery, "discovery")
    except ValueError as exc:
        return {"error": str(exc)}

    if isinstance(scores, str):
        try:
            scores_parsed = json.loads(scores)
        except json.JSONDecodeError as exc:
            return {"error": f"scores is not valid JSON: {exc}"}
    else:
        scores_parsed = scores
    if not isinstance(scores_parsed, list):
        return {"error": "scores must be a JSON array of score records."}

    if isinstance(inventory, str):
        try:
            inventory_parsed = json.loads(inventory)
        except json.JSONDecodeError as exc:
            return {"error": f"inventory is not valid JSON: {exc}"}
    else:
        inventory_parsed = inventory
    if not isinstance(inventory_parsed, list):
        return {"error": "inventory must be a JSON array of inventory records."}

    aa_code = str(discovery_obj.get("aa_code", "")).strip().upper()
    infrastructure = discovery_obj.get("infrastructure") or {}
    servers = infrastructure.get("servers") or []
    applications = infrastructure.get("applications") or []
    if not isinstance(servers, list):
        servers = []
    if not isinstance(applications, list):
        applications = []

    score_lookup = _score_index(scores_parsed)
    eligible: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    server_by_id = {
        str(s.get("id", "")): s for s in servers if isinstance(s, dict) and s.get("id")
    }

    def _assess_entity(
        entity_type: str,
        entity_id: str,
        entity_name: str,
        *,
        region: str = "",
        environment: str = "",
        runtime: str = "",
        source: dict[str, Any] | None = None,
    ) -> None:
        key = (entity_type.lower(), str(entity_id))
        score_row = score_lookup.get(key)
        score = score_row.get("score") if score_row else None
        entry: dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "entity_name": entity_name or (score_row or {}).get("entity_name", ""),
            "score": score,
            "score_notes": (score_row or {}).get("notes", ""),
            "region": region,
            "environment": environment,
            "runtime": runtime,
        }
        if source:
            entry["discovery"] = source

        suitable = score is not None and score >= min_score
        entry["migration_suitable"] = suitable

        if not suitable:
            reason = "missing score" if score is None else f"score {score} below {min_score}"
            entry["ineligible_reason"] = reason
            ineligible.append(entry)
            return

        eligible.append(entry)
        targets = _match_inventory(
            region=region,
            environment=environment,
            runtime=runtime,
            inventory=inventory_parsed,
        )
        recommendations.append(
            {
                **entry,
                "recommended_targets": targets,
                "primary_recommendation": targets[0] if targets else None,
            }
        )

    for server in servers:
        if not isinstance(server, dict):
            continue
        sid = str(server.get("id", ""))
        _assess_entity(
            "server",
            sid,
            str(server.get("hostname", "")),
            region=str(server.get("datacenter", "")),
            environment=str(server.get("environment", "")),
            source=server,
        )

    for app in applications:
        if not isinstance(app, dict):
            continue
        aid = str(app.get("id", ""))
        server_id = str(app.get("server_id", ""))
        server = server_by_id.get(server_id, {})
        _assess_entity(
            "application",
            aid,
            str(app.get("name", "")),
            region=str(server.get("datacenter", app.get("datacenter", ""))),
            environment=str(server.get("environment", app.get("environment", ""))),
            runtime=str(app.get("runtime", "")),
            source=app,
        )

    schema_path = _skill_root() / "recommendation.schema.json"
    template: dict[str, Any] = {}
    if schema_path.is_file():
        try:
            template = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            template = {}

    recommendation = copy.deepcopy(template)
    recommendation.update(
        {
            "aa_code": aa_code or None,
            "schema_version": recommendation.get("schema_version", "1.0"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_score_threshold": min_score,
            "discovery_source": "/discovery-artifact.json",
            "scores_source": str(_skill_root() / _SCORES_DIR / f"{aa_code}.csv")
            if aa_code
            else str(_skill_root() / "migration-scores.csv"),
            "inventory_source": str(_skill_root() / "target-inventory.csv"),
            "summary": {
                "total_servers": len(servers),
                "total_applications": len(applications),
                "eligible_servers": sum(
                    1 for e in eligible if e["entity_type"] == "server"
                ),
                "eligible_applications": sum(
                    1 for e in eligible if e["entity_type"] == "application"
                ),
                "recommended_targets_used": len(
                    {t["cluster_name"] for r in recommendations for t in r["recommended_targets"]}
                ),
            },
            "eligible_entities": eligible,
            "ineligible_entities": ineligible,
            "recommendations": recommendations,
        }
    )

    return {
        "aa_code": aa_code,
        "recommendation": recommendation,
        "recommendation_json": json.dumps(recommendation, indent=2),
        "eligible_count": len(eligible),
        "ineligible_count": len(ineligible),
        "recommendation_count": len(recommendations),
        "output_path": "/migration-recommendation.json",
    }
