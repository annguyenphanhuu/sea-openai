# Chợ Phố frontend implementation plan

**Goal:** Implement the approved operations frontend in frontend.
**Architecture:** Next.js App Router shell, Fluent controls, Tailwind v4 layout, validated demo HTTP adapter. Existing prototype remains intact.
**Execution:** Inline in this session, as authorized by the user.

- [x] Scaffold local package/configuration, install Next/React, Fluent, Phosphor, Zod, Tailwind, and verification tools.
- [x] Define demo wire schemas and four existing prototype order fixtures in src/lib; expose no-store GET snapshot and POST preview endpoints with validated input and server guard checks.
- [x] Build themed provider and responsive shell, overview, selected-order workspace, evidence timeline, search/filter, loading/error/empty states, draft preview and handoff feedback.
- [x] Add Playwright checks against the running app for selection/search, mobile overflow, theme, preview actions, and server-side guard blocking.
- [x] Run lint, tsc, production build, browser checks, Lighthouse, Python import and pytest. Inspect desktop/mobile screenshots and resolve issues.
- [x] Document startup and limits and review the diff after fetching and merging team updates.

Validation commands (from frontend): npm run lint; npm run typecheck; npm run build; npm run test:e2e. Repository checks: python -c "import contracts"; python -m pytest -q. Preview responses must explicitly state delivered=false and persisted=false. Missing dates remain null, never inferred from other dates.



Delivery: commit the verified unit and push truc/nextjs-frontend to origin. Keep main unchanged.
