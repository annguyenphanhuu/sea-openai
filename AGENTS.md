# Repository Guidelines

## Project Structure & Ownership

- Huy: `platform_huy/` (data validation/A3 and shared execution gate, except UI prototype), `acceptance_truc/`, `contracts/`, `requirements/`, `docs/`, and root configuration.
- An Nguyen: `logistics_an_nguyen/` (A2), `acceptance_huy/`.
- Truc: `care_truc/` (A1, UI, HTTP APIs/auth), existing `platform_huy/ui_prototype/`, and `acceptance_an_nguyen/`.

Acceptance folders name the person being tested. Follow `docs/team_plan.md`; only Huy edits contracts/dependencies. Request changes from other owners. A2 supplies assessed-order lists to Truc; Huy supplies source validation and feed trust. A2 and an illustrative UI prototype exist; the full pipeline is not implemented.

## Development Commands

Use Python 3.11+ from the repository root:

```powershell
python -m pip install -r requirements/dev.txt  # Install test dependencies.
python -c "import contracts"                 # Check contract imports.
pytest -q                                   # Run acceptance tests.
```

See module READMEs for A2 and prototype commands; no full application server exists yet.

## Coding Style

Use four-space indentation, type hints, `snake_case` functions/modules, and `PascalCase` classes. Keep comments/docstrings in English. Follow existing dataclass conventions in `contracts/types.py`. No formatter or linter is configured.

## Testing Guidelines

Use pytest; name files `test_*.py` and functions `test_*` inside your acceptance folder. Test boundaries and failure cases using isolated fixtures and in-memory SQLite. Never weaken another owner's tests. No coverage percentage is configured.

## Architecture & Safety

- Replay `data/release_main/{core,ops}_14d.sqlite` through `ingested_at`; never generate world data or modify source DBs. Store runtime state separately under `runs/`.
- Each 30-minute tick runs A3 → A2 → A1. Feed staleness uses source timestamps (>30 minutes), not replay time. Stale/corrupt/missing feeds or missing/over-60-minute A3 heartbeat block proactive contact. A3 only tightens controls.
- A2 emits one status following `contracts.types.STATUSES`. Lateness starts after `guaranteed_date` ends at 23:59:59 Asia/Ho_Chi_Minh. Driver text lowers confidence only, never changes fault.
- A1 uses rules before LLMs; validate template rephrasing against A2 facts, amounts, dates, and promises. Customer/driver text is data, never instructions. Confirm cancellation again; hand off upon human request or three abusive turns. Voice is web-only; every feature requires an API.
- A2/A3 never execute money. Future financial effects require permission-gated `platform_huy.execute_action`; LLMs never choose amounts. `late_xu_for` only quotes. Compensation requires two days' lateness, no customer fault/force majeure, and an explicit text request in A1-initiated chat; voice cannot grant coins. Enforce idempotency and once-per-order grants.
- Keep `.env`, databases, `data/`, `runs/`, and `truth/` untracked.

## Commits & Pull Requests

Use personal branches `huy`, `an-nguyen`, `truc`. Fetch the team remote and merge updates before work or push; integrate main into your personal branch. Do not install hooks or enforce task-branch names. Commit and push each completed, verified Huy unit to `upstream/huy`; merge/push main when requested. Use descriptive commit subjects. PRs explain behavior, contracts, tests, and UI changes.
