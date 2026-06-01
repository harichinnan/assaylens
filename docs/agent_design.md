# Agent design

AssayLens's copilot is a **governed, read-only data interface**, not a generic
chatbot. It is orchestrated as a **LangGraph** state machine (`agent/app/graph.py`).
The LLM (Claude Haiku) does only two small jobs; deterministic tools do all data
access. All LLM calls are **response-cached** to save tokens.

## Request lifecycle (`POST /ask`) — LangGraph

```
question
   │  log (request id + question)
   ▼
START ─► route ─────► execute ─────► summarize ─► END
         │             │              │
         │ LLM plan     │ deterministic│ LLM summary (cached)
         │ (cached):    │ tool dispatch│ over compact results
         │ {steps:[…]}  │ (guardrails) │
         ▼              ▼              ▼
response: {answer, steps:[{tool,arguments,result_count,result}], + primary mirror}
```

- **route** — one cached LLM call classifies the question into an ordered plan
  of **1–3 governed tool calls**. A single step for most questions; multiple
  steps only for genuine multi-entity comparisons (e.g. "compare EGFR and HER2"
  → two `get_target_summary` steps). Plans are bounded at 3 steps and unknown
  tools are dropped.
- **execute** — runs each planned tool deterministically. The LLM never touches
  data directly; every guardrail lives inside the tools.
- **summarize** — one cached LLM call turns the compact results into the answer.

Each step in the response carries the **filters / SQL / ES query that produced
it** — the transparency guardrail. The graph is intentionally linear (no
unbounded agent loop) so the governance stays auditable.

## Response caching (token savings)

`agent/app/cache.py` caches every LLM completion keyed by a sha256 of
`(model, system, messages, max_tokens)`. Identical routing or summarization
requests return the cached text and cost **zero tokens** (verify via `GET /cache`
— `hits` rise while `llm_api_calls` stays flat). The cache is in-memory with
optional write-through JSON persistence (`AGENT_CACHE_PATH`, mounted to a Docker
volume by default) and an optional TTL (`AGENT_CACHE_TTL_SECONDS`).

## The LLM's narrow role

1. **Intent routing.** Given the question and compact tool specs, output JSON
   `{tool, arguments}`. Prompt: `prompts/intent_router.md`.
2. **Summarization.** Given a *compact* tool result, write a short faithful
   answer. Prompt: `prompts/system_prompt.md`.

The LLM never sees raw rows in bulk, never writes SQL that executes, and never
makes scientific claims. Without an API key, both steps fall back to
deterministic keyword routing + templated summaries, so the service still runs.

## Tools

| Tool | Data source | Notes |
|------|-------------|-------|
| `search_assay_evidence(query, target?, standard_type?, max_value_nm?, min_confidence?, limit?)` | Elasticsearch | builds a bool query from typed args |
| `run_curated_sql(sql)` | Postgres marts | SELECT-only, allow-listed, LIMIT-capped |
| `get_compound_profile(molecule_chembl_id)` | marts | properties + evidence + best potency |
| `get_target_summary(target_name)` | marts | counts, median potency, DQ breakdown |
| `explain_data_quality(activity_id?/molecule_chembl_id?/assay_chembl_id?)` | fact (via lineage tool) | inclusion/exclusion reasons |
| `get_metric_definition(metric_name)` | static dictionary | IC50/Ki/Kd/EC50/pChEMBL/… |
| `get_metabase_dashboard(dashboard_name, filters)` | config | link + filter params |

## Guardrails

- **Read-only** end to end. DB connection uses the `agent_ro` role and a
  read-only transaction.
- **SELECT-only SQL.** `sql_guardrails.validate_sql` rejects DDL/DML/DCL/TCL,
  stacked statements, `COPY`, file functions, `pg_catalog`/`information_schema`,
  and any table not on the curated allow-list. A `LIMIT` is injected if missing
  and capped to `SQL_MAX_ROWS`.
- **Statement timeout + max rows.** Set via `.env` (`SQL_STATEMENT_TIMEOUT_MS`,
  `SQL_MAX_ROWS`) and enforced at the connection + validator level.
- **Curated by default.** Raw/staging are unreachable via SQL; the fact table is
  reachable only through `explain_data_quality`.
- **Structured search.** No free-form ES DSL from the LLM.
- **Transparency.** Every answer surfaces the exact filters/SQL used.
- **Audit log.** Each request logs the question, chosen tool, arguments, and
  result count with a request id.
- **No overclaiming.** The system prompt forbids efficacy/safety/mechanism
  conclusions; the agent describes measurements, not drug performance.

## Why a small LLM is enough

Routing is a short classification, and summarization operates on already-
aggregated, compact results. Deterministic SQL templates and small schema
summaries keep token usage low and outputs reproducible — the warehouse, not the
model, is the source of truth.

## Example mappings

| Question | Tool | Key arguments |
|----------|------|---------------|
| "Find high-confidence EGFR assays with IC50 under 100 nM." | `search_assay_evidence` | target=EGFR, standard_type=IC50, max_value_nm=100, min_confidence=8 |
| "Which EGFR compounds have the strongest curated potency evidence?" | `search_assay_evidence` / `run_curated_sql` | target=EGFR, sort by pChEMBL |
| "Why do raw EGFR rows differ from the curated EGFR potency mart?" | `explain_data_quality` | (warehouse or target scope) |
| "Show me the assay quality dashboard for BRAF." | `get_metabase_dashboard` | dashboard=data_quality, filters={target: BRAF} |
| "Explain pChEMBL versus IC50 in plain English." | `get_metric_definition` | metric_name=pChEMBL |
| "Compare EGFR and HER2 by assay coverage and active compound count." | `get_target_summary` | target_name=EGFR (then HER2) |
