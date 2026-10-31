"""Bounded per-session turn orchestration with durable request ownership."""

import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
import json
from uuid import uuid4

from .storage_port import CareStore, StorageError
from .local_store import LocalCareStore
from .store import MemoryStore
from .guardrails import Guardrails
from .models import normalize_utc, DomainError
from .hooks import RuntimeHooks, bounded
from .phrases import allowed_ids, build_model_context, select_phrase
from .policy import CarePolicy
from .renderer import ResponseRenderer
from .runtime_types import (CareError, ContextSnapshot, CustomerEvent, EffectProposal,
    HookDecision, PhraseSelection, PolicyOutcome, SessionState, TrustedRequestContext, TurnResult,
    canonical, fingerprint)


def tracked(method):
    @wraps(method)
    async def call(self, *args, **kwargs):
        owner = getattr(self, "harness", self)
        if not owner.accepting:
            raise CareError("not_ready", 503)
        task = asyncio.current_task()
        owner.active_tasks[task] = owner.active_tasks.get(task, 0) + 1
        try:
            return await method(self, *args, **kwargs)
        finally:
            remaining = owner.active_tasks[task] - 1
            if remaining:
                owner.active_tasks[task] = remaining
            else:
                del owner.active_tasks[task]
    return call


class CareHarness:
    def __init__(self, run_id, store, context_provider, clock, *, selector=None, hooks=None):
        self.run_id = run_id
        self.store = store
        self.storage: CareStore = LocalCareStore(store, monotonic=clock.monotonic) if isinstance(store, MemoryStore) else store
        self.context_provider = context_provider
        self.clock = clock
        self.selector = selector
        self.hooks = hooks or RuntimeHooks({}, clock)
        self.policy = CarePolicy()
        self.renderer = ResponseRenderer()
        self.guards = Guardrails()
        self.locks = {}
        self.owners = {}
        self.active_tasks = {}
        self.observer_codes = set()
        self.accepting = True
        self.dispatcher = None

    async def session(self, session_id):
        state = await self.storage.load_session(session_id, deadline=self.clock.monotonic() + 2)
        if state.run_id != self.run_id:
            raise CareError("not_found", 404)
        return state

    def lock(self, session_id):
        return self.locks.setdefault(session_id, asyncio.Lock())

    async def record_observation(self, session_id, phase, result, reference):
        self.observer_codes.update(result.codes)
        try:
            (await self.storage.record_hook_event(session_id, phase, result, reference, deadline=self.clock.monotonic() + 2))
        except StorageError:
            self.observer_codes.add("hook_audit_unavailable")

    async def authorize(self, ctx, order_id, principal_id=None):
        if not isinstance(ctx, TrustedRequestContext) or not ctx.principal_id:
            raise CareError("unauthenticated", 401)
        if principal_id is not None and ctx.principal_id != principal_id:
            if not ctx.staff_permissions:
                raise CareError("forbidden", 403)
        try:
            await bounded(self.context_provider.authorize(ctx, order_id), self.clock, 2)
        except TimeoutError:
            raise CareError("auth_unavailable", 503) from None

    async def snapshot(self, state, ctx, *, handoff=False):
        try:
            snapshot = copy.deepcopy(await bounded(self.context_provider.load(ctx, state.order_id), self.clock, 2))
            if snapshot.order_id != state.order_id or snapshot.principal_id != state.principal_id:
                raise CareError("context_binding_invalid", 503)
            assessment = snapshot.assessment
            if assessment is not None and assessment.order_id != state.order_id:
                raise CareError("context_binding_invalid", 503)
            try:
                snapshot = replace(snapshot, cutoff=normalize_utc(snapshot.cutoff))
            except DomainError:
                raise CareError("context_cutoff_invalid", 503) from None
            if state.last_cutoff is not None and snapshot.cutoff < state.last_cutoff:
                raise CareError("context_cutoff_regressed", 409)
            if assessment is not None:
                try:
                    assessed = normalize_utc(assessment.assessed_at)
                    evidence = tuple(dict(item, ingested_at=normalize_utc(item['ingested_at']))
                                     for item in assessment.evidence)
                    eta = normalize_utc(assessment.revised_eta) if assessment.revised_eta else None
                except (DomainError, KeyError, TypeError):
                    raise CareError("assessment_invalid", 409) from None
                if assessed > snapshot.cutoff:
                    raise CareError("assessment_invalid", 409)
                if any(item['ingested_at'] > snapshot.cutoff for item in evidence):
                    raise CareError("evidence_future", 409)
                snapshot = replace(snapshot, assessment=replace(assessment,
                    assessed_at=assessed, evidence=evidence, revised_eta=eta))
            if state.opened_by == "a1":
                sent_here = any(row["session_id"] == state.session_id and row["outcome"] == "succeeded"
                    and json.loads(row["proposal"])["kind"] == "contact_send"
                    for row in (await self.storage.effects(deadline=self.clock.monotonic() + 2)))
                snapshot = replace(snapshot, contact_sent=snapshot.contact_sent and sent_here)
            return snapshot
        except CareError as error:
            if not handoff or error.code not in (
                    "context_cutoff_invalid", "context_cutoff_regressed",
                    "assessment_invalid", "evidence_future"):
                raise
            # Discard the entire rejected business snapshot, including its time.
            # Only the authenticated session identity survives for escalation.
            return ContextSnapshot(state.principal_id, state.order_id,
                datetime.min.replace(tzinfo=timezone.utc), None, None,
                validation_codes=(error.code,))
        except (TimeoutError, OSError):
            # A sentinel marks absent business time; operational UTC cannot grant business rights.
            return ContextSnapshot(state.principal_id, state.order_id,
                                   datetime.min.replace(tzinfo=timezone.utc), None, None)

    @tracked
    async def open_chat(self, order_id, request_id, ctx):
        CustomerEvent("request_handoff", request_id)
        if not self.accepting:
            raise CareError("not_ready", 503)
        await self.authorize(ctx, order_id)
        key = fingerprint((self.run_id, "customer", ctx.principal_id, request_id))
        state = (await self.storage.create_session(SessionState(uuid4().hex, self.run_id, ctx.principal_id, order_id), key, deadline=self.clock.monotonic() + 2))
        return TurnResult("opened", state.session_id)

    @tracked
    async def open_contact(self, task, ctx):
        if not self.accepting:
            raise CareError("not_ready", 503)
        if not isinstance(ctx, TrustedRequestContext) or "care_contact" not in ctx.staff_permissions:
            raise CareError("system_context_required", 403)
        await self.authorize(ctx, task.order_id)
        try:
            task = replace(task, assessment_at=normalize_utc(task.assessment_at),
                           created_at=normalize_utc(task.created_at))
        except DomainError:
            raise CareError("invalid_contact", 400) from None
        if task.channel not in ("chat", "web_voice") or not task.proactive:
            raise CareError("invalid_contact", 400)
        key = fingerprint((self.run_id, "contact", task.idempotency_key))
        proposed = SessionState(uuid4().hex, self.run_id, ctx.principal_id,
            task.order_id, task.channel, "a1", task.contact_id, open_fingerprint=fingerprint(task))
        event = CustomerEvent("open_contact", "contact:" + task.contact_id, canonical(task))
        row = await self.storage.has_open_session(key, deadline=self.clock.monotonic() + 2)
        state = proposed
        if row:
            state = (await self.storage.create_session(proposed, key, deadline=self.clock.monotonic() + 2))
            prior = (await self.storage.find_request(state.session_id, state.principal_id, event.request_id, deadline=self.clock.monotonic() + 2))
            if prior and prior["phase"] == "committed":
                return self.storage.response(prior)
        snapshot = await self.snapshot(state, ctx)
        decision = self.guards.validate_context(snapshot)
        if (snapshot.assessment is None or task.assessment_at != snapshot.assessment.assessed_at
                or task.created_at > snapshot.cutoff):
            decision = replace(decision, allowed=False, codes=("contact_context_invalid",))
        if not decision.allowed:
            raise CareError(decision.codes[0], 409)
        state = (await self.storage.create_session(proposed, key, deadline=self.clock.monotonic() + 2))
        request = (await self.storage.begin_request(state.session_id, state.principal_id, event, fingerprint(task), deadline=self.clock.monotonic() + 2))
        if request["phase"] == "committed":
            return self.storage.response(request)
        if request["phase"] == "failed_terminal":
            raise CareError(request["error"])
        token = (await self.storage.reserve_processing(request["id"], (await self.storage.get_boot_generation(deadline=self.clock.monotonic() + 2)),
                                             self.clock.utcnow().timestamp(), deadline=self.clock.monotonic() + 2))
        if not token:
            return TurnResult("processing", state.session_id)
        outcome = PolicyOutcome(replace(state, last_cutoff=snapshot.cutoff), "off_topic", "opening", decision.codes)
        rendered = self.renderer.render(outcome, snapshot, outcome.phrase_id)
        if not self.guards.validate_output(rendered, outcome, snapshot).allowed:
            raise CareError("opening_output_invalid", 503)
        proposal = EffectProposal(task.idempotency_key, task.idempotency_key, state.session_id,
            state.order_id, "contact_send", canonical({"contact": task, "text": rendered.text}), request["id"])
        result = TurnResult("pending_delivery" if decision.allowed else "blocked", state.session_id,
                            text=rendered.text, codes=decision.codes,
                            effect_ids=(proposal.effect_id,) if decision.allowed else (),
                            assessment_ref=rendered.assessment_ref, evidence_refs=(request["id"],),
                            public_evidence=rendered.public_evidence)
        outcome = replace(outcome, proposals=(proposal,) if decision.allowed else ())
        try:
            committed = (await self.storage.commit_turn(request["id"], state.version, outcome, result,
                                   canonical(snapshot), canonical({"opening": True}), token=token, deadline=self.clock.monotonic() + 2))
            if committed is False:
                raise CareError("stale_callback")
        except (StorageError, OSError):
            (await self.storage.retry_request(request["id"], self.clock.utcnow().timestamp(), deadline=self.clock.monotonic() + 2))
            raise CareError("service_error", 503) from None
        return committed

    async def handle_message(self, session_id, message_id, text, ctx, reply_to=None):
        return await self._process_event(session_id, CustomerEvent("message", message_id, text, reply_to), ctx)

    @tracked
    async def confirm_cancel(self, confirmation_id, request_id, ctx, reply_to=None, confirmed=False):
        event = CustomerEvent("confirm_cancel", request_id, reply_to=reply_to,
                              confirmation_id=confirmation_id, confirmed=confirmed)
        record = await self.storage.cancellation_record(confirmation_id, self.run_id, ctx.principal_id,
            deadline=self.clock.monotonic() + 2)
        if record is None:
            legacy = await self.storage.legacy_confirmation_session(confirmation_id, self.run_id, ctx.principal_id,
                deadline=self.clock.monotonic() + 2)
            return await self._process_event(legacy, event, ctx)
        state = (await self.session(record["session_id"]))
        if state.principal_id != ctx.principal_id:
            raise CareError("not_found", 404)
        await self.authorize(ctx, state.order_id, state.principal_id)
        record = await self.storage.cancellation_record(confirmation_id, self.run_id, ctx.principal_id,
            deadline=self.clock.monotonic() + 2)
        if record is None:
            raise CareError("not_found", 404)
        binding = json.loads(record["data"])
        if (binding["principal_id"], binding["session_id"], binding["order_id"], binding["contact_id"]) != (
                state.principal_id, state.session_id, state.order_id, state.contact_id):
            raise CareError("not_found", 404)
        prior = (await self.storage.find_request(state.session_id, ctx.principal_id, request_id, deadline=self.clock.monotonic() + 2))
        if prior:
            if prior["fingerprint"] != fingerprint(event):
                raise CareError("request_conflict")
            if prior["phase"] == "committed":
                return self.storage.response(prior)
        replay = await self.storage.replay_cancellation_alias(state, event, deadline=self.clock.monotonic() + 2)
        if replay is not None:
            return replay
        return await self._process_event(state.session_id, event, ctx)

    async def request_handoff(self, session_id, request_id, ctx):
        return await self._process_event(session_id, CustomerEvent("request_handoff", request_id), ctx)

    @tracked
    async def _process_event(self, session_id, event, ctx):
        started_at = self.clock.monotonic()
        if not self.accepting:
            raise CareError("not_ready", 503)
        state = (await self.session(session_id))
        await self.authorize(ctx, state.order_id, state.principal_id)
        # Staff reads do not confer permission to act as the customer.
        if ctx.principal_id != state.principal_id:
            raise CareError("forbidden", 403)
        existing = (await self.storage.find_request(session_id, ctx.principal_id, event.request_id, deadline=self.clock.monotonic() + 2))
        if existing:
            if existing["fingerprint"] != fingerprint(event):
                raise CareError("request_conflict")
            if existing["phase"] == "committed":
                return self.storage.response(existing)
            if existing["phase"] == "failed_terminal":
                raise CareError(existing["error"], 409)
            owner = self.owners.get(existing["id"])
            if owner is not None and not owner.done():
                return TurnResult("processing", session_id)
        if state.status in ("handoff_pending", "transferred", "completed"):
            raise CareError("session_state_conflict")
        lock = self.lock(session_id)
        if lock.locked():
            return TurnResult("session_busy", session_id)
        await lock.acquire()
        request = None
        try:
            request = (await self.storage.begin_request(session_id, ctx.principal_id, event, fingerprint(event), deadline=self.clock.monotonic() + 2))
            if request["phase"] == "committed":
                return self.storage.response(request)
            self.owners[request["id"]] = asyncio.current_task()
            token = (await self.storage.reserve_processing(request["id"], (await self.storage.get_boot_generation(deadline=self.clock.monotonic() + 2)),
                                                   self.clock.utcnow().timestamp(), deadline=self.clock.monotonic() + 2))
            if token is None:
                latest = (await self.storage.request(request["id"], deadline=self.clock.monotonic() + 2))
                if latest["phase"] == "failed_terminal":
                    raise CareError(latest["error"])
                return TurnResult("processing", session_id)
            # Reload committed state and original payload when continuing an orphan.
            state = (await self.session(session_id))
            event = CustomerEvent(**json.loads(request["payload"]))
            replay = await self.storage.replay_cancellation_alias(state, event, deadline=self.clock.monotonic() + 2)
            if replay is not None:
                return replay
            snapshot = await self.snapshot(state, ctx,
                handoff=self.policy.escalation_reason(state, event) is not None)
            await self.storage.save_context(request["id"], canonical(snapshot), deadline=self.clock.monotonic() + 2)
            input_hook = await self.hooks.run("on_input", {"kind": event.kind, "request_id": event.request_id})
            hook_outcomes = {"on_input": {"action": input_hook.action, "codes": input_hook.codes}}
            reserved = await self.storage.coins_reserved(state.run_id, state.order_id, deadline=self.clock.monotonic() + 2)
            if reserved:
                snapshot = replace(snapshot, ledger_pending=True)
            if state.pending and (event.kind == "confirm_cancel" or event.reply_to):
                lifecycle = await self.storage.cancellation_record(state.pending.confirmation_id, state.run_id,
                    state.principal_id, session_id=state.session_id, deadline=self.clock.monotonic() + 2)
                if lifecycle is None or lifecycle["status"] != "pending" or lifecycle["data"] != canonical(state.pending):
                    state = replace(state, pending=None)
            outcome = self.policy.evaluate(state, event, snapshot)
            outcome = replace(outcome, codes=outcome.codes + snapshot.validation_codes)
            if snapshot.cutoff != datetime.min.replace(tzinfo=timezone.utc):
                outcome = replace(outcome, state=replace(outcome.state, last_cutoff=snapshot.cutoff))
            if outcome.state.pending is not None and outcome.state.pending != state.pending:
                outcome = replace(outcome, state=replace(outcome.state,
                    pending=replace(outcome.state.pending, reply_to=request["id"] + ":response")))
            if input_hook.action == "veto" and outcome.state.status != "handoff_pending":
                outcome = PolicyOutcome(replace(state, turn_count=outcome.state.turn_count,
                    abusive_turn_count=outcome.state.abusive_turn_count,
                    last_cutoff=outcome.state.last_cutoff), outcome.intent, "blocked", input_hook.codes)
            selection = PhraseSelection(outcome.phrase_id, "template")
            # Human/limit outcomes bypass the optional model entirely.
            if (outcome.phrase_id in ("explain", "clarify") and self.selector is not None
                    and not any(code.startswith('cancel_confirmation_') for code in outcome.codes)):
                events = await self.storage.events(session_id, deadline=self.clock.monotonic() + 2)
                natural = getattr(self.selector, 'natural_replies', False) is True
                if natural:
                    from .natural import build_natural_context
                    history = [{'role': 'user' if item['kind'] == 'customer' else 'assistant',
                                'text': json.loads(item['content']).get('text', '')}
                               for item in events if item['kind'] in ('customer', 'response')]
                    model_context = build_natural_context(outcome, snapshot, history, event.text or '')
                else:
                    history = [json.loads(item['content']).get('text', '') for item in events
                               if item['kind'] == 'customer'][-4:]
                    model_context = build_model_context(outcome, snapshot, history)
                before = await self.hooks.run("before_model", {"context": model_context.decode() if model_context else None,
                                                               "token": token})
                hook_outcomes["before_model"] = {"action": before.action, "codes": before.codes}
                if model_context and before.action == "continue" and (await self.storage.reserve_model(request["id"], deadline=self.clock.monotonic() + 2)):
                    if natural:
                        from .natural import generate_reply
                        selection = await generate_reply(self.selector, model_context, outcome.phrase_id, snapshot, self.clock)
                    else:
                        selection = await select_phrase(self.selector, model_context, allowed_ids(outcome), token, self.clock)
                    after = await self.hooks.run("after_model", {"selection": selection, "token": token})
                    hook_outcomes["after_model"] = {"action": after.action, "codes": after.codes}
                    if after.action != "continue":
                        selection = PhraseSelection(outcome.phrase_id, "template", after.codes)
            if ((await self.storage.get_boot_generation(deadline=self.clock.monotonic() + 2)) != token.boot_generation
                    or (await self.session(session_id)).version != token.state_version):
                raise CareError("stale_callback")
            rendered = self.renderer.render(outcome, snapshot, selection.phrase_id, draft=selection.draft)
            if not self.guards.validate_output(rendered, outcome, snapshot).allowed:
                raise ValueError("output_invariant")
            proposals = []
            for proposal in outcome.proposals:
                decision = self.guards.validate_dispatch(proposal, snapshot)
                if not decision.allowed:
                    outcome = replace(outcome, codes=outcome.codes + decision.codes, phrase_id="blocked")
                    continue
                payload = json.loads(proposal.payload)
                if proposal.kind == "action_request":
                    payload["evidence_ref"] = request["id"]
                if proposal.kind == "handoff_request":
                    history = [json.loads(item["content"]) for item in (await self.storage.events(session_id, deadline=self.clock.monotonic() + 2))
                               if item["kind"] == "customer"]
                    effects = [dict(row) for row in (await self.storage.effects(deadline=self.clock.monotonic() + 2)) if row["session_id"] == session_id]
                    payload["summary"] = self.renderer.render_handoff(outcome.state, snapshot, event=event,
                        history=history, effects=effects, previous_pending=state.pending,
                        reason=payload["reason"], evidence_refs=(request["id"],),
                        receipts=await self.storage.session_receipts(session_id, deadline=self.clock.monotonic() + 2))
                proposals.append(replace(proposal, payload=canonical(payload), evidence_ref=request["id"]))
            outcome = replace(outcome, proposals=tuple(proposals))
            if outcome.phrase_id == "blocked":
                selection = PhraseSelection("blocked", "template")
                rendered = self.renderer.render(outcome, snapshot, "blocked")
            pending = outcome.state.pending
            result = TurnResult("pending_delivery" if proposals else "committed", session_id,
                rendered.text, outcome.intent, outcome.codes + selection.codes + rendered.codes,
                tuple(p.effect_id for p in proposals), pending.confirmation_id if pending else None, selection.source,
                rendered.assessment_ref, (request["id"],), rendered.public_evidence, request["id"] + ":response")
            trace = {"trace_id": uuid4().hex, "run_id": self.run_id, "session_id": session_id,
                "request_id": request["id"], "phases": list(range(1, 11)), "policy_version": self.policy.version,
                "template_version": self.renderer.version, "hook_version": self.hooks.version,
                "assessment_ref": rendered.assessment_ref, "codes": result.codes, "source": result.source,
                "effect_ids": result.effect_ids, "elapsed_runtime_s": self.clock.monotonic() - started_at,
                "hook_outcomes": hook_outcomes}
            bundle = {"snapshot": snapshot, "session": state, "event": event,
                      "decision_codes": outcome.codes, "proposals": outcome.proposals}
            committed = (await self.storage.commit_turn(request["id"], state.version, outcome, result,
                                           canonical(bundle), canonical(trace), token=token, deadline=self.clock.monotonic() + 2))
            if committed is False:
                raise CareError("stale_callback")
            return committed
        except (StorageError, OSError):
            if request:
                try:
                    (await self.storage.retry_request(request["id"], self.clock.utcnow().timestamp(), deadline=self.clock.monotonic() + 2))
                except StorageError:
                    pass
            raise CareError("service_error", 503) from None
        except CareError:
            raise
        except Exception:
            if request:
                (await self.storage.fail_request(request["id"], "policy_invariant_failed", deadline=self.clock.monotonic() + 2))
            observed = await self.hooks.run("on_error", {"phase": "turn", "code": "policy_invariant_failed"})
            await self.record_observation(session_id, "on_error", observed, request["id"] if request else "")
            raise CareError("policy_invariant_failed", 503) from None
        finally:
            if request:
                self.owners.pop(request["id"], None)
            lock.release()

    @tracked
    async def drain_pending(self):
        if self.dispatcher is None:
            raise CareError("dispatcher_unavailable", 503)
        return await self.dispatcher.drain_pending()

    @tracked
    async def get_messages(self, session_id, ctx):
        state = (await self.session(session_id))
        await self.authorize(ctx, state.order_id, state.principal_id)
        messages = []
        system_events = []
        for event in (await self.storage.events(session_id, deadline=self.clock.monotonic() + 2)):
            if event["visibility"] != "customer":
                continue
            payload = json.loads(event["content"])
            if event["kind"] == "receipt":
                system_events.append({"id": event["id"], "sequence": event["sequence"],
                    "kind": event["kind"], "outcome": payload["outcome"], "effect_id": payload["effect_id"]})
                continue
            messages.append({"id": event["id"], "sequence": event["sequence"], "kind": event["kind"],
                "text": payload.get("text", ""),
                **({key: payload.get(key) for key in ("intent", "assessment_ref", "evidence_refs",
                    "codes", "effect_ids", "source", "message_id", "public_evidence")}
                   if event["kind"] == "response" else {})})
        effects = [{"effect_id": row["id"], "delivery_status": row["state"], "outcome": row["outcome"]}
                   for row in (await self.storage.effects(deadline=self.clock.monotonic() + 2)) if row["session_id"] == session_id]
        return {"messages": messages, "system_events": system_events, "effects": effects, "status": state.status}

    @tracked
    async def get_trace(self, session_id, ctx):
        if not ctx or "care_trace" not in ctx.staff_permissions:
            raise CareError("forbidden", 403)
        state = (await self.session(session_id))
        await self.authorize(ctx, state.order_id, state.principal_id)
        rows = await self.storage.traces(session_id, deadline=self.clock.monotonic() + 2)
        return {"decisions": [json.loads(row) for row in rows], "runtime_events": [
            json.loads(event["content"]) for event in (await self.storage.events(session_id, deadline=self.clock.monotonic() + 2))
            if event["kind"] == "runtime_hook"]}

    @tracked
    async def get_handoffs(self, ctx):
        if not ctx or "care_handoffs" not in ctx.staff_permissions:
            raise CareError("forbidden", 403)
        result = []
        for row in (await self.storage.effects(deadline=self.clock.monotonic() + 2)):
            proposal = json.loads(row["proposal"])
            if proposal["kind"] != "handoff_request":
                continue
            state = (await self.storage.load_session(row["session_id"], deadline=self.clock.monotonic() + 2))
            if state.run_id != self.run_id:
                continue
            await self.authorize(ctx, state.order_id, state.principal_id)
            result.append({"session_id": state.session_id, "order_id": state.order_id,
                "status": state.status, "delivery_status": row["state"],
                "summary": json.loads(proposal["payload"]).get("summary")})
        return {"handoffs": result}

    @tracked
    async def retry_handoff(self, session_id: str, ctx: TrustedRequestContext) -> str:
        """Internal capability: requeue only a blocked, never submitted envelope."""
        if not isinstance(ctx, TrustedRequestContext) or "care_handoff_retry" not in ctx.staff_permissions:
            raise CareError("forbidden", 403)
        state = (await self.session(session_id))
        await self.authorize(ctx, state.order_id, state.principal_id)
        async with self.lock(session_id):
            state = (await self.session(session_id))
            row = await self.storage.handoff_effect(self.run_id, session_id, deadline=self.clock.monotonic() + 2)
            if (state.status != "handoff_pending" or row is None or row["state"] != "blocked"
                    or row["attempts"] or row["manual"] or row["outcome"] != "unknown"):
                raise CareError("handoff_retry_not_allowed", 409)
            if self.dispatcher is None or not getattr(self.dispatcher.gate, "supports_deadlines", False):
                raise CareError("dispatcher_unavailable", 503)
            proposal = EffectProposal(**json.loads(row["proposal"]))
            snapshot = await self.snapshot(state, ctx, handoff=True)
            if snapshot.validation_codes:
                await self.record_observation(session_id, "context_validation",
                    HookDecision(codes=snapshot.validation_codes), row["id"])
            if not self.guards.validate_dispatch(proposal, snapshot).allowed:
                return "blocked"
            try:
                gate = await bounded(self.dispatcher.gate.check(proposal, ctx,
                    deadline=self.clock.monotonic() + 2), self.clock, 2)
            except Exception:
                return "blocked"
            if not gate.allowed:
                return "blocked"
            # Gate calls yield: another owner may have claimed or accepted this envelope.
            changed = await self.storage.requeue_handoff(state, row, deadline=self.clock.monotonic() + 2)
            if changed != 1:
                raise CareError("handoff_retry_not_allowed", 409)
            return "pending_delivery"

    @tracked
    async def resolve(self, ref: str, server_ctx: TrustedRequestContext) -> str:
        if not server_ctx or "care_evidence" not in server_ctx.staff_permissions:
            raise CareError("forbidden", 403)
        row = await self.storage.evidence(ref, deadline=self.clock.monotonic() + 2)
        if row is None:
            raise CareError("not_found", 404)
        state = (await self.session(row["session_id"]))
        await self.authorize(server_ctx, state.order_id, state.principal_id)
        return row["data"]
