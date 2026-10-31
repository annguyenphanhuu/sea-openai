import sqlite3, pathlib, hashlib, json, datetime, re, collections
ROOT=pathlib.Path('E:/Sea_openai/sea-openai/data'); OUT=pathlib.Path(__file__).parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def open_ro(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); c.row_factory=sqlite3.Row; c.execute('pragma query_only=on'); return c
paths=list(ROOT.rglob('*.sqlite')); before={str(p.relative_to(ROOT)):sha(p) for p in paths}
core=open_ro(ROOT/'release_main/core_14d.sqlite'); ops=open_ro(ROOT/'release_main/ops_14d.sqlite')
E={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'queries':{},'dataset_docs_researched':True,'external_web_research':False}
def q(label,sql,args=(),db=core):
    E['queries'][label]={'sql':sql,'parameters':args,'result':[dict(r) for r in db.execute(sql,args)]}
    return E['queries'][label]['result']
now=core.execute('select now from sim_clock').fetchone()[0]; E['source_sim_clock']=now
q('order_channels','select channel,count(*) n from orders group by channel')
q('guaranteed_integrity',"select count(*) n,sum(guaranteed_date is null) missing,sum(length(guaranteed_date)!=10 or guaranteed_date not glob '????-??-??') malformed,sum(estimated_date!=guaranteed_date) estimated_changed,sum(substr(promised_at,1,10)!=guaranteed_date) promise_date_differs,min(guaranteed_date) min_guaranteed,max(guaranteed_date) max_guaranteed from orders")
q('attempt_reason_calls','select outcome,reason_code,call_attempts,count(*) n from delivery_attempts group by outcome,reason_code,call_attempts order by outcome,reason_code,call_attempts')
q('attempt_dates_vs_guarantee',"select reason_code,count(*) n,sum(substr(a.attempt_at,1,10)<=o.guaranteed_date) on_before_guarantee,sum(a.call_attempts=0) no_calls,sum(a.call_attempts>=3) three_calls from delivery_attempts a join orders o using(order_id) group by reason_code")
q('reports','select reason_code,reported_by,count(*) n,count(distinct trip_id) trips,min(gps_delay_min) min_delay,max(gps_delay_min) max_delay,sum(driver_note is null) missing_note from linehaul_reports group by reason_code,reported_by')
q('trip_report_coverage','select (select count(*) from linehaul_trips) trips,count(distinct trip_id) reported_trips,count(*) reports from linehaul_reports')
q('trip_link_integrity',"select count(*) trip_scans,sum(exists(select 1 from linehaul_trips t where t.trip_id=s.location_id)) matched_trips,count(distinct s.order_id) orders from scan_events s where location_type='trip'")
q('external_event_kinds','select kind,count(*) n,count(distinct province_code) provinces,sum(province_code is null) no_province,min(ts) first_ts,max(ts) last_ts from external_events group by kind')
q('ledger_kind_program',"select kind,substr(idempotency_key,1,instr(idempotency_key,':')-1) program,actor,amount_vnd,count(*) n from compensation_ledger group by kind,program,actor,amount_vnd order by kind,program,amount_vnd")
q('ledger_duplicates_per_kind','select kind,count(*) order_groups,max(n) max_per_order,sum(n>1) multi_entry_orders from (select kind,order_id,count(*) n from compensation_ledger group by kind,order_id) group by kind')
q('ledger_bad_values',"select count(*) n,sum(amount_vnd<=0) nonpositive,sum(instr(idempotency_key,':')=0) key_without_program,sum(not exists(select 1 from orders o where o.order_id=l.order_id)) orphan_order from compensation_ledger l")
q('return_channel_carrier','select o.channel,c.is_platform_owned carrier_platform_owned,count(*) return_rows,count(distinct r.order_id) orders,count(distinct o.seller_id) sellers from returns r join orders o using(order_id) join carriers c using(carrier_id) group by o.channel,c.is_platform_owned')
q('return_reason_status','select reason,status,count(*) n from returns group by reason,status')
q('return_by_seller','select o.seller_id,count(*) n from returns r join orders o using(order_id) group by o.seller_id order by n desc,o.seller_id')
q('scan_ingest_lag','select count(*) n,sum(ingested_at<event_at) negative_lag,sum((julianday(ingested_at)-julianday(event_at))*86400>1800.00001) lag_gt_30m,min((julianday(ingested_at)-julianday(event_at))*86400) min_lag_s,max((julianday(ingested_at)-julianday(event_at))*86400) max_lag_s from scan_events')
q('scan_lag_by_day',"select substr(event_at,1,10) day,count(*) n,sum((julianday(ingested_at)-julianday(event_at))*86400>1800.00001) lag_gt_30m from scan_events group by day")
q('scan_lag_by_carrier','select o.carrier_id,count(*) n,sum((julianday(s.ingested_at)-julianday(s.event_at))*86400>1800.00001) lag_gt_30m,sum(s.carrier_event_id is null) no_carrier_event_id from scan_events s join orders o using(order_id) group by o.carrier_id')
q('scan_out_of_order',"with x as(select order_id,event_id,event_at,ingested_at,max(event_at) over(partition by order_id order by ingested_at,event_id rows between unbounded preceding and 1 preceding) previous_max_event from scan_events) select count(*) out_of_order_rows,count(distinct order_id) orders from x where event_at<previous_max_event")
q('duplicate_carrier_events','select count(*) duplicated_ids,sum(n-1) excess_rows,max(n) max_multiplicity from(select carrier_event_id,count(*) n from scan_events where carrier_event_id is not null group by carrier_event_id having count(*)>1)')
q('webhook_processing','select count(*) n,sum(processed_at is null) unprocessed,sum(processed_at<received_at) negative_processing_delay,max((julianday(processed_at)-julianday(received_at))*86400) max_processing_s from webhook_inbox',db=ops)
q('webhook_duplicates','select count(*) duplicated_ids,sum(n-1) excess_rows,max(n) max_multiplicity from(select carrier_event_id,count(*) n from webhook_inbox group by carrier_event_id having count(*)>1)',db=ops)
q('metrics_series','select service_id,metric,count(*) n,min(ts) first_ts,max(ts) last_ts,min(value) min_value,max(value) max_value from metrics group by service_id,metric',db=ops)
q('metric_source_gaps',"with x as(select service_id,metric,ts,lag(ts) over(partition by service_id,metric order by ts) previous_ts from metrics) select service_id,metric,max((julianday(ts)-julianday(previous_ts))*86400) max_gap_s,sum((julianday(ts)-julianday(previous_ts))*86400>1800.00001) gaps_gt_30m from x group by service_id,metric",db=ops)

