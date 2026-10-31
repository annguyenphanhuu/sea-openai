# Unified dashboard execution

1. Controller merged upstream/main 008addd into huy as 403cf83; origin/main is the older fork and was already contained. Run baseline full tests and preserve logs.
2. dashboard_ui works in its own worktree on live.html only: five tabs, existing selectors, original /orders iframe, API-backed controls.
3. dashboard_api works in its own worktree on demo_flow.py, serve_ui.py and its new test: state aliases, named review audit, real scenarios, tab routes.
4. Controller reviews and copies disjoint changes, resolves only platform regressions, runs full tests. Independent clean-context reviewer checks final contract and code.
5. Controller checks Chromium scenarios on separate port and runtime, fetches/merges before push, publishes huy and main only after accepted verification, restarts live 8765 preserving runtime and presenter authentication. Do not restart an existing tunnel.
6. Record main hash and test counts. Azure final source deployment uses that verified main; no feature additions beyond the approved scope.
