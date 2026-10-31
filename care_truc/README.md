# Customer care, A1, UI, and APIs
Input: A2 assessed-order lists with shipping dates, ETA and delay evidence, plus A3 gates and customer turns.
Implemented output: in-process chat JSON responses, durable action requests and handoffs. Web voice and HTTP mounting remain external integration work.
Owner: Truc.
Boundary: Rules first; LLM output is untrusted; no direct money effects or telephone calls.

`OpenAIPhraseSelector` implements the optional asynchronous model adapter. Run the integrated launcher with `--llm` to enable it using the repository `.env` key. It uses `httpx` from the shared development requirements. The default model is `gpt-5.4-mini`; `OPENAI_MODEL` overrides it. No key is exposed in runtime snapshots.

Conversational turns use a structured natural reply template with server-selected fact placeholders and checked social language. The model receives the latest message and recent customer/assistant turns, with phone numbers, emails and key-shaped strings redacted. Code fills all factual blocks and rejects unknown, missing or duplicate placeholders and unapproved prose. Missing or stale ETA and location remain explicitly unknown. Transactional outcomes, including cancellation and coins, keep deterministic templates and do not call the model. Natural replies have an eight-second deadline; invalid output or timeout uses a question-specific fallback. Legacy phrase-ID selectors remain supported with their existing three-second deadline.

ETA, location and explanation responses also report available journey evidence. A last recorded stage requires a matching structured scan and event timestamp from the same source record and ingestion time. Failed delivery attempts are counted once per record. Recorded no-answer outcomes describe delivery history without changing A2 fault attribution. Stale, future, conflicting or unstructured evidence does not become a public fact. Missing ETA or geographic location does not erase the verified stage and delivery history.

## Care harness

The framework-independent runtime lives in `lifecycle.py`, `harness.py` and
`dispatcher.py`. `CareRuntime.start(run_id, adapters)` opens
`runs/<run_id>/care.sqlite`, acquires an OS process lock and recovers durable work.
Call `await runtime.shutdown()` before leaving the event loop. All calls and the
SQLite connection must run on the same event-loop thread.

`CareApi(runtime.harness).handle(operation, payload, trusted_context)` is an
in-process JSON adapter. It does not authenticate HTTP credentials or mount routes.
The server must construct `TrustedRequestContext` after authentication and supply
an ownership-checking `ContextProvider`. Never construct trusted context from JSON.
Mutation responses are immutable; poll `get_messages` for receipt system events
and current delivery status. Accepted requests are not executed money or confirmed
cancellation. Unknown effects require reconciliation, not a new idempotency key.

Proposed route mapping, not mounted HTTP routes:

| Route | Operation |
| --- | --- |
| POST /api/chats | open_chat |
| GET/POST /api/chats/{id}/messages | get_messages / handle_message |
| POST /api/orders/{id}/cancel-requests | prepare_cancel after server resolves owned session |
| POST /api/cancel-requests/{id}/confirm | confirm_cancel |
| POST /api/chats/{id}/handoff | request_handoff |
| GET /api/handoffs | get_handoffs, care_handoffs staff permission |
| GET /api/chats/{id}/decisions | get_trace, care_trace staff permission; proposed extra route |

`open_contact`, `drain_pending`, `recover` and `get_health` are internal operations.
Voice transport and arbitrary client-submitted Actions are not exposed.

## Platform adapter handoff

`ports.py` defines the integration contracts requiring review with Huy before
real dispatch. Required context includes authenticated principal/ownership,
business cutoff, complete A2 assessment, A3 identity/heartbeat, mandatory feeds
with source timestamps, controls, as-of item value, grant ledger and actual
successful contact delivery. A3 controls can only tighten. Fresh source data does
not itself reopen a blocked proposal.

The gateway must atomically recheck permissions/control at dispatch, be idempotent
for an identical stable key/payload, support receipt lookup and monotonic receipt
revisions, and distinguish accepted, approval, success and rejection. It also
routes handoff envelopes to a durable sink. Network adapters declare deadline
capabilities and honor cancellation; blocking network I/O on the loop is invalid.
Evidence references identify durable A1 bundles. The server-side resolver must
read them under platform authorization; missing evidence capability blocks
financial effects. No production adapter defaults to a test fixture.

## Verification

From the repository root:

```powershell
python -c "import contracts"
pytest -q care_truc/tests
pytest -q
git diff --check
python scripts/guardrails.py --all --tests
```

The root pytest configuration discovers acceptance folders only, so the explicit
harness command is required. Tests use isolated SQLite, fake operational time,
fixed authenticated context and scripted gateways under `care_truc/tests/`.
They do not read or generate replay world data. The separate
`acceptance_huy/test_e2e_flow.py`, `test_e2e_proof.py` and
`test_integration_tick.py` exercise the release-fed local integration described
below. Neither suite establishes external provider delivery or production readiness.
Retention is run-scoped; a production retention policy remains separate work.
`CareHarness.resolve(ref, server_ctx)` supplies durable decision evidence to the platform under the explicit `care_evidence` server permission and ownership authorization. It is not a customer API operation.
See [VERIFICATION.md](VERIFICATION.md) for current commands, results and deployment scope.


## Integrated business policy

The only production entry point is `CareRuntime` / `CareHarness`; the earlier
synchronous `CareService` and session/outbox store have been replaced.
`CarePolicy` uses `rules.classify`, and `ResponseRenderer` uses the reviewed
`rendering.render_facts` through a conversion of the server guard snapshot.

