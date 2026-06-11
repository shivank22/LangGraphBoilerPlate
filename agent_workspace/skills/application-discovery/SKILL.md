---
name: application-discovery
description: Use this skill to discover application details for a given AA number using platform REST APIs and an interactive questionnaire. It collects server/application data from APIs and walks the user through a structured questionnaire with optional dropdown answers, persisting responses to a per-AA Excel workbook.
metadata:
  author: langgraph-app
  version: "1.0"
---

# application-discovery

## Overview

This skill orchestrates application discovery for a given AA number. You will
call platform REST APIs (with the bearer-token tool `call_authenticated_api`),
run an interactive questionnaire loaded from an Excel template, and accumulate
intermediate results in a canvas file on the filesystem so nothing is lost between
steps.

> MOCK MODE: the endpoints below call the local mock discovery API served by
> this app's FastAPI instance (`http://localhost:8000`). Start the app with
> `./start.sh`, set the bearer token in the sidebar to **`1234`** (or set
> `API_BEARER_TOKEN=1234` in `.env`). The mock API rejects other tokens.
> When your real platform is ready, replace the mock URLs in the Configuration
> section below.

## Questionnaire file

Questions are defined in the shared template at
`/skills/application-discovery/questionnaire.template.xlsx` with columns:

- **Question** — text shown to the user
- **DropDownValues** — allowed answers separated by `/` (empty = free text)
- **Answer** — filled during discovery (empty in the template)

Per-AA answers are maintained in
`/skills/application-discovery/questionnaires/{aa_code}.xlsx` (created from the
template on first load). Use `load_application_questionnaire` and
`save_questionnaire_answer` to read and update that workbook — do not edit the
Excel file manually with `write_file`.

## Artifacts

Write all artifacts using simple top-level paths like `/canvas.md`,
`/servers.json`, `/applications.json`, and `/discovery-artifact.json`. You do NOT
need to add the conversation id or a run id to the path — the system
automatically isolates every run's files under a private per-conversation,
per-run folder, so parallel conversations and consecutive runs never overwrite
each other.

The only case you must handle yourself: if you run this same skill **more than
once within a single response/turn** (e.g. two separate discovery runs back to
back), nest each run's files under its own subfolder so they don't collide —
`/application-discovery/canvas.md` for the first,
`/application-discovery-2/canvas.md` for the second, and so on (increment the
suffix). When you do this, reference the subfolder consistently for every file in
that run. For the normal case of one discovery per turn, just use the top-level
paths.

## Configuration (mock endpoints — swap for the real platform later)

- Servers list endpoint:
  `http://localhost:8000/mock/discovery/{aa_code}/servers`
  Response shape: `{"aa_code": "...", "servers": [{"id", "hostname", "environment", ...}]}`
- Applications-per-server endpoint:
  `http://localhost:8000/mock/discovery/{aa_code}/servers/{server_id}/applications`
  Response shape: `{"aa_code", "server_id", "applications": [{"id", "name", "runtime", ...}]}`
- Pass `{aa_code}` in the URL path and also as query param `aa_code` for
  traceability (both must match).

## Discovery JSON artifact

The canonical output of a completed discovery run is `/discovery-artifact.json`.
Its shape is defined by two files in this skill folder (you can replace them
with your own platform schema):

- **`discovery-artifact.schema.json`** — example JSON structure (template).
  Paste your own schema here; keys starting with `_` are ignored as comments.
- **`discovery-artifact.mapping.json`** — maps data sources to paths inside the
  schema. Update the `target` paths when you change the schema layout.

Default mappings:

| Target path | Source |
|---|---|
| `aa_code` | validated AA number |
| `discovered_at` | UTC timestamp when the artifact is built |
| `infrastructure.servers` | `servers` array from the servers API response |
| `infrastructure.applications` | flattened list from all applications API responses |
| `questionnaire.responses` | all questionnaire rows (question, answer, dropdowns) |

Use `build_discovery_artifact` to fill the schema from API responses and the
questionnaire workbook, then persist the returned `artifact_json` with
`write_file` to `/discovery-artifact.json`.

## Required identifiers

Before calling any platform API you MUST have one identifier from the user:

- **AA number** — an application/account code in the form `AA` followed by
  exactly 5 digits. Pattern: `^AA\d{5}$` (example: `AA12345`).

This is NOT a secret — collect it in plain conversation (unlike the bearer
token, which is injected automatically and must never be asked for).

## Instructions

### 0. Collect and validate the AA number

This step runs first and gates everything else.

1. If the user has not already provided a valid AA number in their message,
   call `ask_user` with a clear prompt, e.g.:
   "To start application discovery I need your **AA number** (looks like
   `AA12345`)."
