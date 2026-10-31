# Frontend verification

The integrated console was verified on 2026-10-31 using a real Python integrated server on port 8875 with isolated runtime state outside the source data directory.

Two Chrome Playwright tests passed through the running Next development server. They cover loading release-fed assessments, persisted chat after reload, cancellation pending before explicit confirmation, a recorded cancellation request after confirmation, A3 blocking, staff handoff while proactive contact is blocked, cross-origin rejection, public forwarded-host rejection and invalid command rejection. No backend requests were mocked.

`npm run lint`, `npm run typecheck` and `npm run build` passed. The production build completed with only the integrated `/api/runtime` route. The browser checks above used the development server.

The screenshot is saved locally at `test-results/integrated-runtime.png`. Test traces and runtime state are untracked. Browser tests mutate the isolated runtime. Use a fresh state path before repeating them.

This proves local web-inbox integration. It does not prove external message delivery, real wallet payout, voice transport or per-customer authentication. The Next server binds to loopback and the proxy enforces local Host and same-origin mutation checks. Public deployment requires a separate authentication design.

The former static-demo Lighthouse numbers and six preview tests do not describe this implementation.
