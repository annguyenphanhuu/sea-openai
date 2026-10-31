# An Nguyen acceptance tests

Initial regression tests: An Nguyen. Cross-test ownership after handoff: Truc. Run `python -m pytest -q acceptance_an_nguyen` from the root.

- `test_assessment.py`: status priority, probability boundaries, Vietnam midnight,
  delivered-order lateness, ingestion visibility, structured ETA/fault, conflicting
  facts, feed health, invalid inputs, untrusted text and JSON output.
- `test_questions.py`: deterministic review requests, retry deduplication,
  supervisor answers, caller rollback, runtime DB path restrictions and no writes
  to financial, contact or guard state.
- `test_release_adapter.py`: read-only source projection, future ingestion and
  cancellation masking, scan order/retries, attempt attribution, driver claims,
  terminal exceptions, derived-feed dependencies and midnight forecasting.
- `test_forecast.py`: censored observations, conditional remaining-time estimates,
  insufficient samples, unsupported tails and deterministic cohort identifiers.

Fixtures are isolated test data; persistence uses the shared schema in memory.
Source-reader tests use minimal SQLite fixtures in pytest temporary directories.
Tests never read or modify release databases and add no dependencies.
