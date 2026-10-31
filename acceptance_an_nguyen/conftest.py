"""Isolated normalized fixtures; no release data is created or modified."""

from datetime import date, datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from logistics_an_nguyen import FeedHealth, OrderFacts


TICK = datetime(2026, 11, 1, 5, tzinfo=timezone.utc)


@pytest.fixture
def tick():
    return TICK


@pytest.fixture
def fact():
    def make(code, value, *, ingested_at=TICK, feed="ops", structured=True, record_id=None):
        return {
            "feed": feed, "source_table": "test_events",
            "record_id": record_id or code, "ingested_at": ingested_at,
            "fact_code": code, "value": value, "is_structured": structured,
        }
    return make


@pytest.fixture
def order(fact):
    def make(*evidence, order_id="order-1", guaranteed_date=date(2026, 11, 1),
             ingested_at=TICK, required_feeds=("core", "ops"), defaults=True):
        base = (fact("late_probability", 0.1), fact("confidence", 0.9)) if defaults else ()
        return OrderFacts(order_id, guaranteed_date, ingested_at, required_feeds, base + evidence)
    return make


@pytest.fixture
def health(tick):
    return (FeedHealth("core", "trusted", tick, tick), FeedHealth("ops", "trusted", tick, tick))


@pytest.fixture
def state():
    connection = sqlite3.connect(":memory:")
    schema = Path(__file__).resolve().parents[1] / "contracts" / "schema_state.sql"
    connection.executescript(schema.read_text(encoding="utf-8"))
    yield connection
    connection.close()
