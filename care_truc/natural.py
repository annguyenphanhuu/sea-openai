"""Conversational model drafts around immutable, server-rendered facts."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import unicodedata

from contracts.params import feed_stale_max_min
from .runtime_types import NaturalDraft, PhraseSelection, canonical


SOCIAL_SENTENCES = (
    'Chào bạn', 'Xin chào', 'Xin chào bạn', 'Chào bạn nhé',
    'Mình có thể hỗ trợ gì cho bạn', 'Bạn cần mình hỗ trợ điều gì',
    'Bạn cần hỗ trợ gì không', 'Bạn cần hỗ trợ gì thêm không',
    'Bạn có muốn mình hỗ trợ gì thêm không', 'Bạn cần mình giúp thêm điều gì không',
    'Bạn muốn mình giải thích thêm phần nào',
    'Bạn cần thêm thông tin gì hay muốn mình hỗ trợ điều gì khác không',
    'Rất vui được hỗ trợ bạn', 'Mình rất vui được hỗ trợ bạn',
    'Cảm ơn bạn', 'Cảm ơn bạn vì sự thông cảm', 'Cảm ơn bạn vì đã thông cảm',
    'Mình luôn sẵn sàng hỗ trợ bạn', 'Bạn cứ chia sẻ nếu cần hỗ trợ thêm nhé',
    'Mình hiểu cảm giác chờ đợi của bạn', 'Mình hiểu băn khoăn của bạn',
    'Mình hiểu sự bực bội của bạn', 'Mình hiểu nhu cầu hỗ trợ của bạn',
    'Mình hiểu bạn muốn kiểm tra thông tin',
    'Mình hiểu rằng bạn mong muốn giải quyết nhanh chóng',
    'Mình hiểu bạn muốn biết rõ hơn về chính sách',
    'Mình xin lỗi vì sự bất tiện này', 'Mình rất tiếc vì trải nghiệm chưa thuận tiện của bạn',
    'Bạn cần hỗ trợ về thông tin đơn hàng hay muốn gặp nhân viên',
)


def folded(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
                   if unicodedata.category(c) != 'Mn')


def reply_topic(text: str, intent: str) -> str:
    value = folded(text)
    if re.search(r'\b(bao gio|khi nao|chung nao|ngay nao|du kien|eta)\b', value):
        return 'eta'
    if re.search(r'\b(o dau|den dau|vi tri)\b', value):
        return 'location'
    if re.search(r'\b(chinh sach|boi thuong|den bu|xu|voucher|hoan tien)\b', value):
        return 'policy'
    if re.search(r'\b(chao|hello|hi)\b', value):
        return 'greeting'
    if re.search(r'\b(cam on|thanks|thank you)\b', value):
        return 'thanks'
    if intent == 'ask_why' or re.search(r'\b(giai thich|ro hon|hoan tra|giao may lan|may lan giao|tinh trang don)\b', value):
        return 'explanation'
    return 'help'


@dataclass(frozen=True, slots=True)
class LastScan:
    stage: str
    event_at: datetime


@dataclass(frozen=True, slots=True)
class JourneyFacts:
    last_scan: LastScan | None
    failed_attempts: int
    no_answer_attempts: int


STAGE_LABELS = {
    'created': 'đơn được tạo', 'handed_over': 'đã bàn giao cho đơn vị vận chuyển',
    'linehaul_departed': 'đã xuất phát trên tuyến vận chuyển',
    'linehaul_arrived': 'đã đến điểm nhận trên tuyến vận chuyển',
    'out_for_delivery': 'đang giao hàng', 'delivered': 'đã giao hàng',
    'returning': 'đang hoàn trả', 'returned': 'đã hoàn trả',
    'lost': 'ghi nhận thất lạc', 'damaged': 'ghi nhận hư hỏng',
    'return_failed': 'hoàn trả chưa thành công',
}


def _evidence_groups(snapshot, feed: str) -> list[list[dict]]:
    from .guardrails import age_valid
    health = next((item for item in snapshot.guard.feeds if item.name == feed), None)
    if (health is None or health.status != 'trusted'
            or not age_valid(health.source_timestamp, snapshot.cutoff, feed_stale_max_min)):
        return []
    groups = {}
    for item in snapshot.assessment.evidence:
        if (item['is_structured'] is not True or item['feed'] != feed or item['source_table'] != feed
                or not isinstance(item['record_id'], str) or not item['record_id']):
            continue
        groups.setdefault((item['record_id'], item['ingested_at']), []).append(item)
    return list(groups.values())


def _one_value(rows, code: str, expected_type):
    values = [item['value'] for item in rows if item['fact_code'] == code]
    if not values or any(type(value) is not expected_type or value != values[0] for value in values):
        return None
    return values[0]


def journey_facts(snapshot) -> JourneyFacts:
    scan_groups = [rows for rows in _evidence_groups(snapshot, 'scan_events')
                   if any(item['fact_code'] == 'logistics_stage' for item in rows)]
    last_scan = None
    if len(scan_groups) == 1:
        rows = scan_groups[0]
        stage = _one_value(rows, 'logistics_stage', str)
        stamp = _one_value(rows, 'stage_event_at', str)
        if stage in STAGE_LABELS and stamp:
            try:
                event_at = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                if event_at.utcoffset() is not None and event_at <= rows[0]['ingested_at'] <= snapshot.cutoff:
                    last_scan = LastScan(stage, event_at)
            except ValueError:
                pass
    records = {}
    for rows in _evidence_groups(snapshot, 'delivery_attempts'):
        records.setdefault(rows[0]['record_id'], []).extend(rows)
    failures = no_answer = 0
    for rows in records.values():
        if _one_value(rows, 'failed_delivery_attempt', bool) is True:
            failures += 1
            no_answer += _one_value(rows, 'attempt_outcome', str) == 'no_answer'
    return JourneyFacts(last_scan, failures, no_answer)


def journey_summary(facts: JourneyFacts) -> str:
    parts = []
    if facts.last_scan:
        stamp = facts.last_scan.event_at.astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M')
        parts.append('Mốc vận chuyển gần nhất được ghi nhận lúc ' + stamp + ' theo giờ Việt Nam: '
                     + STAGE_LABELS[facts.last_scan.stage] + '.')
    if facts.failed_attempts:
        attempts = f'Lịch sử ghi nhận {facts.failed_attempts} lần giao chưa thành công'
        if facts.no_answer_attempts:
            attempts += f', trong đó {facts.no_answer_attempts} lần được ghi nhận không liên lạc được'
        parts.append(attempts + '. Đây là kết quả ghi nhận của các lần giao, không phải kết luận bên có lỗi.')
    return ' '.join(parts)


def fact_slots(snapshot, topic: str) -> dict[str, str]:
    from .guardrails import Guardrails
    from .renderer import public_reason
    from .rendering import STATUS

    assessment = snapshot.assessment
    trusted = Guardrails().validate_context(snapshot).allowed
    journey = journey_summary(journey_facts(snapshot)) if trusted else ''
    unknown = 'Thông tin hiện chưa đủ mới hoặc chưa được xác minh, nên mình chưa thể kết luận tình trạng hiện tại.'
    if trusted:
        status = 'Theo thông tin đã xác minh, đơn hàng ' + STATUS.get(assessment.status, 'chưa xác định tình trạng') + '.'
        reason = public_reason(assessment)
        eta = assessment.revised_eta
        if eta is not None and eta >= snapshot.cutoff:
            eta_text = 'Thời gian nhận hàng dự kiến là ' + eta.astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M') + ' theo giờ Việt Nam. Đây là dự kiến, chưa phải cam kết giao mới.'
        else:
            eta_text = 'Mình chưa có thời gian giao dự kiến đã được xác minh, nên chưa thể hẹn bạn ngày nhận hàng cụ thể.'
    else:
        status = unknown
        reason = 'Mình chưa có đủ thông tin đã xác minh để giải thích nguyên nhân cụ thể.'
        eta_text = 'Dự báo giao hàng hiện chưa được xác minh, nên mình chưa thể hẹn bạn ngày nhận hàng cụ thể.'
    if journey:
        eta_text = journey + ' ' + eta_text
        reason = journey + ' ' + reason
    location = (journey + ' ' if journey else '') + 'Mình chưa có vị trí hiện tại đã được xác minh của đơn hàng. Bạn có thể yêu cầu gặp nhân viên để kiểm tra thêm.'
    by_topic = {
        'eta': {'eta': eta_text},
        'location': {'location': location},
        'explanation': {'status': status, 'reason': reason},
        'policy': {'policy': 'Yêu cầu hỗ trợ hoặc bồi thường cần được kiểm tra điều kiện và bằng chứng của đơn. Mình không thể tự hứa số tiền hoặc xác nhận cấp xu qua câu trả lời này.'},
        'greeting': {}, 'thanks': {}, 'help': {},
    }
    return by_topic[topic]


def redact(text: str) -> str:
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email đã ẩn]', text)
    text = re.sub(r'(?<!\w)(?:\+?\d[\d .-]{7,}\d)(?!\w)', '[số đã ẩn]', text)
    return re.sub(r'\bsk-[A-Za-z0-9_-]+', '[khóa đã ẩn]', text)[:1500]


def build_natural_context(outcome, snapshot, history, latest: str, *, semantic_topics: bool = False) -> bytes | None:
    topic = reply_topic(latest, outcome.intent)
    payload = {'mode': 'grounded_reply', 'topic': topic, 'intent': outcome.intent,
               'slots': fact_slots(snapshot, topic),
               'history': [{'role': item['role'], 'text': redact(item['text'])} for item in history[-6:]],
               'customer_message': redact(latest)}
    if semantic_topics and topic == 'help':
        payload['topic_slots'] = {name: fact_slots(snapshot, name) for name in
            ('eta', 'location', 'explanation', 'policy', 'greeting', 'thanks', 'help')}
    while True:
        encoded = canonical(payload).encode('utf-8')
        if len(encoded) <= 12000:
            return encoded
        if not payload['history']:
            return None
        payload['history'].pop(0)


def render_template(draft: NaturalDraft, snapshot) -> str:
    slots = fact_slots(snapshot, draft.topic)
    text = draft.template
    if not isinstance(text, str) or not 1 <= len(text) <= 900:
        raise ValueError('natural_template_invalid')
    names = re.findall(r'\{([a-z_]+)\}', text)
    if set(names) != set(slots) or len(names) != len(slots):
        raise ValueError('natural_slots_invalid')
    literal = re.sub(r'\{[a-z_]+\}', '', text)
    if re.search(r'[\d{}<>\[\]@/\\]|https?\b', literal):
        raise ValueError('natural_literal_invalid')
    allowed_sentences = {folded(sentence) for sentence in SOCIAL_SENTENCES}
    clauses = [folded(' '.join(clause.split()))
               for segment in re.split(r'\{[a-z_]+\}', text)
               for clause in re.split(r'[.!?\n]+', segment) if clause.strip()]
    if len(clauses) > 3 or any(clause not in allowed_sentences for clause in clauses):
        raise ValueError('natural_social_clause_invalid')
    plain = folded(literal)
    if draft.topic == 'greeting' and not re.search(r'\b(chao|hello)\b', plain):
        raise ValueError('natural_greeting_missing')
    if draft.topic == 'thanks' and not re.search(r'\b(vui|cam on|ho tro)\b', plain):
        raise ValueError('natural_acknowledgement_missing')
    for name, value in slots.items():
        text = text.replace('{' + name + '}', value)
    if not text.strip():
        raise ValueError('natural_empty_reply')
    return text.strip()


def fallback_draft(topic: str) -> NaturalDraft:
    templates = {
        'greeting': 'Chào bạn! Mình có thể hỗ trợ gì cho bạn?',
        'thanks': 'Rất vui được hỗ trợ bạn. Bạn cần mình giúp thêm điều gì không?',
        'eta': 'Mình hiểu cảm giác chờ đợi của bạn. {eta}',
        'location': 'Mình hiểu bạn muốn kiểm tra thông tin. {location}',
        'explanation': 'Mình hiểu băn khoăn của bạn. {status} {reason}',
        'policy': 'Mình hiểu nhu cầu hỗ trợ của bạn. {policy}',
        'help': 'Bạn cần hỗ trợ về thông tin đơn hàng hay muốn gặp nhân viên?',
    }
    return NaturalDraft(topic, templates[topic])


async def generate_reply(selector, context: bytes, phrase_id: str, snapshot, clock):
    from .hooks import bounded
    data = json.loads(context)
    topic = data['topic']
    try:
        raw = await bounded(selector.select(context, deadline=clock.monotonic() + 8), clock, 8)
        if not isinstance(raw, bytes) or len(raw) > 4096:
            raise ValueError('natural_bytes_invalid')
        parsed = json.loads(raw)
        expected = {'template', 'topic'} if 'topic_slots' in data else {'template'}
        if not isinstance(parsed, dict) or set(parsed) != expected:
            raise ValueError('natural_schema_invalid')
        selected_topic = parsed.get('topic', topic)
        if 'topic_slots' in data and selected_topic not in data['topic_slots']:
            raise ValueError('natural_topic_invalid')
        draft = NaturalDraft(selected_topic, parsed['template'])
        render_template(draft, snapshot)
        if isinstance(getattr(selector, 'last_call', None), dict):
            selector.last_call['validation_status'] = 'accepted'
        return PhraseSelection(phrase_id, 'model-generated', draft=draft)
    except TimeoutError:
        if isinstance(getattr(selector, 'last_call', None), dict):
            selector.last_call.update(status='fallback', code='model_timeout', validation_status='rejected')
        return PhraseSelection(phrase_id, 'template', ('model_timeout',), fallback_draft(topic))
    except Exception:
        if isinstance(getattr(selector, 'last_call', None), dict):
            selector.last_call.update(status='fallback', validation_status='rejected')
        return PhraseSelection(phrase_id, 'template', ('model_output_rejected',), fallback_draft(topic))
