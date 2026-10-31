# A2 offline ETA validation

Scope: An Nguyen's `logistics_an_nguyen/`, tests in `acceptance_huy/` and this
task's scratch files. Do not change contracts, dependencies, A1/A3 or their tests.

- CLI accepts explicit aware ticks, a positive integer follow-up in hours and a
  caller-declared observed-through timestamp. Reject incomplete windows rather
  than silently shorten a later tick's follow-up.
- Freeze every prediction from its as-of source snapshot before reading outcome
  snapshots. Outcome cutoff for each tick is exactly tick + follow-up.
- Read source SQLite in read-only mode, compare SHA-256 before/after, and write
  only aggregate reports under repository `runs/`. Never read truth/heldout or
  create healthy A3 snapshots. This measures candidate forecasts, not authority
  to contact customers. Leave model parameters and production assessments alone.
- Include active orders without forecasts in coverage. Score ETA only for
  visible deliveries after prediction and within follow-up. Report no outcome,
  terminal-before-delivery and already-delivered-at-prediction separately.
- Score lateness probability only for forecasts made before the guarantee ends
  and whose guarantee ends within follow-up. A delivered-on-time order whose
  deadline has not matured is also excluded, avoiding selective early inclusion.
- Do not infer a negative or positive label from an absent delivery. Report
  complete-case Brier alongside an always-on-time baseline and worst/best-case
  Brier bounds for unresolved nonterminal outcomes. Bounds are descriptive,
  not censoring-adjusted estimates or confidence intervals.
- Report the full cohort, each tick, and carrier/service/stage groups; keep
  small cohorts and missing metrics explicit. No model tuning or auto-approval.
- A repeated order across ticks is a repeated observation. Report distinct
  order counts and warn against treating observations as independent samples.

Acceptance: hand-calculated metrics, VN midnight boundary, equal windows,
unobserved/terminal cases, delayed ingestion, as-of isolation, read-only source,
input validation, safe output destination, deterministic replay and regression.
