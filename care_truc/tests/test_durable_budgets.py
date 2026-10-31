from dataclasses import replace
import pytest

from care_truc.store import MemoryStore
from care_truc.runtime_types import (CareError, CustomerEvent, EffectProposal,
    PolicyOutcome, SessionState, TurnResult, canonical, fingerprint)
from .test_memory import setup_turn


def effect_turn(path):
    store, request, outcome = setup_turn(path)
    proposal = EffectProposal("e", "run:coins:o1", "s", "o1", "action_request", canonical({"kind":"coins","order_id":"o1"}), request["id"])
    outcome = replace(outcome, proposals=(proposal,))
    store.commit_turn(request["id"], 0, outcome, TurnResult("pending_delivery", "s"), "{}", "{}")
    return store, proposal, request


def test_model_reservation_survives_restart(tmp_path):
    path = tmp_path / "care.sqlite"
    store, request, _ = setup_turn(path)
    assert store.reserve_model(request["id"]) is not None
    store.close()
    store = MemoryStore.open(path)
    assert store.reserve_model(request["id"]) is None
    store.close()


def test_processing_budget_survives_restart(tmp_path):
    path = tmp_path / "care.sqlite"
    store, request, _ = setup_turn(path)
    for attempt, now in enumerate((0, 1, 6), 1):
        assert store.reserve_processing(request["id"], 1, now) is not None
        store.retry_request(request["id"], now)
        store.close()
        store = MemoryStore.open(path)
    assert store.request(request["id"])["phase"] == "failed_terminal"
    assert store.reserve_processing(request["id"], 2, 20) is None
    assert store.load_session("s").turn_count == 0
    store.close()


def test_coins_key_unique_across_sessions(tmp_path):
    store, proposal, request = effect_turn(tmp_path / "care.sqlite")
    state = SessionState("s2", "run", "customer", "o1")
    store.create_session(state, "open2")
    event = CustomerEvent("message", "new", "xu")
    req2 = store.begin_request("s2", "customer", event, fingerprint(event))
    outcome = PolicyOutcome(replace(state, turn_count=1), "want_more", "pending",
                            proposals=(replace(proposal, effect_id="e2", session_id="s2"),))
    store.commit_turn(req2["id"], 0, outcome, TurnResult("pending_delivery", "s2"), "{}", "{}")
    assert len(store.effects()) == 1
    assert store.effect("e")["revision"] == 1
    store.close()


def test_unsent_revision_append_only(tmp_path):
    store, proposal, request = effect_turn(tmp_path / "care.sqlite")
    store.set_effect("e", state="blocked")
    event = CustomerEvent("message", "new", "xin xu")
    req2 = store.begin_request("s", "customer", event, fingerprint(event))
    assert store.revise_proposal(proposal.key, req2["id"], replace(proposal, payload=canonical({'kind':'coins','order_id':'o1','new':1}))) == 2
    assert store.db.execute("SELECT count(*) FROM effect_proposals").fetchone()[0] == 2
    assert store.claim_effect("e", 1, 1, 0) is None
    store.close()


def test_first_claim_freezes_payload(tmp_path):
    store, proposal, request = effect_turn(tmp_path / "care.sqlite")
    assert store.claim_effect("e", 1, 1, 0) is not None
    with pytest.raises(CareError, match="frozen"):
        store.revise_proposal(proposal.key, request["id"], replace(proposal, payload=canonical({'kind':'coins','order_id':'o1','new':1})))
    assert store.effect("e")["attempts"] == 1
    assert not store.db.in_transaction
    store.close()


def test_stale_version_or_revision_cannot_claim(tmp_path):
    store, proposal, request = effect_turn(tmp_path / "care.sqlite")
    assert store.claim_effect("e", 0, 1, 0) is None
    assert store.claim_effect("e", 1, 2, 0) is None
    assert store.effect("e")["attempts"] == 0
    store.close()
