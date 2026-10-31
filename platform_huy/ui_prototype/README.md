# Chợ Phố UI prototype — throwaway

Question: should early operations prioritize a portfolio overview, a case workspace, or a decision timeline?

Run from the repository root (standard library only):

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory platform_huy/ui_prototype
```

Open http://127.0.0.1:8765/?variant=A. Switch with the bottom arrows or keyboard left/right (outside text inputs).

- A: portfolio table with assessment details.
- B: case queue with evidence and a conversation preview.
- C: sequential A3 → A2 → A1 decision timeline.

Try selecting orders, filtering/searching in A, preparing a draft, adding a human handoff, toggling the feed-failure scenario, and advancing the UI clock. State is shown in the expandable footer and resets on reload.

All records and metrics are explicitly labeled illustrative UI fixtures, not world data or source-database records. No API, source database, LLM, messaging, or financial action is connected. The clock button does not run the replay pipeline. The scenario-reset button is a prototype control, not a proposed production control-unlock permission. The full page is prototype-only; do not promote it or its switcher to production. No variant has been selected yet.

Captured on branch `feat/ui-prototype`. Review the three layouts before choosing an implementation direction. No issue was provided for a context pointer.
