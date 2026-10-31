"""A2 interoperability with Huy's delivered state primitives, not a tick runner."""

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import sqlite3

import pytest

from logistics_an_nguyen import FeedHealth, OrderFacts, ProgressTracker, QuestionStore, evaluate_tick
from platform_huy.dto import SourceIdentity
from platform_huy.state import bootstrap, canonical, immediate, utc


TICK = datetime(2026, 10, 28, 5, tzinfo=timezone.utc)


@pytest.mark.parametrize("abort", [False, True])
def test_questions_progress_and_payload_share_actual_platform_transaction(abort):
    with sqlite3.connect(":memory:", isolation_level=None) as db:
        bootstrap(db, run_id="isolated-a2-test", start_at=TICK,
                  identity=SourceIdentity("a" * 64, "b" * 64, TICK, TICK + timedelta(days=1)))
        store = QuestionStore(db)
        tracker = ProgressTracker()
        feeds = (FeedHealth("orders", "trusted", TICK, TICK),)
        facts = tracker.apply((OrderFacts("o1", date(2026, 10, 29), TICK, ("orders",)),),
                              tick_at=TICK, feed_health=feeds)
        result = evaluate_tick(facts, tick_at=TICK, feed_health=feeds)
        payload = canonical(result)

        def publish():
            with immediate(db):
                store.save(result.questions)
                db.execute("INSERT INTO a2_progress VALUES (1,?,?)", (utc(TICK), canonical(tracker.records)))
                db.execute("INSERT INTO tick_results VALUES (?,?,?)",
                           (utc(TICK), payload, sha256(payload.encode()).hexdigest()))
                if abort:
                    raise RuntimeError("caller aborts publication")
                db.execute("UPDATE replay_checkpoint SET tick_at=?,scan_watermark=?,version=1 WHERE singleton=1",
                           (utc(TICK), utc(TICK)))

        if abort:
            with pytest.raises(RuntimeError, match="caller aborts"):
                publish()
        else:
            publish()
        assert not db.in_transaction
        assert len(store.list_questions()) == (0 if abort else len(result.questions))
        assert db.execute("SELECT COUNT(*) FROM a2_progress").fetchone()[0] == int(not abort)
        assert db.execute("SELECT COUNT(*) FROM tick_results").fetchone()[0] == int(not abort)
        assert db.execute("SELECT version FROM replay_checkpoint").fetchone()[0] == int(not abort)
        assert db.execute("SELECT current_at,version FROM demo_clock").fetchone() == (None, 0)
        if not abort:
            saved = json.loads(db.execute("SELECT records_json FROM a2_progress").fetchone()[0])
            restored = ProgressTracker(saved)
            repeated = evaluate_tick(restored.apply(
                (OrderFacts("o1", date(2026, 10, 29), TICK, ("orders",)),), tick_at=TICK, feed_health=feeds),
                tick_at=TICK, feed_health=feeds)
            assert repeated == result
            with immediate(db):
                store.save(repeated.questions)
            assert len(store.list_questions()) == len(result.questions)
