from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from care_truc.natural import fact_slots, reply_topic
from care_truc.runtime_types import FeedSnapshot, GuardSnapshot
from .helpers import context

NOW = datetime(2026, 10, 24, 9, tzinfo=timezone.utc)
SEEN = datetime(2026, 10, 23, 16, 5, 3, tzinfo=timezone.utc)


def evidence(code, value, *, record='scan-private', feed='scan_events', seen=SEEN, structured=True):
    return {'feed': feed, 'source_table': feed, 'record_id': record,
            'ingested_at': seen, 'fact_code': code, 'value': value, 'is_structured': structured}


def snapshot():
    rows = [evidence('logistics_stage', 'returning'),
            evidence('stage_event_at', '2026-10-23T23:03:19+07:00'), evidence('stage_location', None)]
    for index, outcome in enumerate(('no_answer', 'no_answer', 'other')):
        rows.extend([evidence('failed_delivery_attempt', True, record=f'attempt-{index}', feed='delivery_attempts'),
                     evidence('attempt_outcome', outcome, record=f'attempt-{index}', feed='delivery_attempts')])
    original = context()
    guard = GuardSnapshot('a3', NOW, tuple(FeedSnapshot(name, 'trusted', NOW) for name in ('scan_events', 'delivery_attempts')),
                          ('scan_events', 'delivery_attempts'), True, True)
    return replace(original, cutoff=NOW, guard=guard,
                   assessment=replace(original.assessment, assessed_at=NOW, evidence=tuple(rows), revised_eta=None,
                                      reason_codes=('status:late', 'guaranteed_day_exceeded', 'eta_missing')))


@pytest.mark.parametrize('topic', ['eta', 'location', 'explanation'])
def test_known_journey_survives_missing_eta(topic):
    reply = ' '.join(fact_slots(snapshot(), topic).values())
    assert 'đang hoàn trả' in reply
    assert '23/10/2026 23:03' in reply
    assert 'gần nhất' in reply
    assert 'scan-private' not in reply
    if topic == 'eta':
        assert 'chưa có thời gian giao dự kiến' in reply


def test_delivery_attempts_describe_recorded_history_without_assigning_customer_fault():
    ctx = snapshot()
    reply = ' '.join(fact_slots(ctx, 'explanation').values())
    assert '3 lần giao chưa thành công' in reply
    assert '2 lần' in reply and 'không liên lạc được' in reply
    assert 'lỗi khách hàng' not in reply
    assert ctx.assessment.fault_party == 'carrier'


@pytest.mark.parametrize('text', ['Đơn có đang hoàn trả không?', 'Đã giao mấy lần rồi?', 'Tình trạng đơn hiện tại thế nào?'])
def test_journey_questions_select_factual_explanation(text):
    assert reply_topic(text, 'off_topic') == 'explanation'

@pytest.mark.parametrize('change', ['stale_assessment', 'missing_guard', 'stale_feed', 'future_evidence'])
def test_untrusted_context_does_not_expose_journey_as_current_fact(change):
    ctx = snapshot()
    if change == 'stale_assessment':
        ctx = replace(ctx, assessment=replace(ctx.assessment, assessed_at=NOW - timedelta(minutes=31)))
    elif change == 'missing_guard':
        ctx = replace(ctx, guard=None)
    elif change == 'stale_feed':
        feeds = tuple(replace(feed, source_timestamp=NOW - timedelta(minutes=31)) for feed in ctx.guard.feeds)
        ctx = replace(ctx, guard=replace(ctx.guard, feeds=feeds))
    else:
        rows = tuple(dict(item, ingested_at=NOW + timedelta(seconds=1)) for item in ctx.assessment.evidence)
        ctx = replace(ctx, assessment=replace(ctx.assessment, evidence=rows))
    for topic in ('eta', 'location', 'explanation'):
        reply = ' '.join(fact_slots(ctx, topic).values())
        assert 'đang hoàn trả' not in reply and '3 lần giao' not in reply
        assert '23/10/2026' not in reply


