# Unified demo dashboard

Approved scope: integrate main 008addd into huy; expose a single serve_ui application with five navigation tabs: overview, original A2 orders, contacts, chat, money. Keep Care and A2 implementations unchanged. All operational values come from the runtime state API. Original A2 UI is embedded from /orders, never copied or replaced with Next.js.

State retains current fields and adds arrays tasks, chats, timings; orders include actual A2 LSR and evidence data. Staff verification accepts a supplied staff name and records it with the existing evidence audit. Three selectable real-release scenes: late COD, lost, customer fault. Do not fabricate source evidence or automatically approve fault/force majeure.

Acceptance: full pytest, HTTP 200 for each tab, actual Chromium interactions for 26000 coins, queued cancellation, lost cancellation rejection, human handoff and A3 kill. Preserve source hashes and money idempotency. User permits recording the known Care deadline test failure without editing Care; all other failures require diagnosis before platform-only fixes.
