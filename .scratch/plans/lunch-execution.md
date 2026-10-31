# Lunch execution ledger — 2026-10-31

Authority: latest user message and [decisions-lunch.md](decisions-lunch.md). This is not the older nine-task plan. Work remains on Huy; no pushes or main merges during this run.

## Task boundaries and preflight

| Work | Producer / consumer | Ruling |
| --- | --- | --- |
| Fetch and baseline | Both remotes -> Huy | Complete: origin/main and upstream/main already included; 518 tests passed |
| Money | SQLite runtime/evidence -> ExecutionResult | Only money.py executes financial effects; StateStore interface, SqliteStateStore only |
| Deploy | HF download -> SEA_RELEASE_DIR -> serve_ui | Independent worktree; no source data or secrets in image; missing dataset configuration fails closed |
| Gateway | Persisted A1 proposal -> money.execute_action -> real receipt | Starts after money passes; no mock executor or fabricated financial clearance |
| Review | Worker changes -> controller integration | Inspect code and fresh independent review; save RED/GREEN/mutation logs |

Money and deploy own disjoint files. Deploy alone edits serve_ui/a3_demo minimally for env/host. Gateway owns platform_huy/effect_gateway.py and its own test file. All contracts, A2 and care_truc source remain unchanged. Workers never perform Git mutations.

## Gateway preparation

Use actual care_truc EffectGateway protocol. Scope adapter to server-configured customer principal and ServerContext, the actual A1 SQLite store, and an explicit server mapping from A1 evidence reference to an existing platform evidence row. Bind to the persisted A1 proposal/request/session before dispatch. Compare customer text/contact/order with platform provenance; no new proof of fault, force majeure or historical benefit clearance is minted by the adapter.

Canonicalize the known A1 legacy `run:coins:order` key to `xu:order` internally; preserve A1 key, effect ID and payload hash in its returned Receipt. Voucher keys stay independent. Failed entitlement decisions do not reserve platform financial keys. Current A1 terminal-rejection behavior may still require Truc changes; report this boundary, never claim fully integrated retry UX.

Only action_request for configured monetary kinds is supported by this gateway. Contact, handoff, cancellation and provider delivery must not receive fake success. Successful lookup reads the persisted platform receipt. Apply local SQLite deadlines without network calls, and do not keep transactions across await.

## Evidence locations

- Baseline: `.scratch/runs/lunch/baseline/pytest.log`.
- Money worker: `.scratch/runs/lunch-money/` in worker, copied to controller after completion.
- Deploy worker: `.scratch/runs/lunch-deploy/` in worker, copied to controller after completion.
- Gateway and integration: `.scratch/runs/lunch/`.
- Final handover: `.scratch/plans/handover-1300.md`.

## Completed

Money commit `6dd2652`, deployment commit `9309df5`, gateway commit `b4ee32d` on local Huy only. Independent review found and verified fixes for four groups: semantic receipt binding, seller/customer recovery scope, contact lifetime, and source/runtime aliasing. Every finding has actual failing regression output followed by GREEN. Final default suite: 618 passed; separate A1 suite: 96 passed. Independent lunch review: 100 passed.

Actual Python 3.11.17 Space launcher passed offline HTTP/NEXT against immutable release. Real-release executor smoke rejected missing customer evidence with live A3 and no money writes. No Docker engine/private HF deployment or live care transport was claimed. Final handover records remaining integration work. Stop after documentation commit; no push/main mutation.
