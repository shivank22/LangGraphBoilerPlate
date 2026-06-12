---
name: migration-recommendation
description: Use after application-discovery to recommend AKS migration targets. Reads the discovery JSON artifact, migration suitability scores (0–1) from CSV, and a target inventory CSV, then produces a migration-recommendation.json with eligible servers/applications and suggested clusters.
metadata:
  author: langgraph-app
  version: "1.0"
---

# migration-recommendation

## Overview

This skill consumes the output of **application-discovery** and produces migration
recommendations. It:

1. Reads `/discovery-artifact.json` from the current run
2. Loads migration **scores** (0–1) from CSV in this skill folder
3. Determines which servers/applications are suitable to migrate (score ≥
   threshold, default **0.7**)
4. Loads the **target inventory** CSV (available AKS clusters)
5. Matches eligible entities to inventory rows (region, environment, runtime)
6. Writes `/migration-recommendation.json` and summarizes for the user

> **Prerequisite:** Run `application-discovery` first so
> `/discovery-artifact.json` exists in the current run's artifact folder.

## Score and inventory files

Templates live beside this file:

| File | Purpose |
|------|---------|
| `migration-scores.template.csv` | Template for suitability scores |
| `scores/{aa_code}.csv` | Per-AA scores (created from template on first load) |
| `target-inventory.template.csv` | Template for AKS target clusters |
| `target-inventory.csv` | Working inventory (created from template on first load) |
| `recommendation.schema.json` | Example output shape |

### Score CSV columns

- **EntityType** — `server` or `application`
- **EntityId** — must match `id` from the discovery JSON
- **EntityName** — display name (hostname, app name)
- **Score** — float **0.0 to 1.0** (1 = highly suitable)
- **Notes** — optional rationale

Use `load_migration_scores` to read scores — do not parse the CSV manually.

### Inventory CSV columns

- **Region** — e.g. `DC-East` (matches server `datacenter` from discovery)
- **Environment** — e.g. `Prod`, `QA`
- **ClusterName**, **NodePool**, **Capacity** (`available` / `limited` / `unavailable`)
- **CpuCores**, **MemoryGb**, **StorageGb**
- **PreferredRuntimes** — comma-separated, e.g. `Java 17,Node.js 20`
- **Notes**

Use `load_target_inventory` to read inventory.

## Artifacts

Write outputs to top-level paths (same run isolation as application-discovery):

- Input: `/discovery-artifact.json` (from prior discovery step)
- Output: `/migration-recommendation.json`
- Optional: `/migration-canvas.md` for human-readable summary

## Instructions

### 0. Confirm discovery artifact exists

1. Use `read_file` on `/discovery-artifact.json`.
2. If missing or invalid, tell the user to run **application-discovery** first and stop.
3. Parse the JSON and note `aa_code`, servers, and applications.
4. Record `aa_code` at the top of `/migration-canvas.md` under "## Context".

### 1. Load migration scores

1. Call `load_migration_scores` with `aa_code` from the discovery artifact.
2. If the tool returns an `error`, report it and stop.
3. Review `records` — every server and application from discovery should have a
   row with a valid score in **0–1**. Note `valid_score_count` and any invalid rows.

### 2. Assess eligibility (preview)

Before loading inventory, summarize which entities meet the default threshold
(**0.7**) using the scores from step 1. Mention counts only — full matching
happens in step 4.

### 3. Load target inventory

1. Call `load_target_inventory` (no arguments).
2. If the tool returns an `error`, report it and stop.
3. Review `records` — note available clusters by region and environment.

### 4. Build recommendation JSON

1. Call `build_migration_recommendation` with:
   - `discovery`: the full discovery JSON object (from step 0)
   - `scores`: the `records` array from `load_migration_scores`
   - `inventory`: the `records` array from `load_target_inventory`
   - `min_score`: `0.7` unless the user specified a different threshold
2. If the tool returns an `error`, report it and stop.
3. Call `write_file` with:
   - `file_path`: `/migration-recommendation.json`
   - `content`: the `recommendation_json` string from the tool (verbatim)

### 5. Summarize for the user

1. Append a "## Migration recommendations" section to `/migration-canvas.md` with:
   - Eligible vs ineligible counts
   - For each **eligible** server/application: score, and the **primary_recommendation**
     cluster (region, environment, cluster name)
   - Brief note on ineligible entities and why (score below threshold or missing)
2. Give the user a concise chat summary and point to `/migration-recommendation.json`
   and `/migration-canvas.md`.

## Progress phases

Defined in `phases.json` beside this file. The UI shows live step status
automatically; no extra tool calls are required.

## Notes

- Scores are **per entity** (server or application), not per AA number alone.
- Inventory matching prefers same **region** (`datacenter`) and **environment**,
  then runtime fit via `PreferredRuntimes`.
- To change scores or inventory for your platform, edit the CSV files in this
  skill folder (or per-AA `scores/{aa_code}.csv`).
- Do not put credentials in artifact files.
