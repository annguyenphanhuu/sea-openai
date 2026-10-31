"""Durable chat orchestration; host adapters run outside store transactions.

Task-specific action and handoff builders extend the mutation before commit.
Preparing a contact only queues delivery; it never invokes a gateway.
"""
from dataclasses import asdict, replace
import hashlib
import json
from uuid import uuid4

from contracts.types import ContactTask
from care_truc.context import check_proactive, validate_assessment
from care_truc.models import (
    AssessmentRef, CareContext, DomainError, MessageCommand, Mutation,
    PendingDelivery, Session, StoredEvidence, StoredMessage, TrustedContext,
    TurnResponse, normalize_utc, validate_context_time,
)
from care_truc.ports import ActionGateway, ContactGateway, ContextReader, HandoffSink, PhraseSelector
from care_truc.rendering import render, select_phrases
from care_truc.rules import classify
from care_truc.store import SqliteSessionStore, payload_hash


def _json(value: object) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


class CareService:
    def __init__(self, store: SqliteSessionStore, reader: ContextReader,
                 contact_gateway: ContactGateway | None = None,
                 action_gateway: ActionGateway | None = None,
                 handoff_sink: HandoffSink | None = None,
                 phrase_selector: PhraseSelector | None = None) -> None:
        self.store = store
        self.reader = reader
        self.contact_gateway = contact_gateway
        self.action_gateway = action_gateway
        self.handoff_sink = handoff_sink
        self.phrase_selector = phrase_selector

    def open_chat(self, trusted: TrustedContext, order_id: str, request_id: str) -> Session:
        validate_context_time(trusted)
        if not isinstance(order_id, str) or not order_id.strip():
            raise DomainError('invalid_order_id')
        if not isinstance(request_id, str) or not request_id.strip():
            raise DomainError('invalid_request_id')
        key = _json(('open_chat', trusted.principal.customer_id, request_id))
        fingerprint = _fingerprint(('open_chat', trusted.run_id, order_id, 'chat'))
        cached = self.store.replay_creation(trusted.principal.customer_id, key, fingerprint)
        if cached is not None:
            return cached
        ctx = self.reader.read(trusted, order_id)
        self._check_order(ctx, order_id)
        session = Session(str(uuid4()), trusted.principal.customer_id, trusted.run_id,
                          order_id, 'chat', 'customer', None, None, 'active', 0, 0, 0, None)
        return self.store.create_once(session, key, fingerprint)

    def prepare_contact(self, trusted: TrustedContext, contact: ContactTask) -> Session:
        validate_context_time(trusted)
        if trusted.source != 'system' or not trusted.principal.is_staff:
            raise DomainError('system_context_required', 403)
        if not isinstance(contact, ContactTask):
            raise DomainError('invalid_contact')
        if not isinstance(contact.idempotency_key, str) or not contact.idempotency_key.strip():
            raise DomainError('invalid_contact_key')
        if contact.proactive is not True:
            raise DomainError('invalid_proactive_contact')
        contact = replace(contact, assessment_at=normalize_utc(contact.assessment_at),
                          created_at=normalize_utc(contact.created_at))
        key = _json(('prepare_contact', contact.idempotency_key))
        fingerprint = _fingerprint((trusted.run_id, asdict(contact)))
        cached = self.store.replay_creation(trusted.principal.customer_id, key, fingerprint)
        if cached is not None:
            return cached
        ref = AssessmentRef(contact.order_id, contact.assessment_at)
        ctx = self.reader.read(trusted, contact.order_id, ref)
        validate_assessment(ctx, trusted, contact.order_id, ref)
        if contact.created_at > trusted.cutoff:
            raise DomainError('contact_future', 409)
        if ctx.contact is not None and ctx.contact != contact:
            raise DomainError('contact_context_mismatch', 409)
        gate = check_proactive(ctx.guard, trusted.cutoff)
        if not gate.allowed:
            raise DomainError(gate.codes[0], 409)
        if any(code.startswith(('feed_', 'untrusted_fact:', 'conflicting_fact:'))
               for code in ctx.assessment.reason_codes):
            raise DomainError('facts_untrusted', 409)
        session = Session(str(uuid4()), trusted.principal.customer_id, trusted.run_id,
                          contact.order_id, contact.channel, 'a1', contact,
                          'pending_delivery', 'active', 0, 0, 0, None)
        delivery = PendingDelivery(str(uuid4()), session.id, 'contact', key,
                                   contact, 'pending_delivery', None)
        return self.store.create_once(session, key, fingerprint, delivery)

    @staticmethod
    def _check_order(ctx: CareContext, order_id: str) -> None:
        if ctx.assessment is not None and ctx.assessment.order_id != order_id:
            raise DomainError('assessment_order_mismatch', 409)
        if ctx.contact is not None and ctx.contact.order_id != order_id:
            raise DomainError('contact_order_mismatch', 409)

    def message(self, trusted: TrustedContext, session_id: str,
                command: MessageCommand) -> TurnResponse:
        validate_context_time(trusted)
        snapshot = self.store.get_session(trusted.principal.customer_id, session_id)
        if snapshot.run_id != trusted.run_id:
            raise DomainError('session_not_found', 404)
        if command.channel != snapshot.channel:
            raise DomainError('channel_mismatch', 409)
        fingerprint = payload_hash('message', command.text, command.reply_to)
        cached = self.store.replay_turn(snapshot.principal_id, session_id,
                                        command.request_id, fingerprint)
        if cached is not None:
            return cached
        if snapshot.state in ('handoff_pending', 'transferred', 'completed'):
            raise DomainError('session_state_conflict', 409)
        signals = classify(command.text)
        ctx = self.reader.read(trusted, snapshot.order_id)
        self._check_order(ctx, snapshot.order_id)
        turn_count = snapshot.turn_count + 1
        abusive_count = snapshot.abusive_turn_count + int(signals.abusive)
        reason = ('human_requested' if signals.intent == 'ask_human' else
                  'abuse_limit' if abusive_count >= 3 else
                  'turn_limit' if turn_count >= 8 else None)
        template_id = ('ask_human' if reason == 'human_requested' else 'handoff') if reason else signals.intent
        selection = select_phrases(self.phrase_selector, template_id)
        reply = render(template_id, ctx, signals, selection, cutoff=trusted.cutoff)
        message_id = str(uuid4())
        assessment_ref = (AssessmentRef(ctx.assessment.order_id, ctx.assessment.assessed_at)
                          if ctx.assessment is not None else None)
        # Scope source references per accepted turn so every response has durable
        # trace material even when two sessions/turns use the same source snapshot.
        evidence = tuple(StoredEvidence(
            'evidence:' + _fingerprint((session_id, message_id, index, source_ref)),
            ' '.join(reply.public_evidence),
            _json({'source_ref': source_ref, 'assessment_ref': asdict(assessment_ref),
                   'source': ctx.assessment.evidence[index]}))
            for index, source_ref in enumerate(reply.evidence_refs))
        codes = reply.decision_codes + ((reason,) if reason else ())
        response = TurnResponse(message_id, reply.text, signals.intent, assessment_ref,
                                tuple(item.id for item in evidence), codes, (),
                                reply.response_source, None)
        after = replace(snapshot, state='handoff_pending' if reason else snapshot.state,
                        version=snapshot.version + 1, turn_count=turn_count,
                        abusive_turn_count=abusive_count)
        messages = (StoredMessage(str(uuid4()), 'customer', command.text, trusted.cutoff),
                    StoredMessage(message_id, 'assistant', reply.text, trusted.cutoff))
        mutation = Mutation(after, response, messages=messages, evidence=evidence)
        return self.store.mutate(snapshot.principal_id, session_id, command.request_id,
                                 fingerprint, lambda current: mutation,
                                 expected_version=snapshot.version)
