# Harness verification and boundaries

The runtime was implemented against the 2026-10-31 care harness and business
specifications. Each implementation unit was tested and pushed separately to
`truc/care-harness`. Run the commands in README from the repository root.

The test environment uses real SQLite transactions and Windows OS process locks,
with fixed authenticated context, fake operational time, scripted platform
receipts/gates and optional phrase selectors. No release database was changed.
These results do not establish live HTTP, provider, A3/A2 or executor integration.

## Independent final review

A fresh read-only reviewer examined commit `53d1395` and found one critical and
eight important issues. They were addressed in one fix pass with regression tests
in `tests/test_review_regressions.py`:

| Finding | Verified behavior |
| --- | --- |
| Shutdown released ownership during external drain | Every active harness/dispatcher operation is tracked before storage/lock release |
| Text confirmation used customer request ID | Confirmation binds to public assistant response event ID |
| Interrupted opening could not resume | Typed open_contact payload recovers with the original task and processing budget, zero customer turns |
| Blocked effects starved later work | Non-actionable rows are skipped and scans advance fairly |
| Repeating blocked handoff failed revision checks | New explicit human request reuses the unsent handoff key/envelope |
| D4 used unbound order-level contact success | Current session requires its own authoritative successful contact receipt |
| Why response omitted supported reasons | Approved templates map structured evidence and reason codes; unknown reasons remain neutral |
| Handoff lost the conversation/action context | Summary preserves labelled customer statements, facts, pending requests and known action outcomes |
| Hook failures disappeared | Sanitized hook phase outcomes appear in staff trace and observer failures degrade health without undoing receipts |

The same fix pass verified that contact envelopes contain a validated opening
message and that the persisted internal opening payload is staff-only, rather
than being displayed as a customer message.

Deferred minor: a conflicting repeat of an older, already superseded receipt
revision is ignored rather than reported as an adapter inconsistency. The latest
authoritative state is preserved. Conflicts at the current revision are rejected.

The reviewer did not judge live authentication correctness, atomic external
permission enforcement, provider cancellation compliance, executor once-per-order
guarantees or live HTTP/provider integration. Those require actual platform
adapters and remain separate integration checks; test fixtures do not prove them.

## Execution decisions

- Updated ownership on main gives Truc HTTP/auth; this implementation keeps the
  requested in-process scope. Risk: later adapter handoff ownership needs alignment.
- Store request references use generated internal IDs, scoped separately from
  client IDs. Risk: an extra internal lookup, avoiding cross-session collisions.
- Canonical JSON captures nested contract evidence before callbacks can change
  it. Risk: serialization overhead, without widening business authority.
- Initial full guardrails failed on pre-existing tracked `.scratch/runs` files.
  They were preserved while this branch used staged checks plus both suites.
  Subsequent main updates removed those artifacts and full guardrails passed.
  Risk at that stage was blocked repository CI; no longer outstanding.

Execution record correction: Task 4 RED tests were inadvertently included in the
Task 3 commit by an overlapping bookkeeping command. They were observed failing
before their implementation; subsequent commit/check operations were serialized.

Final verification after updating origin/main: **96 harness tests and 518 acceptance tests passed**. `import contracts`, `git diff --check` and `python scripts/guardrails.py --all --tests` passed. Nine review regressions exercise the fixes (reason rendering and handoff context share one scenario). No post-fix independent re-review was requested; regression tests and the full suites verify the single fix pass.