@pytest.mark.parametrize('change', [
    'free_text', 'wrong_source', 'different_record', 'different_ingestion',
    'missing_timestamp', 'invalid_timestamp', 'naive_timestamp', 'future_timestamp',
    'timestamp_after_ingestion', 'conflicting_stage', 'conflicting_time', 'multiple_stage_records',
    'object_stage', 'object_timestamp',
])
def test_last_scan_requires_one_coherent_source_record(change):
    ctx = snapshot()
    rows = [dict(item) for item in ctx.assessment.evidence]
    stage, stamp = rows[0], rows[1]
    if change == 'free_text':
        stage['is_structured'] = False
    elif change == 'wrong_source':
        stamp['source_table'] = 'driver_messages'
    elif change == 'different_record':
        stamp['record_id'] = 'other-scan'
    elif change == 'different_ingestion':
        stamp['ingested_at'] += timedelta(seconds=1)
    elif change == 'missing_timestamp':
        rows.remove(stamp)
    elif change == 'invalid_timestamp':
        stamp['value'] = 'yesterday'
    elif change == 'naive_timestamp':
        stamp['value'] = '2026-10-23T23:03:19'
    elif change == 'future_timestamp':
        stamp['value'] = (NOW + timedelta(minutes=1)).isoformat()
    elif change == 'timestamp_after_ingestion':
        stamp['value'] = (SEEN + timedelta(seconds=1)).isoformat()
    elif change == 'conflicting_stage':
        rows.append(dict(stage, value='delivered'))
    elif change == 'conflicting_time':
        rows.append(dict(stamp, value='2026-10-23T22:03:19+07:00'))
    elif change == 'multiple_stage_records':
        rows.extend([dict(stage, record_id='other-scan'), dict(stamp, record_id='other-scan')])
    elif change == 'object_stage':
        stage['value'] = {'stage': 'returning'}
    else:
        stamp['value'] = {'date': '2026-10-23'}
    ctx = replace(ctx, assessment=replace(ctx.assessment, evidence=tuple(rows)))
    reply = ' '.join(fact_slots(ctx, 'location').values())
    assert 'đang hoàn trả' not in reply and '23/10/2026' not in reply
    assert 'chưa có vị trí hiện tại đã được xác minh' in reply


def test_attempt_duplicates_and_conflicting_outcomes_never_inflate_counts():
    ctx = snapshot()
    rows = list(ctx.assessment.evidence)
    rows.extend([dict(item) for item in rows if item['feed'] == 'delivery_attempts'])
    rows.append(evidence('attempt_outcome', 'other', record='attempt-0', feed='delivery_attempts'))
    ctx = replace(ctx, assessment=replace(ctx.assessment, evidence=tuple(rows)))
    reply = ' '.join(fact_slots(ctx, 'explanation').values())
    assert '3 lần giao chưa thành công' in reply
    assert '1 lần được ghi nhận không liên lạc được' in reply
    assert '6 lần' not in reply


def test_nonstructured_attempts_and_object_values_are_not_public_claims():
    ctx = snapshot()
    rows = tuple(dict(item, is_structured=False) if item['feed'] == 'delivery_attempts' else dict(item, value={'private': 'SECRET'})
                 for item in ctx.assessment.evidence)
    ctx = replace(ctx, assessment=replace(ctx.assessment, evidence=rows))
    reply = ' '.join(fact_slots(ctx, 'explanation').values())
    assert 'lần giao' not in reply and 'SECRET' not in reply


def test_fact_projection_never_exposes_location_ids_or_driver_text():
    ctx = snapshot()
    rows = tuple(dict(item, value='WAREHOUSE-PRIVATE') if item['fact_code'] == 'stage_location' else item
                 for item in ctx.assessment.evidence)
    rows += (evidence('driver_note', 'CUSTOMER-NAME PHONE-PRIVATE caused delay', feed='driver_messages', structured=False),)
    ctx = replace(ctx, assessment=replace(ctx.assessment, evidence=rows))
    reply = ' '.join(fact_slots(ctx, 'location').values())
    assert 'đang hoàn trả' in reply
    assert 'WAREHOUSE-PRIVATE' not in reply and 'CUSTOMER-NAME' not in reply


def test_optional_untrusted_feed_cannot_supply_attempt_history():
    ctx = snapshot()
    guard = replace(ctx.guard, required_feeds=('scan_events',), feeds=tuple(
        replace(feed, status='stale') if feed.name == 'delivery_attempts' else feed for feed in ctx.guard.feeds))
    ctx = replace(ctx, guard=guard)
    reply = ' '.join(fact_slots(ctx, 'explanation').values())
    assert 'đang hoàn trả' in reply and 'lần giao' not in reply
