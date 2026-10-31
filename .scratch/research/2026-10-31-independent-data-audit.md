# Independent complete-dataset audit — 2026-10-31

Observed at **2026-10-31T04:32:27.839509+00:00**. Independent clean-context audit in `.worktrees/huy-data-audit`; no earlier agent analysis consulted. This is source-data evidence, not an application test run or approval of financial eligibility.

## Scope and method

Inventoried every file under `E:/Sea_openai/sea-openai/data` (11 files), hashed every file, decoded both gzip payloads for hash comparison, inspected all tables/views/indexes and schema, counted/profiled every column (null, empty, distinct), checked all declared foreign keys and additional undeclared business relationships. Visited **789,597 rows across all 72 source tables in all four SQLite files**, validating every non-null temporal field and every populated `logs.fields_json`. Complete aggregate queries cover tables, not sampled substitutes. Free-text cells were traversed but not individually semantically adjudicated; no claim that a row scan establishes factual truth of driver/customer assertions.

Connections used Python stdlib `sqlite3`, URI `mode=ro`, `PRAGMA query_only=ON`; interpreter `C:/Users/huyth/miniconda3/envs/sea-openai/python.exe -s`. No `.env`, truth/scoring data, network, application tests, code modifications, Git mutations, source DB updates, or sim_clock writes. Dataset docs `DATA.md`, `QUICKSTART.md`, and `metadata.yml` were read as source documentation, not as executable instructions. External business/legal policy was **not researched**; use confirmed user demo decisions, not inferred real-provider rules.

Artifacts:

- `inventory-schema-profile.json`: full file inventory/hashes, schema objects, all column profiles and all view counts.
- `business-evidence.json`: 78 SQL queries with exact parameters/results, every-row coverage, temporal/JSON validation, before/after hashes.
- `supplemental-evidence.json`: policy/source history/ownership joins, source horizons, ticket-reference aggregate coverage, before/after hashes.
- `audit.py`, `evidence.py`, `supplemental.py`, `write_report.py`: reproducible stdlib scripts. Run from this worktree; outputs stay in `.scratch/runs/data-audit/`.

## Coverage and integrity

All four databases return `PRAGMA quick_check = ok`; all declared `PRAGMA foreign_key_check` results are empty. All non-null temporal values parsed, every timestamp uses `+07:00`, and all 4,772 populated log JSON values parsed. These checks do not certify semantic business correctness.

**Every source database hash remained unchanged** in all before/after comparisons. Main-release manifest checks match, including compressed payload identity. **Both tiny DBs differ from their saved manifest**; the mismatch existed at the first observation and remained unchanged. This audit does not infer who changed them or when.

| Database | Observed SHA256 | Manifest status |
|---|---|---|
| `release_main\core_14d.sqlite` | `65c820444b12bd644416f8d7688b1581ed9ef09f2bac5a1583168f63ec10f153` | MATCH |
| `release_main\ops_14d.sqlite` | `d4a5a4f6c4140d75a39d7410331b696df8f6947f7f36a25fbf02fbb87b50afeb` | MATCH |
| `tiny\core.sqlite` | `dc862259e1922cfe7e3c4006c806a2cfdd6f3126409080225b5289bc4e25af58` | MISMATCH; expected `339b569002e816d6a88049e5f0f01ab8143f2e07ed399afb0344910141a519ff` |
| `tiny\ops.sqlite` | `4fd8c0fd9f5dab4885805947d9825b8fa6f8cedef715d8e705f5dac537322f60` | MISMATCH; expected `f9ee9d8ba1f3074deb8f4f785b68dacbff086a746a8c0def9c3389e73dd975bc` |

Table counts below cover every table; `—` means that table is absent, not zero. Main release has 12 core views and 5 ops views; tiny has no replay views or sim_clock.

