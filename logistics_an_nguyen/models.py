"""A2-local input types; these do not extend the shared contracts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Literal

from contracts.types import Evidence, OrderAssessment


# Modern Vietnam replay dates use UTC+07, without an optional tzdata dependency.
VIETNAM = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")
FeedStatus = Literal["healthy", "degraded", "blocked", "unknown"]


def aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


def nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def probability(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in [0, 1]")
    if not 0 <= value <= 1 or not isfinite(value):
        raise ValueError(f"{name} must be a finite number in [0, 1]")
    return float(value)


def parse_instant(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO 8601 timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO 8601 timestamp") from error
    return aware(result, name)


def utc_iso(value: datetime) -> str:
    return aware(value, "timestamp").astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class OrderFacts:
    order_id: str
    guaranteed_date: date
    ingested_at: datetime
    required_feeds: tuple[str, ...]
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        nonempty(self.order_id, "order_id")
        if type(self.guaranteed_date) is not date:
            raise ValueError("guaranteed_date must be a date, not a datetime")
        aware(self.ingested_at, "order ingested_at")
        if not isinstance(self.required_feeds, tuple) or not self.required_feeds:
            raise ValueError("required_feeds must be a nonempty tuple")
        for feed in self.required_feeds:
            nonempty(feed, "required feed")
        if len(set(self.required_feeds)) != len(self.required_feeds):
            raise ValueError("required_feeds must be unique")
        if not isinstance(self.evidence, tuple):
            raise ValueError("evidence must be a tuple")


@dataclass(frozen=True, slots=True)
class FeedHealth:
    feed: str
    status: FeedStatus
    checked_at: datetime

    def __post_init__(self) -> None:
        nonempty(self.feed, "feed")
        if self.status not in ("healthy", "degraded", "blocked", "unknown"):
            raise ValueError("invalid feed status")
        aware(self.checked_at, "checked_at")


@dataclass(frozen=True, slots=True)
class SupervisorQuestion:
    question_id: str
    order_id: str
    reason_code: str
    question_text: str
    asked_at: datetime
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class TickResult:
    assessments: tuple[OrderAssessment, ...]
    questions: tuple[SupervisorQuestion, ...]
