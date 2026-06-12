"""Skill execution progress — phase definitions and per-run progress file I/O."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_WAITING = "waiting"

_PROGRESS_FILENAME = "skill-progress.json"


def skill_name_from_skill_path(path: str) -> str | None:
    normalised = path.replace("\\", "/")
    parts = [part for part in normalised.split("/") if part]
    if not parts or not parts[-1].upper().startswith("SKILL"):
        return None
    if "skills" not in parts:
        return None
    idx = parts.index("skills")
    if idx + 1 < len(parts):
        return parts[idx + 1]
    return None


def phases_path(skill_name: str) -> Path:
    return Path(settings.workspace_dir) / "skills" / skill_name / "phases.json"


def load_phases(skill_name: str) -> list[dict[str, str]]:
    path = phases_path(skill_name)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    phases = data.get("phases") if isinstance(data, dict) else None
    if not isinstance(phases, list):
        return []
    return [
        {"id": str(phase["id"]), "label": str(phase.get("label", phase["id"]))}
        for phase in phases
        if isinstance(phase, dict) and phase.get("id")
    ]


def progress_file_path(thread_id: str, run_hash: str) -> Path:
    runs_root = settings.artifacts_runs_root.strip("/") or "runs"
    return (
        Path(settings.workspace_dir)
        / runs_root
        / thread_id
        / run_hash
        / _PROGRESS_FILENAME
    )


def progress_is_visible(progress: dict[str, Any] | None) -> bool:
    """True when the progress panel should be shown for a run."""
    if not progress or not progress.get("skill"):
        return False
    phases = progress.get("phases") or {}
    return any(
        (phase or {}).get("status") != STATUS_PENDING for phase in phases.values()
    )


def read_progress(thread_id: str, run_hash: str) -> dict[str, Any] | None:
    path = progress_file_path(thread_id, run_hash)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_progress(thread_id: str, run_hash: str, progress: dict[str, Any]) -> None:
    path = progress_file_path(thread_id, run_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(progress, indent=2), encoding="utf-8")


def _empty_phase_states(phase_ids: list[str]) -> dict[str, dict[str, str]]:
    return {phase_id: {"status": STATUS_PENDING} for phase_id in phase_ids}


def init_progress(skill_name: str) -> dict[str, Any]:
    phases = load_phases(skill_name)
    phase_ids = [phase["id"] for phase in phases]
    states = _empty_phase_states(phase_ids)
    return {
        "skill": skill_name,
        "current_phase": phase_ids[0] if phase_ids else None,
        "phases": states,
        "flags": {},
    }


def _phase_status(progress: dict[str, Any], phase_id: str) -> str:
    phase = progress.get("phases", {}).get(phase_id, {})
    return str(phase.get("status", STATUS_PENDING))


def _set_phase(
    progress: dict[str, Any],
    phase_id: str,
    status: str,
    *,
    detail: str | None = None,
) -> None:
    phases = progress.setdefault("phases", {})
    entry: dict[str, str] = {"status": status}
    if detail:
        entry["detail"] = detail
    phases[phase_id] = entry
    if status in {STATUS_IN_PROGRESS, STATUS_WAITING}:
        progress["current_phase"] = phase_id


def _complete_and_start_next(
    progress: dict[str, Any],
    completed_id: str,
    next_id: str | None,
    *,
    next_detail: str | None = None,
) -> None:
    _set_phase(progress, completed_id, STATUS_COMPLETED)
    if next_id:
        _set_phase(progress, next_id, STATUS_IN_PROGRESS, detail=next_detail)


def _parse_tool_result(result: Any) -> Any:
    if isinstance(result, dict):
        return result
    if hasattr(result, "content"):
        content = result.content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
        return content
    return result


def _is_phase_completed(progress: dict[str, Any], phase_id: str) -> bool:
    return _phase_status(progress, phase_id) == STATUS_COMPLETED


def _infer_waiting_phase(
    progress: dict[str, Any],
    *,
    tool_name: str,
    args: dict[str, Any],
    phase_ids: list[str],
    flags: dict[str, Any],
) -> str:
    """Pick the progress phase that should show a waiting state for an interrupt."""
    if tool_name == "ask_user":
        if not flags.get("questionnaire_started"):
            return "collect_aa"
        return "questionnaire"

    if tool_name == "call_authenticated_api":
        url = str(args.get("url", ""))
        if "/applications" in url:
            return "discover_applications"
        if "/servers" in url:
            return "discover_servers"

    if tool_name in {"write_file", "edit_file"}:
        path = str(args.get("file_path", "")).replace("\\", "/")
        if path.endswith("discovery-artifact.json"):
            return "build_artifact"
        if path.endswith("servers.json"):
            return "discover_servers"
        if path.endswith("applications.json"):
            return "discover_applications"
        if path.endswith("canvas.md"):
            return "summarize"
        if path.endswith("migration-recommendation.json"):
            return "build_recommendation"
        if path.endswith("migration-canvas.md"):
            return "summarize"

    if tool_name == "build_discovery_artifact":
        return "build_artifact"

    if tool_name == "build_migration_recommendation":
        return "build_recommendation"

    if tool_name in {"load_migration_scores", "load_target_inventory"}:
        return progress.get("current_phase") or phase_ids[0]

    return str(progress.get("current_phase") or phase_ids[0])


def _reconcile_progress_phases(progress: dict[str, Any], phase_ids: list[str]) -> None:
    """Ensure phases before the furthest completed step are not left waiting."""
    last_completed_index = -1
    for index, phase_id in enumerate(phase_ids):
        if _phase_status(progress, phase_id) == STATUS_COMPLETED:
            last_completed_index = index
    if last_completed_index <= 0:
        return
    for index in range(last_completed_index):
        phase_id = phase_ids[index]
        status = _phase_status(progress, phase_id)
        if status != STATUS_COMPLETED:
            _set_phase(progress, phase_id, STATUS_COMPLETED)


def apply_tool_call(
    progress: dict[str, Any] | None,
    *,
    thread_id: str,
    run_hash: str,
    tool_name: str,
    args: dict[str, Any],
    result: Any = None,
    interrupted: bool = False,
) -> dict[str, Any] | None:
    """Update progress from a completed or interrupted tool call."""
    skill = (progress or {}).get("skill")
    if not skill:
        if tool_name == "read_file":
            path = str(args.get("file_path", ""))
            detected = skill_name_from_skill_path(path)
            if detected and phases_path(detected).is_file():
                progress = init_progress(detected)
                skill = detected
            else:
                return progress
        else:
            return progress

    if progress is None:
        progress = init_progress(skill)

    phases = load_phases(skill)
    phase_ids = [phase["id"] for phase in phases]
    if not phase_ids:
        return progress

    flags = progress.setdefault("flags", {})

    if tool_name == "read_file":
        path = str(args.get("file_path", "")).replace("\\", "/")
        if skill_name_from_skill_path(path) == skill:
            _set_phase(progress, phase_ids[0], STATUS_IN_PROGRESS)
        elif skill == "migration-recommendation" and path.endswith("discovery-artifact.json"):
            _complete_and_start_next(progress, "load_discovery", "load_scores")
        write_progress(thread_id, run_hash, progress)
        return progress

    if interrupted:
        waiting_phase = _infer_waiting_phase(
            progress,
            tool_name=tool_name,
            args=args,
            phase_ids=phase_ids,
            flags=flags,
        )
        if _is_phase_completed(progress, waiting_phase):
            for phase_id in phase_ids:
                if _phase_status(progress, phase_id) != STATUS_COMPLETED:
                    waiting_phase = phase_id
                    break
        detail = "Waiting for your answer" if tool_name == "ask_user" else "Waiting for approval"
        _set_phase(progress, waiting_phase, STATUS_WAITING, detail=detail)
        _reconcile_progress_phases(progress, phase_ids)
        write_progress(thread_id, run_hash, progress)
        return progress

    parsed = _parse_tool_result(result)

    if skill == "application-discovery":
        progress = _apply_application_discovery(
            progress,
            tool_name=tool_name,
            args=args,
            parsed=parsed,
            phase_ids=phase_ids,
            flags=flags,
        )
    elif skill == "migration-recommendation":
        progress = _apply_migration_recommendation(
            progress,
            tool_name=tool_name,
            args=args,
            parsed=parsed,
            phase_ids=phase_ids,
            flags=flags,
        )

    write_progress(thread_id, run_hash, progress)
    return progress


def _apply_application_discovery(
    progress: dict[str, Any],
    *,
    tool_name: str,
    args: dict[str, Any],
    parsed: Any,
    phase_ids: list[str],
    flags: dict[str, Any],
) -> dict[str, Any]:
    url = str(args.get("url", ""))

    if tool_name == "ask_user":
        if not flags.get("questionnaire_started"):
            _complete_and_start_next(progress, "collect_aa", "discover_servers")
        else:
            _set_phase(progress, "questionnaire", STATUS_IN_PROGRESS)

    elif tool_name == "call_authenticated_api":
        if "/servers" in url and "/applications" not in url:
            _complete_and_start_next(progress, "discover_servers", "discover_applications")
        elif "/applications" in url:
            _complete_and_start_next(progress, "discover_applications", "load_questionnaire")

    elif tool_name == "load_application_questionnaire":
        flags["questionnaire_started"] = True
        if isinstance(parsed, dict):
            total = parsed.get("total", 0)
            answered = parsed.get("answered_count", 0)
            unanswered = parsed.get("unanswered_count", 0)
            if total > 0 and unanswered == 0:
                flags["all_questions_answered"] = True
                _set_phase(progress, "load_questionnaire", STATUS_COMPLETED)
                _set_phase(progress, "questionnaire", STATUS_COMPLETED)
                _set_phase(progress, "build_artifact", STATUS_IN_PROGRESS)
            elif not _is_phase_completed(progress, "load_questionnaire"):
                detail = f"{answered}/{total} answered" if total else None
                _complete_and_start_next(
                    progress,
                    "load_questionnaire",
                    "questionnaire",
                    next_detail=detail,
                )
            else:
                detail = f"{answered}/{total} answered" if total else None
                _set_phase(progress, "questionnaire", STATUS_IN_PROGRESS, detail=detail)
        else:
            _complete_and_start_next(progress, "load_questionnaire", "questionnaire")

    elif tool_name == "save_questionnaire_answer":
        flags["questionnaire_started"] = True
        detail = None
        if isinstance(parsed, dict):
            answered = parsed.get("answered_count", 0)
            unanswered = parsed.get("unanswered_count", 0)
            total = answered + unanswered
            if total:
                detail = f"{answered}/{total} answered"
            if unanswered == 0 and total > 0:
                flags["all_questions_answered"] = True
                _complete_and_start_next(progress, "questionnaire", "build_artifact")
            else:
                _set_phase(progress, "questionnaire", STATUS_IN_PROGRESS, detail=detail)
        else:
            _set_phase(progress, "questionnaire", STATUS_IN_PROGRESS)

    elif tool_name == "build_discovery_artifact":
        if isinstance(parsed, dict) and "error" not in parsed:
            _complete_and_start_next(progress, "build_artifact", "summarize")

    elif tool_name in {"write_file", "edit_file"}:
        path = str(args.get("file_path", "")).replace("\\", "/")
        if path.endswith("discovery-artifact.json"):
            if _phase_status(progress, "build_artifact") != STATUS_COMPLETED:
                _complete_and_start_next(progress, "build_artifact", "summarize")
        elif path.endswith("servers.json"):
            if _phase_status(progress, "discover_servers") != STATUS_COMPLETED:
                _complete_and_start_next(progress, "discover_servers", "discover_applications")
        elif path.endswith("applications.json"):
            if _phase_status(progress, "discover_applications") != STATUS_COMPLETED:
                _complete_and_start_next(progress, "discover_applications", "load_questionnaire")
        elif path.endswith("canvas.md") and flags.get("questionnaire_started"):
            if _is_phase_completed(progress, "questionnaire") or (
                isinstance(parsed, dict) and "error" not in parsed
            ):
                questionnaire_done = _is_phase_completed(progress, "questionnaire")
                unanswered = 0
                if not questionnaire_done:
                    questionnaire_done = flags.get("questionnaire_complete", False)
                if questionnaire_done or flags.get("all_questions_answered"):
                    _complete_and_start_next(progress, "questionnaire", "summarize")
                elif _phase_status(progress, "summarize") != STATUS_COMPLETED:
                    _set_phase(progress, "summarize", STATUS_IN_PROGRESS)
        if _phase_status(progress, "summarize") == STATUS_IN_PROGRESS:
            content = str(args.get("content", ""))
            if "Questionnaire responses" in content or "## Questionnaire" in content:
                _set_phase(progress, "summarize", STATUS_COMPLETED)
                progress["current_phase"] = "summarize"

    _reconcile_progress_phases(progress, phase_ids)
    return progress


def _apply_migration_recommendation(
    progress: dict[str, Any],
    *,
    tool_name: str,
    args: dict[str, Any],
    parsed: Any,
    phase_ids: list[str],
    flags: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "load_migration_scores":
        if isinstance(parsed, dict) and "error" not in parsed:
            _complete_and_start_next(progress, "load_scores", "assess_eligibility")

    elif tool_name == "load_target_inventory":
        if isinstance(parsed, dict) and "error" not in parsed:
            if not _is_phase_completed(progress, "assess_eligibility"):
                _set_phase(progress, "assess_eligibility", STATUS_COMPLETED)
            _complete_and_start_next(progress, "load_inventory", "build_recommendation")

    elif tool_name == "build_migration_recommendation":
        if isinstance(parsed, dict) and "error" not in parsed:
            _complete_and_start_next(progress, "build_recommendation", "summarize")

    elif tool_name in {"write_file", "edit_file"}:
        path = str(args.get("file_path", "")).replace("\\", "/")
        if path.endswith("migration-recommendation.json"):
            if _phase_status(progress, "build_recommendation") != STATUS_COMPLETED:
                _complete_and_start_next(progress, "build_recommendation", "summarize")
        elif path.endswith("migration-canvas.md"):
            if _phase_status(progress, "summarize") == STATUS_IN_PROGRESS:
                _set_phase(progress, "summarize", STATUS_COMPLETED)
                progress["current_phase"] = "summarize"

    _reconcile_progress_phases(progress, phase_ids)
    return progress


def reconcile_progress(thread_id: str, run_hash: str) -> dict[str, Any] | None:
    """Fix stale waiting/pending phases after a run or auto-approve drain."""
    progress = read_progress(thread_id, run_hash)
    if not progress:
        return None
    skill = progress.get("skill")
    if not skill:
        return progress
    phase_ids = [phase["id"] for phase in load_phases(str(skill))]
    if phase_ids:
        _reconcile_progress_phases(progress, phase_ids)
        write_progress(thread_id, run_hash, progress)
    return progress


def mark_waiting_for_interrupt(
    thread_id: str,
    run_hash: str,
    *,
    tool_name: str | None = None,
    args: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    progress = read_progress(thread_id, run_hash)
    if not progress:
        return None
    return apply_tool_call(
        progress,
        thread_id=thread_id,
        run_hash=run_hash,
        tool_name=tool_name or "ask_user",
        args=args or {},
        interrupted=True,
    )


def complete_summarize(thread_id: str, run_hash: str) -> dict[str, Any] | None:
    progress = read_progress(thread_id, run_hash)
    if not progress:
        return None
    _set_phase(progress, "summarize", STATUS_COMPLETED)
    progress["current_phase"] = "summarize"
    write_progress(thread_id, run_hash, progress)
    return progress
