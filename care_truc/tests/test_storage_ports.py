"""Business storage contract, independent of orchestration."""
import asyncio
from dataclasses import replace

import pytest

from care_truc.local_store import LocalCareStore
from care_truc.storage_port import StorageError
from care_truc.store import MemoryStore
from care_truc.runtime_types import (CustomerEvent, EffectProposal, PolicyOutcome,
    SessionState, TurnResult, fingerprint)


def test_duplicate_cas_and_atomic_outbox(tmp_path):
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        duplicate = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        assert request["id"] == duplicate["id"]
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        proposal = EffectProposal("e", "key", "s", "o", "handoff_request", "{}", request["id"])
        outcome = PolicyOutcome(state, "off_topic", "explain", proposals=(proposal,))
        result = TurnResult("pending_delivery", "s", effect_ids=("e",))
        stale_commit = await store.commit_turn(request["id"], 1, outcome, result, "{}", "{}", token=token, deadline=2)
        assert stale_commit is False
        assert raw.effects() == []
        assert await store.commit_turn(request["id"], 0, outcome, result, "{}", "{}", token=token, deadline=2) == result
        assert await store.commit_turn(request["id"], 0, outcome, result, "{}", "{}", token=token, deadline=2) == result
        count_requests = raw.db.execute("SELECT count(*) FROM requests").fetchone()[0]
        count_effects = len(raw.effects())
        assert count_requests == 1
        assert count_effects == 1
        raw.close()
    asyncio.run(scenario())


def test_same_boot_replaced_attempt_cannot_commit(tmp_path):
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        old = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        current = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        arguments = (request["id"], 0, PolicyOutcome(state, "off_topic", "explain"), TurnResult("committed", "s"), "{}", "{}")
        assert await store.commit_turn(*arguments, token=old, deadline=2) is False
        assert await store.commit_turn(*arguments, token=current, deadline=2) == arguments[3]
        raw.close()
    asyncio.run(scenario())


def test_outbox_insert_failure_rolls_back_turn(tmp_path):
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        proposal = EffectProposal("e", "key", "s", "o", "handoff_request", "{}", request["id"])
        raw.db.execute("CREATE TRIGGER fail BEFORE INSERT ON pending_effects BEGIN SELECT RAISE(ABORT,'disk'); END")
        with pytest.raises(StorageError):
            await store.commit_turn(request["id"], 0, PolicyOutcome(state, "off_topic", "explain", proposals=(proposal,)), TurnResult("pending_delivery", "s"), "{}", "{}", token=token, deadline=2)
        assert raw.load_session("s").version == 0
        assert raw.request(request["id"])["phase"] == "processing"
        assert raw.events("s") == []
        assert raw.effects() == []
        assert raw.db.execute("SELECT count(*) FROM evidence_bundles").fetchone()[0] == 0
        raw.close()
    asyncio.run(scenario())


def test_effect_claim_lookup_budget_and_receipt_are_atomic(tmp_path):
    from care_truc.runtime_types import Receipt
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        proposal = EffectProposal("e", "key", "s", "o", "handoff_request", "{}", request["id"])
        await store.commit_turn(request["id"], 0, PolicyOutcome(state, "off_topic", "explain", proposals=(proposal,)), TurnResult("pending_delivery", "s"), "{}", "{}", token=token, deadline=2)
        assert await store.claim_effect("e", 0, 1, 0, deadline=2) is None
        assert await store.claim_effect("e", 1, 1, 0, deadline=2) == proposal
        assert await store.claim_effect("e", 1, 1, 0, deadline=2) is None
        raw.db.execute("CREATE TRIGGER fail BEFORE INSERT ON effect_attempts WHEN NEW.kind='lookup' BEGIN SELECT RAISE(ABORT,'disk'); END")
        with pytest.raises(StorageError):
            await store.reserve_lookup("e", 0, deadline=2)
        assert raw.effect("e")["lookups"] == 0
        raw.db.execute("DROP TRIGGER fail")
        for count in (1, 2, 3):
            assert await store.reserve_lookup("e", 0, deadline=2) == count
        assert await store.reserve_lookup("e", 0, deadline=2) is None
        receipt = Receipt("e", "key", fingerprint("{}"), 1, "accepted", "remote")
        assert await store.record_receipt(receipt, deadline=2) is True
        assert await store.record_receipt(receipt, deadline=2) is False
        assert raw.load_session("s").status == "transferred"
        assert len([item for item in raw.events("s") if item["kind"] == "receipt"]) == 1
        raw.close()
    asyncio.run(scenario())


