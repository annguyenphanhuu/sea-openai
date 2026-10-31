# Bounded SQLite money executor — 2026-10-31

## Controller review corrections

The independent reviewer reproduced receipt seller-scope and contact-lifetime gaps. Controller added failing regressions before fixes: successful receipt recovery now recomputes the original semantic request hash with the current full ServerContext (including seller/customer), without depending on mutable original eligibility evidence. New grants enforce message creation no later than closed_at, when present, and reject a future close timestamp. The immutable-scope correction supersedes the original worker limitation about get_receipt depending on evidence below. Controller logs are `.scratch/runs/lunch/review-red.log`, `review-green.log`, `contact-red.log` and final suite logs. Worker manifests remain historical evidence of the originally reviewed version.

## Scope and evidence

Implemented in the private lunch-money worktree under the controller's authorized lunch task. Repository AGENTS, state.py, dto.py, migration 001, sysguard.py, contracts/types.py, contracts/schema_state.sql, contracts/params.py and the current demo/lunch decisions were read. No contract, migration, source database, UI, transport, dependency or Git mutation was made by this worker. No additional old nine-task dependencies were implemented.

External documentation research was not completed: an attempted official SQLite/Python documentation tool invocation was aborted before dispatch. The implementation conservatively reuses the already tested standard-library SQLite `state.immediate` (`BEGIN IMMEDIATE`, rollback on error), `current_clock`, `lookup_key` and canonical serialization; it introduces no persistence algorithm or remote backend. This limitation is explicit rather than a claim of reviewed external research.

## Stable interface

```python
execute_action(action: contracts.Action, *, store: StateStore,
               context: ServerContext) -> ExecutionResult
get_receipt(key: str, *, store: StateStore,
            context: ServerContext) -> ExecutionResult | None
SqliteStateStore(conn: sqlite3.Connection, *,
                evidence_producers: frozenset[str] = frozenset(),
                message_recorders: frozenset[str] = frozenset(),
                request_rule_versions: frozenset[str] = frozenset())
```

`StateStore` is a protocol; `SqliteStateStore` is its sole concrete implementation. `.conn` is the existing bootstrapped connection, whose lifecycle remains caller-owned. Startup configuration and ServerContext must come from trusted server code. They are not client JSON authority or a sandbox against malicious Python with DB access. Empty producer/rule allowlists block all grants.

`Action.evidence_ref` is the raw existing execution_evidence.evidence_id. No URI or automatic reference resolution is added. The parent adapter must resolve an existing server-authorized evidence reference. It must not create eligibility from an A1 text/proposal.

## Persisted evidence payload convention

The existing execution_evidence row has policy_version `huy-demo-v1`, assessment_at and visible_at equal to the current simulation clock, SHA256 of the exact UTF-8 payload_json text, and created_by in the explicitly configured producer allowlist. No new table or migration is necessary. Its payload is:

```json
{
  "schema_version": 1,
  "run_id": "the existing run_metadata.run_id",
  "source_identity": {"the same fields and values": "as run_metadata.source_identity_json"},
  "order": {
    "order_id": "persisted order ID",
    "customer_id": "authenticated owner",
    "seller_id": "persisted seller",
    "guaranteed_date": "2026-10-29",
    "items_value_vnd": 239999,
    "delivered_at": null
  },
  "responsibility": "carrier",
  "force_majeure": "absent",
  "history": {"coins": "not_granted", "voucher": "not_granted"}
}
```

`source_identity` is the actual SourceIdentity serialization (core_sha256, ops_sha256, coverage_start, coverage_end), not the illustrative placeholder above. The tests contain an exact working fixture. Responsibility must resolve to carrier/platform and force_majeure to absent; customer/unknown/present block. Per-kind history must be resolved to not_granted; known voucher history does not consume coins. Unknown historical kinds must be resolved by the authoritative producer, never silently mapped into clearance.

`delivered_at`, when present, is an aware ISO timestamp no later than now. Lateness uses the delivery's Vietnam calendar date; otherwise it uses the simulation clock's Vietnam date. A delivery on the promised day cannot become late merely because the demo advances later.

