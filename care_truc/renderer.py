"""All facts and handoff summaries are rendered by code, not a model."""

from .guardrails import Guardrails
from .models import CareContext, GuardSnapshot, FeedSnapshot
from .rendering import render_facts
import json
from .phrases import CATALOG
from .runtime_types import RenderedResponse, canonical, fingerprint


def public_reason(assessment) -> str:
    reasons = set(assessment.reason_codes)
    facts = {item["fact_code"]: item["value"] for item in assessment.evidence if item["is_structured"]}
    if "status:watch" in reasons and type(facts.get("stationary_ticks")) is int and facts["stationary_ticks"] >= 2:
        return "Qua ít nhất hai kỳ cập nhật, đơn vẫn chưa có tiến triển vận chuyển được ghi nhận."
    if "status:exception" in reasons:
        labels = {"lost": "thất lạc", "damaged": "hư hỏng", "return_failed": "hoàn trả không thành công"}
        if facts.get("logistics_stage") in labels:
            return "Thông tin vận chuyển ghi nhận kiện hàng " + labels[facts["logistics_stage"]] + "."
    if "guaranteed_day_exceeded" in reasons and assessment.late_days > 0:
        return "Hiện mình chưa có thông tin xác nhận vì sao đơn bị trễ, nên chưa thể nói chính xác nguyên nhân với bạn."
    if "eta_missing" in reasons:
        return "Hiện mình chưa có thời gian giao dự kiến đã được xác nhận để báo bạn."
    return "Hiện mình chưa có đủ thông tin để nói chính xác nguyên nhân với bạn."


class ResponseRenderer:
    version = "4"

    def render(self, outcome, context, phrase_id: str, *, draft=None) -> RenderedResponse:
        text = CATALOG[phrase_id]
        if any(code in outcome.codes for code in ("cancel_confirmation_expired", "cancel_confirmation_invalid")):
            text = "Xác nhận hủy không còn hợp lệ. Nếu vẫn muốn hủy, bạn cần yêu cầu hủy và xác nhận lại lời nhắc mới."
        assessment = context.assessment
        reference = fingerprint(assessment) if assessment else None
        guard = context.guard
        domain_guard = GuardSnapshot(guard.agent_id, guard.heartbeat,
            guard.required_feeds, tuple(FeedSnapshot(f.name, f.status, f.source_timestamp)
                                       for f in guard.feeds),
            () if guard.contact_allowed else ("contact_blocked",)) if guard else None
        facts = render_facts(CareContext(assessment, None, context.items_value_vnd,
                            domain_guard, "unknown"), cutoff=context.cutoff)
        if phrase_id.startswith("explain") or phrase_id == "opening":
            text += " " + facts.text
            if assessment and Guardrails().validate_context(context).allowed:
                text += " " + public_reason(assessment)
        if phrase_id == 'opening' and Guardrails().validate_context(context).allowed:
            from .natural import fact_slots
            from .rendering import STATUS
            introduction = 'Chào bạn, mình muốn cập nhật về đơn hàng của bạn.'
            if assessment.status == 'late':
                introduction += ' Mình xin lỗi bạn vì phải chờ thêm.'
            status = 'Đơn hàng ' + STATUS.get(assessment.status, 'chưa xác định tình trạng') + '.'
            promised = 'Ngày giao cam kết: ' + assessment.guaranteed_date.strftime('%d/%m/%Y') + '.'
            text = (introduction + '\n\n' + status + ' ' + promised + ' '
                    + fact_slots(context, 'eta')['eta']
                    + '\n\nBạn muốn mình giải thích tình trạng đơn hay tìm hiểu điều kiện hỗ trợ?')
        if draft is not None:
            from .natural import render_template
            if (outcome.phrase_id not in ('explain', 'clarify') or outcome.proposals
                    or any(code.startswith('cancel_confirmation_') for code in outcome.codes)):
                raise ValueError('natural_transactional_output')
            text = render_template(draft, context)
        return RenderedResponse(text, phrase_id, reference, facts.evidence_refs,
                                facts.public_evidence, facts.decision_codes, draft)

    def render_handoff(self, state, context, *, event=None, history=(), effects=(), previous_pending=None, reason=None, evidence_refs=(), receipts=()) -> str:
        statements = [{"label": "customer_statement", "text": item.get("text") or "",
                       "kind": item.get("kind")} for item in history]
        if event is not None:
            statements.append({"label": "customer_statement", "text": event.text or "",
                               "kind": event.kind})
        return canonical({"order_id": state.order_id, "status": state.status,
            "reason": reason, "evidence_refs": evidence_refs,
            "action_receipts": receipts,
            "cancellation_state": "invalidated" if previous_pending else "none",
            "customer_need": statements,
            "facts_trust": {"available": context.assessment is not None,
                "current_and_trusted": Guardrails().validate_context(context).allowed,
                "codes": Guardrails().validate_context(context).codes,
                "assessed_at": context.assessment.assessed_at if context.assessment else None,
                "cutoff": context.cutoff},
            "turn_count": state.turn_count, "pending_confirmation": state.pending,
            "invalidated_confirmation": previous_pending,
            "assessment_ref": fingerprint(context.assessment) if context.assessment else None,
            "facts": {"status": context.assessment.status, "reason": public_reason(context.assessment),
                "guaranteed_date": context.assessment.guaranteed_date,
                "revised_eta": context.assessment.revised_eta} if context.assessment else {},
            "customer_statements": statements,
            "actions": [{"effect_id": row["id"], "kind": json.loads(row["proposal"])["kind"],
                         "delivery_status": row["state"], "outcome": row["outcome"]} for row in effects],
            "next_decision": "Nhân viên kiểm tra nhu cầu khách và kết quả các yêu cầu đang chờ trước khi xử lý tiếp."})
