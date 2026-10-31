"""Conversational model drafts around immutable, server-rendered facts."""

from datetime import timedelta, timezone
import json
import re
import unicodedata

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
    if intent == 'ask_why' or re.search(r'\b(giai thich|ro hon)\b', value):
        return 'explanation'
    return 'help'


def fact_slots(snapshot, topic: str) -> dict[str, str]:
    from .guardrails import Guardrails
    from .renderer import public_reason
    from .rendering import STATUS

    assessment = snapshot.assessment
    trusted = Guardrails().validate_context(snapshot).allowed
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
    by_topic = {
        'eta': {'eta': eta_text},
        'location': {'location': 'Mình chưa có vị trí hiện tại đã được xác minh của đơn hàng. Bạn có thể yêu cầu gặp nhân viên để kiểm tra thêm.'},
        'explanation': {'status': status, 'reason': reason},
        'policy': {'policy': 'Yêu cầu hỗ trợ hoặc bồi thường cần được kiểm tra điều kiện và bằng chứng của đơn. Mình không thể tự hứa số tiền hoặc xác nhận cấp xu qua câu trả lời này.'},
        'greeting': {}, 'thanks': {}, 'help': {},
    }
    return by_topic[topic]


def redact(text: str) -> str:
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email đã ẩn]', text)
    text = re.sub(r'(?<!\w)(?:\+?\d[\d .-]{7,}\d)(?!\w)', '[số đã ẩn]', text)
    return re.sub(r'\bsk-[A-Za-z0-9_-]+', '[khóa đã ẩn]', text)[:1500]


def build_natural_context(outcome, snapshot, history, latest: str) -> bytes | None:
    topic = reply_topic(latest, outcome.intent)
    payload = {'mode': 'grounded_reply', 'topic': topic, 'intent': outcome.intent,
               'slots': fact_slots(snapshot, topic),
               'history': [{'role': item['role'], 'text': redact(item['text'])} for item in history[-6:]],
               'customer_message': redact(latest)}
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
    topic = json.loads(context)['topic']
    try:
        raw = await bounded(selector.select(context, deadline=clock.monotonic() + 8), clock, 8)
        if not isinstance(raw, bytes) or len(raw) > 4096:
            raise ValueError('natural_bytes_invalid')
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or set(parsed) != {'template'}:
            raise ValueError('natural_schema_invalid')
        draft = NaturalDraft(topic, parsed['template'])
        render_template(draft, snapshot)
        return PhraseSelection(phrase_id, 'model-generated', draft=draft)
    except TimeoutError:
        return PhraseSelection(phrase_id, 'template', ('model_timeout',), fallback_draft(topic))
    except Exception:
        return PhraseSelection(phrase_id, 'template', ('model_output_rejected',), fallback_draft(topic))
