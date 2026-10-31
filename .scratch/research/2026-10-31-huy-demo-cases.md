# Existing release demo candidates — 2026-10-31

These are **source-data query results, not proof of runtime features, A2 accuracy, eligibility, or grants**. All timestamps below use Vietnam time (`+07:00`); ticks are on the 30-minute grid and precede 1 November. Read only `data/release_main/core_14d.sqlite` and `ops_14d.sqlite` with Python `sqlite3.connect(Path.resolve().as_uri() + '?mode=ro', uri=True)` and `PRAGMA query_only=ON`. No truth/heldout, source writes, generated world data, runtime creation, or message bodies were used. Consulted workspace/repository AGENTS, docs/decisions.md, docs/data_audit.md, and the current demo decision log. This investigation does not fetch/merge Git; controller owns Git changes.

Availability conventions: orders `created_at <= T`; scans `ingested_at <= T` (sort visible progress by `event_at`); attempts `attempt_at <= T`; return requests `requested_at <= T`; ledger `created_at <= T`; ops metrics `ts <= T`. Attempts/returns have no measured ingestion timestamp, so their source-time cutoff is a mapping convention, not proof of arrival time. Future mutable fields must be masked; notably return `status/refund_vnd` cannot be copied from a future decision. No source sim_clock/view was used.

## 1. Preferred two-calendar-day late candidate, with fresh business feeds

- Order `261021ZS7E76FW`, created `2026-10-21T08:04:02+07:00`; guaranteed date **2026-10-22**; items value 525,000 VND.
- At **T = 2026-10-24T16:00:00+07:00**, delivered scan **EV000067934** is visible: event `15:36:47`, ingestion `15:36:48` on 24 October. Actual delivery date is **2026-10-24**, two Vietnam calendar dates after guarantee. Do not substitute promised_at/ETA.
- Visible attempt **DA04636708**, `2026-10-24T15:36:47+07:00`, outcome `delivered`, null reason, call_attempts=1. No other visible failed attempt for this order was found. No source ledger row for this order exists by T. Absence of recorded customer-fault evidence does not prove absence of force majeure or other exclusions.
- At prior tick **15:30**, delivered scan is hidden; latest visible progress is **EV001071445**, `out_for_delivery`, event `12:58:48`, ingestion `13:00:48` on 24 October. At 16:00 the delivery evidence becomes available.
- All three candidate strict business timestamp feeds have source age below 30 minutes at 16:00 (table below). Full feed semantic validation/A3 heartbeat and provenance still require runtime verification. Force-majeure clearance, A1-opened chat, customer TEXT request, entitlement history mapping and approval remain unresolved; **do not present this as fully eligible or already granted**. If all rules are later verified, deterministic coin quotation is 26,000 and separate voucher is 10,000 VND; this note performs no issuance.

The earliest +2-day delivery found, `261019X58NOV40`, was deliberately not selected: visible failed attempts DA59182660 and DA25301691 both record customer_unreachable/call_attempts=3. Another early no-failure candidate, `2610197T6ZKT73`, has existing source voucher LG187673678 (created 22 October 03:21:06), introducing the unresolved historical kind mapping. The preferred case avoids those particular complications, without resolving force majeure.

## 2. Visible exception, independently of guarantee lateness

- Order **261019QY8UDYNZ**, created `2026-10-19T10:44:36+07:00`, guaranteed date **2026-10-22**.
- At **T = 2026-10-22T05:00:00+07:00**, scan **EV001358688** has status **lost**, event `04:35:19`, ingestion `04:37:01` that day. At 04:30 it is hidden. `lost` is an allowed D2 exception; guarantee day has not ended, illustrating why exception priority is distinct from late.
- No attempt rows for this order were found. A nighttime attempts feed is sparse/stale under the candidate strict timestamp mapping; this is not evidence of an outage and does not authorize proactive contact.

## 3. Structured customer-fault evidence versus contradictory call count

This is one contrast scenario with two orders; it does not rely on driver prose.

| Branch | Tick T | Order / guaranteed date | Structured attempt | Corresponding failed scan visibility |
| --- | --- | --- | --- | --- |
| Structured fault candidate | 2026-10-18T14:30:00+07:00 | 261018TCVXCW71 / 2026-10-20 | **DA84474882**, attempt_at 2026-10-18T14:20:12+07:00, outcome no_answer, customer_unreachable, **3 calls** | **EV000365689**, event 14:20:12, ingestion 14:21:19 on 18 October |
| Ambiguous, cannot infer fault from reason alone | 2026-10-24T12:30:00+07:00 | 261023FQC24EB0 / 2026-10-24 | **DA62388855**, attempt_at 2026-10-24T12:21:06+07:00, outcome no_answer, customer_unreachable, **0 calls** | **EV000546926**, event 12:21:06, ingestion 12:23:37 on 24 October |

Order creation: first `2026-10-18T09:19:53+07:00`, second `2026-10-23T10:30:36+07:00`. Neither has passed its guarantee date at its proposed tick. The ambiguous branch must not be labeled customer fault solely from customer_unreachable. Actual final A2 status remains subject to higher-priority exception/feed checks. Later delivery outcomes were not used to assess either tick.

## 4. Own-shop return history: one request is not one physical return

