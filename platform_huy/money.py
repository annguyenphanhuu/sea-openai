"""Sole local financial effect gate; no financial provider or network calls."""
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from contracts.params import late_xu_for
from contracts.types import ALLOWED_SOURCES, Action
from .dto import CommandKeyRecord, ExecutionResult, PlatformError, ServerContext
from .state import canonical, utc
from .state_store import StateStore


_VN = timezone(timedelta(hours=7))


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    utc(parsed)
    return parsed.astimezone(timezone.utc)


def _result(action: Action, reason: str) -> ExecutionResult:
    return ExecutionResult(action.action_id, 'blocked', (reason,), action.kind,
                           None, None, None, None, None, False)


def _authority(action: Action, context: ServerContext) -> bool:
    return (bool(context.principal_id) and bool(context.customer_id)
            and context.source == action.source
            and action.source in ALLOWED_SOURCES.get(action.kind, frozenset())
            and (f'actions:{action.kind}' in context.capabilities
                 or (action.kind == 'cancel_request' and 'cancel:request' in context.capabilities)))


def _request_hash(action: Action, context: ServerContext) -> str:
    # Transport IDs and request timestamps may vary on a retry. All financial
    # semantics, original evidence and the authenticated ownership scope bind it.
    fields = asdict(action)
    del fields['action_id']
    del fields['requested_at']
    fields['principal_id'] = context.principal_id
    fields['customer_id'] = context.customer_id
    fields['seller_id'] = context.seller_id
    return hashlib.sha256(canonical(fields).encode('utf-8')).hexdigest()


def _decode_receipt(record: CommandKeyRecord, store: StateStore) -> ExecutionResult:
    try:
        if record.namespace != 'outbox' or not record.request_hash or not record.result_json:
            raise ValueError('No trusted successful receipt')
        payload = json.loads(record.result_json)
        payload['reason_codes'] = tuple(payload['reason_codes'])
        result = ExecutionResult(**payload)
        if not store.receipt_is_committed(record, result):
            raise ValueError('Receipt lacks a committed financial effect')
    except (ValueError, TypeError, KeyError) as error:
        raise PlatformError('idempotency_conflict') from error
    return replace(result, replayed=True)


def get_receipt(key: str, *, store: StateStore, context: ServerContext) -> ExecutionResult | None:
    """Recover original success without rechecking changed business eligibility.

    The authenticated principal/source/customer scope and current capability
    remain required. Unknown, legacy, or nonfinancial records are never success.
    """
    with store.transaction():
        record = store.lookup(key)
        if record is None:
            return None
        result = _decode_receipt(record, store)
        try:
            payload = json.loads(record.payload_json)
            payload['requested_at'] = _instant(payload['requested_at'])
            action = Action(**payload)
        except (TypeError, KeyError, ValueError) as error:
            raise PlatformError('idempotency_conflict') from error
        # Recover authority from the original semantic hash, not mutable facts.
        # This includes both customer and optional seller scope.
        if (record.principal_id != context.principal_id or not _authority(action, context)
                or record.request_hash != _request_hash(action, context)):
            raise PlatformError('permission_denied')
        return result


def _shape_valid(action: Action) -> bool:
    if not isinstance(action, Action):
        return False
    if any(not isinstance(value, str) or not value.strip() for value in (
            action.action_id, action.order_id, action.kind, action.source,
            action.idempotency_key, action.evidence_ref, action.queue)):
        return False
    if type(action.amount_vnd) is not int or action.amount_vnd < 0 or type(action.needs_approval) is not bool:
        return False
    if action.confirmation_id is not None and not isinstance(action.confirmation_id, str):
        return False
    try:
        utc(action.requested_at)
    except PlatformError:
        return False
    return True


