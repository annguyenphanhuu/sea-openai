import sqlite3,pathlib,json,datetime,hashlib,collections,re
ROOT=pathlib.Path('E:/Sea_openai/sea-openai/data'); OUT=pathlib.Path(__file__).parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
paths=list(ROOT.rglob('*.sqlite')); before={str(p.relative_to(ROOT)):sha(p) for p in paths}
def connect(p):
    c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('pragma query_only=on');return c
c=connect(ROOT/'release_main/core_14d.sqlite'); o=connect(ROOT/'release_main/ops_14d.sqlite');E={'queries':{}}
def q(label,sql,args=(),db=c):
    E['queries'][label]={'sql':sql,'parameters':args,'result':[dict(r) for r in db.execute(sql,args)]}
q('policy','select * from policy')
q('cost_params','select * from cost_params')
q('policy_doc','select * from policy_doc')
q('orphan_ledger_breakdown',"select l.kind,substr(idempotency_key,1,instr(idempotency_key,':')-1) program,count(*) n,min(l.created_at) first_at,max(l.created_at) last_at from compensation_ledger l left join orders o using(order_id) where o.order_id is null group by l.kind,program")
q('matched_ledger_breakdown','select l.kind,count(*) n,count(distinct l.order_id) orders from compensation_ledger l join orders o using(order_id) group by l.kind')
q('ledger_temporal_anomalies',"select kind,count(*) n,sum(l.created_at<o.created_at) before_order,sum(substr(l.created_at,1,10)<=o.guaranteed_date) on_or_before_guarantee from compensation_ledger l join orders o using(order_id) group by kind")
q('return_temporal_anomalies','select count(*) n,sum(r.requested_at<o.created_at) before_order,sum(r.decided_at<r.requested_at) decision_before_request,sum(r.refund_vnd<0) negative_refund from returns r join orders o using(order_id)')
q('source_horizons',"select 'scan' feed,min(event_at) first_source,max(event_at) last_source,max(ingested_at) last_ingestion from scan_events union all select 'report',min(reported_at),max(reported_at),null from linehaul_reports union all select 'return',min(requested_at),max(requested_at),null from returns union all select 'ledger',min(created_at),max(created_at),null from compensation_ledger union all select 'ticket',min(created_at),max(created_at),null from tickets")
q('metric_horizon','select min(ts) first_source,max(ts) last_source,count(distinct service_id) services,count(distinct metric) metrics from metrics',db=o)
q('metric_ingest_lag_actual',"select ts,service_id,metric,value from metrics where service_id in ('tracking-ingest','kafka-tracking') and metric in ('queue_oldest_age_s','queue_lag_msgs','error_rate') and ts in ('2026-10-26T12:00:00+07:00','2026-10-28T12:00:00+07:00') order by ts,service_id,metric",db=o)
q('late_active_no_history_counts',"with latest as(select *,row_number() over(partition by order_id order by event_at desc,event_id desc) rn from scan_events where ingested_at<=:now) select count(*) n,sum(not exists(select 1 from compensation_ledger l where l.order_id=o.order_id and l.kind='voucher' and l.created_at<=:now)) no_voucher_history,sum(not exists(select 1 from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now)) no_attempts from orders o join latest s on s.order_id=o.order_id and s.rn=1 where o.created_at<=:now and (o.cancelled_at is null or o.cancelled_at>:now) and o.guaranteed_date<=:threshold and s.status not in ('delivered','returned','returning','lost','damaged','waiting_to_return','return_failed')",{'now':'2026-10-28T12:00:00+07:00','threshold':'2026-10-26'})
q('late_active_no_voucher_candidates',"with latest as(select *,row_number() over(partition by order_id order by event_at desc,event_id desc) rn from scan_events where ingested_at<=:now) select o.order_id,o.guaranteed_date,s.status,s.event_at,s.ingested_at,(select count(*) from delivery_attempts a where a.order_id=o.order_id and a.attempt_at<=:now) visible_attempts from orders o join latest s on s.order_id=o.order_id and s.rn=1 where o.created_at<=:now and (o.cancelled_at is null or o.cancelled_at>:now) and o.guaranteed_date<='2026-10-26' and s.status not in ('delivered','returned','returning','lost','damaged','waiting_to_return','return_failed') and not exists(select 1 from compensation_ledger l where l.order_id=o.order_id and l.kind='voucher' and l.created_at<=:now) order by o.order_id limit 8",{'now':'2026-10-28T12:00:00+07:00'})
q('zero_call_attempt_facts','select order_id,attempt_id,attempt_at,reason_code,call_attempts,outcome from delivery_attempts where reason_code=\'customer_unreachable\' and call_attempts=0')
q('voucher_30k_facts','select entry_id,order_id,kind,amount_vnd,created_at from compensation_ledger where kind=\'voucher\' and amount_vnd=30000 order by created_at limit 3')
q('return_visible_channel_counts',"select o.channel,count(*) n from returns r join orders o using(order_id) where r.requested_at<='2026-10-28T12:00:00+07:00' group by o.channel")
q('largest_seller_return_cases',"select o.seller_id,r.return_id,r.order_id,r.requested_at,r.reason,r.status from returns r join orders o using(order_id) where o.seller_id=(select o.seller_id from returns r join orders o using(order_id) group by o.seller_id order by count(*) desc,o.seller_id limit 1) order by r.requested_at")

# Exact ticket references only; does not infer fuzzy matches or request intent from free text.
orders={r['order_id']:r['customer_id'] for r in c.execute('select order_id,customer_id from orders')}; tracks={r['tracking_no']:r['order_id'] for r in c.execute('select tracking_no,order_id from shipments')}
stats=collections.Counter(); candidates=[]
for t in c.execute('select ticket_id,customer_id,created_at,channel,text from tickets'):
    text=t['text'].upper(); refs=set(re.findall(r'(?<![A-Z0-9])[A-Z0-9]{14}(?![A-Z0-9])',text)); direct=refs&orders.keys()
    trackmatches={oid for track,oid in tracks.items() if track.upper() in text}
    stats['total_tickets']+=1;stats['exact_order_reference_tickets']+=bool(direct);stats['exact_tracking_reference_tickets']+=bool(trackmatches)
    matching=direct|trackmatches
    good={oid for oid in matching if orders[oid]==t['customer_id']}; bad=matching-good
    stats['matching_owner_reference_tickets']+=bool(good);stats['wrong_owner_reference_tickets']+=bool(bad);stats['no_exact_reference_tickets']+=not bool(matching)
    if bad or (good and len(candidates)<8): candidates.append({'ticket_id':t['ticket_id'],'created_at':t['created_at'],'channel':t['channel'],'own_order_ids':sorted(good),'other_owner_order_ids':sorted(bad)})
E['ticket_exact_reference_coverage']=dict(stats);E['ticket_reference_candidates']=candidates
c.close();o.close();E['hashes_before']=before;E['hashes_after']={str(p.relative_to(ROOT)):sha(p) for p in paths};E['unchanged']=E['hashes_before']==E['hashes_after']
(OUT/'supplemental-evidence.json').write_text(json.dumps(E,ensure_ascii=False,indent=2),encoding='utf-8')
print('WROTE',OUT/'supplemental-evidence.json','unchanged',E['unchanged'])
