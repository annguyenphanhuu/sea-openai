# A2 verification plan

Specification: [a2-verification.md](../specs/a2-verification.md).

1. Integrate latest main and establish the full-suite baseline.
2. Read the A2 modules and existing tests; identify uncovered boundary behavior.
3. Add independent integration and regression cases in `acceptance_huy/`.
4. Reproduce defects, fix only A2-owned implementation, and preserve test evidence.
5. Replay several release ticks and repeat a tick/restart with hash verification;
   run fixed-window offline forecast validation independently.
6. Run focused tests and full regression; use targeted negative controls on
   temporary module copies to confirm important assertions detect regressions.
7. Write findings and limitations, then commit/push the verified feature branch.

Branch: `nguyen/a2-verification`, based on `an-nguyen` after merging main
`3f2e904`. The pre-existing local `nguyen` scaffold ref was renamed to
`archive/nguyen-scaffold` (same commit, no deletion) to allow the required prefix.
