# A2 seller LSR protection implementation

1. Fetch origin and create `nguyen/seller-lsr-protection`; merge `origin/main`.
2. Project and validate the optional static seller preparation policy. Share the
   earliest visible handover selection between adapter and handoff export.
3. Add trusted source facts and deterministic seller protection to assessment;
   expose additive payload fields without editing shared contracts.
4. Add An-owned acceptance regressions, document the interface, and refresh the
   existing sample from its same read-only source snapshot and order IDs.
5. Run focused and full pytest, contract import, source hash and diff checks.
6. Fetch and integrate main again, commit the verified unit, and push the feature
   branch. Do not merge main or change another owner's UI/API.

## Requested main integration

The user subsequently requested updating from current main and merging the
feature into main after verification. Integrate `origin/main`, verify the actual
A3/A2/A1 demo and A1 suite, repair necessary compatibility issues, then push the
feature and merge/push main without force.

New main persists `assessment_payload` and reloads shared `OrderAssessment`
instances. Preserve the additive LSR payload while limiting reconstruction to
the dataclass fields; test restart with both old and extended checkpoint shapes.
Update An-owned integration expectations for evidence-backed carrier attribution,
retaining missing-review money denial and all grant/cancellation assertions.
Adapt the one outdated A1 test's direct SQLite inspection to `runtime.store`,
as used by the existing harness tests, without changing its safety assertions.
