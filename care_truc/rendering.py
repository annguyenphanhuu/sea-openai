"""Closed phrase choices; facts are attached only by deterministic rendering.

Call select_phrases outside database transactions. Supply the server replay cutoff
on every render. Missing cutoff is safe but always renders unverified facts.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from care_truc.context import assessment_is_current, check_proactive
from care_truc.models import CareContext, IntentSignals, RenderedReply, normalize_utc
from typing import Protocol


class ClosedPhraseSelector(Protocol):
    def select(self, template_id: str, allowed_phrase_ids: tuple[str, ...]) -> object: ...

VIETNAM=timezone(timedelta(hours=7))
PHRASES={'standard':'Xin lỗi vì sự bất tiện này.', 'warm':'Xin lỗi vì trải nghiệm chưa thuận tiện của bạn.'}
TEMPLATES={
 'opening':'Tôi xin cập nhật đơn hàng của bạn.',
 'ask_why':'Tôi xin giải thích theo thông tin đã được ghi nhận.',
 'ask_human':'Yêu cầu gặp nhân viên đã được ghi nhận để bàn giao.',
 'handoff':'Yêu cầu hỗ trợ đã được ghi nhận để bàn giao.',
 'want_cancel':'Bạn có chắc chắn muốn yêu cầu hủy đơn không? Vui lòng xác nhận lại.',
 'cancel_confirmation':'Bạn có chắc chắn muốn yêu cầu hủy đơn không? Vui lòng xác nhận lại.',
 'cancel_retracted':'Tôi đã ghi nhận bạn không muốn tiếp tục yêu cầu hủy.',
 'want_more':'Tôi đã ghi nhận nhu cầu hỗ trợ thêm của bạn.',
 'coins_pending':'Yêu cầu xu đang chờ xử lý; chưa có xác nhận cấp thành công.',
 'coins_blocked':'Hiện chưa đủ điều kiện để xử lý yêu cầu xu.',
 'accept':'Cảm ơn bạn đã phản hồi.',
 'off_topic':'Bạn cần hỗ trợ điều gì về đơn hàng?',
 'unreasonable_abusive':'Tôi có thể tiếp tục hỗ trợ nếu cuộc trò chuyện giữ sự tôn trọng.',
}
STATUS={'exception':'có ngoại lệ vận chuyển','unknown_feed':'chưa xác minh','customer_fault':'cần phối hợp từ khách hàng','late':'đã trễ ngày cam kết','at_risk':'có nguy cơ trễ','watch':'cần theo dõi','slow_safe':'đang vận chuyển chậm','on_track':'đang theo tiến độ ghi nhận'}
REASONS={'guaranteed_day_exceeded':'Đã qua ngày giao cam kết.', 'delivery_confirmed':'Nguồn có cấu trúc đã ghi nhận giao hàng.'}
PUBLIC_FACTS={'logistics_stage':{'lost':'Nguồn ghi nhận thất lạc.', 'damaged':'Nguồn ghi nhận hư hỏng.', 'return_failed':'Nguồn ghi nhận hoàn hàng chưa thành công.'}, 'slow_safe':{True:'Nguồn ghi nhận vận chuyển chậm nhưng an toàn.'}}


def select_phrases(selector: ClosedPhraseSelector | None, template_id: str) -> object | None:
    if selector is None:
        return None
    try:
        return selector.select(template_id,tuple(PHRASES))
    except Exception:
        return {'_selector_error':True}


def render(template_id: str, ctx: CareContext, signals: IntentSignals,
           selection: object | None = None, *, cutoff: datetime | None = None) -> RenderedReply:
    codes=[]
    source='template'
    phrase=PHRASES['standard']
    if selection is not None:
        phrase_id=None
        if type(selection) is dict and set(selection)=={'phrase_id'} and type(selection['phrase_id']) is str:
            phrase_id=selection['phrase_id']
        elif type(selection) is str:
            phrase_id=next((key for key,value in PHRASES.items() if value==selection),None)
        if phrase_id in PHRASES:
            phrase=PHRASES[phrase_id]
            source='phrase_selector'
        else:
            codes.append('phrase_selector_error' if type(selection) is dict and selection=={'_selector_error':True} else 'phrase_selection_invalid')
    if template_id not in TEMPLATES:
        codes.append('template_unknown')
    parts=[phrase,TEMPLATES.get(template_id,TEMPLATES['off_topic'])]
    facts = render_facts(ctx, cutoff=cutoff)
    return RenderedReply(' '.join(parts) + ' ' + facts.text, source,
                         facts.evidence_refs, tuple(codes) + facts.decision_codes,
                         facts.public_evidence)


def render_facts(ctx: CareContext, *, cutoff: datetime | None) -> RenderedReply:
    parts=[]
    codes=[]
    assessment=ctx.assessment
    refs=[]
    public=[]
    if assessment is None:
        parts.append('Chưa đủ thông tin đã xác minh về đơn hàng. ETA chưa xác định.')
        codes.append('assessment_missing')
    else:
        current=cutoff is not None and assessment_is_current(assessment,cutoff)
        trusted=current and check_proactive(ctx.guard,cutoff).allowed
        if any(code.startswith(('feed_', 'untrusted_fact:', 'conflicting_fact:')) for code in assessment.reason_codes):
            trusted=False
        if cutoff is not None and any(item['ingested_at']>normalize_utc(cutoff) for item in assessment.evidence):
            trusted=False
        stamp=assessment.assessed_at.astimezone(VIETNAM).strftime('%d/%m/%Y %H:%M %z')
        parts.append(f'Thông tin cập nhật lúc {stamp}.')
        if not trusted:
            codes.append('facts_unverified')
            parts.append('Thông tin chưa xác minh ở thời điểm hiện tại; tình trạng ghi nhận trước đó: '+STATUS.get(assessment.status,'chưa xác định')+'.')
        else:
            parts.append('Tình trạng: '+STATUS.get(assessment.status,'chưa xác định')+'.')
        parts.append('Ngày giao cam kết: '+assessment.guaranteed_date.strftime('%d/%m/%Y')+'.')
        eta=assessment.revised_eta
        if trusted and eta is not None and eta>=normalize_utc(cutoff):
            parts.append('ETA dự kiến: '+eta.astimezone(VIETNAM).strftime('%d/%m/%Y %H:%M %z')+'; đây là dự kiến, chưa phải cam kết mới.')
        else:
            parts.append('ETA hiện chưa xác định.' if trusted else 'ETA chưa xác định ở thời điểm hiện tại; dự báo cũ không được dùng làm dự báo hiện tại.')
        reasons=[REASONS[c] for c in assessment.reason_codes if c in REASONS] if trusted else []
        parts.extend(reasons or ['chưa đủ thông tin để xác nhận nguyên nhân.'])
        for item in assessment.evidence:
            # Opaque staff trace refs, never source record IDs or raw text.
            payload='|'.join(str(item[k]) for k in ('feed','source_table','record_id','fact_code','ingested_at'))
            refs.append('evidence:'+sha256(payload.encode()).hexdigest())
            mapping=PUBLIC_FACTS.get(item['fact_code'],{})
            value=item['value']
            if trusted and item['is_structured'] is True and type(value) in (str,bool) and value in mapping:
                public.append(mapping[value])
    return RenderedReply(' '.join(parts),'template',tuple(refs),tuple(codes),tuple(dict.fromkeys(public)))