# Explicit joins include undeclared business relationships, rather than assuming PRAGMA covers them.
relationship_pairs=[('scan_events','order_id','orders','order_id'),('delivery_attempts','order_id','orders','order_id'),('returns','order_id','orders','order_id'),('compensation_ledger','order_id','orders','order_id'),('orders','ship_ward_code','wards','ward_code'),('inventory_events','product_id','products','product_id'),('inventory_events','warehouse_id','warehouses','warehouse_id'),('inventory_snapshots','product_id','products','product_id'),('inventory_snapshots','warehouse_id','warehouses','warehouse_id'),('external_events','province_code','provinces','province_code'),('shipments','carrier_id','carriers','carrier_id')]
for relpath in ['release_main/core_14d.sqlite','tiny/core.sqlite']:
    c=open_ro(ROOT/relpath)
    for a,ac,b,bc in relationship_pairs:
        q(relpath+':relationship:'+a+'.'+ac,'select count(*) orphan_rows from '+a+' a where a.'+ac+' is not null and not exists(select 1 from '+b+' b where b.'+bc+'=a.'+ac+')',db=c)
    q(relpath+':scan_order_shipment_mismatch','select count(*) n from scan_events s join shipments h using(shipment_id) where s.order_id!=h.order_id',db=c)
    q(relpath+':items_seller_mismatch','select count(*) n from order_items i join orders o using(order_id) join products p using(product_id) where o.seller_id!=p.seller_id',db=c)
    c.close()

for at in [now,'2026-10-26T12:00:00+07:00','2026-10-26T12:30:00+07:00','2026-10-28T12:30:00+07:00','2026-10-31T12:00:00+07:00','2026-11-02T12:00:00+07:00','2026-11-08T23:59:59+07:00']:
    q('visibility:'+at,"select (select count(*) from orders where created_at<=?) orders,(select count(*) from scan_events where ingested_at<=?) scans_visible,(select count(*) from scan_events where event_at<=? and ingested_at>?) occurred_hidden,(select count(*) from scan_events where ingested_at<=? and event_at>?) visible_future_event,(select count(*) from compensation_ledger where created_at<=?) ledger_visible,(select count(*) from returns where requested_at<=?) returns_visible",(at,)*8)
    q('feed_max_source:'+at,'select service_id,metric,max(ts) latest_source_at,(julianday(?)-julianday(max(ts)))*86400 age_s from metrics where ts<=? group by service_id,metric',(at,at),db=ops)
    q('late_calendar:'+at,"select count(*) visible_orders,sum(guaranteed_date<substr(?,1,10)) past_guarantee,sum(cast(julianday(substr(?,1,10))-julianday(guaranteed_date) as int)>=2) calendar_late_ge2 from orders where created_at<=?",(at,at,at))