def _eligible(action: Action, *, store: StateStore, context: ServerContext,
              now: datetime) -> tuple[str | None, str | None]:
    """Resolve persisted evidence only; never accept facts from Action payloads."""
    bundle = store.evidence(action.evidence_ref)
    if bundle is None:
        return 'evidence_missing', None
    evidence, contact, message, run = (bundle[key] for key in ('evidence', 'contact', 'message', 'run'))
    if contact is None or message is None or run is None:
        return 'invalid_request_provenance', None
    try:
        text = evidence['payload_json']
        facts = json.loads(text)
        if (not store.trusts(evidence, message)
                or hashlib.sha256(text.encode('utf-8')).hexdigest() != evidence['sha256']
                or evidence['policy_version'] != 'huy-demo-v1'
                or facts['schema_version'] != 1 or facts['run_id'] != run['run_id']
                or facts['source_identity'] != json.loads(run['source_identity_json'])
                or _instant(evidence['assessment_at']) != now or _instant(evidence['visible_at']) != now):
            return 'evidence_untrusted', None
        order = facts['order']
        if evidence['order_id'] != action.order_id or order['order_id'] != action.order_id:
            return 'evidence_untrusted', None
        if order['customer_id'] != context.customer_id:
            return 'not_found', None
        if context.seller_id is not None and order['seller_id'] != context.seller_id:
            return 'not_found', None
        contact_id = evidence['contact_id']
        if (contact['order_id'] != action.order_id or message['order_id'] != action.order_id
                or message['customer_id'] != context.customer_id
                or message['contact_id'] != contact_id or message['message_id'] != evidence['message_id']
                or contact['initiated_by'] != 'A1' or contact['channel'] != 'chat'
                or contact['status'] not in ('active', 'completed') or not contact['provider_session_id']
                or message['origin'] != 'text' or message['request_code'] != 'late_compensation'
                or not message['body'].strip() or not message['request_rule_version']
                or not (_instant(contact['requested_at']) <= _instant(contact['opened_at'])
                        <= _instant(message['created_at']) <= now)):
            return 'invalid_request_provenance', None
        if contact['closed_at'] is not None:
            closed = _instant(contact['closed_at'])
            if not (_instant(contact['opened_at']) <= _instant(message['created_at']) <= closed <= now):
                return 'invalid_request_provenance', None
        guaranteed = date.fromisoformat(order['guaranteed_date'])
        if guaranteed.isoformat() != order['guaranteed_date']:
            return 'evidence_untrusted', None
        delivered = order.get('delivered_at')
        endpoint = now if delivered is None else _instant(delivered)
        if endpoint > now:
            return 'evidence_untrusted', None
        if (endpoint.astimezone(_VN).date() - guaranteed).days < 2:
            return 'not_late_enough', None
        if facts['responsibility'] not in ('carrier', 'platform') or facts['force_majeure'] != 'absent':
            return 'eligibility_unverified', None
        history = facts['history'][action.kind]
        if history == 'already_granted' or store.has_grant(action.kind, action.order_id):
            return 'already_granted', None
        if history != 'not_granted':
            return 'history_unverified', None
        expected = late_xu_for(order['items_value_vnd']) if action.kind == 'coins' else 10000
        if action.amount_vnd != expected:
            return 'amount_mismatch', None
        return None, contact_id
    except (KeyError, ValueError, TypeError, AttributeError, PlatformError):
        return 'evidence_untrusted', None


def _cancel_eligible(action, *, store, context, now):
    bundle = store.evidence(action.evidence_ref)
    if bundle is None:
        return 'evidence_missing', None
    try:
        evidence, contact, message, run = (bundle[key] for key in ('evidence', 'contact', 'message', 'run'))
        facts = json.loads(evidence['payload_json'])
        order, confirmation = facts['order'], facts['cancellation']
        if (contact is None or message is None or run is None or not store.trusts(evidence, message)
                or hashlib.sha256(evidence['payload_json'].encode('utf-8')).hexdigest() != evidence['sha256']
                or evidence['policy_version'] != 'huy-demo-v1' or facts['schema_version'] != 1
                or facts['run_id'] != run['run_id'] or facts['source_identity'] != json.loads(run['source_identity_json'])
                or _instant(evidence['assessment_at']) != now or _instant(evidence['visible_at']) != now
                or evidence['order_id'] != action.order_id or order['order_id'] != action.order_id):
            return 'evidence_untrusted', None
        if order['customer_id'] != context.customer_id or (context.seller_id is not None and order['seller_id'] != context.seller_id):
            return 'not_found', None
        if (contact['contact_id'] != evidence['contact_id'] or message['message_id'] != evidence['message_id']
                or message['contact_id'] != contact['contact_id'] or message['customer_id'] != context.customer_id
                or contact['order_id'] != action.order_id or message['order_id'] != action.order_id
                or contact['initiated_by'] != 'A1' or contact['channel'] != 'chat' or contact['status'] != 'active'
                or not contact['provider_session_id'] or message['origin'] != 'text' or not message['body'].strip()
                or not (_instant(contact['requested_at']) <= _instant(contact['opened_at']) <= _instant(message['created_at']) <= now)
                or confirmation['confirmed'] is not True or confirmation['confirmation_id'] != action.confirmation_id
                or not confirmation['request_id'] or not confirmation['reply_to'] or now >= _instant(confirmation['expires_at'])):
            return 'invalid_request_provenance', None
        if order.get('cancelled_at') is not None or order.get('delivered_at') is not None:
            return 'cancellation_not_available', None
        return None, contact['contact_id']
    except (KeyError, ValueError, TypeError, AttributeError, PlatformError):
        return 'evidence_untrusted', None


