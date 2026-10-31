# LLM agents

Start all three agents with the OpenAI key already in the repository-root `.env`:

```powershell
python -m platform_huy.serve_ui --integrated --llm --state-path runs/llm-demo/state.sqlite
```

The existing UI runs at `http://127.0.0.1:8765`. Its existing presenter authentication
still applies. NEXT runs A3 → A2 → A1 at a 30-minute replay interval. A1 uses the
model when a customer sends an informational chat message; opening a proactive
chat, financial decisions and handoffs remain deterministic.

Only `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_REVIEW_MODEL` are loaded from
`.env`; process environment settings take precedence. The default is
`gpt-5.4-mini`. `OPENAI_REVIEW_MODEL` optionally overrides the A2/A3 model.
No key means `--llm` fails at startup. Without `--llm`, behavior stays offline.
No shared contracts or dependencies were changed.

| Agent | LLM responsibility | Enforced boundary |
| --- | --- | --- |
| A1 | Interpret unfamiliar wording and choose a response topic; compose approved social clauses around verified fact slots | Cannot write dates, amounts, locations or promises; cancellation, coins and human requests run through existing policy first |
| A2 | Analyze a diverse priority batch, select evidence and recommend the next operator investigation | Status, fault, ETA, confidence and compensation stay authoritative rule outputs; summaries are explicitly `operator_advisory_only` |
| A3 | Review source freshness and recommend maintaining controls or blocking proactive contact | Can only tighten `proactive_block`; cannot restore feed trust, clear a human block, create a heartbeat after kill, or execute money |

A2 reviews at most **6 orders per tick**, covering distinct statuses before filling
remaining positions by severity. Each order supplies at most 16 structured facts.
Every order still receives its normal deterministic assessment. Coverage reports
distinguish total, selected and successfully reviewed orders. This is bounded
operator triage, not an LLM assessment of every order or calibrated forecasting.
Unstructured driver messages and order/customer/record identifiers are not sent
to the A2 model. Local evidence references are bound back after validation.

The A2/A3 Responses API calls use `store=false`, strict JSON schemas, local schema
and reference validation, a 48 KB input limit, a 3,000-output-token limit, and a
30-second timeout per call. There are no automatic retries. A1 retains its existing
8-second deadline. API failure, refusal, incomplete JSON or invalid references
produce a visible `fallback`, retaining existing rule checks. An A3 model block
is durable and does not clear on a later healthy-model response or revive.

`guard_alive` retains the existing 90-minute liveness indicator. Contact permission
independently expires after the shared contract's **60-minute** heartbeat limit.
Feed freshness still uses source timestamps and the 30-minute threshold.

## Inspect results

- Authenticated `GET /api/demo/state`: `llm.agents.A1.last_call` and
  `llm.agents.A2.latest` / `llm.agents.A3.latest` expose status, sanitized errors,
  provider response IDs, token usage, latency and review results.
- Existing orders API: `llm_review` on the envelope and on successfully reviewed
  rows. Unreviewed orders do not acquire an invented review.
- Existing records API: `table=agent_llm_reviews` reads the durable review audit.
  Records live in runtime SQLite, alongside the existing snapshots. Restarting
  without LLM preserves past traces while reporting `enabled=false`.
- Each A1 turn already reports `source`, `inside.used_llm`, and fallback codes.
  A successful transport is not treated as an accepted customer reply until fact
  slot validation succeeds.

These are API additions; the frontend has not been redesigned to display A2/A3
review prose. Summaries are unverified model hypotheses for an operator and must
not be reused as verified customer-facing facts or executed as instructions.

## Repeat verification

Offline tests (no API key or paid requests):

```powershell
python -m pytest -q
python -m pytest -q care_truc/tests
```

Live evaluation (uses OpenAI credits and the real read-only release DBs):

```powershell
python -m platform_huy.verify_llm
```

Each live run gets a new `runs/llm-verification-*/` directory with isolated runtime
state and `report.json`. It checks real model success rather than accepting a
fallback as a successful integration. Cases cover a complete release tick,
Vietnamese explanation, an English ETA question, injection with and without a
financial keyword, cancellation confirmation/retry, human handoff, driver-text
isolation, stale sources and audit recovery. The driver/staleness perturbations
are explicit isolated tests; they never become replay world data. SHA-256 hashes
of both release databases are recorded before and after.

The offline suite also injects timeouts, HTTP 401/429/500, invalid schema, false
references, unauthorized actions and incomplete batches. Model latency and output
can vary between live runs; retained reports include failures as well as successes.

API reference used: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
