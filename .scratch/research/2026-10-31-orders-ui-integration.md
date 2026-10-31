# Orders integration source review

Bounded task from coding controller: serve Nguyen's original UI from Huy's integration server, link it from Truc's primary demo, and preserve actual A2 fields. No edits to Nguyen or Care files, no Git operations.

Inspected primary sources before implementation:

- Installed CPython `http.server.SimpleHTTPRequestHandler.send_head` source via `inspect.getsource`: directory paths redirect to a trailing slash before resolving relative assets; static files use MIME lookup. Use canonical `/orders/?source=api`, and explicitly serve `.mjs` as JavaScript.
- `logistics_an_nguyen/ui/index.html`: relative `./styles.css` and `./app.js`; app imports `./data.mjs`. No asset rewriting is required.
- `logistics_an_nguyen/ui/app.js`, `data.mjs`, `README.md`: `source=api` selects same-origin `GET /api/orders`, credentials included. `validatePayload` requires the `a2_order_list_v1` envelope, complete evidence pointers, and matching assessment timestamps. Sample mode must not be selected for this integration.
- `logistics_an_nguyen/handoff.py` and `platform_huy/tick.py`: actual A2 handoff already persists atomically in `demo_a2_handoff`. Read that complete envelope under the runtime request lock; do not reconstruct assessments from source SQL or static samples.
- `platform_huy/presenter_auth.py`: exposed APIs require the presenter header. The unchanged Nguyen adapter sends cookies rather than this header. A valid presenter header now establishes an opaque process-local read capability, restricted to `/api/orders`, HttpOnly, SameSite=Strict, Secure on exposed hosts. Only the exact orders action accepts the cookie; existing control APIs retain their header requirement.

Interface:

- `/` remains Truc's integrated live page, with a top `Danh sách đơn` link to `/orders`.
- `/orders` redirects to `/orders/?source=api`; final response is the original Nguyen HTML. Only index, styles, app and data module are served under the mount.
- `/api/orders` returns persisted A2 `a2_order_list_v1` without reshaping. Before the first NEXT it returns a valid empty envelope and does not advance simulation.
- `/api/demo/state` preserves its bounded order projection and adds `cod_refusal_risk` (`high`, `medium`, or null) only from A2 reason codes. All cause/fault/payment/date fields continue to come from handoff. Evidence pointers are rebased only to the displayed array.
- On an exposed deployment, unlock the main demo first, then follow the orders link. Direct anonymous API access returns 401. Restarting the process invalidates the cookie.

Validation evidence is in `.scratch/runs/orders-ui`: failing HTTP routes before implementation (`red.txt`); real HTTP, source-identity, and authorization checks (`green.txt`); original JS adapter against the real HTTP A2 response (`javascript.txt`). No Care compatibility failure observed in actual NEXT against baseline c42a8c0.
