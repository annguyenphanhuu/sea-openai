"""Synchronous HTTP adapter over the actual local A3/A2/A1 runtime.

Both SQLite writers live on one event loop thread. HTTP threads never touch
connections, authenticated contexts, or producer allowlists directly.
"""
import asyncio
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Thread
import time
from uuid import uuid4

from care_truc.lifecycle import CareRuntime
from care_truc.ports import SystemClock
from care_truc.runtime_types import (CareError, ContextSnapshot, FeedSnapshot,
    GateDecision, GuardSnapshot, Receipt, TrustedRequestContext, TurnResult, canonical, fingerprint)
from contracts.params import late_xu_for, p_contact
from contracts.types import STATUSES, ContactTask, OrderAssessment
from logistics_an_nguyen.adapter import ReleaseAdapter, REQUIRED_FEEDS
from logistics_an_nguyen.models import parse_instant
from logistics_an_nguyen.progress import ProgressTracker
from logistics_an_nguyen.replay import ReleaseReader
from logistics_an_nguyen.service import assessment_payload, evaluate_tick

from . import sysguard
from .dto import ServerContext, SourceIdentity
from .effect_gateway import SqliteEffectGateway
from .state import bootstrap, connect_state, immediate, utc
from .state_store import SqliteStateStore


_VN = timezone(timedelta(hours=7))
_START = datetime(2026, 10, 24, 14, tzinfo=_VN)
_CANDIDATE = '261021ZS7E76FW'
_LOST_CANDIDATE = '261019QY8UDYNZ'


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class _Context:
    supports_deadlines = True

    def __init__(self, flow):
        self.flow = flow

    async def authorize(self, ctx, order_id):
        proof = self.flow._inspect(order_id)
        if ctx.principal_id != self.flow._principal(proof):
            raise CareError('forbidden', 403)

    async def load(self, ctx, order_id):
        await self.authorize(ctx, order_id)
        flow = self.flow
        proof = flow._inspect(order_id)
        assessment = flow.assessments.get(order_id)
        # Keep raw A2 output intact. This runtime overlay exists only after an
        # explicit audited per-order staff decision bound to source evidence.
        if assessment and proof.get('evidence_ready'):
            assessment = replace(assessment, fault_party=proof['responsibility'])
        heartbeat = flow.conn.execute(
            "SELECT tick_at FROM guard_heartbeat WHERE agent_id='A3' ORDER BY tick_at DESC LIMIT 1"
        ).fetchone()
        health = flow._health()
        allowed = flow._allowed()
        guard = GuardSnapshot('a3', None if heartbeat is None else parse_instant(heartbeat[0], 'heartbeat'),
            tuple(FeedSnapshot(h.feed, h.status, h.source_timestamp) for h in health),
            REQUIRED_FEEDS, allowed, allowed)
        sent = flow.conn.execute("SELECT 1 FROM contact_log WHERE order_id=? AND initiated_by='A1' "
                                 "AND status IN ('active','completed')", (order_id,)).fetchone() is not None
        history = proof['history']['coins']
        granted = flow.platform.has_grant('coins', order_id) or history == 'already_granted'
        cancel_evidence = False
        if getattr(flow, 'care', None) is not None:
            # Cancellation creates a staff review request. Its evidence is the
            # persisted second customer confirmation, independent of a benefit
            # responsibility/FM review. The executor verifies that confirmation.
            cancel_evidence = flow.care.store.db.execute(
                "SELECT 1 FROM sessions WHERE order_id=? AND principal=? "
                "AND json_type(data,'$.pending')='object' UNION ALL "
                "SELECT 1 FROM pending_effects p JOIN sessions s ON s.id=p.session_id "
                "WHERE s.order_id=? AND s.principal=? AND p.outcome='unknown' "
                "AND json_extract(p.proposal,'$.kind')='action_request' "
                "AND json_extract(json_extract(p.proposal,'$.payload'),'$.kind')='cancel_request' LIMIT 1",
                (order_id, ctx.principal_id, order_id, ctx.principal_id)).fetchone() is not None
        extra = {}
        if any(field.name == 'ledger_pending' for field in fields(ContextSnapshot)):
            pending = flow.conn.execute("SELECT 1 FROM outbox WHERE order_id=? AND kind='coins' "
                "AND status IN ('pending','claimed')", (order_id,)).fetchone() is not None
            extra['ledger_pending'] = pending
        return ContextSnapshot(ctx.principal_id, order_id, flow.now, assessment, guard,
            proof['order']['items_value_vnd'], granted if history != 'unknown' else None,
            sent, bool(proof.get('evidence_ready')) or cancel_evidence, **extra)


