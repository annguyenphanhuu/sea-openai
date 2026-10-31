# Frontend verification

The submission layout pass adds focused care, overview, logistics and guard screens. Eight Chrome presentation tests passed against intercepted runtime snapshots. They verify the send control fits within a 1366 by 768 laptop viewport, eight-item pagination over 119 sessions, search, distinct view content, localized facts, hidden raw evidence, mobile list/detail navigation with preserved search, no horizontal overflow at 390 pixels, matched chat/order identity, disabled transferred sessions, separate message roles, latest-message scroll when opening a mobile detail pane, dark theme and absence of duplicated server-rendered control styles. Screenshots are `test-results/polished-laptop.png`, `polished-mobile.png` and `polished-dark.png`.

`npm run typecheck`, `npm run lint`, `npm run build` and `git diff --check` passed after the layout changes. Presentation snapshots do not establish backend policy behavior. The real integration test remains in `tests/operations.spec.ts` and requires a fresh isolated backend.

The final full browser run passed ten tests on 2026-10-31. The real workflow used an isolated Python runtime on port 8880. The user runtime on port 8875 was kept separate.

Two Chrome Playwright tests passed through the running Next development server. They cover loading release-fed assessments, persisted chat after reload, cancellation pending before explicit confirmation, a recorded cancellation request after confirmation, A3 blocking, staff handoff while proactive contact is blocked, cross-origin rejection, public forwarded-host rejection and invalid command rejection. No backend requests were mocked.

`npm run lint`, `npm run typecheck` and `npm run build` passed. The production build completed with only the integrated `/api/runtime` route. The browser checks above used the development server.

The screenshot is saved locally at `test-results/integrated-runtime.png`. Test traces and runtime state are untracked. Browser tests mutate the isolated runtime. Use a fresh state path before repeating them.

This proves local web-inbox integration. It does not prove external message delivery, real wallet payout, voice transport or per-customer authentication. The Next server binds to loopback and the proxy enforces local Host and same-origin mutation checks. Public deployment requires a separate authentication design.

The former static-demo Lighthouse numbers and six preview tests do not describe this implementation.

Production build, TypeScript and lint passed after the mobile scroll and server-style fixes. Starting the production server was rejected by automatic approval review with the stated reason blocked by policy. Browser verification therefore used Next development mode. The existing local server is restored to the user runtime after tests.

The server-style insertion guard follows the official Griffel App Router guidance at https://griffel.js.org/react/guides/ssr-usage/.
