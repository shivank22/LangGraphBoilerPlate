---
name: custom-llm-call
description: Use this skill when the user wants a dedicated LLM analysis or generation task that requires a custom system prompt defined by this skill. The agent delegates the work to a separate LLM call via the call_custom_llm tool.
metadata:
  author: langgraph-app
  version: "1.0"
---

# custom-llm-call

## Overview

This skill runs a specialized one-shot LLM task using the `call_custom_llm`
tool. The system prompt for that call is defined in the **System Prompt**
section below — you must pass it verbatim to the tool. Gather any context
from the user's request (and from files you have already read), build a clear
`user_prompt`, call the tool, then persist the result to the canvas.

## System Prompt

You are a specialized assistant. Follow the user's instructions precisely.
Respond in clear, structured markdown. If asked to produce JSON, return
valid JSON only with no surrounding prose.

## Artifacts

Write the LLM output to `/canvas.md` using `write_file`. You do NOT need to
add the conversation id or a run id to the path — the system automatically
isolates every run's files under a private per-conversation, per-run folder.

If you run this same skill **more than once within a single response/turn**,
nest each run's files under its own subfolder so they don't collide —
`/custom-llm-call/canvas.md` for the first, `/custom-llm-call-2/canvas.md`
for the second, and so on. For the normal case of one task per turn, use the
top-level `/canvas.md` path.

## Instructions

### 0. Confirm the task

Make sure you understand what the user wants generated or analyzed. If the
request is ambiguous, ask one short clarifying question before calling the
tool.

### 1. Build the user prompt

Compose a `user_prompt` that includes:

- The user's goal or question in plain language.
- Any relevant context you already have (prior messages, file contents,
  structured data).
- Output format expectations if the user stated them (e.g. bullet list,
  JSON schema, table).

Do not include the system prompt in `user_prompt` — that goes in
`system_prompt` only.

### 2. Call `call_custom_llm`

Call `call_custom_llm` with:

- `system_prompt`: the **entire body** of the `## System Prompt` section
  above (everything after the heading), copied **verbatim** — do not
  paraphrase or summarize it.
- `user_prompt`: the message you composed in step 1.

If the tool returns an `error` key, report the failure to the user and stop.

### 3. Persist and respond

1. Write the returned `content` to `/canvas.md` (or the nested path if this
   is a repeat run in the same turn).
2. Reply to the user with a concise summary of what was produced and point
   them to the canvas file.

## Notes

- This skill uses the app's default model and API key from environment
  configuration — never ask the user for API credentials.
- The custom LLM call is separate from your own reasoning loop; treat the
  tool result as the authoritative output for this task.
- If the user wants to change how the specialized LLM behaves, they should
  edit the `## System Prompt` section in this skill file.
