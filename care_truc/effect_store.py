"""Effect SQL helpers, called exclusively by MemoryStore transactions."""

from dataclasses import replace
import json
from uuid import uuid4

from .runtime_types import CareError, EffectProposal, canonical, fingerprint


def save_proposal(store, proposal, request_id, state) -> None:
    if proposal.order_id != state.order_id or proposal.session_id != state.session_id:
        raise CareError("invalid_delivery_order")
    payload = json.loads(proposal.payload)
    if proposal.kind == "action_request" and payload.get("order_id") != state.order_id:
        raise CareError("invalid_delivery_order")
    if proposal.kind == "action_request" and payload.get("kind") == "cancel_request":
        from .cancellation import validate_action
        if proposal.key != payload.get("idempotency_key"):
            raise CareError("cancel_confirmation_invalid")
        validate_action(store, payload, request_id, state)
    existing = store.db.execute("SELECT * FROM pending_effects WHERE run_id=? AND effect_key=?",
                                (state.run_id, proposal.key)).fetchone()
    if existing:
        original = EffectProposal(**json.loads(existing["proposal"]))
        owner = store.load_session(existing["session_id"])
        if (original.order_id != state.order_id or owner.principal_id != state.principal_id
                or original.kind != proposal.kind):
            raise CareError("effect_binding_conflict")
        if existing["state"] == "blocked" and existing["attempts"] == 0:
            if proposal.kind == "handoff_request":
                # A new explicit human request retries the same unsent handoff envelope.
                store.set_effect(existing["id"], state="pending_delivery", next_at=0)
        return
    if proposal.kind == "action_request" and payload.get("kind") == "coins":
        reserved = store.db.execute(
            "SELECT 1 FROM pending_effects WHERE run_id=? "
            "AND json_extract(proposal,'$.order_id')=? "
            "AND json_extract(proposal,'$.kind')='action_request' "
            "AND json_extract(json_extract(proposal,'$.payload'),'$.kind')='coins'",
            (state.run_id, state.order_id)).fetchone()
        if reserved:
            raise CareError("coins_already_reserved")
    if proposal.kind == "handoff_request":
        reserved = store.db.execute(
            "SELECT 1 FROM pending_effects WHERE session_id=? "
            "AND json_extract(proposal,'$.kind')='handoff_request'",
            (state.session_id,)).fetchone()
        if reserved:
            raise CareError("handoff_already_reserved")
    store.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,session_version) VALUES(?,?,?,?,?,?)",
        (proposal.effect_id, state.run_id, proposal.key, state.session_id, canonical(proposal), state.version))
    store.db.execute("INSERT INTO effect_proposals VALUES(?,1,?,?)",
                      (proposal.effect_id, request_id, canonical(proposal)))


def revise_proposal(store, key, source_request, proposal) -> int:
    request = store.request(source_request)
    row = store.db.execute("SELECT * FROM pending_effects WHERE run_id=? AND effect_key=?",
                            (request["run_id"], key)).fetchone()
    if row["attempts"]:
        raise CareError("effect_payload_frozen")
    original = EffectProposal(**json.loads(row["proposal"]))
    old_payload = json.loads(original.payload)
    new_payload = json.loads(proposal.payload)
    if ((original.kind == "action_request" and old_payload.get("kind") in ("coins", "cancel_request"))
            or (proposal.kind == "action_request" and new_payload.get("kind") in ("coins", "cancel_request"))):
        # A coin reservation is immutable even before its first network attempt.
        raise CareError("coins_revision_not_allowed" if old_payload.get("kind") == "coins" or new_payload.get("kind") == "coins" else "cancel_revision_not_allowed")
    event = json.loads(request["payload"])
    if row["state"] != "blocked" or event["kind"] != "message":
        raise CareError("revision_not_allowed")
    version = store.load_session(proposal.session_id).version
    revision = row["revision"] + 1
    proposal = replace(proposal, effect_id=row["id"])
    store.db.execute("INSERT INTO effect_proposals VALUES(?,?,?,?)",
                      (row["id"], revision, source_request, canonical(proposal)))
    store.db.execute("UPDATE pending_effects SET proposal=?,session_id=?,revision=?,session_version=?,state='pending_delivery' WHERE id=?",
                      (canonical(proposal), proposal.session_id, revision, version, row["id"]))
    return revision


def claim_effect(store, effect_id, expected_version, revision, now):
    row = store.effect(effect_id)
    state = store.load_session(row["session_id"])
    if (row["revision"] != revision or state.version != expected_version
            or row["state"] not in ("pending_delivery", "retry_wait")
            or row["attempts"] >= 3 or row["next_at"] > now):
        return None
    from .cancellation import lacks_cancellation_evidence
    if lacks_cancellation_evidence(store, row):
        store.set_effect(effect_id, state="needs_reconciliation" if row["attempts"] else "blocked")
        return None
    store.db.execute("UPDATE pending_effects SET state='in_flight',attempts=attempts+1,session_version=? WHERE id=?",
                      (state.version, effect_id))
    store.db.execute("INSERT INTO effect_attempts(id,effect_id,revision,kind,started_at,deadline) VALUES(?,?,?,'submit',?,?)",
                      (uuid4().hex, effect_id, revision, now, now + 2))
    return EffectProposal(**json.loads(row["proposal"]))


def record_receipt(store, receipt) -> bool:
    row = store.effect(receipt.effect_id)
    if row is None or not row["attempts"]:
        raise CareError("receipt_binding_invalid")
    proposal = EffectProposal(**json.loads(row["proposal"]))
    if (not receipt.authoritative or receipt.key != proposal.key
            or receipt.payload_hash != fingerprint(proposal.payload)):
        raise CareError("receipt_binding_invalid")
    previous = store.db.execute("SELECT revision,data FROM receipts WHERE effect_id=? ORDER BY revision DESC LIMIT 1",
                                (receipt.effect_id,)).fetchone()
    if previous:
        if receipt.revision < previous[0]:
            return False
        if receipt.revision == previous[0]:
            if canonical(receipt) != previous[1]:
                raise CareError("receipt_revision_conflict")
            return False
        previous_outcome = json.loads(previous[1])["outcome"]
        rank = {"unknown": 0, "accepted": 1, "awaiting_approval": 2, "succeeded": 3, "rejected": 3}
        if (previous_outcome in ("succeeded", "rejected") and receipt.outcome != previous_outcome
                or rank.get(receipt.outcome, -1) < rank[previous_outcome]):
            raise CareError("receipt_terminal_conflict")
    if (type(receipt.revision) is not int or receipt.revision < 1
            or receipt.outcome not in ("unknown", "accepted", "awaiting_approval", "succeeded", "rejected")
            or not receipt.remote_ref):
        raise CareError("receipt_schema_invalid")
    store.db.execute("INSERT INTO receipts VALUES(?,?,?)",
                      (receipt.effect_id, receipt.revision, canonical(receipt)))
    store.set_effect(receipt.effect_id, state="delivered", outcome=receipt.outcome, lookups=0, manual=0)
    if proposal.kind == "handoff_request" and receipt.outcome in ("accepted", "awaiting_approval", "succeeded"):
        state = store.load_session(proposal.session_id)
        state = replace(state, status="transferred", version=state.version + 1)
        store.db.execute("UPDATE sessions SET data=?,version=? WHERE id=?",
                         (canonical(state), state.version, state.session_id))
    store._event(proposal.session_id, f"receipt:{receipt.effect_id}:{receipt.revision}",
                 "receipt", canonical({"effect_id": receipt.effect_id, "outcome": receipt.outcome}))
    return True