The row's contact/message bindings must match the order and authenticated customer. contact_log requires A1 initiation, chat channel, active/completed status, opened_at and nonempty provider_session_id as server-recorded successful-delivery evidence. requested_at <= opened_at <= message.created_at <= simulation now. customer_messages requires text origin, nonempty body, persisted late_compensation request_code, and configured recorded_by/request_rule_version. These markers must be minted by the actual trusted transport and deterministic request rule; a client cannot supply them as permission.

## Financial behavior

New grants require authenticated source+capability (`a1`/actions:coins or `rule`/actions:voucher), current ownership, canonical key, literal server amount recomputation, complete persisted evidence, and the actual sysguard.proactive_allowed check. The guard uses the existing strict greater-than-90-minute heartbeat and greater-than-30-minute feed expiry. Host wall time appears only in denial audit.

Coins reuse the pure contract quote: 5%, floor to 1,000, minimum 10,000, maximum 1,000,000, None/0 => 10,000. Voucher face value is exactly 10,000. Canonical keys are xu:{order_id} and voucher:{order_id}; each ledger independently enforces one grant/order. No provider, wallet credit, voucher redemption, TTL or minimum spend is introduced.

One BEGIN IMMEDIATE transaction contains outbox success, the selected ledger and action_receipts. Failures roll back all three. Denials write incidents only and do not reserve any key. A corrected authoritative evidence snapshot may therefore retry the same denied key. Successful retries return the original effect and receipt, with replayed=True, even when the guard or eligibility subsequently closes. The semantic hash includes authenticated principal/customer/seller and every Action field except transport action_id/requested_at. Changed financial semantics or principal conflicts. Legacy/incomplete receipts cannot become success.

get_receipt also requires original principal/source/customer and current capability. It reads the retained original execution_evidence payload to recover ownership; missing/corrupt retained evidence fails closed. execute_action retry itself does not reread changed eligibility evidence. Unsupported actions always return blocked/policy_not_configured; cancellation never reports fake success.

## Claim limits and missing producers

This task provides an executor, not an authoritative source-fact/evidence importer, human review lifecycle, customer auth service, delivery provider, or A1 message transport. No real demo order was granted by this worker. The configured trusted producer must derive actual order/customer/value/delivery/fault/force-majeure/history facts from real persisted authorized runtime evidence at the current cutoff, and resolve any applicable human review and material changes before creating its snapshot. The trusted message recorder must actually attest delivered A1 contact and the real customer TEXT request. Missing producers/proofs remain blocked. Fixture facts are tests only and must never become a demo seeder or fallback clearance.

## Verification and self-review

- RED before implementation: red.txt records ModuleNotFoundError for platform_huy.money.
- Initial implementation test fixture had an incorrect SQL placeholder count; initial-implementation.txt retains that failure. It was corrected in the test fixture before GREEN.
- green.txt and restored-green.txt: 66 real SQLite tests passed, including literal amounts, independent benefits/history, missing/voice/spoofed provenance, ownership/source/capabilities, delivery/calendar semantics, heartbeat/feed boundaries, denied-then-verified retry and successful replay.
- Two actual concurrent SQLite connections produce one ledger/outbox/receipt and one replay. A real SQLite receipt-rejection trigger proves rollback after preceding outbox/ledger writes.
- mutation-guard-bypass.txt: the actual money.py guard conditional was temporarily replaced with False. All three kill/resume/sticky-block tests failed because an incorrect success occurred. The original conditional was restored; all 66 tests passed again. No mocked executor or skipped test was used.
- Full repository test outcomes are preserved in full-pytest*.txt. The first run had 583 passed/one existing worktree-helper test failure caused solely by denied access to the default user Git ignore path. A command-local XDG_CONFIG_HOME rerun checks the suite without changing source or test expectations.
- Self-review checked SQL parameter/column counts, transaction and receipt ordering, canonical keys and namespace collisions, amount replay binding, current source/heartbeat invocation, independent ledgers, original-principal replay, no unconfigured policy effects, and empty trusted-configuration defaults. It found no unresolved source change necessary; independent controller review remains required.

Source checksums and exact logs are recorded in .scratch/runs/lunch-money/manifest.txt. Source files are platform_huy/money.py, platform_huy/state_store.py and acceptance_huy/test_lunch_money.py only. This research file and its assigned run logs are the only additional worker outputs.
