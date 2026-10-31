# Independent platform acceptance cases for An Nguyen

Prepared from D1-D5 and `docs/team_plan.md`, with the interface proposals in
`docs/superpowers/specs/2026-10-31-huy-platform-design.md` as integration context.
Owner: An Nguyen. Implementation tests belong in `acceptance_huy/`; platform
implementation belongs to Huy. These are cases to bind to real public APIs once
available, not passing tests or claims that the platform exists.

For each rejection case, keep all other gates valid. Use hand-authored expected
values rather than deriving expected outcomes from the implementation under test.

| Case | Independent expected result | Observe |
| --- | --- | --- |
| Source age 29:59, 30:00, 30:00.000001 | First two usable; third stale | source timestamp preserved; fresh ingestion/check time cannot rescue old source |
| Missing heartbeat; age 59:59, 60:00, 60:00.000001 | Missing and last blocked; middle two pass heartbeat age only | whole gate also requires valid feed/control |
| Future heartbeat or assessment | Cannot authorize contact now | no contact/effect; reason identifies invalid temporal context |
| Twelve scans share ingestion time; interrupted replay | All twelve visible once after retry | checkpoint covers completed timestamp group, no skipped evidence |
| Event is old; ingestion is after tick | Hidden before ingestion, visible afterwards | source projection and resulting evidence |
| Visible corrupt scan alongside newer valid scan | New row cannot conceal corrupt row | affected feed blocked; incidents/quarantine follow approved platform policy |
| A3 tightens control; feed later recovers | A3 does not reopen control | stored control remains restrictive |
| Contact queued while healthy; dispatched after source age exceeds 30 min | Dispatch gate blocks | enqueue-time approval is not reused as send authorization |
| Failure after health write but before checkpoint | No partial tick commit | health, progress, questions, assessment and checkpoint rollback together |
| Crash after commit, before response; retry same tick | Return committed result | no extra stationary interval or duplicate question |
| Two concurrent tick controllers | At most one committed tick result | separate connections to one runtime SQLite file |
| Coins quote for 239,999 VND | 11,000 xu | quote is not eligibility or an execution permission |
| Claimed source a1 but authenticated principal A2/A3/client | Reject money execution | ledger/effect count unchanged |
| Same grant retried; second key for same order | At most one grant | both persisted ledger and observable effect count |
| Same idempotency key with changed order/amount/evidence | No changed effect and no overwrite | exact conflict response needs finalized public interface |
| Voice request, customer-opened chat, or one day late | No coins grant | check each invalid precondition in isolation |

Pending interface/policy decisions must not be invented in test helpers:
health source mapping, control key/auth, run identity, exact errors, cancellation
confirmation/reviewer API and historical compensation-kind mapping. Use isolated
fixtures and memory/temporary SQLite. Release DB verification is read-only with
source hashes; no truth/heldout labels and no world-data generation.

When Huy supplies implementation: bind these cases to real APIs, keep tests
unchanged during implementation fixes, and add selected negative controls in
temporary copies. Do not substitute mock success responses for missing modules.
