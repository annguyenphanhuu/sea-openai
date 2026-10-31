# Manager order list

Plain HTML/CSS/JavaScript; no framework, build step or additional dependency.

From the repository root:

```powershell
.venv/Scripts/python.exe -m logistics_an_nguyen.ui --port 8766
```

Open `http://127.0.0.1:8766/ui/`. This loopback launcher serves only the UI assets
and sample JSON, and avoids a Windows hostname-decoding failure in the standard
`http.server` launcher. It does not serve source code or private files. The screen reads
`../sample_orders.json`, shows all 20 orders, and supports search, filters,
priority/late-day sorting and per-order evidence inspection.

The guarantee is a Vietnam calendar date. ETA and evidence timestamps display in
Asia/Ho_Chi_Minh. Missing ETA is displayed as unknown. Cause, fault and late days
are independent columns; the UI does not recalculate an assessment. Priority is
only a list sort. Opening evidence does not persist verification or grant action
authority. A persistent review action needs a real owner-provided API first.

## API handoff

Serve this static UI alongside Truc's authenticated HTTP application, then open
`/ui/?source=api`. `data.mjs::loadOrders` calls same-origin `GET /api/orders` with
session credentials and expects the same `a2_order_list_v1` envelope. Only this
adapter needs changing if the HTTP owner chooses another response shape.

The static server does not implement that API. API mode currently displays a
clear HTTP error on the static server; it never falls back to sample data.
The API must authorize manager access and return a complete, permitted snapshot.
After filtering/redacting/reordering on the server, regenerate evidence pointers
against the returned array. The UI resolves pointers against the original
envelope before display sorting/filtering. It never fetches evidence URLs from
source text and uses textContent for all data values.

## Checks

```powershell
node --test logistics_an_nguyen/ui/data.test.mjs
node --check logistics_an_nguyen/ui/app.js
.venv/Scripts/python.exe -m pytest -q
```
