# Monitor Agent — Simplified State-Machine Design

`META_MONITOR` is now parsed from research outputs and persisted into Notion `Research Status` as `monitor`. That means the monitoring queue is simply:

- filter: `Research Status` contains `monitor`
- sort: `Research Date` ascending (oldest first)

This document describes the simplified, end-to-end flow based on that state machine.

---

## Current Behavior (Implemented)

- The system prompt `research_agent/research_agent_prompt_al.md` includes `META_MONITOR: [Yes/No]`.
- The orchestrator `research_agent/research_agent.py` parses `META_MONITOR` from the model’s report and sets `Research Status`:
  - `META_MONITOR: Yes` → `monitor`
  - `META_MONITOR: No` (or missing) → `completed`
  - error reports / failures → `error`
- If `NOTION_DATABASE_ID_EXT` is configured, `research_agent/notion_updater.py` also mirrors `Research Status` into the external database when it finds a matching page (best-effort match by title).

Implementation note: the Notion upload flow may temporarily set `Research Status` to `completed` during property updates; the orchestrator then overwrites it to `monitor` when `META_MONITOR: Yes`.

---

## Status State Machine

Use `Research Status` as a **single-tag state** (even though it is a multi-select in Notion):

- `not researched` (or empty)
- `in progress`
- `monitor` (needs follow-up)
- `monitoring` (lock while monitor agent runs; optional but recommended)
- `completed`
- `error`

Transitions:

- Research agent:
  - `in progress` → `monitor | completed | error`
- Monitor agent:
  - `monitor` → `monitoring` → `monitor | completed | error`

---

## Monitor Agent Workflow

### 1) Pull worklist
Query the main Notion database:
- filter: `Research Status` contains `monitor`
- sort: `Research Date` ascending (then `created_time` ascending as tiebreaker)

### 2) Process each page
For each page:
1. Run monitoring research using the existing deep research pipeline (StreamingProcessor + MCP tools) with:
   - `monitor_agent/monitor_agent_prompt_al.md`
2. Upload the new report to Notion using the existing `NotionUpdater` (same formatting + metadata extraction).
3. Parse `META_MONITOR` from the new report and set:
   - `META_MONITOR: Yes` → `Research Status = monitor` (stay in queue)
   - `META_MONITOR: No` → `Research Status = completed` (kicked out of monitoring queue)

### 3) External database behavior
- When a full report is uploaded, the external DB entry (if configured and found) will have its `Research Status` mirrored to `monitor` or `completed` based on `META_MONITOR`.
- If you ever do “monitor checks” without uploading a report, you’ll need to decide whether/how to update the external DB for those lightweight passes.

---

## Scheduling / Sorting Notes

Because the queue is sorted by `Research Date`, each monitoring cycle should advance whatever timestamp you sort on.

Simplest approach:
- Always run deep monitoring research and upload a report (NotionUpdater updates `Research Date`).

Optional cost-saver:
- Use `monitor_agent/monitor_agent_triage_prompt.md` to do a cheap snapshot diff and skip deep research on “no change”, but then **explicitly update** a timestamp field (either `Research Date` or a dedicated `Last Monitor Check`) so the same page doesn’t get picked every run.

---

## Files

- `monitor_agent/monitor_agent.py` — monitor orchestrator (queries `monitor`, runs monitoring loop)
- `monitor_agent/monitor_agent_prompt_al.md` — deep monitoring system prompt (full report, uses prior context)
- `monitor_agent/monitor_agent_triage_prompt.md` — optional low-cost triage prompt (strict JSON)
