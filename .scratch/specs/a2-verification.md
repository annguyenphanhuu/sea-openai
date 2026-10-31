# A2 verification scope

Owner: An Nguyen. Requested: thorough verification of the existing A2 component.

- Preserve other owners' tests, contracts and dependencies. New tests belong in
  `acceptance_huy/`; fix reproduced A2 defects in `logistics_an_nguyen/`.
- Verify deterministic business rules, VN deadline boundaries, feed freshness,
  structured fault attribution, untrusted text, as-of projection, forecast
  history, progress retry/restart, questions and the assessed-order handoff.
- Use hand-authored expected results and isolated fixtures. Include combinations
  and metamorphic checks that are not copies of implementation logic.
- Run release snapshots read-only, preserve source hashes, write evidence under
  `runs/a2-verification/`, and do not invent healthy A3 state for release data.
- Exercise the existing offline forecast validator separately from production
  assessment; report quality limitations rather than treating valid code as a
  validated prediction model.
- Report failures before fixes and passing regressions afterward. Do not claim
  A3/A1, HTTP/auth, financial execution or end-to-end integration is verified.
