"""Censoring, conditional survival, sample support and baseline output."""

from datetime import datetime, timedelta

import pytest

from logistics_an_nguyen.forecast import Observation, SurvivalCurve


NOW = datetime.fromisoformat("2026-10-28T12:00:00+07:00")


def test_kaplan_meier_includes_censored_orders():
    samples = [Observation(str(i), 10, True) for i in range(10)]
    samples += [Observation(str(i), 20, False) for i in range(10, 20)]
    result = SurvivalCurve(samples).predict(age_seconds=0, remaining_seconds=15, tick_at=NOW)
    assert result.late_probability == pytest.approx(0.5)
    assert result.revised_eta == NOW + timedelta(seconds=10)
    assert result.sample_count == 20


def test_conditional_remaining_time_uses_survivors_at_current_age():
    samples = [Observation(str(i), 10, True) for i in range(10)]
    samples += [Observation(str(i), 30, True) for i in range(10, 30)]
    result = SurvivalCurve(samples).predict(age_seconds=15, remaining_seconds=10, tick_at=NOW)
    assert result.sample_count == 20
    assert result.late_probability == 1
    assert result.revised_eta == NOW + timedelta(seconds=15)


def test_insufficient_history_and_unobserved_tail_have_no_forecast():
    small = SurvivalCurve([Observation(str(i), 30, True) for i in range(19)])
    assert small.predict(age_seconds=0, remaining_seconds=10, tick_at=NOW) is None
    samples = [Observation(str(i), 10, True) for i in range(10)]
    samples += [Observation(str(i), 20, False) for i in range(10, 30)]
    curve = SurvivalCurve(samples)
    assert curve.predict(age_seconds=0, remaining_seconds=30, tick_at=NOW) is None
    result = curve.predict(age_seconds=0, remaining_seconds=15, tick_at=NOW)
    assert result.revised_eta is None


def test_censored_observation_at_event_time_is_still_in_risk_set():
    samples = [Observation(str(i), 10, True) for i in range(10)]
    samples += [Observation(str(i), 10, False) for i in range(10, 20)]
    assert SurvivalCurve(samples).predict(age_seconds=0, remaining_seconds=10, tick_at=NOW).late_probability == 0.5


def test_cohort_identifier_is_order_independent():
    samples = [Observation(str(i), i + 1, True) for i in range(30)]
    assert SurvivalCurve(samples).cohort_id == SurvivalCurve(list(reversed(samples))).cohort_id