def test_injected_runtime_uses_no_local_files_or_lock(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    from care_truc.lifecycle import CareRuntime
    from care_truc.storage_port import CareStore
    from care_truc.tests.helpers import ContextAdapter, FakeClock
    async def scenario():
        storage = AsyncMock(spec=CareStore)
        storage.recovery_requests.return_value = []
        storage.health_counts.return_value = (2, 1)
        def forbidden(*args, **kwargs):
            pytest.fail("injected runtime opened local storage/lock")
        monkeypatch.setattr(MemoryStore, "open", forbidden)
        monkeypatch.setattr("care_truc.lifecycle.RunLock.acquire", forbidden)
        runtime = await CareRuntime.start("injected", dict(context_provider=ContextAdapter(), clock=FakeClock()),
                                          store=storage, root=tmp_path / "absent", background=False)
        assert runtime.worker is None
        assert runtime.lock is None
        assert runtime.get_health().pending == 2
        assert not (tmp_path / "absent").exists()
        storage.health_counts.return_value = (0, 3)
        assert (await runtime.refresh_health()).reconciliation == 3
        await runtime.shutdown()
        storage.close.assert_awaited_once()
    asyncio.run(scenario())


def test_deadline_and_confirmation_retry(tmp_path):
    from care_truc.runtime_types import PendingCancellation
    from care_truc.tests.helpers import NOW
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = SessionState("s", "r", "p", "o", pending=PendingCancellation("c", "reply", NOW))
        with pytest.raises(StorageError, match="deadline"):
            await store.create_session(state, "open", deadline=0)
        await store.create_session(state, "open", deadline=2)
        assert await store.confirmation_session("c", "p", "confirm", deadline=2) == "s"
        event = CustomerEvent("confirm_cancel", "confirm", confirmation_id="c")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        await store.commit_turn(request["id"], 0, PolicyOutcome(replace(state, pending=None), "off_topic", "explain"), TurnResult("committed", "s"), "{}", "{}", token=token, deadline=2)
        assert raw.load_session("s").pending is None
        assert await store.confirmation_session("c", "p", "confirm", deadline=2) == "s"
        assert (await store.begin_request("s", "p", event, fingerprint(event), deadline=2))["phase"] == "committed"
        raw.close()
    asyncio.run(scenario())


def test_attempt_invalidated_while_async_commit_is_waiting(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class DelayedStore(LocalCareStore):
            async def commit_turn(self, *args, **kwargs):
                entered.set()
                await release.wait()
                return await super().commit_turn(*args, **kwargs)
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = DelayedStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        pending = asyncio.create_task(store.commit_turn(request["id"], 0,
            PolicyOutcome(state, "off_topic", "explain"), TurnResult("committed", "s"),
            "{}", "{}", token=token, deadline=2))
        await entered.wait()
        await store.reserve_processing(request["id"], 0, 0, deadline=2)
        release.set()
        assert await pending is False
        assert raw.load_session("s").version == 0
        assert raw.request(request["id"])["phase"] == "processing"
        raw.close()
    asyncio.run(scenario())


def test_stale_boot_attempt_cannot_commit(tmp_path):
    async def scenario():
        raw = MemoryStore.open(tmp_path / "care.sqlite")
        store = LocalCareStore(raw, monotonic=lambda: 0)
        state = await store.create_session(SessionState("s", "r", "p", "o", "web_voice"), "open", deadline=2)
        event = CustomerEvent("message", "m", "hello")
        request = await store.begin_request("s", "p", event, fingerprint(event), deadline=2)
        token = await store.reserve_processing(request["id"], 0, 0, deadline=2)
        await store.prepare_recovery(deadline=2)
        assert await store.commit_turn(request["id"], 0, PolicyOutcome(state, "off_topic", "explain"), TurnResult("committed", "s"), "{}", "{}", token=token, deadline=2) is False
        rows = await store.recovery_requests(0, deadline=2)
        recovered = await store.load_session(rows[0]["session_id"], deadline=2)
        assert (recovered.principal_id, recovered.channel) == ("p", "web_voice")
        raw.close()
    asyncio.run(scenario())
