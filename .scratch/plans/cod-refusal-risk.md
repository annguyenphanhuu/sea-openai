# COD refusal risk implementation

1. Fetch/merge, verify, and push order-list-ui to main: complete (`c2fa3d8`).
2. On `nguyen/cod-refusal-risk`, write the user's three literal cases and
   observe assertion failures before adding the rule.
3. Project existing payment/value/failed-attempt facts with provenance, then
   append the risk reason after the existing status decision. No contract change.
4. Add labelled high/medium badges and translations to the plain-JS list;
   regenerate the 20-order sample from the same read-only release cutoff.
5. Run literal/boundary/integration, UI adapter and acceptance checks under
   Conda seaopenai; verify the served sample and assets, then commit/push.

Prior UI verification was blocked by Computer Use's uncertain browser-URL
safety check. Do not bypass that block or claim screenshots without evidence.

## Verification

- The three literal tests first produced genuine assertion RED (2 failed,
  1 passed), then GREEN (3 passed) after implementation.
- Focused literal, boundary, source and handoff checks: 73 passed.
- Full configured acceptance suite in Conda seaopenai: 633 passed in 26.73s.
- Node adapter/badge tests: 9 passed; JavaScript syntax and diff checks passed.
- Refreshed the same 20 source IDs at the same cutoff, without replacing rows:
  2 high, 2 medium, 16 none; unchanged status, fault, late days and prior reason
  codes (only the COD reason was added). Release source SHA-256 stayed
  `65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153`.
- Live Conda preview on port 8766 serves the updated sample and badge assets
  with HTTP 200. Browser host remains unavailable; no screenshot verification.
- Design detector reported advisory gaps in inherited palette/type documentation;
  the new high-risk red is explicitly documented. Existing visual values were
  retained; unrelated design-system documentation drift was not repaired.
- Independent reviewer disposition: ship, no material defects found in code;
  badge wrapping and rendered mobile layout remain visually unverified.
