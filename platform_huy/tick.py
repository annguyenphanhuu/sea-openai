"""Actual A3 -> A2 -> A1 tick orchestration for the local demo runtime."""
from datetime import datetime, timedelta, timezone
import time

from care_truc.runtime_types import canonical
from logistics_an_nguyen.adapter import ReleaseAdapter
from logistics_an_nguyen.handoff import assessed_orders_payload
from logistics_an_nguyen.progress import ProgressTracker
from logistics_an_nguyen.service import assessment_payload, evaluate_tick
from logistics_an_nguyen.llm import review_assessments

from . import sysguard
from .llm_guard import review_guard
from .state import immediate, utc


def _start(agent):
    return {'agent': agent, 'started_at': utc(datetime.now(timezone.utc)),
            '_monotonic': time.perf_counter()}


def _finish(timing, status='completed'):
    timing['finished_at'] = utc(datetime.now(timezone.utc))
    timing['duration_ms'] = (time.perf_counter() - timing.pop('_monotonic')) * 1000
    timing['status'] = status
    return timing


def _save_timing(flow, now, ordinal, timing):
    timing.update(tick_at=utc(now), ordinal=ordinal)
    flow.conn.execute('INSERT OR REPLACE INTO demo_tick_timings VALUES (?,?,?,?,?,?,?,?)',
        (utc(now), ordinal, timing['agent'], timing['started_at'], timing['finished_at'],
         timing['duration_ms'], timing['status'], canonical({})))


async def run_tick(now, *, flow):
    """Run one manual +30-minute tick; caller holds the flow's request lock.

    A2 hands off assessments and metadata. Platform alone wraps eligible rows
    into ContactTasks and the real A1 harness owns every message and effect.
    """
    if now.utcoffset() is None or now != flow.now + timedelta(minutes=30):
        raise ValueError('NEXT must advance exactly 30 minutes')
    tracker = ProgressTracker(flow.progress.records)
    timings = []
    a3 = _start('A3')
    flow._publish_progress('A3', timings)
    world = flow.reader.snapshot(now)
    with immediate(flow.conn):
        sysguard.run(world, flow.conn, now)
        health = tuple(sysguard.health_for(world, flow.conn, now))
        if flow.reviewer is not None:
            guard_review = await review_guard(health, flow.conn, now, flow.reviewer)
            flow.conn.execute('INSERT OR REPLACE INTO agent_llm_reviews VALUES (?,?,?)',
                              (utc(now), 'A3', canonical(guard_review)))
        timings.append(_finish(a3))
        _save_timing(flow, now, 1, timings[-1])

        a2 = _start('A2')
        flow._publish_progress('A2', timings,
            orders_to_assess=sum(1 for order in world.orders if not order['cancelled_at']))
        facts = tracker.apply(ReleaseAdapter(world).orders(), tick_at=now, feed_health=health)
        result = evaluate_tick(facts, tick_at=now, feed_health=health)
        handoff = assessed_orders_payload(world, result, feed_health=health)
        if flow.reviewer is not None:
            analysis = await review_assessments(result.assessments, flow.reviewer)
            flow.conn.execute('INSERT OR REPLACE INTO agent_llm_reviews VALUES (?,?,?)',
                              (utc(now), 'A2', canonical(analysis)))
            handoff['llm_review'] = analysis
            by_order = {item['order_id']: item for item in analysis['reviews']}
            for row in handoff['orders']:
                if row['order_id'] in by_order:
                    row['llm_review'] = by_order[row['order_id']]
        payload = canonical([assessment_payload(a) for a in result.assessments])
        flow.conn.execute('UPDATE demo_clock SET current_at=?,version=version+1 WHERE singleton=1', (utc(now),))
        flow.conn.execute('INSERT INTO demo_flow_snapshot VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload', (payload,))
        flow.conn.execute('INSERT INTO demo_a2_handoff VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload', (canonical(handoff),))
        flow.conn.execute('INSERT INTO a2_progress VALUES (1,?,?) ON CONFLICT(singleton) DO UPDATE SET tick_at=excluded.tick_at,records_json=excluded.records_json',
                          (utc(now), canonical(tracker.records)))
        for question in result.questions:
            flow.conn.execute('INSERT OR IGNORE INTO supervisor_questions(question_id,order_id,question_text,evidence_json,asked_at) VALUES (?,?,?,?,?)',
                (question.question_id, question.order_id, question.question_text, canonical(question.evidence), utc(now)))
        timings.append(_finish(a2))
        _save_timing(flow, now, 2, timings[-1])

    # Publish the complete A2 snapshot only after its transaction commits.
    flow.now, flow.world, flow.progress = now, world, tracker
    flow._cached_health = health
    flow.assessments = {a.order_id: a for a in result.assessments}
    flow.handoff_orders = {row['order_id']: row for row in handoff['orders']}
    flow.proof_cache.clear()
    flow.phase_trace = ['A3', 'A2']
    if flow.selected_order_id is None:
        queue = flow._queue()
        flow.selected_order_id = queue[0]['order_id'] if queue else None

    a1 = _start('A1')
    flow._publish_progress('A1', timings, committed=('A3', 'A2'))
    try:
        flow.auto_contact = await flow._auto_contact(limit=30)
        await flow.care.harness.drain_pending()
    except BaseException:
        timing = _finish(a1, 'failed')
        _save_timing(flow, now, 3, timing)
        flow._publish_progress(None, timings + [timing], committed=('A3', 'A2'))
        raise
    timings.append(_finish(a1))
    _save_timing(flow, now, 3, timings[-1])
    flow.phase_trace.append('A1')
    flow._publish_progress(None, timings, committed=('A3', 'A2', 'A1'))
    return timings
