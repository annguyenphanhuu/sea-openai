# Seller LSR review corrections

Requested on 2026-10-31, due 14:45 Asia/Ho_Chi_Minh. Work from current main on
`nguyen/lsr-review-fixes`, verify, then merge and push main.

1. Emit the exact reason `lsr_exempt:carrier` and update the payload projection.
2. Include the actual selected `handed_over` scan row and visible reports for
   trips linked by the order's scan history, even after it reaches a station.
   Retain raw linehaul reports as unverified text; they cannot decide fault.
   Never borrow another trip's report or expose records after the replay cutoff.
3. Attribute late preparation to `seller` when fault was otherwise unknown.
   Preserve independently confirmed customer/carrier/platform/force-majeure
   evidence. Add the seller label to the UI fault map.
4. Move the named seller-protection test out of `acceptance_huy`. Its replacement
   in `acceptance_an_nguyen` contains exactly three literal carrier/seller/customer
   cases. Preserve boundary coverage in a separate file in that same folder.
   Customer fixture is refused/customer_refused with one call, not an unsupported
   inference from the call count alone.
5. Display a labelled Miễn trừ LSR badge from the exact assessed exemption reason.

Huy explicitly authorized changing exactly one line in `contracts/types.py` to
add `seller` to `FaultParty`. Commit that change separately and name Huy's approval
in the subject. Do not modify any other contract or dependency.

Do not edit `care_truc`, `platform_huy`, or `acceptance_huy` beyond the specifically
requested test relocation. Report any required owner changes to the user.

The user confirmed that a missing report preserves carrier attribution from the
scan/policy and adds `linehaul_report_missing`. Never fabricate a missing report.
