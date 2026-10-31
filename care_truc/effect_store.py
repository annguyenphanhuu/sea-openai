"""Effect SQL helpers, called exclusively by MemoryStore transactions."""

from dataclasses import replace
import json
from uuid import uuid4

from .runtime_types import CareError, EffectProposal, canonical, fingerprint


def save_proposal(store, proposal, request_id, state) -> None:
    existing = store.db.execute("SELECT * FROM pending_effects WHERE run_id=? AND effect_key=?",
                                (state.run_id, proposal.key)).fetchone()
    if existing:
        if existing["state"] == "blocked" and existing["attempts"] == 0:
            revise_proposal(store, proposal.key, request_id, proposal)
        return
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
    store.db.execute("UPDATE pending_effects SET state='in_flight',attempts=attempts+1,session_version=? WHERE id=?",
                      (state.version, effect_id))
    store.db.execute("INSERT INTO effect_attempts(id,effect_id,revision,kind,started_at,deadline) VALUES(?,?,?,'submit',?,?)",
                      (uuid4().hex, effect_id, revision, now, now + 2))
    return EffectProposal(**json.loads(row["proposal"]))


def record_receipt(store, receipt) -> bool:
    row = store.effect(receipt.effect_id)
    proposal = EffectProposal(**json.loads(row["proposal"]))
    if (not receipt.authoritative or receipt.key != proposal.key
            or receipt.payload_hash != fingerprint(proposal.payload)):
        raise CareError("receipt_binding_invalid")
    if store.db.execute("SELECT 1 FROM receipts WHERE effect_id=? AND revision=?",
                        (receipt.effect_id, receipt.revision)).fetchone():
        return False
    store.db.execute("INSERT INTO receipts VALUES(?,?,?)",
                      (receipt.effect_id, receipt.revision, canonical(receipt)))
    store.set_effect(receipt.effect_id, state="delivered", outcome=receipt.outcome, lookups=0)
    store._event(proposal.session_id, f"receipt:{receipt.effect_id}:{receipt.revision}",
                 "receipt", canonical({"effect_id": receipt.effect_id, "outcome": receipt.outcome}))
    return True
