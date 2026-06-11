"""Application discovery questionnaire tools.

Reads and writes per-AA Excel workbooks under the application-discovery skill
folder using pandas. The template defines questions; each AA number gets its
own workbook that accumulates answers across runs.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from langchain_core.tools import tool

from ..config import settings

_AA_CODE_PATTERN = re.compile(r"^AA\d{5}$")
_SKILL_DIR = "skills/application-discovery"
_TEMPLATE_NAME = "questionnaire.template.xlsx"
_QUESTIONNAIRES_DIR = "questionnaires"
_COLUMNS = ("Question", "DropDownValues", "Answer")
_EXCEL_ENGINE = "openpyxl"


def _skill_root() -> Path:
    return Path(settings.workspace_dir) / _SKILL_DIR


def _template_path() -> Path:
    return _skill_root() / _TEMPLATE_NAME


def _questionnaire_path(aa_code: str) -> Path:
    return _skill_root() / _QUESTIONNAIRES_DIR / f"{aa_code}.xlsx"


def _validate_aa_code(aa_code: str) -> str | None:
    normalised = aa_code.strip().upper()
    if not _AA_CODE_PATTERN.match(normalised):
        return (
            f"Invalid AA number '{aa_code}'. Expected format: AA followed by "
            "exactly 5 digits (e.g. AA12345)."
        )
    return None


def _parse_dropdown_values(raw: Any) -> list[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [part.strip() for part in text.split("/") if part.strip()]


def _is_answered(raw: Any) -> bool:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return False
    return bool(str(raw).strip())


def _ensure_questionnaire(aa_code: str) -> Path | dict[str, Any]:
    template = _template_path()
    if not template.is_file():
        return {
            "error": (
                f"Questionnaire template not found at {template}. "
                "Ensure questionnaire.template.xlsx exists in the skill folder."
            )
        }

    dest = _questionnaire_path(aa_code)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file():
        shutil.copy2(template, dest)
    return dest


def _load_dataframe(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, engine=_EXCEL_ENGINE, dtype=str)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[list(_COLUMNS)].fillna("")
    return df.astype(str)


def _rows_to_questions(df: pd.DataFrame) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for index, row in df.iterrows():
        question = str(row["Question"]).strip() if pd.notna(row["Question"]) else ""
        if not question:
            continue
        dropdown_values = _parse_dropdown_values(row["DropDownValues"])
        answer_raw = row["Answer"]
        answered = _is_answered(answer_raw)
        answer = str(answer_raw).strip() if answered else None
        questions.append(
            {
                "index": int(index),
                "question": question,
                "dropdown_values": dropdown_values,
                "answer": answer,
                "answered": answered,
            }
        )
    return questions


@tool
def load_application_questionnaire(aa_code: str) -> dict[str, Any]:
    """Load the application discovery questionnaire for an AA number.

    Returns all questions with their dropdown options and current answers.
    Creates a per-AA workbook from the template if one does not exist yet.

    Args:
        aa_code: Application/account code (e.g. "AA12345").

    Returns:
        A dict with ``aa_code``, ``file_path``, ``questions`` (list), and counts,
        or an ``error`` key on failure.
    """
    if err := _validate_aa_code(aa_code):
        return {"error": err}

    normalised = aa_code.strip().upper()
    path_or_error = _ensure_questionnaire(normalised)
    if isinstance(path_or_error, dict):
        return path_or_error

    try:
        df = _load_dataframe(path_or_error)
        questions = _rows_to_questions(df)
    except Exception as exc:
        return {"error": f"Failed to read questionnaire: {exc!s}"}

    unanswered = [q for q in questions if not q["answered"]]
    return {
        "aa_code": normalised,
        "file_path": str(path_or_error),
        "questions": questions,
        "total": len(questions),
        "answered_count": len(questions) - len(unanswered),
        "unanswered_count": len(unanswered),
    }


@tool
def save_questionnaire_answer(aa_code: str, question: str, answer: str) -> dict[str, Any]:
    """Save a single questionnaire answer to the per-AA Excel workbook.

    Validates dropdown answers against allowed values when DropDownValues is set.

    Args:
        aa_code: Application/account code (e.g. "AA12345").
        question: Exact question text from the questionnaire row.
        answer: The user's answer.

    Returns:
        A dict confirming the save and reporting remaining unanswered count,
        or an ``error`` key on failure.
    """
    if err := _validate_aa_code(aa_code):
        return {"error": err}

    question_text = question.strip()
    answer_text = answer.strip()
    if not question_text:
        return {"error": "Question text must not be empty."}
    if not answer_text:
        return {"error": "Answer must not be empty."}

    normalised = aa_code.strip().upper()
    path_or_error = _ensure_questionnaire(normalised)
    if isinstance(path_or_error, dict):
        return path_or_error

    try:
        df = _load_dataframe(path_or_error)
    except Exception as exc:
        return {"error": f"Failed to read questionnaire: {exc!s}"}

    mask = df["Question"].astype(str).str.strip() == question_text
    if not mask.any():
        return {"error": f"Question not found in questionnaire: {question_text!r}"}

    row_idx = df.index[mask][0]
    dropdown_values = _parse_dropdown_values(df.at[row_idx, "DropDownValues"])
    if dropdown_values:
        canonical = next(
            (v for v in dropdown_values if v.lower() == answer_text.lower()),
            None,
        )
        if canonical is None:
            return {
                "error": (
                    f"Invalid answer '{answer_text}'. "
                    f"Allowed values: {', '.join(dropdown_values)}"
                )
            }
        answer_text = canonical

    df.at[row_idx, "Answer"] = answer_text
    try:
        df.to_excel(path_or_error, index=False, engine=_EXCEL_ENGINE)
    except Exception as exc:
        return {"error": f"Failed to save questionnaire: {exc!s}"}

    questions = _rows_to_questions(df)
    unanswered = [q for q in questions if not q["answered"]]
    return {
        "aa_code": normalised,
        "file_path": str(path_or_error),
        "saved_question": question_text,
        "saved_answer": answer_text,
        "answered_count": len(questions) - len(unanswered),
        "unanswered_count": len(unanswered),
    }