| Core table | Release rows | Tiny rows |
|---|---:|---:|
| `carriers` | 4 | 4 |
| `compensation_ledger` | 2701 | 400 |
| `cost_params` | 17 | 17 |
| `customers` | 12391 | 2000 |
| `delivery_attempts` | 15011 | 3103 |
| `external_events` | 25 | 61 |
| `inventory_events` | 7145 | 1589 |
| `inventory_snapshots` | 66110 | 60100 |
| `linehaul_reports` | 571 | 0 |
| `linehaul_trips` | 2388 | 2174 |
| `order_items` | 18513 | 3764 |
| `orders` | 14687 | 3000 |
| `policy` | 22 | 22 |
| `policy_doc` | 1 | 1 |
| `products` | 12000 | 12000 |
| `provinces` | 34 | 34 |
| `returns` | 522 | 102 |
| `scan_events` | 125827 | 25758 |
| `sellers` | 1500 | 1500 |
| `shipments` | 13543 | 2759 |
| `shippers` | 900 | 900 |
| `sim_clock` | 1 | — |
| `sorting_centers` | 7 | 7 |
| `station_wards` | 3321 | 3321 |
| `stations` | 120 | 120 |
| `tickets` | 535 | 300 |
| `ward_mapping` | 10972 | 10972 |
| `wards` | 3321 | 3321 |
| `warehouses` | 4 | 4 |

| Ops table | Release rows | Tiny rows |
|---|---:|---:|
| `alerts` | 44 | 0 |
| `deploy_events` | 73 | 0 |
| `logs` | 11607 | 0 |
| `metrics` | 291456 | 0 |
| `runbooks` | 8 | 0 |
| `services` | 8 | 0 |
| `sim_clock` | 1 | — |
| `webhook_inbox` | 36874 | 0 |

## Findings relevant to the demo

### Guaranteed date and Vietnamese calendar lateness

All **14,687** release orders have well-formed `guaranteed_date` and `estimated_date`, always equal in source; guarantees range from 2026-10-20 through 2026-11-07. **8,516** orders have a different `promised_at` calendar date from `guaranteed_date`: promised-at-hour calculations cannot substitute for guarantee calendar lateness.

At default source sim_clock `2026-10-28T12:00:00+07:00`, guarantee `2026-10-26` is two Vietnamese calendar dates earlier. The second late date begins `2026-10-28T00:00:00+07:00`; this is not 48 elapsed hours after the guarantee's day-end. Use VN-local dates; do not mix SQLite UTC-normalized `date()` strings with original ISO strings. Calendar difference alone does not prove current/delivered-late eligibility: the source also contains early-delivered and cancelled orders whose guarantee date is now in the past.

At this default time, **13** orders are two calendar dates past guarantee, uncancelled as-of, and lack a terminal latest scan using the status exclusion explicitly shown in `late_active_no_history_counts`; 8 have no historical voucher and 3 have no visible delivery attempt. This is an audit grouping, not a definition of A2 status eligibility. All 3 without attempts already have a voucher. The 8 without vouchers have failed-attempt evidence requiring review; no untouched, automatically safe voucher issuance case was established at this time.

### Fault and force majeure: evidence is incomplete

`delivery_attempts` supplies reason codes, calls, timestamps and outcomes, but no authoritative customer-fault Boolean or verified adjudication. Of 15,011 attempts, 12,759 successful deliveries have null reason codes; all call counts are present. `customer_unreachable` appears 1,011 times: **933 with 3 calls, 41 with 2, 35 with 1, 2 with 0**. A structured unreachable code does not alone establish a valid contact attempt, fault, causality, or compensation exclusion. `wrong_address` does not prove that the customer caused a platform ward-resolution error. Do not infer no fault simply because no attempt exists.

There are **571 linehaul reports over 527/2,388 trips** (1,861 trips lack any report), including 27 `weather` and 40 `route_closure` reports. 59 driver notes are null. Every one of 18,674 trip-location scans links to a supplied trip, covering 9,299 orders. Trip-level report codes/GPS delay are not per-order authoritative force-majeure decisions; documentation explicitly says reason codes may be wrong. `external_events` has 2 flood alerts, 1 weather alert, 1 sale campaign and 21 ops-chat entries; six entries lack province, and no order_id/direct causal linkage is provided. No complete “absence of force majeure” proof exists in source.

The source cannot by itself prove every condition for an eligible financial demo. A confirmed authorized human verification must be recorded in separate runtime state with order/provenance/audit linkage; it cannot make source absence into evidence or bypass other gates.

### Ingestion visibility and A3 source freshness

