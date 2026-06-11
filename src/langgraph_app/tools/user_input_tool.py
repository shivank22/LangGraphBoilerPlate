"""Pause the agent and collect structured input from the user via LangGraph interrupt."""

from __future__ import annotations

from langchain_core.tools import tool
from langgraph.types import interrupt


def _normalise_dropdown_values(dropdown_values: list[str] | str | None) -> list[str]:
    if dropdown_values is None:
        return []
    if isinstance(dropdown_values, str):
        return [part.strip() for part in dropdown_values.split("/") if part.strip()]
    return [str(v).strip() for v in dropdown_values if str(v).strip()]


@tool
def ask_user(
    question: str,
    dropdown_values: list[str] | str | None = None,
) -> str:
    """Ask the user a question and wait for their response before continuing.

    Pauses graph execution until the user submits an answer in the chat UI (or
    API resume endpoint). Use this whenever the skill needs explicit user input,
    such as questionnaire answers or collecting the AA number.

    Args:
        question: The question or prompt to show the user.
        dropdown_values: Optional allowed answers. Pass a list like
            ``["Dev", "QA", "Prod"]`` or a slash-separated string like
            ``"Dev/QA/Prod"``. When provided, the UI shows a dropdown and
            invalid answers are rejected with a follow-up prompt.

    Returns:
        The user's answer (canonical casing when dropdown values are set).
    """
    prompt = question.strip()
    if not prompt:
        prompt = "Please provide your answer."

    options = _normalise_dropdown_values(dropdown_values)

    while True:
        answer = interrupt(
            {
                "type": "user_input",
                "question": prompt,
                "dropdown_values": options,
            }
        )
        if answer is None:
            answer_text = ""
        elif isinstance(answer, dict):
            answer_text = str(answer.get("answer", "")).strip()
        else:
            answer_text = str(answer).strip()

        if not answer_text:
            prompt = "Please provide a non-empty answer."
            continue

        if options:
            canonical = next(
                (value for value in options if value.lower() == answer_text.lower()),
                None,
            )
            if canonical is None:
                prompt = (
                    f"Invalid answer '{answer_text}'. "
                    f"Please choose one of: {', '.join(options)}"
                )
                continue
            return canonical

        return answer_text