Internal `open_contact(task, ctx)` requires the server-issued `care_contact`
permission, with `ctx.principal_id` bound to the customer owning the order.
The customer API cannot invoke this operation. The context provider still checks
ownership; a staff permission does not authorize customer message impersonation.
Invalid proactive context is rejected before creating a session. Contact keys bind
the entire normalized task. Customer open request IDs bind the order within the
run and principal. Committed retries replay before reading business context.

New requests after `handoff_pending`, `transferred`, or `completed` return a state
conflict. Old requests still replay their immutable response. Internal
`retry_handoff(session_id, ctx)` requires `care_handoff_retry`, rechecks the latest
gate and reuses only a blocked, never-submitted handoff envelope. It does not
reopen customer automation. Timeouts retain reconciliation.

Turn responses include the assessment fingerprint, safe public evidence, and
references resolvable through the permission-gated durable bundle resolver. Facts
use the server replay cutoff; source timestamps and ETAs are normalized to UTC,
while customer dates are rendered in Vietnam time. Stale data never supplies a
current ETA. The committed session cutoff cannot move backwards.

Authenticated human requests and mandatory turn/abuse escalation do not depend
on valid business facts. Rejected assessment/evidence timestamps or cutoff values
are discarded as a whole snapshot for these handoffs; the audit records the
validation code, with no rejected facts or business time. Identity/ownership
binding errors remain errors. The same rule permits dispatch and internal retry
of an existing handoff without weakening the platform gate or receipt checks.

The integrated schema is the main harness schema. There is no migration from the
superseded synchronous prototype database; existing prototype state must not be
silently opened as harness state. Use a fresh run or design an explicit migration.

Cancellation confirmation uses `confirm_cancel(confirmation_id, request_id, ctx,
reply_to=None, confirmed=False)`. JSON callers must supply `confirmation_id`,
`request_id`, `reply_to` (the prepare response's `message_id`), and the strict
boolean `confirmed`. Only explicit `true` on this command authorizes the second
step. Explicit acceptance text can also confirm when replying to the exact
current prompt; unbound, quoted, or negated acceptance cannot authorize it. Confirmation expires
at ten business minutes including the exact expiry instant. A fresh request is
required after expiry, retraction, handoff, or lost legacy confirmation evidence.
Consumed confirmation IDs replay the immutable original response, including
with a new request ID. Current delivery receipts remain available through GET.

The existing v1 store receives an additive `cancellations` lifecycle table on
open. Embedded legacy pending confirmations without this evidence fail closed;
there is no backfill of authorization or consumed tokens. No source DB or
shared runtime schema is changed.

## Labeled adapter demo

Run `python -m care_truc.demo`. This is an **adapter demo: algorithm fixtures
only**, using one `CareRuntime`/`CareHarness`/`CareApi`, temporary SQLite and
explicitly injected memory context, gateway, gate, clock and hostile selector.
The temporary directory is deleted on exit. No source databases or world data
are accessed, modified or generated. Receipt `succeeded` values are simulated
algorithm outcomes, never evidence of real contact, money or cancellation.

The flow checks proactive contact, ask-why, explicit coin request, receipt polling,
separate explicit cancellation confirmation and human handoff, selector fallback,
blocked guard, resolvable durable evidence and immutable POST replay. GET returns
current `effects` and separate `system_events`; render those separately from
conversation `messages`. `message_id` identifies the reply used as `reply_to`.

For real adapters, inject `context_provider`, `gateway`, `gate`, optional `selector`
and `clock` into `await CareRuntime.start(run_id, adapters, root=Path('runs'))`.
Shutdown on the same event loop. There are no fixture defaults in production.
`ContextSnapshot.ledger_pending` must be explicitly `False` for coin eligibility;
`None` is unknown and blocks it. `ledger_granted=False`, successful actual contact,
resolvable evidence, valid trusted facts and all other policy conditions remain
required. Gateway `atomic_final_validation` must be exactly `True`: this is a
platform guarantee of atomic latest permission/control/D4 validation at acceptance,
not permission for a caller to set a flag to bypass a missing implementation.

The standalone algorithm demo remains separate from
`platform_huy.demo_flow.DemoFlow`. The latter replays the existing release inputs
through A3, A2 and A1, writes actual local web-inbox contacts and staff handoffs,
and uses `SqliteEffectGateway`/`execute_action` for durable local coin ledgers and
cancellation review requests. Source databases stay read-only; runtime state is
separate. These receipts describe local SQLite effects, not commercial payouts
or contact delivery through an external provider.

Both local gateways now declare `atomic_final_validation` after final authority
and dispatch checks. Care provenance stays locked through financial acceptance;
the executor owns its own atomic permission, guard, eligibility, amount and
once-per-order ledger checks. Demo contact checks run under both write locks
without an await before inbox acceptance. This guarantee requires the existing
single event-loop thread, care OS ownership lock and one trusted runtime writer.
It does not establish a distributed transaction or support arbitrary competing
platform processes. A deployment with multiple runtime writers needs a reviewed
executor-owned provenance acceptance seam before using this attestation.

The presenter HTTP adapter has separate authentication tests; those do not mount
the proposed customer CareApi routes or establish customer network authentication.
External delivery and voice provider/session negotiation remain unintegrated.

API payloads use `handle_message(session_id, message_id, text, reply_to?)` and
`confirm_cancel(confirmation_id, request_id, reply_to, confirmed)`; JSON confirmed
must be a boolean and authorization requires explicit `true`. Customer JSON
cannot provide channel, amount, source, permissions or cutoff. See
[VERIFICATION.md](VERIFICATION.md) for repeatable checks and integration limits.