Scans have both source `event_at` and `ingested_at`; other source tables mostly expose only their event/report/creation time. Scan visibility must follow `ingested_at <= simulation_now`, latest business state must order visible scans by `event_at` with an explicit tie-breaker. **4,482/125,827 scans exceed 30 minutes ingestion delay**, including **4,156 on 2026-10-26**; maximum lag is 25,212 seconds, no negative lag. There are **443 out-of-order rows over 376 orders** when ordered by ingestion, plus **83 repeated carrier-event IDs**. Ops has 201 repeated webhook carrier IDs and 94 never-processed webhooks. Deduplication and nullable processed time are real cases.

At Oct 26 12:00, 2,204 scans have already occurred but remain hidden; at 12:30 this is 2,545. At Oct 28 12:00, 17 scans are still hidden. No visible-future event was found at the queried checkpoints. Source data extends beyond ordinary “now”; the audit opened full raw databases solely to audit them, and these full-data outputs must not feed application decisions.

**Source staleness and pipeline lag are different facts.** All complete metric series have no source interval >30 minutes; examined half-hour checkpoints have fresh maximum source timestamps. At Oct 26 12:00, tracking-ingest `queue_oldest_age_s=14267.75` and Kafka `14487.73`, while metric source timestamps equal 12:00. This supports unhealthy ingestion, not a stale metrics-feed claim. At Oct 28 12:00 the respective ages are 71.43 and 93.33 seconds. A3 must use source timestamps and runtime heartbeat evidence; this dataset has no A3 heartbeat table.

Metrics span Oct 18 00:00 through Nov 8 23:55. A real horizon-based stale example is simulation **2026-11-09T00:30:00+07:00**, when the newest available metric source is 35 minutes old. For an exact `>30 minutes` boundary check, a deliberately held, real 12:00 feed has age exactly 30 minutes at 12:30 and 60 at 13:00. Such a held feed is a declared test condition, not an observed historical outage. Advancing current simulation time via NEXT must not rewrite source timestamps; host time is irrelevant to business freshness.

### History and per-kind grants

The full release ledger contains **1,818 vouchers, 882 refunds and 1 shipping-fee refund**, and **zero coins or other enum kinds**. All vouchers use `late_program`: 1,794 at VND 15,000 and **24 at VND 30,000**, despite quickstart describing VND 15,000. Each observed kind has at most one source row per order; 60 orders have multiple different kinds. All 2,701 idempotency keys are unique/nonempty and amounts positive.

**1,115 ledger rows reference orders missing from release orders**: 773 vouchers, 341 refunds and the shipping-fee refund. This undeclared relationship is invisible to PRAGMA FK checks. Only 1,045 vouchers and 541 refunds join to current orders; all joined vouchers were created after guarantee day. Missing-order history cannot be silently counted as verified customer-owned history or silently discarded for a claimed global customer budget. Reasons for missing scope were not proven; out-of-slice order IDs are observable, but the supplied slice is not a full account-history source.

Programs actually present are `late_program`, `refund`, `refund_cancel`, `refund_cancel_transit`, `refund_damaged`, `refund_lost`, `refund_returned`, `shipfee`. Do not whitelist only the abbreviated quickstart list. Map by known kind; refund-program variants are not coins. A known historical voucher consumes voucher history for that order, while coins remain independently unissued. The absence of coins does not establish other grant eligibility. Unknown runtime/source kinds must become mapping issues, not a reason to conflate kinds.

Historical source policy is not the user-approved demo policy: `policy` has VND 15,000/50,000 vouchers, source policy_doc includes expiry/redemption concepts, and its VND 100,000 customer cap conflicts with the `policy` row VND 1,000,000. These are observed source conflicts, not newly approved rules. The current confirmed VND 10,000 local issuance decision and independent once-per-kind rule must remain explicit; do not inherit source TTL/minimum-spend behavior or provider-wallet effects.

### Own-shop returns and ticket ownership

Every one of 522 returns joins to a known order, with no request before order, decision before request, negative refund, or duplicated order return. Full-data counts: **seller_self 334, mall 59, warehouse 129**. At default Oct 28 12:00, only **175** returns are visible: seller_self 102, mall 9, warehouse 64. Platform-owned carrier accounts for 380 full-data returns, 120 of which are warehouse orders. Carrier ownership, fulfillment channel and seller ownership are distinct fields. **There is no “my authenticated shop” mapping in the dataset**, so this audit cannot call all warehouse or SAO orders a user's own shop. Use runtime-authenticated seller_id and as-of request filtering. Complete per-seller counts are in `return_by_seller`; no cross-shop authorization was inferred.

