# Care verification

From the repository root, Python 3.11+:

```powershell
python -c "import contracts; import care_truc"
python -m pytest care_truc/tests/test_flow.py -q
python -m pytest care_truc/tests -q
python -m pytest -q
python -m pytest acceptance_huy acceptance_an_nguyen acceptance_truc care_truc/tests -q
python -m care_truc.demo
git diff --check
python scripts/guardrails.py --all --tests
```

Root pytest discovers acceptance folders; include care tests explicitly for the
combined suite. The flow test invokes the same labeled demo used by the CLI. All
its inputs are algorithm fixtures, SQLite is isolated, and no source DB or world
data is accessed or generated. The gateway uses memory receipts; simulated
success never asserts actual delivery or execution. Expected CLI fields are
`coin_receipt`, `cancel_receipt`, `handoff_receipt` = `succeeded`, selector source
`template`, and true immutable replay, evidence, privacy and blocked-guard checks.

The single runtime starts with explicitly injected adapters. Tests cover immutable
POST/current GET (`effects`, `system_events`), durable evidence resolution,
`care_contact`, explicit `ledger_pending=False`, and strict gateway capability
`atomic_final_validation is True`. Internal handoff retry requires
`care_handoff_retry`; it preserves the original envelope and terminal session.
Cancellation requires explicit confirmed consent and the exact prompt
`reply_to`/`message_id`; ordinary acceptance without that binding cannot execute it.

The v1 harness adds cancellation lifecycle storage, but cannot migrate the former
synchronous prototype schema. Legacy embedded confirmations without durable
authorization evidence fail closed. Contact sessions lacking the bound open
fingerprint also need an explicit migration decision. Use fresh run state;
retention and migration of existing production state require separate review.

## Local release-fed integration

`acceptance_huy/test_e2e_flow.py`, `test_e2e_proof.py` and
`test_integration_tick.py` verify `DemoFlow` against existing release inputs and
isolated runtime SQLite. A3, A2 and A1 run in order. Actual local effects include
web-inbox/contact rows, staff handoffs, cancellation review requests and a coin
ledger committed by the real SQLite executor. A staff review in these tests is
explicit simulated authorization, not a source finding about responsibility or
force majeure. Release databases remain read-only. None of these local effects
asserts external provider delivery or commercial payout.

Both local gateways attest `atomic_final_validation is True`. Financial dispatch
holds the care write lock through durable provenance validation and executor
acceptance. The executor owns the platform transaction and checks current server
permission, guard, trusted evidence, eligibility, immutable amounts and global
once-per-order grants. Contact dispatch rechecks durable identity/run/order/key,
current context and daily contact limits under both write locks without an await
before inbox acceptance. Handoff remains available when proactive controls close.

The guarantee is scoped to one event-loop thread, the care OS ownership lock and
a single trusted runtime writer. It is not a distributed transaction and does not
authorize arbitrary concurrent platform processes. Such a deployment needs an
executor-owned provenance acceptance seam and fresh review before attestation.

New regression tests reject changed final delivery authority or stale context,
require explicit bound cancellation consent at both provenance boundaries, and
prove a competing SQLite writer cannot change care authority during financial
acceptance. All ten fail against the pre-integration production modules loaded
in memory and pass against the implemented modules.

Presenter HTTP authentication is covered separately. Customer CareApi HTTP routes,
customer network authentication, external contact providers and web voice/session
negotiation are not established by the local integration. Required adapter inputs
and proposed route mapping remain in README.

## Verified integration revision, 2026-10-31

The user-approved main integration changes pass these fresh checks:

- Touched release-fed flow/tick and presenter authentication tests: **30 passed**.
- Proof, coin, cancellation and dispatch regression tests: **115 passed**.
- Required combined acceptance and care suite: **1174 passed**.
- Root acceptance suite through `guardrails.py --all --tests`: **684 passed**;
  guardrails passed. Contract/care imports, standalone demo and diff checks pass.

The ten new authority/consent/concurrency tests also fail against the previous
gateway implementations loaded in memory, proving they detect the repaired gaps.
Implementation verification is complete for the local scope above. Independent
controller review precedes push; production deployment approval is separate.
