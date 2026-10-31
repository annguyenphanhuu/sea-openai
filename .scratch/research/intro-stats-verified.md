# Landing statistics verification — 2026-10-31

Read-only inspection of `data/release_main/core_14d.sqlite` via SQLite URI `mode=ro`. No DB writes or Git mutations. These are synthetic simulation figures, not real-world marketplace statistics. Full release covers orders created 18–31 October and their later events through 8 November; it contains future outcomes relative to default demo clock `2026-10-28T12:00:00+07:00`.

## Findings

### Follow-up: user supplied exact outcome cohort

**The supplied 651/1,474 versus 0/7,575 is reproduced exactly.** The cohort is all **9,049 noncancelled COD orders** in the full release (9,999 COD orders minus 950 cancellations), split by final delivery outcome. `late_or_undelivered` means successful delivery after guaranteed date **OR no successful delivery at all**. It contains 731 delivered late plus 743 undelivered = 1,474, of which 651 have a refused attempt: **44.17%**, rounding to 44%. The remaining 7,575 were successfully delivered by guaranteed date and none had a refusal. Using delivered scans instead of successful attempts gives identical results.

This resolves the initially unreproduced 44% below: the user's denominator was final late-or-undelivered orders, not late delivery attempts. All 743 undelivered orders have guaranteed dates on/before 7 November, while scan history runs through 8 November 19:32:24 +07:00. This is valid retrospective final-release analysis, **not live as-of evidence**. All refused orders remain undelivered; the grouping therefore cannot establish that lateness caused refusal or that refusal occurred after the deadline. Only 131 of the 651 COD refusals happened after guaranteed date.

For third-failure orders, the user's exact status set **`returning`, `returned`, `waiting_to_return`** covers **158/158**; adding `return_failed` is unnecessary. There are **49 returned**, **0 delivered scans**, and **0 successful delivery attempts**. Latest status counts are **49 returned, 92 returning, 12 waiting_to_return, 5 return_failed**. Thus say "49 completed return; 109 have not completed return", rather than claiming all 109 are currently returning.

```sql
-- Exact user's COD final-outcome cohorts, full release only.
WITH d AS (
 SELECT order_id,min(attempt_at) delivered_at
 FROM delivery_attempts WHERE outcome='delivered' GROUP BY order_id
), r AS (
 SELECT DISTINCT order_id FROM delivery_attempts WHERE outcome='refused'
)
SELECT CASE WHEN d.delivered_at IS NULL
                  OR substr(d.delivered_at,1,10)>o.guaranteed_date
            THEN 'late_or_undelivered' ELSE 'on_time_delivered' END cohort,
       count(*) denominator,
       sum(r.order_id IS NOT NULL) refused,
       sum(d.delivered_at IS NULL) undelivered
FROM orders o LEFT JOIN d USING(order_id) LEFT JOIN r USING(order_id)
WHERE o.payment_method='COD' AND o.cancelled_at IS NULL
GROUP BY cohort;
-- late_or_undelivered:1474,651,743; on_time_delivered:7575,0,0.

WITH t AS (
 SELECT DISTINCT order_id FROM delivery_attempts
 WHERE attempt_no=3 AND outcome<>'delivered'
)
SELECT count(*) denominator,
 sum(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id=t.order_id
            AND s.status IN ('returning','returned','waiting_to_return'))) return_workflow,
 sum(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id=t.order_id
            AND s.status='returned')) returned,
 sum(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id=t.order_id
            AND s.status='delivered')) delivered_scan,
 sum(EXISTS(SELECT 1 FROM delivery_attempts a WHERE a.order_id=t.order_id
            AND a.outcome='delivered')) successful_attempt
FROM t;
-- 158,158,49,0,0.

WITH t AS (
 SELECT DISTINCT order_id FROM delivery_attempts
 WHERE attempt_no=3 AND outcome<>'delivered'
), s AS (
 SELECT s.*,row_number() OVER (
   PARTITION BY s.order_id ORDER BY event_at DESC,ingested_at DESC,event_id DESC
 ) rn FROM scan_events s JOIN t USING(order_id)
)
SELECT status,count(*) FROM s WHERE rn=1 GROUP BY status;
-- return_failed5,returned49,returning92,waiting_to_return12.
```

### Initial exploratory cohorts (retained for audit)

