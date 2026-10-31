"""Read-only release evidence and explicit, audited staff verification.

Missing source facts never establish absence of force majeure. Only an
authorized human caller may submit a review; the HTTP layer owns staff auth.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from care_truc.policy import signals
from care_truc.runtime_types import canonical as care_canonical
from logistics_an_nguyen.replay import ReleaseReader
from .state import canonical, current_clock, immediate, utc

EVIDENCE_PRODUCER = 'demo-release-v1'
MESSAGE_RECORDER = 'demo-care-v1'
REQUEST_RULE = 'care-signals-v1'
_VN = timezone(timedelta(hours=7))


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _rows(conn, sql, args=()):
    cursor = conn.execute(sql, args)
    return [dict(zip((column[0] for column in cursor.description), row)) for row in cursor]


class DemoEvidence:
    def __init__(self, conn, core_path, ops_path):
        self.conn = conn
        self.core_path, self.ops_path = Path(core_path), Path(ops_path)
        row = conn.execute('SELECT run_id,source_identity_json FROM run_metadata WHERE singleton=1').fetchone()
        if row is None:
            raise ValueError('runtime_not_initialized')
        self.run_id, identity = row
        self.identity = json.loads(identity)
        for name, path in (('core', self.core_path), ('ops', self.ops_path)):
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != self.identity[name + '_sha256']:
                raise ValueError('source_identity_mismatch')

    def inspect_order(self, order_id, now):
        utc(now)
        if not (_instant(self.identity['coverage_start']) <= now <= _instant(self.identity['coverage_end'])):
            raise ValueError('outside_source_coverage')
        cutoff = now.astimezone(_VN).isoformat(timespec='seconds')
        # ReleaseReader establishes mode=ro and query_only. Bounded allowlisted
        # projections preserve its ingestion cutoff without loading all orders.
        with ReleaseReader(self.core_path) as reader:
            db = reader.connection
            orders = _rows(db, 'SELECT order_id,customer_id,seller_id,created_at,guaranteed_date,items_value_vnd,payment_method, '
                           'CASE WHEN cancelled_at<=? THEN cancelled_at END AS cancelled_at,dest_station_id,warehouse_id '
                           'FROM orders WHERE order_id=? AND created_at<=?', (cutoff, order_id, cutoff))
            if not orders:
                raise ValueError('order_not_visible')
            order = orders[0]
            scans = _rows(db, 'SELECT event_id,status,location_type,location_id,event_at,ingested_at FROM scan_events '
                          'WHERE order_id=? AND ingested_at<=? AND event_at<=? ORDER BY event_at,event_id', (order_id, cutoff, cutoff))
            attempts = _rows(db, 'SELECT attempt_id,attempt_at,outcome,reason_code,call_attempts FROM delivery_attempts '
                             'WHERE order_id=? AND attempt_at<=? ORDER BY attempt_at,attempt_id', (order_id, cutoff))
            history_rows = _rows(db, 'SELECT entry_id,kind,created_at FROM compensation_ledger WHERE order_id=? AND created_at<=? ORDER BY created_at,entry_id', (order_id, cutoff))
            trips = sorted({s['location_id'] for s in scans if s['location_type'] == 'trip' and s['location_id']})
            reports = []
            for trip in trips:
                reports.extend(_rows(db, 'SELECT report_id,trip_id,reported_at,reason_code,driver_note FROM linehaul_reports WHERE trip_id=? AND reported_at<=? ORDER BY reported_at,report_id', (trip, cutoff)))
            provinces = set()
            for table, key, location in [('stations', 'station_id', order['dest_station_id']), ('warehouses', 'warehouse_id', order['warehouse_id'])] + [
                    ('sorting_centers', 'sc_id', scan['location_id']) for scan in scans if scan['location_type'] == 'sorting_center']:
                if location:
                    found = db.execute(f'SELECT province_code FROM {table} WHERE {key}=?', (location,)).fetchone()
                    if found:
                        provinces.add(found[0])
            external = _rows(db, 'SELECT event_id,ts,kind,province_code,title,detail FROM external_events WHERE ts>=? AND ts<=? ORDER BY ts,event_id', (order['created_at'], cutoff))
            external = [event for event in external if event['province_code'] is None or event['province_code'] in provinces]
        order.pop('dest_station_id'); order.pop('warehouse_id')
        order['delivered_at'] = next((s['event_at'] for s in scans if s['status'] == 'delivered'), None)
        evidence = [{'ref': f'core:orders:{order_id}', 'source_table': 'orders', 'record_id': order_id, 'data': order}]
        for table, rows, key in [('scan_events', scans, 'event_id'), ('delivery_attempts', attempts, 'attempt_id'),
                                  ('compensation_ledger', history_rows, 'entry_id'), ('linehaul_reports', reports, 'report_id'), ('external_events', external, 'event_id')]:
            evidence.extend({'ref': f'core:{table}:{row[key]}', 'source_table': table, 'record_id': row[key], 'data': row} for row in rows)
        history = {kind: 'already_granted' if any(row['kind'] == kind for row in history_rows) else 'not_granted' for kind in ('coins', 'voucher')}
        known = {'coins','voucher','refund','shipping_fee_refund','priority_push','eta_notice','carrier_switch','cancel_unlock'}
        if any(row['kind'] not in known for row in history_rows):
            history = {kind: 'already_granted' if state == 'already_granted' else 'unknown' for kind, state in history.items()}
        material = _hash({'order': order, 'evidence': evidence, 'history': history})
        customer_fault = any((a['outcome'], a['reason_code']) in {('no_answer','customer_unreachable'), ('refused','customer_refused'), ('rescheduled','reschedule_requested')}
                             and (a['call_attempts'] or 0) >= (3 if a['outcome'] == 'no_answer' else 1) for a in attempts)
        responsibility, fm, review_id = ('customer' if customer_fault else 'unknown'), 'unknown', None
        reviews = _rows(self.conn, 'SELECT * FROM eligibility_reviews WHERE order_id=? ORDER BY revision DESC LIMIT 1', (order_id,))
        if reviews:
            review = reviews[0]
            if (review['state'] == 'active'
                    and json.loads(review['source_identity_json']) == self.identity
                    and json.loads(review['material_fingerprints_json']) == {'material': material}
                    and _instant(review['evidence_as_of']) <= now):
                decision = json.loads(review['decision_json'])
                responsibility = 'customer' if customer_fault else decision['responsibility']
                fm, review_id = decision['force_majeure'], review['review_id']
        endpoint = now if order['delivered_at'] is None else _instant(order['delivered_at'])
        ready = review_id is not None and responsibility in ('carrier', 'platform') and fm == 'absent'
        return {'order': order, 'as_of': utc(now), 'source_identity': self.identity,
                'late_days': max(0, (endpoint.astimezone(_VN).date() - date.fromisoformat(order['guaranteed_date'])).days),
                'responsibility': responsibility, 'force_majeure': fm, 'verification_required': review_id is None,
                'review_id': review_id, 'evidence_ready': ready, 'history': history,
                'evidence': evidence, 'evidence_refs': [e['ref'] for e in evidence], 'material_fingerprint': material}

    def verify(self, order_id, now, *, reviewed_by, reason, responsibility, force_majeure, evidence_refs):
        if not isinstance(reviewed_by, str) or not reviewed_by.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('review_identity_and_reason_required')
        if responsibility not in ('carrier', 'platform', 'customer', 'unknown') or force_majeure not in ('absent', 'present', 'unknown'):
            raise ValueError('invalid_review_decision')
        facts = self.inspect_order(order_id, now)
        if (not isinstance(evidence_refs, (tuple, list)) or not evidence_refs
                or any(not isinstance(ref, str) or ref not in facts['evidence_refs'] for ref in evidence_refs)):
            raise ValueError('evidence_refs_must_belong_to_visible_order')
        if current_clock(self.conn)[0] != now:
            raise ValueError('stale_review')
        review_id = uuid4().hex
        decision = {'responsibility': responsibility, 'force_majeure': force_majeure}
        with immediate(self.conn):
            revision = self.conn.execute('SELECT coalesce(max(revision),0)+1 FROM eligibility_reviews WHERE order_id=?', (order_id,)).fetchone()[0]
            self.conn.execute('INSERT INTO eligibility_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (review_id, order_id, revision, 'active', canonical(self.identity), utc(now), canonical({'material': facts['material_fingerprint']}),
                 canonical(decision), canonical(evidence_refs), reason.strip(), reviewed_by.strip(), utc(datetime.now(timezone.utc)),
                 f'review:{review_id}', _hash({'order_id': order_id, 'decision': decision, 'refs': evidence_refs})))
        return self.inspect_order(order_id, now)

    def record_text(self, care_store, proposal, now, assessment=None):
        """Bind persisted customer intent and delivered A1 contact to source facts."""
        row = care_store.db.execute('SELECT e.data,r.payload,r.phase,r.principal,r.session_id,r.id FROM evidence_bundles e JOIN requests r ON r.id=e.request_id WHERE e.ref=?', (proposal.evidence_ref,)).fetchone()
        if row is None:
            raise ValueError('care_evidence_missing')
        bundle, event = json.loads(row['data']), json.loads(row['payload'])
        session = bundle['session']
        state = care_store.load_session(proposal.session_id)
        if (row['phase'] != 'committed' or row['session_id'] != proposal.session_id
                or row['principal'] != state.principal_id or bundle['event'] != event
                or session['session_id'] != state.session_id or session['run_id'] != self.run_id
                or state.run_id != self.run_id or state.order_id != proposal.order_id
                or session['order_id'] != proposal.order_id or session['principal_id'] != state.principal_id
                or state.channel != 'chat' or state.opened_by != 'a1'
                or session['channel'] != 'chat' or session['opened_by'] != 'a1'
                or session['contact_id'] != state.contact_id
                or care_canonical(proposal) not in [care_canonical(item) for item in bundle['proposals']]):
            raise ValueError('care_provenance_invalid')
        effect = care_store.effect(proposal.effect_id)
        if effect is None or care_canonical(json.loads(effect['proposal'])) != care_canonical(proposal):
            raise ValueError('care_proposal_not_persisted')
        snapshot = bundle.get('snapshot', {})
        if not snapshot.get('cutoff') or _instant(snapshot['cutoff']) != now or current_clock(self.conn)[0] != now:
            raise ValueError('care_assessment_stale')
        delivered = [item for item in care_store.effects() if item['session_id'] == state.session_id
                     and item['outcome'] == 'succeeded' and json.loads(item['proposal'])['kind'] == 'contact_send']
        if not delivered:
            raise ValueError('a1_delivery_missing')
        action = json.loads(proposal.payload)
        if action['order_id'] != state.order_id or action['evidence_ref'] != proposal.evidence_ref:
            raise ValueError('care_action_invalid')
        facts = self.inspect_order(state.order_id, now)
        contact = _rows(self.conn, 'SELECT * FROM contact_log WHERE contact_id=?', (state.contact_id,))
        if (not contact or contact[0]['order_id'] != state.order_id or contact[0]['initiated_by'] != 'A1'
                or contact[0]['channel'] != 'chat' or contact[0]['status'] != 'active'
                or contact[0]['provider_session_id'] != state.session_id
                or not (_instant(contact[0]['requested_at']) <= _instant(contact[0]['opened_at']) <= now)):
            raise ValueError('a1_delivery_missing')
        is_coins = action['kind'] == 'coins'
        if is_coins:
            if event['kind'] != 'message' or not signals(event.get('text') or '')[2]:
                raise ValueError('explicit_coins_text_required')
            body, request_code = event['text'], 'late_compensation'
        elif action['kind'] == 'cancel_request':
            pending = session.get('pending')
            if (not pending or action.get('confirmation_id') != pending['confirmation_id']
                    or now >= _instant(pending['expires_at'])
                    or not ((event['kind'] == 'confirm_cancel' and event.get('confirmation_id') == pending['confirmation_id'])
                            or (event['kind'] == 'message' and signals(event.get('text') or '')[0] == 'accept' and event.get('reply_to') == pending['reply_to']))):
                raise ValueError('cancel_confirmation_invalid')
            prior = care_store.db.execute("SELECT content FROM events WHERE id=? AND session_id=? AND kind='response'", (pending['reply_to'], state.session_id)).fetchone()
            if prior is None or json.loads(prior[0]).get('confirmation_id') != pending['confirmation_id']:
                raise ValueError('cancel_prior_confirmation_missing')
            facts['cancellation'] = {'confirmed': True, 'confirmation_id': pending['confirmation_id'],
                                     'request_id': row['id'], 'reply_to': pending['reply_to'], 'expires_at': pending['expires_at']}
            body, request_code = event.get('text') or 'confirm_cancel:' + pending['confirmation_id'], None
        else:
            raise ValueError('action_kind_not_supported')
        payload = {'schema_version': 1, 'run_id': self.run_id, 'source_identity': self.identity,
                   'order': facts['order'], 'responsibility': facts['responsibility'], 'force_majeure': facts['force_majeure'],
                   'history': facts['history'], 'review_id': facts['review_id'], 'source_refs': facts['evidence_refs'],
                   'care_request_id': row['id']}
        if 'cancellation' in facts:
            payload['cancellation'] = facts['cancellation']
        message_id, evidence_id = f'care:{row["id"]}', f'demo:{row["id"]}:{_hash(payload)}'
        text = canonical(payload)
        with immediate(self.conn):
            self.conn.execute('INSERT OR IGNORE INTO customer_messages VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                (message_id, state.contact_id, state.order_id, facts['order']['customer_id'], 'text', utc(now), utc(now), body, request_code, REQUEST_RULE, MESSAGE_RECORDER))
            self.conn.execute('INSERT OR IGNORE INTO execution_evidence VALUES (?,?,?,?,?,?,?,?,?,?)',
                (evidence_id, state.order_id, state.contact_id, message_id, utc(now), utc(now), 'huy-demo-v1', text, hashlib.sha256(text.encode('utf-8')).hexdigest(), EVIDENCE_PRODUCER))
        return evidence_id
