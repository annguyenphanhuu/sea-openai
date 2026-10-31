"""All facts and handoff summaries are rendered by code, not a model."""

from .guardrails import Guardrails
from .phrases import CATALOG
from .runtime_types import RenderedResponse, canonical, fingerprint


class ResponseRenderer:
    version = "1"

    def render(self, outcome, context, phrase_id: str) -> RenderedResponse:
        text = CATALOG[phrase_id]
        assessment = context.assessment
        reference = fingerprint(assessment) if assessment else None
        if phrase_id.startswith("explain"):
            if assessment and Guardrails().validate_context(context).allowed:
                eta = assessment.revised_eta.isoformat() if assessment.revised_eta else "chưa xác định"
                text += f" Ngày cam kết: {assessment.guaranteed_date.isoformat()}. ETA: {eta}."
                text += f" Cập nhật: {assessment.assessed_at.isoformat()}."
            else:
                text += " Thông tin hiện tại chưa được xác nhận; ETA chưa xác định."
        return RenderedResponse(text, phrase_id, reference)

    def render_handoff(self, state, context) -> str:
        return canonical({"order_id": state.order_id, "status": state.status,
            "turn_count": state.turn_count, "pending_confirmation": state.pending,
            "assessment_ref": fingerprint(context.assessment) if context.assessment else None})
