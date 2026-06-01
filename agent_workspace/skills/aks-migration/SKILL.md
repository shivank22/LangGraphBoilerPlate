---
name: aks-migration
description: Use this skill whenever the user wants to plan or assess migrating a legacy on-prem application or server workload to managed Azure Kubernetes Service (AKS). It drives the end-to-end workflow of discovering servers, finding the applications running on them, researching each application's GitLab codebase, and recommending good AKS migration target options.
metadata:
  author: langgraph-app
  version: "1.0"
---

# aks-migration

## Overview

This skill orchestrates a legacy on-prem -> AKS migration assessment. You will
call platform REST APIs (with the bearer-token tool `call_authenticated_api`),
delegate codebase research to the `code-researcher` subagent (which uses the
GitLab tool), and accumulate intermediate results in a canvas file on the
filesystem so nothing is lost between steps.

> DUMMY MODE: the endpoints below currently point at the public
> [JSONPlaceholder](https://jsonplaceholder.typicode.com) test API so the whole
> workflow can be exercised end-to-end without a real platform. JSONPlaceholder
> ignores the bearer token, but `call_authenticated_api` still requires one, so
> set any non-empty token in the sidebar (or `API_BEARER_TOKEN` in `.env`) —
> e.g. `dummy-token`. When wiring the real platform, replace the dummy URLs in
> the Configuration section below.

## Artifacts

Write all artifacts using simple top-level paths like `/canvas.md`,
`/servers.json`, and `/applications.json`. You do NOT need to add the
conversation id or a run id to the path — the system automatically isolates
every run's files under a private per-conversation, per-run folder, so
parallel conversations and consecutive runs never overwrite each other.

The only case you must handle yourself: if you run this same skill **more than
once within a single response/turn** (e.g. two separate migration assessments
back to back), nest each run's files under its own subfolder so they don't
collide — `/aks-migration/canvas.md` for the first, `/aks-migration-2/canvas.md`
for the second, and so on (increment the suffix). When you do this, reference
the subfolder consistently for every file in that run. For the normal case of
one assessment per turn, just use the top-level paths.

## Configuration (dummy endpoints — swap for the real platform later)

- Servers list endpoint: `https://jsonplaceholder.typicode.com/users`
  (each returned **user** stands in for a **server**: use `id` as the server id,
  `name`/`username` as the hostname, and `company.name` as the environment.)
- Applications-per-server endpoint:
  `https://jsonplaceholder.typicode.com/users/{server_id}/posts`
  (each returned **post** stands in for an **application** running on that
  server: use `id` as the application id and `title` as the application name.)
- Pass the collected `{aa_code}` and `{at_number}` as query params
  (`aa_code`, `at_number`) for traceability — the dummy API ignores them.
- GitLab project lookup: the dummy "applications" have no real GitLab project.
  Derive a placeholder project path from the application name
  (e.g. `dummy-group/<slugified-title>`) and pass that to the `code-researcher`
  subagent; treat its findings as best-effort in dummy mode.

## Required identifiers

Before calling any platform API you MUST have two identifiers from the user:

- **AA code** — an application/account code in the form `AA` followed by exactly
  5 digits. Pattern: `^AA\d{5}$` (example: `AA12345`).
- **AT number** — a ticket/tenant number in the form `AT` followed by exactly
  4 digits. Pattern: `^AT\d{4}$` (example: `AT1234`).

These are NOT secrets — collect them in plain conversation (unlike the bearer
token / GitLab PAT, which are injected automatically and must never be asked
for).

## Instructions

### 0. Collect and validate the AA code and AT number

This step runs first and gates everything else.

1. If the user has not already provided both, ask them explicitly, e.g.:
   "To start the AKS migration assessment I need your **AA code** (looks like
   `AA12345`) and your **AT number** (looks like `AT1234`)."
2. Validate each value:
   - AA code must match `^AA\d{5}$` (the letters `AA` + 5 digits).
   - AT number must match `^AT\d{4}$` (the letters `AT` + 4 digits).
3. If either value is missing or fails its pattern, do NOT call any API. Tell
   the user which value is invalid, show the expected format, and ask again.
   Repeat until both are valid.
4. Once both are valid, treat them as `{aa_code}` and `{at_number}` and
   substitute them into every endpoint URL below. Record them at the top of
   `/canvas.md` under a "## Request context" section (e.g. `AA code: AA12345`,
   `AT number: AT1234`) so the run is auditable.

### 1. Discover servers

Call `call_authenticated_api` with the servers list endpoint:

- `method`: `GET`
- `url`: `https://jsonplaceholder.typicode.com/users`
- `query_params`: `{"aa_code": "{aa_code}", "at_number": "{at_number}"}`
  (passed for traceability; the dummy API ignores them)

Write the raw response to `/servers.json` using `write_file`, then create
`/canvas.md` (if it does not exist) with a "## Servers" section summarizing the
servers found. Map each user to a server: `id` -> server id, `name`/`username`
-> hostname, `company.name` -> environment.

### 2. Find applications on the relevant server(s)

For the server(s) relevant to the user's request, call `call_authenticated_api`
again with the applications endpoint (substituting `{server_id}` with the chosen
server's `id`):

- `method`: `GET`
- `url`: `https://jsonplaceholder.typicode.com/users/{server_id}/posts`
- `query_params`: `{"aa_code": "{aa_code}", "at_number": "{at_number}"}`

Save each response to `/applications.json` and append an "## Applications"
section to `/canvas.md`. Map each post to an application: `id` -> application id,
`title` -> application name, `userId` -> the server it runs on. Derive a
placeholder GitLab project path from the title (e.g. `dummy-group/<slug>`).

### 3. Research each application's codebase (delegate)

For each application of interest, delegate to the `code-researcher` subagent via
the task tool. Provide:

- the application name,
- its GitLab project id or path,
- what you need: an AKS migration-readiness assessment (runtime, build system,
  existing Docker/Kubernetes/Helm assets, config & secrets handling, stateful
  dependencies, and blockers).

Append the subagent's findings under an "## Application research" section in
`/canvas.md`, one subsection per application.

### 4. Recommend migration targets

Using `/canvas.md` as the source of truth, write a final
"## Migration recommendations" section that, for the application(s) the user
asked about, identifies which servers/applications are good AKS migration
candidates and why (e.g. already containerized, stateless, few on-prem
dependencies), and flags the ones that need remediation first.

### 5. Respond

Give the user a concise summary of the recommendations and reference
`/canvas.md` (and `/servers.json` / `/applications.json`) for the full detail.

## Notes

- Always persist intermediate results to the filesystem before moving on, so a
  long run can be resumed and audited.
- Never put credentials in files. The bearer token and GitLab PAT are injected
  into the tools automatically; do not ask for or echo them.
