# V4 existing-code basis

- `DemoFlow._request('chat-say')` already awaits Care `drain_pending`; its reply was
  still the original pre-dispatch TurnResult. The projection now follows only that
  response's effect IDs, its authoritative successful Care receipt, and the matching
  successful local action receipt/outbox/ledger. Amount comes from `ledger_new`.
- Care `is_cancel_confirmation` already recognizes chắc/ok/đồng ý. The HTTP route
  supplies the current session pending `reply_to` only for that explicit text, and
  restores the original persisted binding on an idempotent request retry.
- Existing denial codes remain audited. Killed benefit requests project the exact
  requested pause wording; ordinary information requests still use Care rendering.
- Evidence-pending want_more receives a dedicated approved phrase. The route's
  deterministic projection inserts assessment `late_days`; the Care renderer and
  financial eligibility decisions remain unchanged. Handoff completion wording is
  projected only after actual successful handoff dispatch.
- Reset reserves against NEXT, initializes a UUID-separated runtime before closing
  the old runtime, keeps the selector, preserves old databases, and requires the
  existing presenter capability even when other loopback APIs allow no key.
- Sources: existing local Care/runtime APIs and real read-only release databases.
  No external research, generated source data, executor mocks or skips are used.

## Verification evidence

- Initial runs hit a full E: disk during the real tick snapshot write. The
  controller freed old completed test fixtures; no product fix was made for that.
- `red-clean.txt`: baseline HEAD, 9 failures. The initial cancellation setup text
  was corrected to an existing supported cancellation request; `red-confirm.txt`
  independently proves all three requested typed affirmatives fail to queue a
  cancellation against baseline HEAD (3 failures).
- `green-clean.txt`: all original 9 V4 cases pass against the implementation.
- `extra-final.txt`: 3 pass, covering a valid non-None selector retained by reset,
  no/stale confirmation prompt, and reset initialization failure rollback.
- `reset-next.txt`: reset followed by a real NEXT passes, with 30 fresh contacts
  and an empty ledger. Logs are under `.scratch/runs/route-v4/`.
- The full acceptance/Care suite uses an isolated C: temporary directory to avoid
  filling E: again; see `acceptance-care.txt` for its actual result.
