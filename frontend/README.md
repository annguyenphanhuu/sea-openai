# Chợ Phố frontend

Operations UI built with Next.js App Router, React, TypeScript, Tailwind CSS v4, official Fluent UI React controls, and Phosphor icons. This is a separately runnable application shared by the repository.

## Run

Use Node.js 20.9+ and npm, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. For a production build:

```powershell
npm run build
npm run start
```

## What is connected

The browser calls local demo Route Handlers, not the Python runtime:

- `GET /api/demo/snapshot?scenario=healthy|failure`: four original illustrative orders plus a simulated guard gate.
- `POST /api/demo/preview`: `{ orderId, scenario, kind: "draft" | "handoff" }`. Validates input, checks simulated per-order/guard conditions on the server, and returns a deterministic preview with `delivered: false` and `persisted: false`.

No source DB is read or changed. No message, handoff, payment, cancellation, voice session, replay, or real assessment is executed. Scenario selection is deliberately client-controlled demo input, never a production permission. The dataset and timestamps remain the original prototype's examples; this is not current operational data.

Drafts and handoff previews live only in browser memory and reset on page reload. Repeating a preview HTTP request has no side effect. Theme preference alone is stored locally. Missing order and handover dates remain unavailable.

## Screens and interactions

- Phòng điều hành: search by order/customer/route, filters, order selection, risk and evidence.
- Giám sát dữ liệu: A3/A2/A1 boundaries and simulated contact gate.
- Phân tích logistics: decision timeline for the selected order.
- Chăm sóc khách hàng: draft preview and handoff preview.

The expandable demo controls let you simulate a feed failure. Draft preparation is blocked for failure, missing-feed, or low-risk examples. Handoff preview remains available. Both themes follow system preference until manually changed; layouts adapt down to 375px.

## Validation

```powershell
npm run lint
npm run typecheck
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser checks use Playwright Chromium by default. To reuse installed Microsoft Edge on Windows, set `$env:PLAYWRIGHT_CHANNEL = "msedge"` before running the tests. The test runner starts the production server on port 3000. Screenshots and failure traces are written to ignored `test-results/`. Tests cover filters/search, order selection, missing data, evidence, preview cycles, server rejection, error recovery, responsive layout, and light/dark themes.

## Integration boundary

`src/lib/api.ts` owns browser HTTP transport. `src/lib/demo.ts` is a demo wire schema and fixture set, not a copy of the complete shared Python contract. Replace the demo adapter with authenticated team APIs when available, deriving production DTOs from the team's authoritative schemas. Server-side ownership, source trust/heartbeat checks, permissions, persisted idempotency, and action execution belong to the actual API/platform. Do not promote the demo gate or fixture assessments into production authorization.

The original prototype and its `?variant=A|B|C` behavior remain untouched. Dependencies/configuration are local to this folder; shared Python dependencies and contracts are unchanged.

References: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [Tailwind Next.js setup](https://tailwindcss.com/docs/installation/framework-guides/nextjs), [Fluent UI React](https://fluent2.microsoft.design/get-started/develop).
