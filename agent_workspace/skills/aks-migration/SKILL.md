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

> Replace every `<PLACEHOLDER>` below with the real values. Endpoints are left
> blank intentionally so they can be filled in for the target environment.

## Configuration (fill these in)

- Servers list endpoint: `<SERVERS_ENDPOINT e.g. https://platform.internal/api/v1/servers>`
- Applications-per-server endpoint: `<APPLICATIONS_ENDPOINT e.g. https://platform.internal/api/v1/servers/{server_id}/applications>`
- GitLab project lookup: use the `code-researcher` subagent; pass the GitLab
  project path or id found on the application record.

## Instructions

### 1. Discover servers

Call `call_authenticated_api` with the servers list endpoint:

- `method`: `GET`
- `url`: the servers endpoint above

Write the raw response to `/servers.json` using `write_file`, then create
`/canvas.md` (if it does not exist) with a "## Servers" section summarizing the
servers found (id, hostname, environment, OS).

### 2. Find applications on the relevant server(s)

For the server(s) relevant to the user's request, call `call_authenticated_api`
again with the applications endpoint (substituting `{server_id}`):

- `method`: `GET`
- `url`: the applications endpoint with the server id filled in

Save each response to `/applications.json` and append an "## Applications"
section to `/canvas.md`, including for every application: name, the server it
runs on, and its GitLab project path/id.

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
