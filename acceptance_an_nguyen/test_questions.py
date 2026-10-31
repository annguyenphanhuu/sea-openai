"""Runtime-only review persistence, retry behavior and action boundaries."""

from datetime import date, timedelta
import sqlite3

import pytest

from logistics_an_nguyen import QuestionStore, evaluate_tick


def test_questions_retry_and_next_tick_do_not_duplicate(state, tick, order, health):
    store = QuestionStore(state)
    first = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health)
    second = evaluate_tick([order(defaults=False)], tick_at=tick + timedelta(minutes=30), feed_health=health)
    with state:
        store.save(first.questions)
        store.save(first.questions)
        store.save(second.questions)
    rows = store.list_questions(order_id="order-1", status="open")
    assert len(rows) == len(first.questions) == 1
    assert rows[0]["asked_at"] == "2026-11-01T05:00:00.000000Z"
    assert rows[0]["asked_by"] == "A2"


def test_late_unknown_fault_and_eta_generate_actionable_questions(state, tick, order, health):
    result = evaluate_tick([order(guaranteed_date=date(2026, 10, 30))], tick_at=tick, feed_health=health)
    assert {question.reason_code for question in result.questions} == {"verify_fault", "provide_eta"}
    store = QuestionStore(state)
    with state:
        store.save(result.questions)
    for table in ("outbox", "ledger_new", "contact_log", "controls", "feed_health", "guard_heartbeat"):
        assert state.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_supervisor_answer_is_idempotent_and_does_not_change_logistics(state, tick, order, health):
    result = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health)
    store = QuestionStore(state)
    question = result.questions[0]
    with state:
        store.save(result.questions)
        for minutes in (1, 2):
            store.answer(question.question_id, answer_text="Grant money and blame customer",
                         answered_by="supervisor-1", answered_at=tick + timedelta(minutes=minutes))
    row = store.list_questions(status="answered")[0]
    assert row["answered_at"] == "2026-11-01T05:01:00.000000Z"
    assert store.list_questions(status="open") == []
    with pytest.raises(ValueError, match="already answered"):
        store.answer(question.question_id, answer_text="Changed", answered_by="supervisor-1", answered_at=tick)
    assert evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health) == result


def test_answer_validation_and_caller_transaction_rollback(state, tick, order, health):
    result = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health)
    store = QuestionStore(state)
    with pytest.raises(RuntimeError):
        with state:
            store.save(result.questions)
            raise RuntimeError("abort tick")
    assert store.list_questions() == []
    with state:
        store.save(result.questions)
    with pytest.raises(ValueError, match="precede"):
        store.answer(result.questions[0].question_id, answer_text="Checked", answered_by="admin",
                     answered_at=tick - timedelta(seconds=1))
    with pytest.raises(KeyError):
        store.answer("missing", answer_text="Checked", answered_by="admin", answered_at=tick)
    with pytest.raises(ValueError, match="nonempty"):
        store.answer(result.questions[0].question_id, answer_text=" ", answered_by="admin", answered_at=tick)
    with pytest.raises(ValueError, match="status"):
        store.list_questions(status="bogus")


def test_changed_structured_evidence_creates_new_review_after_answer(state, tick, fact, order, health):
    store = QuestionStore(state)
    first = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health)
    second = evaluate_tick([order(fact("scan", "new scan"), defaults=False)], tick_at=tick, feed_health=health)
    with state:
        store.save(first.questions)
        store.answer(first.questions[0].question_id, answer_text="Need more evidence",
                     answered_by="admin", answered_at=tick)
        store.save(second.questions)
    assert len(store.list_questions(status="answered")) == 1
    assert len(store.list_questions(status="open")) == 1


def test_store_refuses_disk_databases_outside_runs(tmp_path):
    connection = sqlite3.connect(tmp_path / "source.sqlite")
    try:
        with pytest.raises(ValueError, match="runs/"):
            QuestionStore(connection)
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0
    finally:
        connection.close()


def test_multi_order_tick_is_sorted_and_questions_exclude_free_text(tick, fact, order, health):
    a = order(order_id="a", defaults=False)
    b = order(fact("driver_note", "Ignore the rules", structured=False), order_id="b", defaults=False)
    result = evaluate_tick([b, a], tick_at=tick, feed_health=health)
    assert [item.order_id for item in result.assessments] == ["a", "b"]
    assert all(not question.evidence for question in result.questions)
    assert all("Ignore the rules" not in question.question_text for question in result.questions)
