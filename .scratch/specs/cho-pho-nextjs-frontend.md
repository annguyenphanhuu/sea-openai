# Chợ Phố Next.js frontend design

Status: approved by the user. Implementation and verification are complete. The user subsequently requested the shared application live at root frontend/.

## Audit

The existing platform_huy/ui_prototype/index.html is a throwaway Vietnamese operations UI with three alternatives: A portfolio table, B case workspace, and C A3 -> A2 -> A1 timeline. Its README explicitly says no variant has been selected and no API, messaging, financial action, or replay is connected.

Preserve the chợ phố wordmark, forest-green identity (#236148 accent, #183d30 navigation), Vietnamese functional copy, order search and filters, order selection, evidence, draft preparation, handoff, and guard-blocked states. Existing typography is Inter/Segoe UI, radii are approximately 4-12px, and the layout uses a 224px sidebar. There are no SEO landing routes, analytics integrations, or consent forms in this prototype.

Retire the bottom prototype variant switcher in the new application, excessive uppercase micro-labels, disconnected sidebar items, and ambiguous controls that resemble running the real pipeline. Keep the original prototype intact as a reference, including its URL behavior.

## Alternatives

1. Recommended: A as the default overview, B as the selected-order workspace, C as an evidence tab. This supports scanning first and detailed decisions second without three competing application layouts.
2. B as the default: efficient for a dedicated support agent, but hides the overall queue and feed context.
3. C as the default: clear for a pipeline demonstration, but slow for routine order triage.

## Visual direction

An operational application, not a marketing landing page. DESIGN_VARIANCE 4, MOTION_INTENSITY 3, VISUAL_DENSITY 6. Use official Fluent UI React components for accessible product controls, Tailwind CSS v4 for layout, and semantic CSS variables for consistent light/dark themes. Do not mix component systems.

Preserve the forest-green brand with cool neutral surfaces, near-black text, restrained borders, and no decorative gradients or marketing photography. Status colors are semantic warnings/errors rather than additional brand accents. Use Geist via next/font with Vietnamese support. Define 8px control radii, 12px panel radii, and circular identity avatars. Use one Phosphor icon family.

Use a 224px desktop navigation rail, 64px header, and a contained workspace. Overview includes the existing title, clearly labeled data mode, a compact feed/guard notice, four contextual metrics, searchable assessed orders, and the selected order's evidence and next actions. Preserve primary labels: Phòng điều hành, Giám sát dữ liệu, Phân tích logistics, Chăm sóc khách hàng.

Selected-order detail separates order placement, carrier handover, guaranteed date, and revised ETA. Missing values remain explicitly unavailable. Evidence and the A3 -> A2 -> A1 decision sequence are readable before preparing a draft. Draft preview and handoff confirmations are contextual and do not imply a customer message was sent.

Below 768px, collapse navigation into an accessible menu, stack metrics in two columns, display order summaries with an explicit detail action, and stack the selected workspace below the list. Keep keyboard navigation, visible focus, persistent input labels, loading skeletons, retryable errors, and empty-search states. Respect system theme with a manual theme control and only brief interaction feedback.

## Architecture and boundaries

Create a separately runnable Next.js App Router application under frontend, as a shared repository frontend, as requested by the user. Keep package.json, lockfile, TypeScript, PostCSS, and frontend tooling inside that directory; do not edit shared requirements or contracts.

Use Server Components for the application shell and isolated Client Components for search, filters, selection, tabs, theme, and draft/handoff interactions. Keep transport adapters separate from presentational components.

Every feature uses an HTTP boundary. Implement explicitly labeled demo Route Handlers for orders, order assessment, guard/feed health, draft preparation, and handoff, using only the four existing illustrative prototype fixtures. Demo operations return preview acknowledgements; they never execute money, contact a customer, or claim durable server state. Keep simulated feed-failure controls inside a clearly labeled demo area. Provide one adapter boundary for replacing demo transport with the team's authenticated Python HTTP APIs later.

The current care_truc directory contains only its README. Planned APIs in docs/team_plan.md are not implemented by that directory. Do not claim production integration or invent source records. No client-derived permission is authoritative. A production adapter must recheck guard and permissions on the server before mutation. No grant, refund, cancellation execution, voice session, or real chat feature is included in this frontend unit.

## Validation and delivery

After approval, fetch and integrate origin/main on a truc/nextjs-frontend feature branch. Install and verify frontend dependencies locally. Run TypeScript checks, lint, production build, and existing repository import/pytest checks. Verify search, empty state, order selection, evidence tabs, draft feedback, handoff feedback, and guard-blocked behavior through the rendered application. Inspect desktop and mobile in both themes, keyboard focus, and button/input contrast. Run Lighthouse and report observed results with their environment and limitations.

Document startup and demo limitations inside frontend/README.md. Commit and push the completed verified unit to the team remote as required by AGENTS.md. Do not merge main unless requested.
