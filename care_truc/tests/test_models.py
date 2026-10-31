from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone

import pytest

from contracts.types import Action
from care_truc.models import (
    AssessmentRef, CareContext, DomainError, FeedSnapshot, GuardSnapshot,
    MessageCommand, Principal, Receipt, Session, TrustedContext, normalize_utc,
    validate_context_time,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def test_boundary_types():
    with pytest.raises(DomainError) as error:
        normalize_utc(datetime(2026, 10, 31))
    assert error.value.http_status == 400
    local = NOW.astimezone(timezone(timedelta(hours=7)))
    assert normalize_utc(local) == NOW
    assert normalize_utc(local).tzinfo is UTC
    context = TrustedContext(Principal('customer-1', False), 'run-1', local)
    assert context.cutoff == NOW
    assert context.cutoff.tzinfo is UTC
    validate_context_time(context)
    with pytest.raises(FrozenInstanceError):
        context.run_id = 'other'


@pytest.mark.parametrize('value', [True, False, -1, 1.5, '100', [], {}])
def test_items_value_rejects_invalid_money(value):
    with pytest.raises(DomainError) as error:
        CareContext(None, None, value, None, 'none')
    assert error.value.http_status == 400


@pytest.mark.parametrize('value', [None, 0, 100])
def test_items_value_allows_missing_or_nonnegative_integer(value):
    assert CareContext(None, None, value, None, 'none').items_value_vnd == value


@pytest.mark.parametrize('run_id', ['../other', '..', '.', '/tmp', 'a/b', r'a\b', '', 'C:foo', 'a b', 'a\x00b'])
def test_run_id_is_one_safe_segment(run_id):
    with pytest.raises(DomainError):
        TrustedContext(Principal('c', False), run_id, NOW)


@pytest.mark.parametrize('principal', [None, 'customer', Principal('c', False)])
def test_trusted_context_requires_principal_and_aware_cutoff(principal):
    with pytest.raises(DomainError):
        TrustedContext(principal, 'run-1', datetime(2026, 10, 31))


@pytest.mark.parametrize('customer_id,is_staff', [('', False), (None, False), ('c', 1)])
def test_principal_rejects_invalid_identity(customer_id, is_staff):
    with pytest.raises(DomainError):
        Principal(customer_id, is_staff)


def test_trusted_provenance_is_explicit_and_server_only():
    customer = TrustedContext(Principal('c', False), 'run-1', NOW)
    assert customer.source == 'customer'
    system = TrustedContext(Principal('platform', True), 'run-1', NOW, source='system')
    assert system.source == 'system'
    with pytest.raises(DomainError):
        TrustedContext(Principal('c', False), 'run-1', NOW, source='system')


def test_time_values_are_normalized_and_invalid_literals_rejected():
    local = NOW.astimezone(timezone(timedelta(hours=7)))
    assert AssessmentRef('o', local).assessed_at.tzinfo is UTC
    assert FeedSnapshot('ops', 'fresh', local).source_timestamp.tzinfo is UTC
    assert GuardSnapshot('a3', local, ('ops',), (), ()).heartbeat_at.tzinfo is UTC
    with pytest.raises(DomainError):
        MessageCommand('r', 'hello', 'telephone', None)
    with pytest.raises(DomainError):
        Receipt('key', None, 'sent', 1, None)
    with pytest.raises(DomainError):
        Receipt('key', None, 'pending', True, None)
    with pytest.raises(DomainError):
        CareContext(None, None, None, None, 'maybe')


def test_session_accepts_only_declared_states():
    base = dict(id='s', principal_id='c', run_id='run', order_id='o', channel='chat',
                origin='customer', contact=None, contact_delivery_status=None,
                version=0, turn_count=0, abusive_turn_count=0, pending_cancel_id=None)
    for state in ('active', 'awaiting_cancel_confirmation', 'handoff_pending', 'transferred', 'completed'):
        assert Session(**base, state=state).state == state
    with pytest.raises(DomainError):
        Session(**base, state='unknown')


def test_action_serialization_preserves_shared_contract_fields():
    action = Action('a', 'o', 'coins', 1000, 'a1', NOW, 'key', 'evidence', False, 'care')
    assert asdict(action) == dict(action_id='a', order_id='o', kind='coins', amount_vnd=1000,
        source='a1', requested_at=NOW, idempotency_key='key', evidence_ref='evidence',
        needs_approval=False, queue='care', confirmation_id=None)


def test_neighbor_values_are_immutable_and_validate_boundary_types():
    from care_truc.models import ApiResponse, History, Mutation, RenderedReply, TurnResponse
    with pytest.raises(DomainError):
        ApiResponse(True, {})
    with pytest.raises(DomainError):
        History(None)
    with pytest.raises(DomainError):
        Mutation(None, None)
    with pytest.raises(DomainError):
        TurnResponse('m', 'hello', 'accept', 'not-a-ref', (), (), (), 'template', None)
    with pytest.raises(DomainError):
        RenderedReply('hello', 'llm')


def test_nested_contact_timestamps_normalize_in_session_and_delivery():
    from contracts.types import ContactTask
    from care_truc.models import PendingDelivery
    local = NOW.astimezone(timezone(timedelta(hours=7)))
    contact = ContactTask('c', 'o', local, local, 'chat', True, 'late', 'key')
    session = Session('s', 'customer', 'run', 'o', 'chat', 'a1', contact, None,
                      'active', 0, 0, 0, None)
    assert session.contact.created_at.tzinfo is UTC
    delivery = PendingDelivery('d', 's', 'contact', 'key', contact, 'pending', local)
    assert delivery.payload.created_at.tzinfo is UTC
    assert delivery.lease_until.tzinfo is UTC


@pytest.mark.parametrize('name', ['CON', 'nul', 'COM1', 'LPT9'])
def test_run_id_rejects_windows_devices(name):
    with pytest.raises(DomainError):
        TrustedContext(Principal('c', False), name, NOW)


def test_remaining_model_boundary_validation():
    from care_truc.models import Eligibility, GateDecision, HandoffSummary, IntentSignals, PendingCancel, PendingDelivery
    assert GateDecision(True, ('ok',)).allowed
    assert Eligibility(False, ('ineligible',), None).amount_vnd is None
    assert IntentSignals('accept', False, False, False).intent == 'accept'
    with pytest.raises(DomainError):
        GateDecision(1, ())
    with pytest.raises(DomainError):
        Eligibility(True, (), True)
    with pytest.raises(DomainError):
        IntentSignals('accept', 1, False, False)
    with pytest.raises(DomainError):
        PendingCancel('c', 'p', 's', 'o', None, 0, 'm', datetime(2026, 1, 1), 'pending')
    summary = HandoffSummary('h', 's', 'human', 'help', (), (), (), None, ())
    delivery = PendingDelivery('d', 's', 'handoff', 'key', summary, 'pending', None)
    assert delivery.payload == summary
    with pytest.raises(DomainError):
        PendingDelivery('d', 's', 'action', 'key', summary, 'pending', None)
    with pytest.raises(DomainError):
        GuardSnapshot('a3', NOW, ('ops',), ['wrong'], ())
