# Plan Review

**Status:** Issues Found

Reviewed the full 602-line implementation plan against the approved design and current decision log, using the Superpowers plan-document reviewer checklist. Also inspected the existing A2 replay/adapter/progress/question-store interfaces, Action contract, and release manifest/documentation. This is a document review; no implementation or tests were run.

**Issues:**

- **Task 9, Step 3 — `issue-kind` retry can change the request it is retrying.** The adapter always prepares current evidence and then submits a stable action key. Task 6 includes `evidence_ref` in the semantic hash, and the spec requires an existing receipt to replay unchanged even after review withdrawal. After a successful grant with a lost response, NEXT or a new review can produce a different evidence reference; rerunning the same CLI command then conflicts instead of recovering the original receipt. Reusing unchanged evidence by content hash alone does not cover those changes. Specify how the adapter retrieves and reuses the original server-bound Action/evidence for an existing key **before** preparing new evidence, with principal/order/kind and original contact/message bindings checked. Keep changed command semantics conflicting. Add an actual CLI restart/retry test: issue coins, lose the response, withdraw the review or advance NEXT, rerun the same command/key, and assert the original receipt/effect ID with one ledger row; a genuinely new voucher request must still check current review authority. This needs a bounded Huy-owned recovery helper or documented persistence path, not a weakened executor hash or bypass of live checks for new requests.

**Recommendations (advisory, do not block approval):**

- Tasks 3 and 5 already require shared key-namespace checks, while the named `lookup_key` helper is introduced in Task 6. Assign the common collision primitive to an earlier task/module, or explicitly consolidate the earlier checks in Task 6, to avoid several subtly different implementations.
- Preserve the existing distinctions during implementation: latest review head versus immutable receipt replay, independent per-kind history/local ledgers, current A3 versus last-good A2, production canonical sources versus fixture-only root patching, and business-assertion mutation failures versus harness errors. These are explicitly covered by the plan. Ownership boundaries and the pending real-A1/staff-proof dependency are also accurately stated; no additional business decision is needed for this review finding.
