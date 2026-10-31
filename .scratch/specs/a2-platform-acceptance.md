# Independent platform acceptance cases for An Nguyen

Prepared from D1-D5 and `docs/team_plan.md`, with the interface proposals in
`.scratch/specs/2026-10-31-huy-platform-design.md` as integration context
(Huy revision `0acf3ef`, reviewed on 2026-10-31).
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
| A3 completed and committed; A2 fails before publication | Keep actual A3 heartbeat/health; roll back the entire A2 publication | assessments, questions, progress, watermark and checkpoint remain last-good; current attempt failed and proactive denied |
| A3 fails before completing | No fabricated success heartbeat or current health | durable failure when state is writable; current gate denies even if an older heartbeat is recent |
| First A3 completes but first A2 publication fails | Current guard shows actual A3; latest_tick remains null | no invented assessment/checkpoint; proactive denied |
| NEXT races with NEXT or is retried after response loss | Advance simulated time by exactly 30 minutes once | stable command receipt, clock version and attempt identity; A2 failure does not rewind clock |
| Retry failed A2 after completed A3 at the same tick | Reuse completed A3, rebuild tracker from committed progress | no duplicate heartbeat; no extra stationary interval or partial question batch |
| NEXT skips a failed tick | Reset stationary intervals for the gap | no fabricated watch count for an uncommitted interval |
| Read view after A3 completes at T+30 but A2 fails | Historical assessment stays at T and is marked non-current | current guard is T+30; historical feed health is not relabeled as current |
| Crash after commit, before response; retry same tick | Return committed result | no extra stationary interval or duplicate question |
| Two concurrent tick controllers | At most one committed tick result | separate connections to one runtime SQLite file |
| Coins quote for 239,999 VND | 11,000 xu | quote is not eligibility or an execution permission |
| Claimed source a1 but authenticated principal A2/A3/client | Reject money execution | ledger/effect count unchanged |
| Same grant retried; second key for same order | At most one grant | both persisted ledger and observable effect count |
| Same idempotency key with changed order/amount/evidence | No changed effect and no overwrite | exact conflict response needs finalized public interface |
| Voice request, customer-opened chat, or one day late | No coins grant | check each invalid precondition in isolation |
| Eligible coins and voucher requests for the same order | At most one grant per kind; one kind does not consume the other | separate runtime ledgers and receipts; coins source a1, voucher source rule |
| Eligibility review withdrawn after evidence preparation | Old review cannot authorize a later grant | execution checks current review head in the effect transaction; no fallback to an older clearance |
| Published order list read after a later source update | Dates, evidence and assessment retain one published cutoff | persist the A2 metadata payload or provide an equivalent version-bound projection; do not join live source dates |

The two-stage A3/A2 transaction expectations above supersede the earlier matrix's
single rollback expectation. They follow the latest proposed platform design;
they are not assertions that those platform APIs or migrations already exist.
Coins/voucher and review cases follow Huy's recorded demo decisions and still
require real implementation before executable cross-owner acceptance can pass.

Do not invent missing interfaces in test helpers. Huy's updated spec now proposes
run identity, capabilities, typed errors and cancellation/review APIs, but the
public implementations and migrations are absent. Bind tests to those real seams
when delivered; confirm source-health/history mapping and version-bound order
metadata with the owners. Use isolated
fixtures and memory/temporary SQLite. Release DB verification is read-only with
source hashes; no truth/heldout labels and no world-data generation.

When Huy supplies implementation: bind these cases to real APIs, keep tests
unchanged during implementation fixes, and add selected negative controls in
temporary copies. Do not substitute mock success responses for missing modules.