- **72%: reproducible with a narrower label.** Exactly **444/619 = 71.73%** of **seller_self orders delivered after the guaranteed Vietnamese calendar date** had first handover within `seller_prepare_days=2` elapsed days of creation, across the full release. It is not 72% of every late order. Across all channels, the corresponding delivered-late cohort is **912/1,126 = 80.99%**. At default demo cutoff, seller_self delivered-late cohort is **122/136 = 89.71%**. Existing `.scratch/research/seller-lsr-protection.md` explicitly notes 444/619 was not reproduced at the demo cutoff; full-release scope explains the difference.
- **158/158: accurate only for entering the return workflow, not completed return.** Full release has **158** distinct orders with third attempt unsuccessful. All **158** have at least one of `returning`, `returned`, `waiting_to_return`, `return_failed`. Only **49/158** have `returned`; **146/158** have `returning` or `returned`; 12 have `waiting_to_return`, 5 have `return_failed` (states may overlap). At default cutoff there are **59** third-failure orders, **0** already returned, **53** returning/returned.
- **44% of late COD orders refused: not reproduced.** Using first attempt after guaranteed date: **41/566 = 7.24%** were ever refused. Using COD orders having any attempt after guaranteed date: **131/921 = 14.22%** were refused on a late attempt (default-clock as-of: **39/263 = 14.83%**). Among late failed attempts there are **131 refused / 319 failed attempts = 41.07%**; among distinct COD orders with a late failed attempt, **131/248 = 52.82%**. None supports a general 44% statement. Do not publish 44% as verified without its original cohort/query.

Lateness uses `substr(timestamp,1,10) > guaranteed_date`, preserving the source +07:00 local calendar day. Handover duration uses `julianday` subtraction, not SQLite date conversion. First-handover aggregation is insensitive to repeated scan rows. SQL counts distinct orders where appropriate.

## Reproducible SQL

```sql
-- Full-release delivered-late handover cohort, by channel.
WITH d AS (
 SELECT order_id, min(attempt_at) delivered_at
 FROM delivery_attempts WHERE outcome='delivered' GROUP BY order_id
), h AS (
 SELECT order_id, min(event_at) handed_over_at
 FROM scan_events WHERE status='handed_over' GROUP BY order_id
)
SELECT o.channel, count(*) denominator,
 sum(julianday(h.handed_over_at)-julianday(o.created_at)<=
     CAST((SELECT value FROM policy WHERE key='seller_prepare_days') AS REAL)) numerator
FROM orders o JOIN d USING(order_id) LEFT JOIN h USING(order_id)
WHERE substr(d.delivered_at,1,10)>o.guaranteed_date
GROUP BY o.channel;

-- Third unsuccessful attempt and actual return-state evidence.
WITH t AS (
 SELECT DISTINCT order_id FROM delivery_attempts
 WHERE attempt_no=3 AND outcome<>'delivered'
)
SELECT count(*) denominator,
 sum(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id=t.order_id
            AND s.status='returned')) completed_returns,
 sum(EXISTS(SELECT 1 FROM scan_events s WHERE s.order_id=t.order_id
            AND s.status IN ('returning','returned','waiting_to_return','return_failed')))
   return_workflow
FROM t;

-- COD late attempts: distinct order population, refused on a late attempt.
SELECT count(DISTINCT a.order_id) denominator,
 count(DISTINCT CASE WHEN a.outcome='refused' THEN a.order_id END) numerator
FROM delivery_attempts a JOIN orders o USING(order_id)
WHERE o.payment_method='COD' AND substr(a.attempt_at,1,10)>o.guaranteed_date;

-- COD orders whose first delivery attempt was late, ever refused.
WITH a AS (
 SELECT order_id,min(attempt_at) first_at,
 max(CASE WHEN outcome='refused' THEN 1 ELSE 0 END) refused
 FROM delivery_attempts GROUP BY order_id
)
SELECT count(*) denominator,sum(a.refused) numerator
FROM orders o JOIN a USING(order_id)
WHERE o.payment_method='COD' AND substr(a.first_at,1,10)>o.guaranteed_date;
```

To reproduce default-clock as-of comparisons, substitute `v_orders_asof`, `v_attempts_asof`, and `v_scan_asof` for their tables. Full-release queries are retrospective analysis, not evidence that the runtime can see future events at the demo tick.
