# Data validation, platform, and A3
Input: Read-only release databases, ingested_at replay cursors, tick time, and action requests.
Output: Validated source access, feed health, guard heartbeats, runtime state, and the future execute_action gateway.
Owner: Huy; ui_prototype and serve_ui.py belong to Truc, who owns UI and HTTP APIs.
Boundary: Future platform implementation; no agent or financial executor is included in this scaffold.
