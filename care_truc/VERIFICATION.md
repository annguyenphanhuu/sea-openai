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

No HTTP server, network authentication, voice provider/session negotiation or
replay-fed A2/A3/executor delivery is demonstrated. Huy's current
`SqliteEffectGateway` does not advertise atomic final validation, so integrated
delivery is blocked until the owner implements and declares that guarantee.
Separate gate checking cannot establish it. Required handoff inputs and proposed
route mapping are in README; all route decisions remain subject to platform review.