2. Validate the returned value:
   - AA number must match `^AA\d{5}$` (the letters `AA` + 5 digits).
3. If the value is missing or fails its pattern, call `ask_user` again with the
   validation error and expected format. Do NOT call any API until valid.
4. Once valid, treat it as `{aa_code}` and substitute it into every endpoint
   URL below. Record it at the top of `/canvas.md` under a "## Request context"
   section (e.g. `AA number: AA12345`) so the run is auditable.

### 1. Discover servers

Call `call_authenticated_api` with the servers list endpoint:

- `method`: `GET`
- `url`: `http://localhost:8000/mock/discovery/{aa_code}/servers`
- `query_params`: `{"aa_code": "{aa_code}"}`

Write the raw response to `/servers.json` using `write_file`, then create
`/canvas.md` (if it does not exist) with a "## Servers" section summarizing the
`servers` array from the response (`id`, `hostname`, `environment`, etc.).

### 2. Find applications on the relevant server(s)

For the server(s) relevant to the user's request, call `call_authenticated_api`
again with the applications endpoint (substituting `{server_id}` with the chosen
server's `id`):

- `method`: `GET`
- `url`: `http://localhost:8000/mock/discovery/{aa_code}/servers/{server_id}/applications`
- `query_params`: `{"aa_code": "{aa_code}"}`

Save each response to `/applications.json` (use a JSON array when multiple
servers were queried) and append an "## Applications" section to `/canvas.md`
using the `applications` array (`id`, `name`, `runtime`, and `server_id` from
the response).

### 3. Load the questionnaire

Call `load_application_questionnaire` with `aa_code` set to `{aa_code}`.

If the tool returns an `error` key, report the failure to the user and stop.

Review the returned `questions` list. Note which rows have `answered: false`.

### 4. Interactive questionnaire

For each unanswered question, collect input with `ask_user` — **one question per
tool call**:

1. Call `ask_user` with:
   - `question`: the row's `question` text
   - `dropdown_values`: the row's `dropdown_values` list when non-empty; omit
     or pass empty for free-text questions
2. The tool pauses until the user submits an answer in the UI (dropdown or text
   field). It validates dropdown answers automatically.
3. Call `save_questionnaire_answer` with `aa_code`, `question` (exact text from
   the questionnaire row), and `answer` set to the value returned by `ask_user`.
   Do this immediately after each answer — do not batch.
4. Repeat for the next unanswered question until all rows are answered.

If the user has already answered some questions in a prior run (the per-AA
workbook has existing answers), skip those rows and only ask unanswered ones.

When all questions are answered, proceed to step 5.

### 5. Build discovery JSON artifact

Assemble the canonical JSON artifact from everything collected so far:

1. Call `build_discovery_artifact` with:
   - `aa_code`: `{aa_code}`
   - `servers`: the full JSON object returned by the servers API in step 1
     (must include a `servers` array for the default mapping)
   - `applications`: a **JSON array** of every applications API response from
     step 2 — one object per server queried, each including `server_id` and
     `applications`
2. If the tool returns an `error` key, report the failure and stop.
3. Call `write_file` with:
   - `file_path`: `/discovery-artifact.json`
   - `content`: the `artifact_json` string from the tool result (do not
     reformat or omit fields)
4. Optionally append a short "## Discovery artifact" note to `/canvas.md`
   referencing `/discovery-artifact.json` and the counts returned by the tool
   (`server_count`, `application_count`, `questionnaire_response_count`).

### 6. Summarize and respond

1. Call `load_application_questionnaire` again to get the final state.
2. Append a "## Questionnaire responses" section to `/canvas.md` listing each
   question and its answer.
3. Give the user a concise summary of what was discovered (servers, applications,
   questionnaire answers, and the JSON artifact) and reference `/canvas.md`,
   `/discovery-artifact.json`, `/servers.json`, and `/applications.json` for
   full detail.

## Progress phases

Defined in `phases.json` beside this file. The UI shows live step status
automatically; no extra tool calls are required.

## Notes

- Always persist intermediate results to the filesystem before moving on, so a
  long run can be resumed and audited.
- Never put credentials in files. The bearer token is injected into the tools
  automatically; do not ask for or echo it.
- Use `ask_user` (not plain chat text) whenever you need input from the user —
  including the AA number and each questionnaire answer. The UI renders a form
  with a dropdown when `dropdown_values` are provided.
- To add or change questionnaire questions, edit
  `questionnaire.template.xlsx` in this skill folder (new discoveries copy from
  the template; existing per-AA workbooks are not overwritten).
