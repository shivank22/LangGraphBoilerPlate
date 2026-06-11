"""Build the application-discovery JSON artifact from API and questionnaire data."""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from ..config import settings
from .questionnaire_tool import _ensure_questionnaire, _load_dataframe, _rows_to_questions

_AA_CODE_PATTERN = re.compile(r"^AA\d{5}$")
_SKILL_DIR = "skills/application-discovery"
_SCHEMA_NAME = "discovery-artifact.schema.json"
_MAPPING_NAME = "discovery-artifact.mapping.json"

_DEFAULT_MAPPINGS: list[dict[str, str]] = [
    {"target": "aa_code", "source": "aa_code"},
    {"target": "discovered_at", "source": "generated.discovered_at"},
    {"target": "infrastructure.servers", "source": "servers.servers"},
    {"target": "infrastructure.applications", "source": "generated.applications_flat"},
    {"target": "questionnaire.responses", "source": "generated.questionnaire_responses"},
]


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


def _parse_json_input(value: Any, field_name: str) -> dict[str, Any] | list[Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, (dict, list)):
            raise ValueError(f"{field_name} must be a JSON object or array.")
        return parsed
    raise ValueError(f"{field_name} must be a dict, list, or JSON string.")


def _strip_comments(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            key: _strip_comments(value)
            for key, value in obj.items()
            if not str(key).startswith("_")
        }
    if isinstance(obj, list):
        return [_strip_comments(item) for item in obj]
    return obj


def _load_schema() -> dict[str, Any]:
    path = _skill_root() / _SCHEMA_NAME
    if not path.is_file():
        return {
            "aa_code": None,
            "schema_version": "1.0",
            "discovered_at": None,
            "infrastructure": {"servers": [], "applications": []},
            "questionnaire": {"responses": []},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read schema at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Schema file must contain a JSON object: {path}")
    return _strip_comments(data)


def _load_mappings() -> list[dict[str, str]]:
    path = _skill_root() / _MAPPING_NAME
    if not path.is_file():
        return _DEFAULT_MAPPINGS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read mapping at {path}: {exc}") from exc
    mappings = data.get("mappings") if isinstance(data, dict) else None
    if not isinstance(mappings, list):
        return _DEFAULT_MAPPINGS
    valid = [
        {"target": str(item["target"]), "source": str(item["source"])}
        for item in mappings
        if isinstance(item, dict) and item.get("target") and item.get("source")
    ]
    return valid or _DEFAULT_MAPPINGS


def _resolve_source(sources: dict[str, Any], source_path: str) -> Any:
    current: Any = sources
    for part in source_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _deep_set(obj: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cursor: dict[str, Any] = obj
    for part in parts[:-1]:
        next_val = cursor.get(part)
        if not isinstance(next_val, dict):
            next_val = {}
            cursor[part] = next_val
        cursor = next_val
    cursor[parts[-1]] = copy.deepcopy(value)


def _flatten_applications(
    applications_responses: list[Any],
    aa_code: str,
) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for entry in applications_responses:
        if not isinstance(entry, dict):
            continue
        server_id = str(entry.get("server_id", ""))
        apps = entry.get("applications")
        if not isinstance(apps, list):
            continue
        for app in apps:
            if not isinstance(app, dict):
                continue
            record = dict(app)
            record.setdefault("server_id", server_id)
            record.setdefault("aa_code", aa_code)
            flat.append(record)
    return flat


def _questionnaire_responses(aa_code: str) -> list[dict[str, Any]] | dict[str, Any]:
    path_or_error = _ensure_questionnaire(aa_code)
    if isinstance(path_or_error, dict):
        return path_or_error
    try:
        df = _load_dataframe(path_or_error)
        questions = _rows_to_questions(df)
    except Exception as exc:
        return {"error": f"Failed to read questionnaire: {exc!s}"}

    responses: list[dict[str, Any]] = []
    for row in questions:
        responses.append(
            {
                "question": row["question"],
                "answer": row["answer"],
                "dropdown_values": row["dropdown_values"],
                "answered": row["answered"],
            }
        )
    return responses


@tool
def build_discovery_artifact(
    aa_code: str,
    servers: dict[str, Any] | str,
    applications: list[dict[str, Any]] | str,
) -> dict[str, Any]:
    """Assemble the discovery JSON artifact from API responses and the questionnaire.

    Reads the example schema from ``discovery-artifact.schema.json`` in the
    application-discovery skill folder and fills it using
    ``discovery-artifact.mapping.json``. Replace those files to customize the
    output shape.

    Args:
        aa_code: Application/account code (e.g. ``"AA12345"``).
        servers: Servers API response object (or JSON string). Must include a
            ``servers`` array when using the default mapping.
        applications: List of per-server applications API responses (or JSON
            string). Each entry should include ``server_id`` and ``applications``.

    Returns:
        A dict with ``artifact`` (filled object), ``artifact_json`` (pretty string
        for ``write_file``), ``schema_path``, ``mapping_path``, and counts; or an
        ``error`` key on failure.
    """
    if err := _validate_aa_code(aa_code):
        return {"error": err}

    normalised = aa_code.strip().upper()

    try:
        servers_parsed = _parse_json_input(servers, "servers")
        applications_parsed = _parse_json_input(applications, "applications")
    except ValueError as exc:
        return {"error": str(exc)}

    if not isinstance(servers_parsed, dict):
        return {"error": "servers must be a JSON object (the servers API response)."}
    if not isinstance(applications_parsed, list):
        return {"error": "applications must be a JSON array of per-server API responses."}

    questionnaire_data = _questionnaire_responses(normalised)
    if isinstance(questionnaire_data, dict) and questionnaire_data.get("error"):
        return questionnaire_data

    try:
        schema_template = _load_schema()
        mappings = _load_mappings()
    except ValueError as exc:
        return {"error": str(exc)}

    sources: dict[str, Any] = {
        "aa_code": normalised,
        "servers": servers_parsed,
        "generated": {
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "applications_flat": _flatten_applications(applications_parsed, normalised),
            "questionnaire_responses": questionnaire_data,
        },
    }

    artifact = copy.deepcopy(schema_template)
    for mapping in mappings:
        value = _resolve_source(sources, mapping["source"])
        if value is not None:
            _deep_set(artifact, mapping["target"], value)

    schema_path = _skill_root() / _SCHEMA_NAME
    mapping_path = _skill_root() / _MAPPING_NAME

    return {
        "aa_code": normalised,
        "artifact": artifact,
        "artifact_json": json.dumps(artifact, indent=2),
        "schema_path": str(schema_path),
        "mapping_path": str(mapping_path),
        "server_count": len(servers_parsed.get("servers") or []),
        "application_count": len(sources["generated"]["applications_flat"]),
        "questionnaire_response_count": len(questionnaire_data),
        "output_path": "/discovery-artifact.json",
    }
