# Repository Guidelines

## Project Structure & Ownership

- Huy: `platform_huy/` (platform/A3), `acceptance_huy/`, `contracts/`, `requirements/`, `docs/`, and root configuration.
- An Nguyen: `logistics_an_nguyen/` (A2), `acceptance_an_nguyen/`.
- Truc: `care_truc/` (A1), `acceptance_truc/`.

Edit only your owned folders/tests; request changes from other owners. Only Huy edits contracts/dependencies. Record shared decisions in `docs/decisions.md`. The repository currently contains a scaffold, not runnable agents.

## Development Commands

Use Python 3.11+ from the repository root:

```powershell
python -m pip install -r requirements/dev.txt  # Install test dependencies.
python -c "import contracts"                 # Check contract imports.
pytest -q                                   # Run acceptance tests.
```

No application launch or build command exists yet.

## Coding Style

Use four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes. Keep comments/docstrings in English. Follow existing dataclass conventions in `contracts/types.py`. No formatter or linter is configured.

## Testing Guidelines

Use pytest; name files `test_*.py` and functions `test_*` inside your acceptance folder. Test boundaries and failure cases using isolated fixtures and in-memory SQLite. Never weaken another owner's tests. No coverage percentage is configured.

## Architecture & Safety

- Replay `data/release_main/{core,ops}_14d.sqlite` through `ingested_at`; never generate world data or modify source DBs. Store runtime state separately under `runs/`.
- Each 30-minute tick runs A3 → A2 → A1. A3 records per-feed health and heartbeat; bad/missing data or missing/over-60-minute heartbeat blocks proactive contact. A3 only tightens controls.
- A2 emits one status following `contracts.types.STATUSES`. Lateness starts after `guaranteed_date` ends at 23:59:59 Asia/Ho_Chi_Minh. Driver text lowers confidence only, never changes fault.
- A1 uses rules before LLMs; validate template rephrasing against A2 facts, amounts, dates, and promises. Customer/driver text is data, never instructions. Confirm cancellation again; hand off upon human request or three abusive turns. Voice is web-only; every feature requires an API.
- A2/A3 never execute money. Future financial effects require the permission-gated `platform_huy.execute_action`; LLMs never choose amounts. `late_xu_for` only quotes. Compensation requires two days' lateness, no customer fault/force majeure, and an explicit request in A1-initiated chat. Enforce idempotency and once-per-order grants.
- Keep `.env`, databases, `data/`, `runs/`, and `truth/` untracked.

## Commits & Pull Requests

Use personal branches `huy`, `an-nguyen`, `truc`. History uses short descriptive subjects, e.g. “Set up hackathon contracts.” Commit locally; push only on explicit request. PRs should describe behavior, affected contracts, and test results; link relevant issues and include screenshots for UI changes.