# Candidate facts are evidence, not an assertion that all financial gates are satisfied.
base="""with visible as (select * from orders where created_at<=:now), latest as (select s.*,row_number() over(partition by order_id order by event_at desc,event_id desc) rn from scan_events s where ingested_at<=:now)
select o.order_id,o.guaranteed_date,o.created_at,o.channel,o.carrier_id,s.status latest_scan_status,s.event_at latest_event_at,s.ingested_at latest_ingested_at,
cast(julianday(substr(:now,1,10))-julianday(o.guaranteed_date) as int) calendar_late_days,
(select count(*) from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now) visible_attempts,
(select count(*) from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now and a.reason_code='customer_unreachable' and a.call_attempts=0) unreachable_no_calls,
(select count(*) from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now and a.reason_code in ('customer_unreachable','customer_refused','reschedule_requested','wrong_address') and a.call_attempts>=3) customer_reason_three_calls,
(select group_concat(distinct kind) from compensation_ledger l where l.order_id=o.order_id and l.created_at<=:now) historical_kinds
from visible o left join latest s on s.order_id=o.order_id and s.rn=1 where {condition} order by o.order_id limit 8"""
conditions={
'late_ge2_active_no_attempts':"cast(julianday(substr(:now,1,10))-julianday(o.guaranteed_date) as int)>=2 and (o.cancelled_at is null or o.cancelled_at>:now) and s.status not in ('delivered','returned','returning','lost','damaged','waiting_to_return','return_failed') and not exists(select 1 from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now)",
'late_ge2_historical_voucher':"cast(julianday(substr(:now,1,10))-julianday(o.guaranteed_date) as int)>=2 and exists(select 1 from compensation_ledger l where l.order_id=o.order_id and l.kind='voucher' and l.created_at<=:now)",
'late1_active':"cast(julianday(substr(:now,1,10))-julianday(o.guaranteed_date) as int)=1 and (o.cancelled_at is null or o.cancelled_at>:now) and s.status not in ('delivered','returned','returning','lost','damaged','waiting_to_return','return_failed')",
'not_late_active':"o.guaranteed_date>=substr(:now,1,10) and (o.cancelled_at is null or o.cancelled_at>:now)",
'unreachable_without_calls':"exists(select 1 from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now and a.reason_code='customer_unreachable' and a.call_attempts=0)",
'customer_reason_three_calls':"exists(select 1 from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now and a.reason_code in ('customer_unreachable','customer_refused','reschedule_requested','wrong_address') and a.call_attempts>=3)"
}
for label,condition in conditions.items(): q('candidates:'+label,base.format(condition=condition),{'now':now})
q('hidden_scan_candidates',"select event_id,order_id,status,event_at,ingested_at,(julianday(ingested_at)-julianday(event_at))*86400 lag_s from scan_events where event_at<=? and ingested_at>? order by ingested_at desc limit 8",('2026-10-26T12:00:00+07:00',)*2)
q('force_majeure_link_candidates',"select distinct s.order_id,s.event_id,s.event_at,s.ingested_at,r.trip_id,r.report_id,r.reason_code,r.reported_at,r.gps_delay_min from scan_events s join linehaul_reports r on s.location_type='trip' and s.location_id=r.trip_id where r.reason_code in ('weather','route_closure') and s.ingested_at<=? and r.reported_at<=? order by s.order_id limit 8",(now,now))

# Visit every row in every source table, validate every non-null temporal field, and validate JSON without publishing free text.
E['all_rows_scanned']={}; E['timestamp_integrity']={}; E['json_integrity']={}
for p in paths:
    c=open_ro(p); rel=str(p.relative_to(ROOT)); totals={}; temporal={}; jsons={}
    for table, in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"):
        columns=[r['name'] for r in c.execute('pragma table_info("'+table+'")')]
        timecols=[x for x in columns if x.endswith(('_at','_date')) or x in ('now','ts')]
        n=0
        for row in c.execute('select * from "'+table+'"'):
            n+=1
            for col in timecols:
                key=table+'.'+col; st=temporal.setdefault(key,{'nonnull':0,'invalid':0,'non_plus07_timestamp':0})
                val=row[col]
                if val is None: continue
                st['nonnull']+=1
                try:
                    parsed=datetime.datetime.fromisoformat(val) if 'T' in val else datetime.date.fromisoformat(val)
                    if 'T' in val and not val.endswith('+07:00'): st['non_plus07_timestamp']+=1
                except (ValueError,TypeError): st['invalid']+=1
            if 'fields_json' in columns and row['fields_json'] is not None:
                st=jsons.setdefault(table+'.fields_json',{'nonnull':0,'invalid':0}); st['nonnull']+=1
                try: json.loads(row['fields_json'])
                except (ValueError,TypeError): st['invalid']+=1
        totals[table]=n
    E['all_rows_scanned'][rel]=totals; E['timestamp_integrity'][rel]=temporal; E['json_integrity'][rel]=jsons;c.close()

core.close();ops.close(); E['hashes_before']=before; E['hashes_after']={str(p.relative_to(ROOT)):sha(p) for p in paths}; E['all_databases_unchanged']=E['hashes_before']==E['hashes_after']
E['manifests']={str(p.relative_to(ROOT)):p.read_text(encoding='utf-8') for p in ROOT.rglob('manifest.sha256')}
(OUT/'business-evidence.json').write_text(json.dumps(E,ensure_ascii=False,indent=2),encoding='utf-8')
print('WROTE',OUT/'business-evidence.json','queries',len(E['queries']),'rows visited',sum(sum(v.values()) for v in E['all_rows_scanned'].values()),'unchanged',E['all_databases_unchanged'])
