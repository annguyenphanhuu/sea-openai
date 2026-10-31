"""Uncalibrated, as-of Kaplan-Meier baseline for remaining delivery time."""

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json


@dataclass(frozen=True, slots=True)
class Observation:
    order_id: str
    seconds: float
    delivered: bool


@dataclass(frozen=True, slots=True)
class Forecast:
    late_probability: float
    revised_eta: datetime | None
    confidence: float
    sample_count: int
    delivered_count: int
    cohort_id: str


class SurvivalCurve:
    """Retain undelivered observations as right-censored, rather than dropping them."""

    def __init__(self, observations: list[Observation]) -> None:
        self.samples = sorted(observations, key=lambda item: (item.seconds, item.order_id))
        events = Counter(item.seconds for item in observations if item.delivered)
        all_times = Counter(item.seconds for item in observations)
        self.times = sorted(all_times)
        self.survival = []
        remaining, survival = len(observations), 1.0
        for seconds in self.times:
            survival *= 1 - events[seconds] / remaining
            self.survival.append(survival)
            remaining -= all_times[seconds]
        self.event_times = sorted(item.seconds for item in observations if item.delivered)
        self.durations = sorted(item.seconds for item in observations)
        payload = [(item.order_id, item.seconds, item.delivered) for item in self.samples]
        self.cohort_id = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

    def _survival_at(self, seconds: float) -> float:
        index = bisect_right(self.times, seconds) - 1
        return self.survival[index] if index >= 0 else 1.0

    def predict(self, *, age_seconds: float, remaining_seconds: float,
                tick_at: datetime, min_samples: int = 20) -> Forecast | None:
        if age_seconds < 0 or remaining_seconds < 0:
            return None
        sample_count = len(self.durations) - bisect_right(self.durations, age_seconds)
        delivered_count = len(self.event_times) - bisect_right(self.event_times, age_seconds)
        if sample_count < min_samples or delivered_count < 5:
            return None
        survival_now = self._survival_at(age_seconds)
        horizon = age_seconds + remaining_seconds
        if survival_now <= 0 or (horizon > self.times[-1] and self.survival[-1] > 0):
            return None
        probability = self._survival_at(horizon) / survival_now
        median = next((seconds for seconds, survival in zip(self.times, self.survival)
                       if seconds > age_seconds and survival <= survival_now / 2), None)
        # This support score is explicitly not a calibrated probability of correctness.
        confidence = min(0.8, sample_count / 100) * delivered_count / sample_count
        return Forecast(
            late_probability=min(1.0, max(0.0, probability)),
            revised_eta=tick_at + timedelta(seconds=median - age_seconds) if median else None,
            confidence=confidence, sample_count=sample_count,
            delivered_count=delivered_count, cohort_id=self.cohort_id,
        )
