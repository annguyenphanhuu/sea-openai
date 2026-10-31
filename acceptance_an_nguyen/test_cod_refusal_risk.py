"""Literal COD risk cases supplied by the user; isolated normalized facts."""

from datetime import date

from logistics_an_nguyen import assess_order


def risk_codes(assessment):
    return tuple(code for code in assessment.reason_codes if code.startswith("cod_refusal_risk"))


def test_literal_high_cod_late_value_or_one_failed_attempt(tick, fact, order, health):
    for amount, failed in ((1_200_000, False), (250_000, True)):
        assessment = assess_order(order(
            fact("payment_method", "COD"), fact("items_value_vnd", amount),
            fact("failed_delivery_attempt", failed), guaranteed_date=date(2026, 10, 31),
        ), tick_at=tick, feed_health=health)
        assert assessment.status == "late"
        assert assessment.fault_party == "unknown"
        assert risk_codes(assessment) == ("cod_refusal_risk:high",)


def test_literal_medium_cod_at_risk_250000_without_failed_attempt(tick, fact, order, health):
    assessment = assess_order(order(
        fact("payment_method", "COD"), fact("items_value_vnd", 250_000),
        fact("failed_delivery_attempt", False),
        fact("revised_eta", "2026-11-02T10:00:00+07:00"),
    ), tick_at=tick, feed_health=health)
    assert assessment.status == "at_risk"
    assert assessment.fault_party == "unknown"
    assert risk_codes(assessment) == ("cod_refusal_risk:medium",)


def test_literal_none_prepaid_late_or_cod_on_track(tick, fact, order, health):
    for payment, guarantee, expected_status in (
        ("PREPAID", date(2026, 10, 31), "late"),
        ("COD", date(2026, 11, 1), "on_track"),
    ):
        assessment = assess_order(order(
            fact("payment_method", payment), fact("items_value_vnd", 1_200_000),
            fact("failed_delivery_attempt", True), guaranteed_date=guarantee,
        ), tick_at=tick, feed_health=health)
        assert assessment.status == expected_status
        assert assessment.fault_party == "unknown"
        assert risk_codes(assessment) == ()
