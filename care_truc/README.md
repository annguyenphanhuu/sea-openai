# Customer care, A1, UI, and APIs
Input: A2 assessed-order lists with shipping dates, ETA and delay evidence, plus A3 gates and customer turns.
Output: Customer care, web voice, management/customer/shop UI and HTTP APIs, action requests, and handoffs.
Owner: Truc.
Boundary: Rules first; LLM output is untrusted; no direct money effects or telephone calls.

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
They do not read or generate replay world data. Passing these tests does not prove
HTTP integration, real A3/A2/executor/provider delivery or production readiness.
Retention is run-scoped; a production retention policy remains separate work.