class _Gate:
    supports_deadlines = True

    def __init__(self, flow):
        self.flow = flow

    async def check(self, proposal, ctx, *, deadline):
        state = self.flow.care.store.load_session(proposal.session_id)
        snapshot = await self.flow.context.load(ctx, state.order_id)
        decision = self.flow.care.harness.guards.validate_dispatch(proposal, snapshot)
        if proposal.kind == 'action_request' and json.loads(proposal.payload)['kind'] == 'cancel_request':
            if self.flow._lost(state.order_id):
                decision = GateDecision(False, ('lost_order_cannot_cancel',))
        self.flow.gate_decisions[proposal.effect_id] = asdict(decision)
        return decision


class _Gateway:
    supports_deadlines = True
    idempotent = True

    def __init__(self, flow):
        self.flow = flow

    def _financial(self, proposal):
        flow = self.flow
        state = flow.care.store.load_session(proposal.session_id)
        proof = flow._inspect(state.order_id)
        binding = flow.conn.execute('SELECT platform_ref FROM demo_evidence_bindings WHERE care_ref=?',
                                    (proposal.evidence_ref,)).fetchone()
        if binding:
            raw = binding[0]
        else:
            raw = flow.evidence.record_text(flow.care.store, proposal, flow.now,
                                           assessment=flow.assessments.get(state.order_id))
            flow.conn.execute('INSERT INTO demo_evidence_bindings VALUES (?,?)', (proposal.evidence_ref, raw))
        return SqliteEffectGateway(flow.platform, flow.care.store,
            context=ServerContext('demo-care-service', 'a1', proof['order']['customer_id'], None,
                                  frozenset({'actions:coins', 'actions:cancel_request'})),
            customer_principal=state.principal_id, evidence_bindings={proposal.evidence_ref: raw})

    async def submit(self, proposal, *, deadline):
        flow = self.flow
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError('deadline_exceeded')
            if proposal.kind == 'action_request':
                return await self._financial(proposal).submit(proposal, deadline=deadline)
            state = flow.care.store.load_session(proposal.session_id)
            persisted = flow.care.store.effect(proposal.effect_id)
            if persisted is None or persisted['attempts'] < 1 or persisted['proposal'] != canonical(proposal):
                raise CareError('effect_binding_invalid', 403)
            if proposal.kind == 'contact_send':
                payload = json.loads(proposal.payload)
                with immediate(flow.conn):
                    # Recheck under the same write transaction that makes the
                    # message available in the inbox. Earlier async guard/gate
                    # snapshots cannot authorize delivery after a runtime kill.
                    if not flow._allowed():
                        raise CareError('proactive_blocked', 409)
                    customer = flow._inspect(state.order_id)['order']['customer_id']
                    if flow._contacted_today(customer, excluding=state.contact_id):
                        raise CareError('customer_daily_contact_limit', 409)
                    timestamp = utc(flow.now)
                    flow.conn.execute(
                        "INSERT OR IGNORE INTO contact_log(contact_id,order_id,channel,initiated_by,status,"
                        "requested_at,opened_at,guard_checked_at,provider_session_id) "
                        "VALUES (?,?,'chat','A1','active',?,?,?,?)",
                        (state.contact_id, state.order_id, timestamp, timestamp, timestamp, state.session_id))
                    flow.conn.execute('INSERT OR IGNORE INTO demo_inbox VALUES (?,?,?,?,?,?)',
                        (proposal.effect_id, proposal.key, state.session_id, state.order_id,
                         payload['text'], timestamp))
                remote = 'web-inbox:' + proposal.effect_id
            elif proposal.kind == 'handoff_request':
                with immediate(flow.conn):
                    flow.conn.execute('INSERT OR IGNORE INTO demo_handoffs VALUES (?,?,?,?)',
                        (proposal.effect_id, state.session_id, proposal.payload, utc(flow.now)))
                remote = 'staff-inbox:' + proposal.effect_id
            else:
                raise CareError('effect_kind_not_supported', 409)
            return Receipt(proposal.effect_id, proposal.key, fingerprint(proposal.payload),
                           1, 'succeeded', remote)
        except Exception as error:
            flow.gateway_errors.append({'effect_id': proposal.effect_id, 'code': str(error)})
            raise

    async def lookup(self, key, *, deadline):
        flow = self.flow
        row = flow.care.store.db.execute('SELECT proposal FROM pending_effects WHERE effect_key=?', (key,)).fetchone()
        if row is None:
            return None
        from care_truc.runtime_types import EffectProposal
        proposal = EffectProposal(**json.loads(row[0]))
        if proposal.kind == 'action_request':
            return await self._financial(proposal).lookup(key, deadline=deadline)
        table = 'demo_inbox' if proposal.kind == 'contact_send' else 'demo_handoffs'
        exists = flow.conn.execute(f'SELECT 1 FROM {table} WHERE effect_id=?', (proposal.effect_id,)).fetchone()
        if exists is None:
            return None
        prefix = 'web-inbox:' if proposal.kind == 'contact_send' else 'staff-inbox:'
        return Receipt(proposal.effect_id, proposal.key, fingerprint(proposal.payload), 1,
                       'succeeded', prefix + proposal.effect_id)


