# Manager order list

Plain HTML/CSS/JavaScript; no framework, build step or additional dependency.

From the repository root:

```powershell
conda activate seaopenai
python -m logistics_an_nguyen.ui --port 8766
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

COD risk badges use the A2 `reason_codes` only: `cod_refusal_risk:high` is red
and `cod_refusal_risk:medium` is amber. Neither replaces the status badge or
changes fault. The current 20-order sample has two high and two medium cases;
filter by status `late` and payment `COD` to inspect the red badges. The browser
does not infer risk from payment, amount or source text. The Python rule uses
the confirmed 1,000,000 VND threshold and visible failed delivery attempts.

The green **Miễn trừ LSR** badge appears only for the assessed
`lsr_exempt:carrier` reason. The seller fault label is **Người bán**.
Inspect `handed_over_scan`, linked `linehaul_trip_id` and `linehaul_report` in the
evidence panel; reports remain unverified text. `linehaul_report_missing` makes a
missing report visible without fabricating one or overriding the scan/policy rule.
The badge is an A2 recommendation, not proof that an external penalty was changed.

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
conda run -n seaopenai python -m pytest -q
```
