"""Synchronous HTTP adapter over the actual local A3/A2/A1 runtime.

Both SQLite writers live on one event loop thread. HTTP threads never touch
connections, authenticated contexts, or producer allowlists directly.
"""
import asyncio
from copy import deepcopy
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Condition, Lock, Thread
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
from .effect_gateway import SqliteEffectGateway, check_deadline, sqlite_deadline
from .state import bootstrap, connect_state, immediate, utc
from .state_store import SqliteStateStore


_VN = timezone(timedelta(hours=7))
_START = datetime(2026, 10, 24, 14, tzinfo=_VN)
_CANDIDATE = '261021ZS7E76FW'
_LOST_CANDIDATE = '261019QY8UDYNZ'
_CUSTOMER_FAULT_CANDIDATE = '2610181FZM7I7I'


def _customer_reply(text, codes, effect_ids):
    """Present a denied benefit politely without changing its durable decision."""
    if 'coins_actions_blocked' in codes and not effect_ids:
        return 'Hệ thống đang tạm dừng ưu đãi để kiểm tra , mình vẫn hỗ trợ thông tin đơn'
    return text


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
        return self.snapshot(ctx, order_id)

    def snapshot(self, ctx, order_id):
        if ctx.principal_id != self.flow._principal(self.flow._inspect(order_id)):
            raise CareError('forbidden', 403)
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
    atomic_final_validation = True

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
            # No await inside these locks: final durable authority and controls
            # remain stable until the local inbox transaction commits.
            with (sqlite_deadline((flow.care.store.db, flow.conn), deadline),
                  flow.care.store.transaction(), immediate(flow.conn)):
                check_deadline(deadline)
                state = flow.care.store.load_session(proposal.session_id)
                persisted = flow.care.store.effect(proposal.effect_id)
                if (persisted is None or persisted['attempts'] < 1
                    or persisted['run_id'] != flow.run_id or state.run_id != flow.run_id
                    or persisted['effect_key'] != proposal.key or persisted['session_id'] != state.session_id
                    or state.order_id != proposal.order_id
                    or state.principal_id != flow._principal(flow._inspect(state.order_id))
                    or persisted['proposal'] != canonical(proposal)):
                    raise CareError('effect_binding_invalid', 403)
                if proposal.kind == 'contact_send':
                    if state.status != 'active' or state.opened_by != 'a1' or state.channel != 'chat':
                        raise CareError('session_not_active', 409)
                    payload = json.loads(proposal.payload)
                    # Recheck under the same write transaction that makes the
                    # message available in the inbox. Earlier async guard/gate
                    # snapshots cannot authorize delivery after a runtime kill.
                    if not flow._allowed():
                        raise CareError('proactive_blocked', 409)
                    snapshot = flow.context.snapshot(TrustedRequestContext(state.principal_id), state.order_id)
                    decision = flow.care.harness.guards.validate_dispatch(proposal, snapshot)
                    if not decision.allowed:
                        raise CareError('final_dispatch_blocked', 409)
                    customer = flow._inspect(state.order_id)['order']['customer_id']
                    if flow._contacted_today(customer, excluding=state.contact_id):
                        raise CareError('customer_daily_contact_limit', 409)
                    check_deadline(deadline)
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
                    if state.status not in ('handoff_pending', 'transferred'):
                        raise CareError('session_state_conflict', 409)
                    check_deadline(deadline)
                    flow.conn.execute('INSERT OR IGNORE INTO demo_handoffs VALUES (?,?,?,?)',
                        (proposal.effect_id, state.session_id, proposal.payload, utc(flow.now)))
                    remote = 'staff-inbox:' + proposal.effect_id
                else:
                    raise CareError('effect_kind_not_supported', 409)
                check_deadline(deadline)
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
    def __init__(self, core_path, state_path, start_at=None, ops_path=None, *, selector=None, reviewer=None):
        self.selector = selector
        self.reviewer = reviewer
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
        self._resetting = False
        self._runtime_root = self.state_path.parent
        self._snapshot_lock = Lock()
        self._next_finished = Condition(self._snapshot_lock)
        self._status_snapshot = {}
        self._tick_progress = {'busy': False, 'current_phase': None, 'status': 'idle',
            'run_id': None, 'from_at': None, 'to_at': None, 'elapsed_seconds': 0,
            'phase_trace': [], 'timings': [], 'committed_phases': []}
        self._tick_started = None
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
        if not hasattr(self, 'lock'):
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
        self.conn.execute('CREATE TABLE IF NOT EXISTS agent_llm_reviews(tick_at TEXT,agent TEXT,payload_json TEXT,PRIMARY KEY(tick_at,agent))')
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
                # A2 export metadata is additive; the shared assessment stays v0.
                self.assessments[payload['order_id']] = OrderAssessment(**{
                    field.name: payload[field.name] for field in fields(OrderAssessment)
                })
        self.phase_trace = [row[0] for row in self.conn.execute(
            "SELECT agent FROM demo_tick_timings WHERE tick_at=? AND status='completed' ORDER BY ordinal",
            (utc(self.now),))]
        saved_handoff = self.conn.execute('SELECT payload FROM demo_a2_handoff WHERE singleton=1').fetchone()
        if saved_handoff:
            self.handoff_orders = {row['order_id']: row for row in json.loads(saved_handoff[0])['orders']}
        progress = self.conn.execute('SELECT records_json FROM a2_progress WHERE singleton=1').fetchone()
        self.progress = ProgressTracker(None if progress is None else json.loads(progress[0]))
        self.conn.execute('CREATE TABLE IF NOT EXISTS demo_voice_links(session_id TEXT PRIMARY KEY,parent_session_id TEXT NOT NULL)')
        self.context = _Context(self)
        self.gateway = _Gateway(self)
        self.care = await CareRuntime.start(self.run_id,
            {'context_provider': self.context, 'gateway': self.gateway, 'gate': _Gate(self), 'clock': SystemClock(), 'selector': self.selector},
            root=self.state_path.parent / 'care', background=False)
        self._cache_view(await self._view({}))

    def _cache_view(self, view):
        # Called only on the owner event loop, after runtime operations finish.
        snapshot = json.loads(canonical(view))
        with self._snapshot_lock:
            self._status_snapshot = snapshot

    def _publish_progress(self, phase, timings, *, committed=(), orders_to_assess=None):
        # This cache contains timing metadata only, never uncommitted source rows.
        with self._snapshot_lock:
            self._tick_progress.update(current_phase=phase,
                phase_trace=[row['agent'] for row in timings if row['status'] == 'completed'],
                timings=deepcopy(timings), committed_phases=list(committed))
            if orders_to_assess is not None:
                self._tick_progress['orders_to_assess'] = orders_to_assess

    def _cached_status(self):
        with self._snapshot_lock:
            return self._cached_status_locked()

    def _cached_status_locked(self):
        view = deepcopy(self._status_snapshot)
        progress = deepcopy(self._tick_progress)
        if progress['busy']:
            progress['elapsed_seconds'] = time.perf_counter() - self._tick_started
        view.update(busy=progress['busy'], current_phase=progress['current_phase'], progress=progress)
        if progress['run_id'] is not None:
            view.update(phase_trace=progress['phase_trace'], timings=progress['timings'],
                        tick_timings=progress['timings'])
        return view

    async def _reserved_next(self, payload):
        try:
            result = await self._request('next', payload)
        except BaseException:
            # A1 can fail after A2 committed; keep the cache aligned with the
            # durable clock before allowing another NEXT reservation.
            try:
                async with self.lock:
                    self._cache_view(await self._view({}))
            except Exception:
                pass
            with self._snapshot_lock:
                self._tick_progress.update(busy=False, current_phase=None, status='failed',
                    elapsed_seconds=time.perf_counter() - self._tick_started)
                self._next_finished.notify_all()
            raise
        with self._snapshot_lock:
            self._tick_progress.update(busy=False, current_phase=None, status='completed',
                elapsed_seconds=time.perf_counter() - self._tick_started)
            # Copy before another HTTP thread can reserve the following tick.
            result.update(self._cached_status_locked())
            self._next_finished.notify_all()
        return result

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
        existing = self.care.store.db.execute("SELECT id FROM sessions WHERE order_id=? AND json_extract(data,'$.channel')='chat' ORDER BY rowid DESC LIMIT 1", (order_id,)).fetchone()
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

    def _demo_scenarios(self, queue):
        """Describe only scenarios established by the current real A2 handoff."""
        cod = self.assessments.get(_CANDIDATE)
        cod_id = (_CANDIDATE if cod is not None and cod.status == 'late'
                  and self.handoff_orders.get(_CANDIDATE, {}).get('payment') == 'COD' else None)
        lost_id = (_LOST_CANDIDATE if self._lost(_LOST_CANDIDATE) else
                   next((order_id for order_id in sorted(self.assessments) if self._lost(order_id)), None))
        fault_ids = sorted(a.order_id for a in self.assessments.values()
                           if a.status == 'customer_fault' and a.fault_party == 'customer')
        fault_id = (_CUSTOMER_FAULT_CANDIDATE if _CUSTOMER_FAULT_CANDIDATE in fault_ids else
                    next(iter(fault_ids), None))
        contact_ids = {row['order_id'] for row in queue}
        scenarios = []
        for scenario, label, order_id in (
                ('cod_late', 'COD late', cod_id),
                ('lost', 'Structured LOST', lost_id),
                ('customer_fault', 'Customer fault', fault_id)):
            if order_id is None:
                reason = ('no_assessment_at_current_tick' if not self.assessments else
                          'no_matching_order_at_current_tick')
            elif order_id not in contact_ids:
                reason = 'order_not_in_contact_queue'
            elif not self._allowed():
                reason = 'proactive_blocked'
            else:
                reason = None
            scenarios.append({'scenario': scenario, 'label': label, 'order_id': order_id,
                'status': None if order_id is None else self.assessments[order_id].status,
                'available': order_id is not None,
                'contact_available': order_id is not None and reason is None,
                'reason': reason, 'as_of': self.now.isoformat()})
        return scenarios

    async def _view(self, payload):
        order_id = payload.get('order_id') or self.selected_order_id
        session_id = payload.get('session_id')
        if session_id:
            state = self.care.store.load_session(session_id)
            order_id = state.order_id
        elif order_id:
            row = self.care.store.db.execute("SELECT id FROM sessions WHERE order_id=? AND json_extract(data,'$.channel')='chat' ORDER BY rowid DESC LIMIT 1", (order_id,)).fetchone()
            session_id = row[0] if row else None
        chat = None
        if session_id:
            state = self.care.store.load_session(session_id)
            ctx = TrustedRequestContext(self._principal(self._inspect(state.order_id)))
            chat = await self.care.harness.get_messages(session_id, ctx)
            # The same projection is applied to persisted history and the current
            # result, so reloads/retries retain the audited denial and no effect.
            for message in chat['messages']:
                if message['kind'] == 'response':
                    message['text'] = self._reply_text(message['text'],
                        message.get('codes') or (), message.get('effect_ids') or (), state,
                        message.get('intent'))
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
        for row in orders + queue:
            row['cod_refusal_risk'] = next((level for level in ('high', 'medium')
                if f'cod_refusal_risk:{level}' in row['reason_codes']), None)
            row['lsr_exempt'] = bool(self.handoff_orders.get(row['order_id'], {}).get('lsr_exemption'))
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
            if state.channel != 'chat' or state.status not in ('active', 'awaiting_cancel_confirmation', 'handoff_pending'):
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
        reviews = {agent: json.loads(payload) for agent, payload in self.conn.execute(
            'SELECT agent,payload_json FROM agent_llm_reviews WHERE tick_at=?', (utc(self.now),))}
        return {'llm': {'enabled': self.selector is not None or self.reviewer is not None,
                'model': getattr(self.selector, 'model', None),
                'agents': {'A1': {'enabled': self.selector is not None,
                                  'last_call': getattr(self.selector, 'last_call', None)},
                           **{agent: {'enabled': self.reviewer is not None,
                                      'model': getattr(self.reviewer, 'model', None),
                                      'latest': reviews.get(agent)} for agent in ('A2', 'A3')}}},
            'now': self.now.astimezone(_VN).isoformat(), 'guard_alive': sysguard.guard_alive(self.conn, self.now),
            'proactive_allowed': self._allowed(), 'feed_health': [dict(asdict(h), age_minutes=None if h.source_timestamp is None else (self.now-h.source_timestamp).total_seconds()/60) for h in self._health()],
            'last_heartbeat_at': None if heartbeat is None else heartbeat[0],
            'killed': json.loads(controls.get('a3_killed', 'false')) is not False,
            'resume_pending': json.loads(controls.get('a3_resume_pending', 'false')) is not False,
            'phase_trace': self.phase_trace, 'orders': orders, 'contact_queue': queue,
            'tasks': queue, 'chats': active_chats, 'timings': timings,
            'orders_total': len(self.assessments), 'contact_queue_total': len(full_queue),
            'label_counts': label_counts, 'tick_timings': timings, 'active_chats': active_chats,
            'demo_candidates': candidates, 'demo_scenarios': self._demo_scenarios(full_queue),
            'auto_contact': self.auto_contact,
            'selected_order_id': order_id, 'chat': chat, 'pending_verification': verification,
            'outbox': outbox[:20], 'ledger': ledger[:20], 'outbox_total': len(outbox), 'ledger_total': len(ledger),
            'cancellations': self._rows('cancel_requests'), 'contacts': self._rows('contact_log'),
            'contacts_total': self.conn.execute('SELECT count(*) FROM contact_log').fetchone()[0],
            'handoffs': self._rows('demo_handoffs'),
            'inbox': self._rows('demo_inbox'), 'gateway_errors': self.gateway_errors,
            'mode': 'local_integrated_web_inbox', 'actions': []}

    def _reply_text(self, text, codes, effect_ids, state, intent=None):
        """Project only this response's verified effects into customer wording."""
        from care_truc.phrases import CATALOG, checking_evidence_reply
        text = _customer_reply(text, codes, effect_ids)
        if text == CATALOG['checking_evidence']:
            assessment = self.assessments.get(state.order_id)
            if assessment is not None:
                text = checking_evidence_reply(assessment.late_days)
        for effect_id in effect_ids:
            effect = self.care.store.effect(effect_id)
            if (effect is None or effect['session_id'] != state.session_id
                    or effect['run_id'] != self.run_id or effect['outcome'] != 'succeeded'):
                continue
            proposal = json.loads(effect['proposal'])
            if proposal['order_id'] != state.order_id:
                continue
            receipts = self.care.store.db.execute(
                'SELECT data FROM receipts WHERE effect_id=? ORDER BY revision DESC', (effect_id,))
            receipt = next((json.loads(row[0]) for row in receipts
                if json.loads(row[0]).get('outcome') == 'succeeded'), None)
            if (receipt is None or receipt.get('authoritative') is not True
                    or receipt['key'] != proposal['key']
                    or receipt['payload_hash'] != fingerprint(proposal['payload'])):
                continue
            if proposal['kind'] == 'handoff_request':
                if self.conn.execute('SELECT 1 FROM demo_handoffs WHERE effect_id=? AND session_id=?',
                                     (effect_id, state.session_id)).fetchone():
                    text = CATALOG['handoff_succeeded']
                continue
            action = json.loads(proposal['payload'])
            if proposal['kind'] != 'action_request' or action.get('kind') != 'coins':
                continue
            row = self.conn.execute(
                "SELECT l.amount_xu FROM ledger_new l JOIN action_receipts r ON r.action_id=l.action_id "
                "JOIN outbox o ON o.action_id=l.action_id WHERE l.action_id=? AND l.order_id=? "
                "AND r.decision_code='succeeded' AND o.status='succeeded' AND o.kind='coins' "
                "AND l.amount_xu=o.amount_vnd", (receipt['remote_ref'], state.order_id)).fetchone()
            if row is not None and receipt['remote_ref'] == action['action_id']:
                amount = format(row[0], ',').replace(',', '.')
                text += f' Mình đã tặng bạn {amount} xu vào ví để xin lỗi'
        return text

    async def _reset(self):
        """Start a separate runtime; preserve every previous database for audit."""
        previous = self.__dict__.copy()
        self.state_path = self._runtime_root / ('reset-' + uuid4().hex) / 'platform.sqlite'
        try:
            await self._start()
        except BaseException:
            # Initialization must not strand a working presenter runtime.
            if self.care is not previous['care']:
                await self.care.shutdown()
            if self.reader is not previous['reader']:
                self.reader.close()
            if self.conn is not previous['conn']:
                self.conn.close()
            self.__dict__.update(previous)
            raise
        await previous['care'].shutdown()
        previous['reader'].close()
        previous['conn'].close()
        with self._snapshot_lock:
            self._tick_started = None
            self._tick_progress = {'busy': False, 'current_phase': None, 'status': 'idle',
                'run_id': None, 'from_at': None, 'to_at': None, 'elapsed_seconds': 0,
                'phase_trace': [], 'timings': [], 'committed_phases': []}

    async def _reserved_reset(self, payload):
        try:
            return await self._request('reset', payload)
        finally:
            with self._snapshot_lock:
                self._resetting = False

    async def _request(self, action, payload):
        async with self.lock:
            if not isinstance(payload, dict):
                raise CareError('invalid_payload', 400)
            required = {'chat-open': ('order_id',), 'chat-say': ('session_id', 'text'),
                        'verify-order': ('order_id', 'reason', 'responsibility', 'force_majeure', 'evidence_refs')}
            if any(key not in payload or payload[key] is None for key in required.get(action, ())):
                raise CareError('missing_required_field', 400)
            result = None
            if action == 'voice-open':
                parent = self.care.store.load_session(payload['session_id'])
                if parent.channel != 'chat' or parent.status not in ('active', 'awaiting_cancel_confirmation'):
                    raise CareError('voice_session_invalid', 403)
                ctx = TrustedRequestContext(self._principal(self._inspect(parent.order_id)))
                opened = await self.care.harness.open_chat(parent.order_id, payload['request_id'], ctx, channel='web_voice')
                self.conn.execute('INSERT OR IGNORE INTO demo_voice_links VALUES (?,?)', (opened.session_id, parent.session_id))
                return {'session_id': opened.session_id, 'parent_session_id': parent.session_id}
            elif action in ('voice-validate', 'voice-say'):
                state = self.care.store.load_session(payload['session_id'])
                link = self.conn.execute('SELECT parent_session_id FROM demo_voice_links WHERE session_id=?', (state.session_id,)).fetchone()
                if state.channel != 'web_voice' or link is None or state.status not in ('active', 'awaiting_cancel_confirmation'):
                    raise CareError('voice_session_invalid', 403)
                parent = self.care.store.load_session(link[0])
                if parent.channel != 'chat' or parent.status not in ('active', 'awaiting_cancel_confirmation') or parent.order_id != state.order_id or parent.principal_id != state.principal_id:
                    raise CareError('voice_session_invalid', 403)
                if action == 'voice-validate':
                    return {'valid': True}
                ctx = TrustedRequestContext(self._principal(self._inspect(state.order_id)))
                from care_truc.rules import is_cancel_confirmation
                reply_to = state.pending.reply_to if state.pending and is_cancel_confirmation(payload['text']) else None
                result = await self.care.harness.handle_message(state.session_id, payload['request_id'], payload['text'], ctx, reply_to)
                await self.care.harness.drain_pending()
                current = self.care.store.load_session(state.session_id)
                return {'reply': result.text, 'inside': {'channel': 'voice', 'codes': list(result.codes)}, 'status': current.status}
            elif action == 'orders':
                saved = self.conn.execute('SELECT payload FROM demo_a2_handoff WHERE singleton=1').fetchone()
                if saved is None:
                    # No tick has run yet; do not invent assessments or run NEXT on GET.
                    return {'payload_version': 'a2_order_list_v1', 'tick_at': utc(self.now),
                            'orders': [], 'feed_health': []}
                return json.loads(saved[0])
            elif action == 'next':
                await self._next()
            elif action == 'reset':
                await self._reset()
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
                request_id = payload.get('request_id') or uuid4().hex
                reply_to = payload.get('reply_to')
                if reply_to is None:
                    # A retry must reuse its original binding even after pending
                    # was consumed; a new turn binds only the current prompt.
                    prior = self.care.store.find_request(state.session_id, ctx.principal_id, request_id)
                    if prior is not None:
                        reply_to = json.loads(prior['payload']).get('reply_to')
                    elif state.pending is not None:
                        from care_truc.rules import is_cancel_confirmation
                        if is_cancel_confirmation(payload['text']):
                            reply_to = state.pending.reply_to
                result = await self.care.harness.handle_message(state.session_id,
                    request_id, payload['text'], ctx, reply_to)
                await self.care.harness.drain_pending()
                self.selected_order_id = state.order_id
                self.proof_cache.clear()
            elif action == 'verify-order':
                # Legacy API callers keep the existing local authorization actor;
                # explicit operator identities are validated and audited verbatim.
                staff_name = payload.get('staff_name', 'local-authorized-staff')
                if not isinstance(staff_name, str) or not staff_name.strip():
                    raise CareError('staff_name_required', 400)
                self.evidence.verify(payload['order_id'], self.now, reviewed_by=staff_name.strip(),
                    reason=payload['reason'], responsibility=payload['responsibility'],
                    force_majeure=payload['force_majeure'], evidence_refs=payload['evidence_refs'])
                self.proof_cache.clear()
                self.selected_order_id = payload['order_id']
            elif action == 'records':
                allowed = {'outbox', 'ledger_new', 'voucher_ledger', 'cancel_requests', 'contact_log', 'customer_messages',
                           'execution_evidence', 'eligibility_reviews', 'action_receipts', 'demo_inbox', 'demo_tick_timings',
                           'agent_llm_reviews'}
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
                state = self.care.store.load_session(result.session_id)
                result = replace(result, text=self._reply_text(result.text, result.codes,
                    result.effect_ids, state, result.intent))
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
            self._cache_view(view)
            response = json.loads(canonical(view))
            cached = self._cached_status()
            response.update(busy=cached['busy'], current_phase=cached['current_phase'], progress=cached['progress'])
            return response

    def request(self, action='status', payload=None, *, reject_overlapping_next=False):
        if self.closed:
            raise RuntimeError('Demo flow is closed')
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise CareError('invalid_payload', 400)
        with self._snapshot_lock:
            busy = self._tick_progress['busy']
            if self._resetting:
                raise CareError('reset_in_progress', 409)
            if action == 'reset':
                if busy:
                    raise CareError('next_in_progress', 409)
                self._resetting = True
            if action == 'next':
                if busy and reject_overlapping_next:
                    raise CareError('next_in_progress', 409)
                if busy and not self._next_finished.wait_for(
                        lambda: not self._tick_progress['busy'], timeout=120):
                    raise TimeoutError('next_queue_timeout')
                start = self._status_snapshot['now']
                target = datetime.fromisoformat(start) + timedelta(minutes=30)
                self._tick_started = time.perf_counter()
                self._tick_progress = {'busy': True, 'current_phase': None, 'status': 'running',
                    'run_id': uuid4().hex, 'from_at': start, 'to_at': target.isoformat(),
                    'elapsed_seconds': 0, 'phase_trace': [], 'timings': [], 'committed_phases': []}
        if action == 'status' and (busy or not payload):
            return self._cached_status()
        operation = (self._reserved_next(payload) if action == 'next' else
                     self._reserved_reset(payload) if action == 'reset' else self._request(action, payload))
        # A caller timeout does not cancel the coroutine or release the NEXT reservation.
        return asyncio.run_coroutine_threadsafe(operation, self.loop).result(timeout=120)

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