- Scope the seller to **SH2463399** and customer to **KH00014810**, never customer-only across shops.
- At **T = 2026-10-27T05:00:00+07:00**, return request **RT29318990**, order **261023TDK6SMSY**, was requested at `2026-10-27T04:36:19+07:00`. Order created `2026-10-23T10:57:58+07:00`, guaranteed date **2026-10-24**; delivered scan **EV000893112**, event `2026-10-24T15:30:52+07:00`, ingestion `15:31:42` is visible by T.
- Same seller/customer, as-of T: **1 request record, 1 distinct order with a request, 0 visible physical `returned` scans (0 distinct orders with such scans)**. This pair has no return-related scan at all in the source. Show separate descriptive counts and do not call the request a completed physical return.
- At 04:30 the request count is 0; at 05:00 it is 1. Raw row carries decided_at `2026-10-28T08:14:28+07:00` and terminal status refunded; these are future relative to T and **must not be exposed as current status/refund**. This is an explicit future-field masking example.
- Maximum request count and maximum distinct requested-order count per (customer_id,seller_id) are **1/1 at this tick and 1/1 over the entire allowed release returns table**. A repeated same-shop return-history case is **not available**; do not manufacture one or infer fraud. Request counts do not measure pre-release lifetime history.

## 5. Delayed ingestion and event-order preservation

- Order **261018Z9DTA5W6**, created `2026-10-18T09:12:36+07:00`, guarantee **2026-10-24**.
- Scan **EV000410037**, `handed_over`, event **2026-10-19T14:42:58+07:00**, ingestion **2026-10-19T19:02:22+07:00**: **259 minutes 24 seconds ingestion lag**.
- At **T = 2026-10-19T19:00:00+07:00**, this scan is hidden even though its event happened hours earlier. Scan **EV001459809**, `sorting_center`, event `18:49:08`, ingestion `18:50:45` that day is already visible.
- At next tick **19:30**, delayed handed_over becomes available, but sorting_center remains later progress by event_at. Cursor uses ingestion; progress must not regress merely because an older event arrived last. Both proposed ticks have all three business source ages below 30 minutes; a lagging row is not itself proof that its whole feed is stale.

## Feed-level timestamp checks at proposed ticks

Candidate strict mapping from existing research: orders=MAX(created_at) among visible orders; scans=MAX(event_at) among ingested_at<=T; attempts=MAX(attempt_at) among visible attempts. Counts are visible rows, not freshness counts. For each feed the table records **row count / latest source time / source age in minutes**; all dates match the tick date except the explicitly dated nighttime attempts. This checks timestamps only, **not corrupt-row validation, feed liveness, heartbeat, or final trusted status**. The strict mapping remains a proposal where business decisions are pending.

| Tick (+07:00) | orders | scan_events | delivery_attempts | Feeds with source age <=30 min |
| --- | --- | --- | --- | --- |
| Oct24 16:00, late case | 6786 / 15:58:25 / 1.58 | 40901 / 15:59:23 / 0.62 | 3715 / 15:59:07 / 0.88 | 3/3 |
| Oct22 05:00, exception | 4147 / 04:59:37 / 0.38 | 19305 / 04:57:46 / 2.23 | 1065 / Oct21 20:28:12 / 511.80 | 2/3 |
| Oct18 14:30, structured fault | 495 / 14:29:08 / 0.87 | 862 / 14:29:34 / 0.43 | 9 / 14:20:12 / 9.80 | 3/3 |
| Oct24 12:30, ambiguous | 6547 / 12:29:53 / 0.12 | 38835 / 12:28:24 / 1.60 | 3338 / 12:29:06 / 0.90 | 3/3 |
| Oct27 05:00, return history | 9715 / 04:48:37 / 11.38 | 62411 / 04:58:28 / 1.53 | 5856 / Oct26 20:16:52 / 523.13 | 2/3 |
| Oct19 19:00, lag before | 1752 / 18:58:55 / 1.08 | 5076 / 18:59:35 / 0.42 | 222 / 18:54:12 / 5.80 | 3/3 |
| Oct19 19:30, lag after | 1775 / 19:29:49 / 0.18 | 5202 / 19:28:27 / 1.55 | 224 / 19:25:26 / 4.57 | 3/3 |

Metrics were independently queried read-only and include samples at Oct22 05:00, Oct18 14:30, Oct24 12:30, Oct27 05:00, Oct19 19:00 and 19:30. These observations do not replace business feed timestamps or establish a service mapping for delivery_attempts. Sparse nighttime attempts cannot be called an outage from this evidence.

## Reproduction outline

Bounded SQL selected delivered scans with `substr(event_at,1,10) >= date(guaranteed_date,'+2 days')` and ingestion before 1 November; then excluded visible non-delivered attempts and visible ledger rows for the preferred candidate. Exact-order as-of reads confirmed its attempt/ledger facts through the rounded tick. Exception and ingestion-lag searches were limited to a few rows before 1 November. Only IDs, dates, statuses, counts, value and call counts were selected; no personal names, addresses, phones or message bodies.

Return aggregation: `returns JOIN orders USING(order_id)`, filter requested_at<=T and orders.created_at<=T, group by customer_id,seller_id; compute COUNT(*) separately from COUNT(DISTINCT returns.order_id). Physical return aggregation instead filters scan_events.status='returned' AND ingested_at<=T on scoped orders. Full-release max group counts were measured only to establish that repeated same-shop requests are absent, not to give future evidence to an agent at T.

No integration test or runtime feature was exercised. These cases are candidates for a later deterministic integration/demo fixture using immutable release reads and isolated runtime state, after the remaining business/demo decisions are settled.
