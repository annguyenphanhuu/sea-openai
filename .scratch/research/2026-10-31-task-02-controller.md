# Task 02 source-wrapper research — 2026-10-31

- Existing repository logistics_an_nguyen/replay.py ReleaseReader already uses mode=ro and query_only and provides the A2 ReplaySnapshot. Reuse it unchanged; Huy adds validation, masking and source identity around it. Full independent audit is in 2026-10-31-independent-data-audit.md.
- https://www.sqlite.org/uri.html: mode=ro opens read-only; immutable additionally disables change detection/locking based on an assumption about external mutation. Use mode=ro/query_only; do not assert immutable hardware or disable locking.
- https://docs.python.org/3.11/library/hashlib.html: SHA256 and file_digest are available in Python 3.11 for file identity. Compare against the supplied manifest.sha256 at startup, not an invented manifest.json.
- Source DATA.md declares the provided data synthetic and includes future events through November 8. Replay still uses only records available at simulation time. Full audit artifacts are not application truth or runtime inputs.
- All audited source timestamps have +07:00 and second precision. Existing reader normalizes its cutoff to this representation. Verify the invariant before relying on lexical comparisons; malformed availability must fail closed.
- tiny hashes mismatch saved manifest and all tiny guarantees are null; use release_main as the actual demo source. Do not rewrite tiny or its manifest.

No new business rule adopted here. Fault/FM absence and source policy text do not authorize grants.
