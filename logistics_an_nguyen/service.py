"""Python integration API for the platform's A3 -> A2 -> A1 tick runner."""

import json
from datetime import datetime
from hashlib import sha256
from typing import Iterable

from contracts.types import Evidence, OrderAssessment

from .assessment import assess_order
from .models import (
    FeedHealth, OrderFacts, SupervisorQuestion, TickResult, aware, utc_iso,
)


def evidence_payload(evidence: tuple[Evidence, ...]) -> list[dict]:
    return [dict(item, ingested_at=utc_iso(item["ingested_at"])) for item in evidence]


def assessment_payload(assessment: OrderAssessment) -> dict:
    """Return JSON-safe contract v0 fields for Truc's authenticated routes."""
    return {
        "order_id": assessment.order_id,
        "assessed_at": utc_iso(assessment.assessed_at),
        "status": assessment.status,
        "guaranteed_date": assessment.guaranteed_date.isoformat(),
        "revised_eta": utc_iso(assessment.revised_eta) if assessment.revised_eta else None,
        "late_days": assessment.late_days,
        "late_probability": assessment.late_probability,
        "confidence": assessment.confidence,
        "fault_party": assessment.fault_party,
        "reason_codes": list(assessment.reason_codes),
        "evidence": evidence_payload(assessment.evidence),
    }


def supervisor_questions(assessment: OrderAssessment) -> tuple[SupervisorQuestion, ...]:
    """Create stable review requests; text from a source is never an instruction."""
    prompts = {}
    if any(code.startswith(("feed_", "conflicting_fact:")) for code in assessment.reason_codes):
        prompts["verify_evidence"] = "Please verify unavailable feeds or conflicting structured facts."
    if "risk_estimate_missing" in assessment.reason_codes:
        prompts["provide_risk_estimate"] = "Please provide a structured lateness estimate and its provenance."
    if assessment.status == "exception":
        prompts["review_exception"] = "Please review the structured logistics exception."
    if assessment.late_days and assessment.fault_party == "unknown":
        prompts["verify_fault"] = "Please confirm the responsible party using structured evidence."
    if assessment.status in ("exception", "late", "at_risk", "watch") and "eta_missing" in assessment.reason_codes:
        prompts["provide_eta"] = "Please provide an evidence-backed revised ETA."
    questions = []
    # Changing the tick alone does not duplicate a question. Changed evidence does.
    structured = tuple(item for item in assessment.evidence if item["is_structured"])
    for reason, prompt in sorted(prompts.items()):
        identity = json.dumps(
            [assessment.order_id, reason, evidence_payload(structured)],
            sort_keys=True, ensure_ascii=False, allow_nan=False,
        )
        question_id = "a2-" + sha256(identity.encode("utf-8")).hexdigest()
        questions.append(SupervisorQuestion(
            question_id=question_id, order_id=assessment.order_id,
            reason_code=reason, question_text=f"[{reason}] {prompt}",
            asked_at=assessment.assessed_at, evidence=structured,
        ))
    return tuple(questions)


def evaluate_tick(
    orders: Iterable[OrderFacts], *, tick_at: datetime,
    feed_health: Iterable[FeedHealth],
) -> TickResult:
    """Assess a full replay snapshot; platform owns ingestion and checkpoints."""
    aware(tick_at, "tick_at")
    health = tuple(feed_health)
    visible = {}
    for order in orders:
        if order.ingested_at > tick_at:
            continue
        if order.order_id in visible:
            raise ValueError("expected one replay-visible snapshot per order_id")
        visible[order.order_id] = order
    assessments = tuple(
        assess_order(order, tick_at=tick_at, feed_health=health)
        for _, order in sorted(visible.items())
    )
    return TickResult(
        assessments=assessments,
        questions=tuple(question for item in assessments for question in supervisor_questions(item)),
    )
