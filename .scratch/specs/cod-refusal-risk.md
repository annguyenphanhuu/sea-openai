# COD refusal risk reason and list badge

User request, 2026-10-31: merge order-list-ui to main, then add the COD risk
reason, three literal test cases and a red badge on the order list by 13:30 VN.
Main merge completed at `c2fa3d8` after 618 acceptance and 8 UI adapter tests.

The user supplied the literal cases and clarified the amount boundary:

- COD + final status `late` + (`items_value_vnd >= 1_000_000` OR at least one
  visible failed delivery attempt): append `cod_refusal_risk:high`.
- Other COD + final status `late`, or COD + `at_risk`: append
  `cod_refusal_risk:medium`.
- PREPAID or all other final statuses: no `cod_refusal_risk` reason.

This is a deterministic supplementary signal, not a new logistics status,
fault finding, calibrated probability, customer accusation or money permission.
Preserve existing status, fault, dates, late days, confidence and priority.
Only structured, trusted, as-of order/attempt facts can contribute. Failed
attempts use actual non-delivered outcomes in the source schema; driver prose
and future attempts cannot set the flag. Source database files remain read-only.

Keep the shared contracts unchanged. Add source metadata to the A2 adapter and
the reason to assessment output. Handoff already carries reason_codes/cause.
The existing plain-JS UI reads the reason, with a labelled red high badge and
amber medium badge. Evidence inspection shows the underlying records. Refresh
the 20-order source-derived sample, including a genuine high case if available;
never edit a sample flag by hand or manufacture release data.

Literal cases: high (COD/late/1_200_000 or one failure), medium
(COD/at_risk/250_000/no failures), none (PREPAID/late or COD/on_track).
Add focused checks for the clarified boundary and trust/as-of integration.
