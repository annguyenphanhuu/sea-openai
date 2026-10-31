"""Test-only adapter values; no production executor or money effects."""
from dataclasses import dataclass
from care_truc.models import AssessmentRef, CareContext, TrustedContext


@dataclass
class FixedContextReader:
    context: CareContext

    def read(self, trusted: TrustedContext, order_id: str,
             assessment_ref: AssessmentRef | None = None) -> CareContext:
        return self.context
