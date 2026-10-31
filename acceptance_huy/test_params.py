"""Boundary checks for compensation quotes, without issuing compensation."""

import pytest

from contracts.params import late_xu_for


@pytest.mark.parametrize(
    ("items_value_vnd", "expected_xu"),
    [
        (0, 10_000),
        (None, 10_000),
        (6_500, 10_000),
        (300_000, 15_000),
        (1_234_567, 61_000),
        (20_154_000, 1_000_000),
        (100_000, 10_000),
        (200_000, 10_000),
        (219_999, 10_000),
        (220_000, 11_000),
        (999_999, 49_000),
        (1_000_000, 50_000),
        (19_999_999, 999_000),
        (20_000_000, 1_000_000),
        (10**30, 1_000_000),
    ],
)
def test_quote_rounding_and_caps(items_value_vnd, expected_xu):
    assert late_xu_for(items_value_vnd=items_value_vnd) == expected_xu


@pytest.mark.parametrize("invalid", [True, False, 200_000.0, "200000"])
def test_quote_rejects_non_integer_values(invalid):
    with pytest.raises(TypeError):
        late_xu_for(invalid)


def test_quote_rejects_negative_value():
    with pytest.raises(ValueError):
        late_xu_for(-1)