class DemoFlow:
    def __init__(self, core_path, state_path, start_at=None, ops_path=None):
        self.core_path = Path(core_path).resolve(strict=True)
        self.ops_path = Path(ops_path or self.core_path.with_name('ops_14d.sqlite')).resolve(strict=True)
        self.state_path = Path(state_path).resolve()
        for source in (self.core_path, self.ops_path):
            if self.state_path == source or (self.state_path.exists() and self.state_path.samefile(source)):
                raise ValueError('Runtime must be separate from release inputs')
        if any(parent.name.lower() == 'data' for parent in self.state_path.parents):
            raise ValueError('Runtime must be outside data directories')
        self.start_at = start_at
        self.closed = False
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self._run_loop, name='sea-demo-flow', daemon=True)
        self.thread.start()
        try:
            asyncio.run_coroutine_threadsafe(self._start(), self.loop).result(timeout=120)
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)
            raise

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    async def _start(self):
        self.lock = asyncio.Lock()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = connect_state(self.state_path)
        self.reader = ReleaseReader(self.core_path)
        metadata = self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='run_metadata'").fetchone()
        start = self.start_at or _START
        self.run_id = 'demo-' + hashlib.sha256(str(self.state_path).encode()).hexdigest()[:24]
        if metadata:
            saved = self.conn.execute('SELECT start_at FROM run_metadata WHERE singleton=1').fetchone()
            if self.start_at is None:
                start = parse_instant(saved[0], 'start_at')
        coverage = self.reader.connection.execute('SELECT min(created_at),max(created_at) FROM orders').fetchone()
        identity = SourceIdentity(_hash(self.core_path), _hash(self.ops_path),
            parse_instant(coverage[0], 'coverage_start'), parse_instant(coverage[1], 'coverage_end'))
        bootstrap(self.conn, run_id=self.run_id, identity=identity, start_at=start)
        row = self.conn.execute('SELECT current_at FROM demo_clock WHERE singleton=1').fetchone()
        self.now = start if row[0] is None else parse_instant(row[0], 'current_at').astimezone(_VN)
        if row[0] is None:
            self.conn.execute('UPDATE demo_clock SET current_at=? WHERE singleton=1', (utc(self.now),))
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_inbox(effect_id TEXT PRIMARY KEY,effect_key TEXT UNIQUE,session_id TEXT,order_id TEXT,body TEXT,created_at TEXT)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_handoffs(effect_id TEXT PRIMARY KEY,session_id TEXT,payload TEXT,created_at TEXT)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_evidence_bindings(care_ref TEXT PRIMARY KEY,platform_ref TEXT NOT NULL)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_flow_snapshot(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload TEXT NOT NULL)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_a2_handoff(singleton INTEGER PRIMARY KEY CHECK(singleton=1),payload TEXT NOT NULL)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_tick_timings(tick_at TEXT,ordinal INTEGER,agent TEXT,started_at TEXT,finished_at TEXT,duration_ms REAL,status TEXT,detail_json TEXT,PRIMARY KEY(tick_at,agent))')
        self.platform = SqliteStateStore(self.conn,
            evidence_producers=frozenset({'demo-release-v1'}),
            message_recorders=frozenset({'demo-care-v1'}),
            request_rule_versions=frozenset({'care-signals-v1'}))
        from .demo_provenance import DemoEvidence
        self.evidence = DemoEvidence(self.conn, self.core_path, self.ops_path)
        self.world = self.reader.snapshot(self.now)
        self._cached_health = tuple(sysguard.health_for(self.world, self.conn, self.now))
        self.assessments = {}
        self.handoff_orders = {}
        self.phase_trace = []
        self.selected_order_id = None
        self.gateway_errors = []
        self.gate_decisions = {}
        self.auto_contact = {'opened': 0, 'skipped_daily': 0, 'remaining': 0, 'batch_limit': 30, 'errors': []}
        self.proof_cache = {}
        saved = self.conn.execute('SELECT payload FROM demo_flow_snapshot WHERE singleton=1').fetchone()
        if saved:
            for payload in json.loads(saved[0]):
                payload['assessed_at'] = parse_instant(payload['assessed_at'], 'assessed_at')
                from datetime import date
                payload['guaranteed_date'] = date.fromisoformat(payload['guaranteed_date'])
                if payload['revised_eta']:
                    payload['revised_eta'] = parse_instant(payload['revised_eta'], 'revised_eta')
                for evidence in payload['evidence']:
                    evidence['ingested_at'] = parse_instant(evidence['ingested_at'], 'evidence_at')
                payload['evidence'] = tuple(payload['evidence'])
                payload['reason_codes'] = tuple(payload['reason_codes'])
                self.assessments[payload['order_id']] = OrderAssessment(**payload)
        self.phase_trace = [row[0] for row in self.conn.execute(
            "SELECT agent FROM demo_tick_timings WHERE tick_at=? AND status='completed' ORDER BY ordinal",
            (utc(self.now),))]
        saved_handoff = self.conn.execute('SELECT payload FROM demo_a2_handoff WHERE singleton=1').fetchone()
        if saved_handoff:
            self.handoff_orders = {row['order_id']: row for row in json.loads(saved_handoff[0])['orders']}
        progress = self.conn.execute('SELECT records_json FROM a2_progress WHERE singleton=1').fetchone()
        self.progress = ProgressTracker(None if progress is None else json.loads(progress[0]))
        self.context = _Context(self)
        self.gateway = _Gateway(self)
        self.care = await CareRuntime.start(self.run_id,
            {'context_provider': self.context, 'gateway': self.gateway, 'gate': _Gate(self), 'clock': SystemClock()},
            root=self.state_path.parent / 'care', background=False)

    def _inspect(self, order_id):
        if not isinstance(order_id, str) or not order_id:
            raise CareError('order_required', 400)
        if order_id not in self.proof_cache:
            self.proof_cache[order_id] = self.evidence.inspect_order(order_id, self.now)
        return self.proof_cache[order_id]

    @staticmethod
    def _principal(proof):
        return 'customer:' + str(proof['order']['customer_id'])

    def _health(self):
        return self._cached_health

    def _allowed(self):
        return sysguard.proactive_allowed(self.conn, self.now) and all(h.usable_at(self.now) for h in self._health())

    def _lost(self, order_id):
        assessment = self.assessments.get(order_id)
        return assessment is not None and any(e['is_structured'] and e['fact_code'] == 'logistics_stage'
            and e['value'] == 'lost' for e in assessment.evidence)

    def _contacted_today(self, customer_id, *, excluding=None):
        customers = {row['order_id']: row.get('customer_id') for row in self.world.orders}
        for row in self._rows('contact_log'):
            if (row['contact_id'] == excluding or row['initiated_by'] != 'A1'
                    or row['status'] not in ('active', 'completed', 'transferred') or not row['opened_at']):
                continue
            if (customers.get(row['order_id']) == customer_id
                    and parse_instant(row['opened_at'], 'opened_at').astimezone(_VN).date() == self.now.astimezone(_VN).date()):
                return True
        return False

    def _queue(self):
        candidates = [a for a in self.assessments.values()
                      if (a.status in ('late', 'at_risk') and a.late_probability >= p_contact)
                      or (a.status == 'exception' and self._lost(a.order_id))]
        candidates.sort(key=lambda a: (a.order_id != _CANDIDATE, a.order_id != _LOST_CANDIDATE,
                                      STATUSES.index(a.status), -a.late_days, a.order_id))
        return [dict(self.handoff_orders.get(a.order_id, assessment_payload(a)),
                     evidence_ref=f'#/contact_queue/{index}/evidence') for index, a in enumerate(candidates)]

    async def _auto_contact(self, limit=30):
        queue = self._queue()
        report = {'opened': 0, 'reused_sessions': 0, 'skipped_daily': 0, 'remaining': len(queue), 'batch_limit': limit, 'errors': []}
        if not self._allowed():
            return report
        customers = {row['order_id']: row.get('customer_id') for row in self.world.orders}
        contacted = set()
        for row in self._rows('contact_log'):
            if row['initiated_by'] != 'A1' or row['status'] not in ('active', 'completed', 'transferred') or not row['opened_at']:
                continue
            if parse_instant(row['opened_at'], 'opened_at').astimezone(_VN).date() == self.now.astimezone(_VN).date():
                customer = customers.get(row['order_id'])
                if customer:
                    contacted.add(customer)
        attempted = 0
        for candidate in queue:
            customer = candidate.get('customer_id')
            if not customer:
                continue
            if customer in contacted:
                report['skipped_daily'] += 1
                continue
            if attempted >= limit or not self._allowed():
                break
            attempted += 1
            try:
                result = await self._open(candidate['order_id'])
                state = self.care.store.load_session(result.session_id)
                delivered = self.conn.execute('SELECT opened_at FROM contact_log WHERE contact_id=? AND provider_session_id=?',
                                              (state.contact_id, state.session_id)).fetchone()
                if delivered:
                    contacted.add(customer)
                    if parse_instant(delivered[0], 'opened_at').astimezone(_VN).date() == self.now.astimezone(_VN).date():
                        report['opened'] += 1
                    else:
                        report['reused_sessions'] += 1
                        # Reusing yesterday's active session makes no new
                        # contact attempt. Leave the batch budget available
                        # for eligible customers later in the queue.
                        attempted -= 1
            except (CareError, ValueError) as error:
                report['errors'].append({'order_id': candidate['order_id'], 'code': str(error)})
        report['remaining'] = max(0, len(queue) - report['opened'] - report['skipped_daily'] - report['reused_sessions'])
        return report

    async def _next(self):
        from .tick import run_tick
        await run_tick(self.now + timedelta(minutes=30), flow=self)

    async def _open(self, order_id):
        if order_id not in {a['order_id'] for a in self._queue()}:
            raise CareError('order_not_in_contact_queue', 409)
        if not self._allowed():
            raise CareError('proactive_blocked', 409)
        proof = self._inspect(order_id)
        ctx = TrustedRequestContext(self._principal(proof), frozenset({'care_contact'}))
        existing = self.care.store.db.execute('SELECT id FROM sessions WHERE order_id=? ORDER BY rowid DESC LIMIT 1', (order_id,)).fetchone()
        if existing:
            state = self.care.store.load_session(existing[0])
            if state.opened_by == 'a1' and state.status in ('active', 'awaiting_cancel_confirmation', 'handoff_pending'):
                await self.care.harness.authorize(ctx, order_id, state.principal_id)
                return TurnResult('opened', state.session_id)
        if self._contacted_today(proof['order']['customer_id']):
            raise CareError('customer_daily_contact_limit', 409)
        assessment = self.assessments[order_id]
        task = ContactTask('contact-' + self.run_id + '-' + order_id, order_id,
            assessment.assessed_at, self.now, 'chat', True, assessment.status,
            self.run_id + ':contact:' + order_id)
        result = await self.care.harness.open_contact(task, ctx)
        await self.care.harness.drain_pending()
        return result

    def _rows(self, table):
        cursor = self.conn.execute(f'SELECT * FROM {table} ORDER BY rowid DESC')
        return [dict(zip((column[0] for column in cursor.description), row)) for row in cursor]

    async def _view(self, payload):
        order_id = payload.get('order_id') or self.selected_order_id
        session_id = payload.get('session_id')
        if session_id:
            state = self.care.store.load_session(session_id)
            order_id = state.order_id
        elif order_id:
            row = self.care.store.db.execute('SELECT id FROM sessions WHERE order_id=? ORDER BY rowid DESC LIMIT 1', (order_id,)).fetchone()
            session_id = row[0] if row else None
        chat = None
        if session_id:
            state = self.care.store.load_session(session_id)
            ctx = TrustedRequestContext(self._principal(self._inspect(state.order_id)))
            chat = await self.care.harness.get_messages(session_id, ctx)
            chat.update(session_id=session_id, order_id=state.order_id, opened_by=state.opened_by,
                        pending=asdict(state.pending) if state.pending else None, turn_count=state.turn_count)
        controls = dict(self.conn.execute("SELECT control_key,value_json FROM controls WHERE scope='global'"))
        heartbeat = self.conn.execute("SELECT tick_at FROM guard_heartbeat WHERE agent_id='A3' ORDER BY tick_at DESC LIMIT 1").fetchone()
        full_queue = self._queue()
        queue = full_queue[:30]
        selected = self.assessments.get(order_id)
        queue = [dict(row, evidence_ref=f'#/contact_queue/{index}/evidence') for index, row in enumerate(queue)]
        orders = [dict(row, evidence_ref=f'#/orders/{index}/evidence') for index, row in enumerate(queue)]
        if selected and all(a['order_id'] != order_id for a in orders):
            orders.append(dict(self.handoff_orders.get(order_id, assessment_payload(selected)),
                               evidence_ref=f'#/orders/{len(orders)}/evidence'))
        # Evidence remains scoped to the explicitly selected order.
        verification = self._inspect(order_id) if order_id else None
        if verification:
            verification = dict(verification,
                coin_quote=late_xu_for(verification['order']['items_value_vnd']),
                requires_verification=verification['verification_required'],
                verification_status='verified' if verification.get('evidence_ready') else
                    'pending' if verification['verification_required'] else 'blocked')
        active_chats = []
        for row in self.care.store.db.execute('SELECT id FROM sessions ORDER BY rowid DESC'):
            state = self.care.store.load_session(row[0])
            if state.status not in ('active', 'awaiting_cancel_confirmation', 'handoff_pending'):
                continue
            active_chats.append({'session_id': state.session_id, 'order_id': state.order_id,
                'principal_id': state.principal_id, 'status': state.status, 'opened_by': state.opened_by,
                'initiated_by': state.opened_by, 'contact_id': state.contact_id,
                'channel': state.channel, 'turn_count': state.turn_count})
        candidates = []
        if _CANDIDATE in self.assessments:
            candidates.append({'order_id': _CANDIDATE, 'label': 'COD late', 'status': self.assessments[_CANDIDATE].status})
        lost = _LOST_CANDIDATE if self._lost(_LOST_CANDIDATE) else next((a.order_id for a in self.assessments.values() if self._lost(a.order_id)), None)
        if lost:
            candidates.append({'order_id': lost, 'label': 'Structured LOST', 'status': self.assessments[lost].status})
        timing_cursor = self.conn.execute('SELECT tick_at,ordinal,agent,started_at,finished_at,duration_ms,status FROM demo_tick_timings WHERE tick_at=? ORDER BY ordinal', (utc(self.now),))
        timings = [dict(zip((col[0] for col in timing_cursor.description), row)) for row in timing_cursor]
        label_counts = {status: 0 for status in STATUSES}
        for assessment in self.assessments.values():
            label_counts[assessment.status] += 1
        outbox, ledger = self._rows('outbox'), self._rows('ledger_new')
        return {'now': self.now.astimezone(_VN).isoformat(), 'guard_alive': sysguard.guard_alive(self.conn, self.now),
            'proactive_allowed': self._allowed(), 'feed_health': [dict(asdict(h), age_minutes=None if h.source_timestamp is None else (self.now-h.source_timestamp).total_seconds()/60) for h in self._health()],
            'last_heartbeat_at': None if heartbeat is None else heartbeat[0],
            'killed': json.loads(controls.get('a3_killed', 'false')) is not False,
            'resume_pending': json.loads(controls.get('a3_resume_pending', 'false')) is not False,
            'phase_trace': self.phase_trace, 'orders': orders, 'contact_queue': queue,
            'orders_total': len(self.assessments), 'contact_queue_total': len(full_queue),
            'label_counts': label_counts, 'tick_timings': timings, 'active_chats': active_chats,
            'demo_candidates': candidates, 'auto_contact': self.auto_contact,
            'selected_order_id': order_id, 'chat': chat, 'pending_verification': verification,
            'outbox': outbox[:20], 'ledger': ledger[:20], 'outbox_total': len(outbox), 'ledger_total': len(ledger),
            'cancellations': self._rows('cancel_requests'), 'contacts': self._rows('contact_log'),
            'handoffs': self._rows('demo_handoffs'),
            'inbox': self._rows('demo_inbox'), 'gateway_errors': self.gateway_errors,
            'mode': 'local_integrated_web_inbox', 'actions': []}

    async def _request(self, action, payload):
        async with self.lock:
            if not isinstance(payload, dict):
                raise CareError('invalid_payload', 400)
            required = {'chat-open': ('order_id',), 'chat-say': ('session_id', 'text'),
                        'verify-order': ('order_id', 'reason', 'responsibility', 'force_majeure', 'evidence_refs')}
            if any(key not in payload or payload[key] is None for key in required.get(action, ())):
                raise CareError('missing_required_field', 400)
            result = None
            if action == 'next':
                await self._next()
            elif action == 'kill':
                sysguard.kill(self.conn)
            elif action == 'revive':
                sysguard.revive(self.conn)
            elif action == 'chat-open':
                result = await self._open(payload.get('order_id'))
                self.selected_order_id = payload['order_id']
            elif action == 'chat-say':
                state = self.care.store.load_session(payload['session_id'])
                ctx = TrustedRequestContext(self._principal(self._inspect(state.order_id)))
                result = await self.care.harness.handle_message(state.session_id,
                    payload.get('request_id') or uuid4().hex, payload['text'], ctx, payload.get('reply_to'))
                await self.care.harness.drain_pending()
                self.selected_order_id = state.order_id
                self.proof_cache.clear()
            elif action == 'verify-order':
                self.evidence.verify(payload['order_id'], self.now, reviewed_by='local-authorized-staff',
                    reason=payload['reason'], responsibility=payload['responsibility'],
                    force_majeure=payload['force_majeure'], evidence_refs=payload['evidence_refs'])
                self.proof_cache.clear()
                self.selected_order_id = payload['order_id']
            elif action == 'records':
                allowed = {'outbox', 'ledger_new', 'voucher_ledger', 'cancel_requests', 'contact_log', 'customer_messages',
                           'execution_evidence', 'eligibility_reviews', 'action_receipts', 'demo_inbox', 'demo_tick_timings'}
                table = payload.get('table', 'outbox')
                if table not in allowed:
                    raise CareError('invalid_table', 400)
                rows = self._rows(table)
                if payload.get('id'):
                    rows = [r for r in rows if payload['id'] in r.values()]
                return {'table': table, 'rows': rows, 'now': self.now.isoformat()}
            elif action not in ('status', 'proactive-check'):
                raise ValueError('Unknown integrated demo operation')
            view = await self._view(payload)
            if result:
                view['turn_result'] = asdict(result)
                effects = [self.care.store.effect(effect_id) for effect_id in result.effect_ids]
                blocked = bool(result.codes) or any(row is not None and row['state'] == 'blocked' for row in effects)
                gate = 'blocked' if blocked else 'not_requested'
                if effects and not blocked:
                    gate = 'allowed' if all(row is not None and row['outcome'] in ('succeeded', 'accepted', 'awaiting_approval') for row in effects) else 'pending'
                view['reply'] = result.text or next((m['text'] for m in reversed((view.get('chat') or {}).get('messages', [])) if m['kind'] == 'response'), '')
                view['inside'] = {'intent': result.intent, 'gate': gate,
                                  'used_llm': result.source not in ('template', 'fallback'),
                                  'codes': list(result.codes),
                                  'dispatch': [self.gate_decisions[e] for e in result.effect_ids if e in self.gate_decisions]}
            return json.loads(canonical(view))

    def request(self, action='status', payload=None):
        if self.closed:
            raise RuntimeError('Demo flow is closed')
        return asyncio.run_coroutine_threadsafe(self._request(action, {} if payload is None else payload), self.loop).result(timeout=120)

    async def _close(self):
        await self.care.shutdown()
        self.reader.close()
        self.conn.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            asyncio.run_coroutine_threadsafe(self._close(), self.loop).result(timeout=10)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=10)
