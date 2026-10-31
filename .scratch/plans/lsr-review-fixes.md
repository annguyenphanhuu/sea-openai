# Seller LSR review corrections plan

1. Fetch origin and create a new Nguyen branch from origin/main.
2. Record the narrowly approved FaultParty extension, keeping it for a separate
   Huy-approved commit after verification.
3. Update A2 reason/provenance and seller attribution; preserve trust gates and
   structured competing causes.
4. Relocate tests, add the three literal cases, retain boundary coverage, and add
   regression cases for trip associations and replay availability.
5. Add the LSR badge and seller label using the existing UI design. Refresh the
   same 20 sample order IDs from read-only release data; update A2 documentation.
6. Run all acceptance tests including acceptance_huy, all care_truc tests, UI
   adapter checks, contract import, conflict/whitespace/private-path checks.
7. Fetch/integrate any main changes. Commit the one-line enum separately with
   Huy approval, commit the implementation, push the feature, merge/push main.
