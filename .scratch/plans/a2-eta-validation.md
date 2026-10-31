# Implementation plan: A2 offline ETA validation

1. Add isolated fixtures and hand-calculated scoring tests before implementation.
2. Implement immutable forecast/outcome records and pure scoring in A2.
3. Add snapshot extraction, fixed-window runner, source fingerprint and CLI.
4. Verify all forecasts precede outcome reads with a traced real reader and
   fixtures whose future changes must not alter prediction fingerprints.
5. Run regression and release evaluation at 12:00 VN on 25/26/27 October,
   each followed for 72 hours; record limitations and integration instructions.
6. Fetch team updates, commit and push the verified unit. Never modify other
   owners' production code, shared dependencies, or existing acceptance tests.

## Verification completed

- `python -m pytest -q`: 225 passed, including 27 new validation cases.
- Equal 72-hour release windows for 25/26/27 October completed; source hash
  unchanged, 8,497 forecast observations and 44 carrier/service/stage groups.
- A temporary copy under `runs/` changed the midnight comparison from `>=` to
  `>` without changing tests. The boundary tests produced one assertion failure
  and one pass as expected; the production checkout was not mutated.
- Independent platform acceptance scenarios are prepared in
  `../specs/a2-platform-acceptance.md`; runnable integration still needs Huy's APIs.