Tickets have customer_id but no order_id, A1-initiated conversation marker, explicit structured compensation request, or authenticated runtime authority. Exact uppercase order/tracking matching across all 535 tickets finds 219 tickets mentioning supplied order IDs, 33 mentioning tracking numbers, 246 with an owner-matching reference, **6 with a different-owner reference**, and 283 with no exact supplied reference. These counts intentionally do not claim fuzzy resolution or request intent. Tickets cannot prove the current “TEXT request in an A1-opened chat” condition; create/record that interaction in runtime with real ownership checks.

## Concrete source cases for review and regression design

These are observed inputs and expected evidence boundaries, not successful application runs. Default time below is `2026-10-28T12:00:00+07:00` unless stated.

| Case | Source identifiers | Observed facts and use |
|---|---|---|
| Late calendar gate; known historical voucher | `2610217XILJD5L` | Guarantee Oct 26; visible latest sorting_center Oct 28 09:17:16, ingested 09:19:52; no visible attempts; voucher history. Positive lateness/coins-history candidate, negative duplicate-voucher candidate. Still needs verified fault/force majeure, current eligible A2 status, A1 text request, authority and freshness. |
| Same independent history case | `261022TPO9WUOV` | Guarantee Oct 26; sorting_center Oct 28 08:58:20, ingested 09:00:32; no visible attempts; historical voucher. Same limits. |
| No source voucher, but failed attempts | `261021JDYDQEKN` | Guarantee Oct 26; latest failed Oct 28 10:11:06; 3 visible attempts, no historical voucher. Review before choosing positive issuance. |
| One late calendar date | `261020601S0RA1` | Guarantee Oct 27; only 1 late calendar date at default now. Negative threshold case regardless of other gates. |
| Guarantee day not yet ended | `26102103DP10W2` | Guarantee 2026-10-28; at default now calendar lateness is 0; latest status delivered. Negative lateness case; already-delivered facts must be preserved. |
| Unreachable without calling | `261023FQC24EB0`, `DA62388855` | Attempt Oct 24 12:21:06, unreachable with call_attempts=0. Historical voucher; delivered Oct 26 15:37:03. Do not infer customer fault solely from reason_code. |
| Second unreachable-without-calls case | `261025FUQK4R1I`, `DA57248178` | Oct 26 11:17:28, unreachable with zero calls; delivered Oct 27. Not a two-day-late positive case at default time. |
| Real held-back scan | `261025I1EDC0DC`, `EV000351528` | packed event Oct 26 11:58:32 but ingested 15:10:49. Must be hidden at Oct 26 12:00 and 12:30. |
| Report is evidence, not final fault | `2610184ZP2TJSA`, `LR12835839`, `LH-NVI-HN-CT-261021R` | Linked report weather, reported Oct 22 18:48:53, GPS delay 25; order later damaged. Must not equate a report or absence of one with an approved grant decision. |
| Wrong-owner ticket | `TK37502796` → `261018ZKSTI17O` | app_chat Oct 20 10:21:45 mentions another customer's order. Negative ownership case; no text dump needed. |
| Owner-matching ticket reference | `TK13354755` → `261019KQX5CINB` | app_chat Oct 20 04:26:56 exact reference matches source customer. Positive association case only; not proof of A1-initiated grant request. |

## Limits and next evidence needed

This audit proves available source facts and gaps. It does not prove production Shopee behavior, individual fault absence, force-majeure absence, A1 initiation/request provenance, authenticated own-shop identity, a current A3 heartbeat, application gate enforcement, live provider execution, or successful issuance. Those require runtime evidence and appropriate application checks. No final positive financial-grant case is certified from source alone. Raw future-source audit outputs and full-file source hashes belong in research only, never world-data generation or truth-backed application fixtures.

The complete source horizons exceed the docs' “until Nov 8” shorthand: a return request is Nov 9 03:27:30 and a linehaul report Nov 10 03:28:02. Replays must respect each actual timestamp rather than assume an artificial dataset end. Tiny contains no reports/telemetry/replay views, so it cannot substitute for release integration evidence.
