"""Async local question repository contract."""
import asyncio
import pytest
from logistics_an_nguyen import QuestionStore, evaluate_tick
from logistics_an_nguyen.question_port import LocalQuestionRepository, QuestionConflict


def test_answer_contract(state, tick, order, health):
    async def scenario():
        repository = LocalQuestionRepository(QuestionStore(state), monotonic=lambda: 0)
        questions = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health).questions
        await repository.save(questions, deadline=2)
        await repository.save(questions, deadline=2)
        assert len(await repository.list_questions(deadline=2)) == 1
        arguments = dict(answer_text="Checked", answered_by="staff", answered_at=tick, deadline=2)
        await repository.answer(questions[0].question_id, **arguments)
        await repository.answer(questions[0].question_id, **arguments)
        with pytest.raises(QuestionConflict) as answer_conflict:
            await repository.answer(questions[0].question_id, **{**arguments, "answer_text": "Changed"})
        assert answer_conflict.value.code == "conflict"
    asyncio.run(scenario())


def test_save_rolls_back_batch_in_autocommit_mode(state, tick, order, health):
    from logistics_an_nguyen.question_port import QuestionStorageError
    async def scenario():
        state.isolation_level = None
        repository = LocalQuestionRepository(QuestionStore(state), monotonic=lambda: 0)
        questions = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health).questions
        question = questions[0]
        from dataclasses import replace
        other = replace(question, question_id=question.question_id + "-other")
        state.execute("CREATE TRIGGER fail BEFORE INSERT ON supervisor_questions WHEN NEW.question_id LIKE '%-other' BEGIN SELECT RAISE(ABORT,'disk'); END")
        with pytest.raises(QuestionStorageError):
            await repository.save((question, other), deadline=2)
        assert await repository.list_questions(deadline=2) == []
        assert not state.in_transaction
    asyncio.run(scenario())


def test_repository_does_not_commit_callers_transaction(state, tick, order, health):
    from logistics_an_nguyen.question_port import QuestionStorageError
    async def scenario():
        raw = QuestionStore(state)
        questions = evaluate_tick([order(defaults=False)], tick_at=tick, feed_health=health).questions
        raw.save(questions)
        repository = LocalQuestionRepository(raw, monotonic=lambda: 0)
        with pytest.raises(QuestionStorageError, match="transaction_boundary"):
            await repository.save(questions, deadline=2)
        assert state.in_transaction
        state.rollback()
        assert await repository.list_questions(deadline=2) == []
        with pytest.raises(QuestionStorageError, match="deadline"):
            await repository.save(questions, deadline=0)
    asyncio.run(scenario())
