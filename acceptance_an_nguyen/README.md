# An Nguyen acceptance tests

Owner: An Nguyen. Run `python -m pytest -q acceptance_an_nguyen` from the root.

- `test_assessment.py`: status priority, probability boundaries, Vietnam midnight,
  delivered-order lateness, ingestion visibility, structured ETA/fault, conflicting
  facts, feed health, invalid inputs, untrusted text and JSON output.
- `test_questions.py`: deterministic review requests, retry deduplication,
  supervisor answers, caller rollback, runtime DB path restrictions and no writes
  to financial, contact or guard state.

Fixtures are isolated test data; persistence uses the shared schema in memory.
Tests never read or modify release databases and add no dependencies.