def execute_action(action: Action, *, store: StateStore, context: ServerContext) -> ExecutionResult:
    """Atomically evaluate and grant one independently keyed local entitlement.

    Only successful grants reserve keys. Denials insert incidents only. SQLite
    errors propagate as PlatformError and roll back outbox, ledger and receipt.
    """
    if not isinstance(action, Action) or not isinstance(context, ServerContext):
        raise PlatformError('validation_error')
    with store.transaction():
        now = store.clock()

        def deny(reason: str) -> ExecutionResult:
            store.audit_denial(action, context, reason, now)
            return _result(action, reason)

        if not _shape_valid(action):
            return deny('validation_error')
        cancellation = action.kind == 'cancel_request'
        if action.kind not in ('coins', 'voucher', 'cancel_request'):
            return deny('policy_not_configured')
        # Preserve fail-closed behavior for legacy cancellation payloads that
        # never supplied the explicit confirmation/approval workflow.
        if cancellation and (action.amount_vnd != 0 or not action.needs_approval or not action.confirmation_id):
            return deny('policy_not_configured')
        if not _authority(action, context):
            return deny('permission_denied')
        expected_key = f'{"xu" if action.kind == "coins" else "voucher"}:{action.order_id}'
        if cancellation:
            run = store.evidence(action.evidence_ref)
            run_id = run['run']['run_id'] if run and run.get('run') else ''
            valid_keys = {f'{run_id}:cancel:{action.confirmation_id}', f'cancel:{action.order_id}:{action.confirmation_id}'}
        else:
            valid_keys = {expected_key}
        if action.idempotency_key not in valid_keys:
            return deny('invalid_idempotency_key')
        request_hash = _request_hash(action, context)
        record = store.lookup(action.idempotency_key)
        if record is not None:
            if record.principal_id != context.principal_id or record.request_hash != request_hash:
                return deny('idempotency_conflict')
            try:
                return _decode_receipt(record, store)
            except PlatformError:
                return deny('idempotency_conflict')
        if store.has_action(action.action_id):
            return deny('idempotency_conflict')
        if action.requested_at > now:
            return deny('validation_error')
        if action.needs_approval and not cancellation:
            return deny('approval_required')
        if not store.guard_allows(now):
            return deny('proactive_gate_closed')
        reason, contact_id = (_cancel_eligible if cancellation else _eligible)(action, store=store, context=context, now=now)
        if reason is not None:
            return deny(reason)
        effect_id = str(uuid4())
        result = ExecutionResult(action.action_id, 'succeeded', (), action.kind,
                                 action.amount_vnd if action.kind == 'coins' else None,
                                 effect_id if action.kind == 'coins' else None,
                                 action.amount_vnd if action.kind == 'voucher' else None,
                                 effect_id if action.kind == 'voucher' else None,
                                 effect_id if cancellation else None, False)
        if cancellation:
            store.queue_cancellation(action, context, request_hash, result, now)
        else:
            store.grant(action, context, request_hash, result, contact_id, now)
        return result
