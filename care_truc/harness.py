"""Bounded per-session turn orchestration with durable request ownership."""

import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
import sqlite3
from uuid import uuid4

from .guardrails import Guardrails
from .hooks import RuntimeHooks, bounded
from .phrases import allowed_ids, build_model_context, select_phrase
from .policy import CarePolicy
from .renderer import ResponseRenderer
from .runtime_types import (CareError, ContextSnapshot, CustomerEvent, EffectProposal,
    PhraseSelection, PolicyOutcome, SessionState, TrustedRequestContext, TurnResult,
    canonical, fingerprint)


class CareHarness:
    def __init__(self, run_id, store, context_provider, clock, *, selector=None, hooks=None):
        self.run_id = run_id
        self.store = store
        self.context_provider = context_provider
        self.clock = clock
        self.selector = selector
        self.hooks = hooks or RuntimeHooks({}, clock)
        self.policy = CarePolicy()
        self.renderer = ResponseRenderer()
        self.guards = Guardrails()
        self.locks = {}
        self.owners = {}
        self.accepting = True
        self.dispatcher = None

    def lock(self, session_id):
        return self.locks.setdefault(session_id, asyncio.Lock())

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

    async def snapshot(self, state, ctx):
        try:
            snapshot = copy.deepcopy(await bounded(self.context_provider.load(ctx, state.order_id), self.clock, 2))
            if snapshot.order_id != state.order_id or snapshot.principal_id != state.principal_id:
                raise CareError("context_binding_invalid", 503)
            if snapshot.cutoff.tzinfo is None:
                raise CareError("context_cutoff_invalid", 503)
            return snapshot
        except (TimeoutError, OSError):
            # A sentinel marks absent business time; operational UTC cannot grant business rights.
            return ContextSnapshot(state.principal_id, state.order_id,
                                   datetime.min.replace(tzinfo=timezone.utc), None, None)

    async def open_chat(self, order_id, request_id, ctx):
        CustomerEvent("request_handoff", request_id)
        if not self.accepting:
            raise CareError("not_ready", 503)
        await self.authorize(ctx, order_id)
        key = fingerprint((self.run_id, ctx.principal_id, order_id, request_id))
        state = self.store.create_session(SessionState(uuid4().hex, self.run_id, ctx.principal_id, order_id), key)
        return TurnResult("opened", state.session_id)

    async def open_contact(self, task, ctx):
        if not self.accepting:
            raise CareError("not_ready", 503)
        await self.authorize(ctx, task.order_id)
        if task.channel not in ("chat", "web_voice") or not task.proactive:
            raise CareError("invalid_contact", 400)
        key = fingerprint((self.run_id, "contact", task.idempotency_key))
        state = self.store.create_session(SessionState(uuid4().hex, self.run_id, ctx.principal_id,
            task.order_id, task.channel, "a1", task.contact_id), key)
        snapshot = await self.snapshot(state, ctx)
        decision = self.guards.validate_context(snapshot)
        if (snapshot.assessment is None or task.assessment_at != snapshot.assessment.assessed_at
                or task.created_at.tzinfo is None or task.created_at > snapshot.cutoff):
            decision = replace(decision, allowed=False, codes=("contact_context_invalid",))
        event = CustomerEvent("message", "contact:" + task.contact_id, "contact opening")
        request = self.store.begin_request(state.session_id, state.principal_id, event, fingerprint(task))
        if request["phase"] == "committed":
            return self.store.response(request)
        proposal = EffectProposal(task.idempotency_key, task.idempotency_key, state.session_id,
            state.order_id, "contact_send", canonical(task), request["id"])
        result = TurnResult("pending_delivery" if decision.allowed else "blocked", state.session_id,
                            codes=decision.codes, effect_ids=(proposal.effect_id,) if decision.allowed else ())
        outcome = PolicyOutcome(state, "off_topic", "clarify", decision.codes,
                                (proposal,) if decision.allowed else ())
        self.store.commit_turn(request["id"], state.version, outcome, result,
                               canonical(snapshot), canonical({"opening": True}))
        return result

    async def handle_message(self, session_id, message_id, text, ctx, reply_to=None):
        return await self._process_event(session_id, CustomerEvent("message", message_id, text, reply_to), ctx)

    async def confirm_cancel(self, confirmation_id, request_id, ctx):
        rows = self.store.db.execute("SELECT id FROM sessions").fetchall()
        for row in rows:
            state = self.store.load_session(row[0])
            # Previously confirmed IDs remain retriable using the original event.
            prior = self.store.find_request(state.session_id, ctx.principal_id, request_id)
            matches = prior and json.loads(prior["payload"]).get("confirmation_id") == confirmation_id
            if (state.pending and state.pending.confirmation_id == confirmation_id) or matches:
                return await self._process_event(state.session_id,
                    CustomerEvent("confirm_cancel", request_id, confirmation_id=confirmation_id), ctx)
        raise CareError("not_found", 404)

    async def request_handoff(self, session_id, request_id, ctx):
        return await self._process_event(session_id, CustomerEvent("request_handoff", request_id), ctx)

    async def _process_event(self, session_id, event, ctx):
        started_at = self.clock.monotonic()
        if not self.accepting:
            raise CareError("not_ready", 503)
        state = self.store.load_session(session_id)
        await self.authorize(ctx, state.order_id, state.principal_id)
        # Staff reads do not confer permission to act as the customer.
        if ctx.principal_id != state.principal_id:
            raise CareError("forbidden", 403)
        existing = self.store.find_request(session_id, ctx.principal_id, event.request_id)
        if existing:
            if existing["fingerprint"] != fingerprint(event):
                raise CareError("request_conflict")
            if existing["phase"] == "committed":
                return self.store.response(existing)
            if existing["phase"] == "failed_terminal":
                raise CareError(existing["error"], 409)
            owner = self.owners.get(existing["id"])
            if owner is not None and not owner.done():
                return TurnResult("processing", session_id)
        lock = self.lock(session_id)
        if lock.locked():
            return TurnResult("session_busy", session_id)
        await lock.acquire()
        request = None
        try:
            request = self.store.begin_request(session_id, ctx.principal_id, event, fingerprint(event))
            if request["phase"] == "committed":
                return self.store.response(request)
            self.owners[request["id"]] = asyncio.current_task()
            token = self.store.reserve_processing(request["id"], self.store.boot_generation,
                                                   self.clock.utcnow().timestamp())
            if token is None:
                latest = self.store.request(request["id"])
                if latest["phase"] == "failed_terminal":
                    raise CareError(latest["error"])
                return TurnResult("processing", session_id)
            # Reload committed state and original payload when continuing an orphan.
            state = self.store.load_session(session_id)
            event = CustomerEvent(**json.loads(request["payload"]))
            snapshot = await self.snapshot(state, ctx)
            self.store.db.execute("UPDATE requests SET context=? WHERE id=?", (canonical(snapshot), request["id"]))
            input_hook = await self.hooks.run("on_input", {"kind": event.kind, "request_id": event.request_id})
            outcome = self.policy.evaluate(state, event, snapshot)
            if input_hook.action == "veto":
                outcome = PolicyOutcome(replace(state, turn_count=state.turn_count + 1),
                                        outcome.intent, "blocked", input_hook.codes)
            selection = PhraseSelection(outcome.phrase_id, "template")
            # Human/limit outcomes bypass the optional model entirely.
            if outcome.phrase_id in ("explain", "clarify") and self.selector is not None:
                history = [json.loads(item["content"]).get("text", "") for item in self.store.events(session_id)
                           if item["kind"] == "customer"][-4:]
                model_context = build_model_context(outcome, snapshot, history)
                before = await self.hooks.run("before_model", {"context": model_context.decode() if model_context else None,
                                                               "token": token})
                if model_context and before.action == "continue" and self.store.reserve_model(request["id"]):
                    selection = await select_phrase(self.selector, model_context, allowed_ids(outcome), token, self.clock)
                    after = await self.hooks.run("after_model", {"selection": selection, "token": token})
                    if after.action != "continue":
                        selection = PhraseSelection(outcome.phrase_id, "template", after.codes)
            if (self.store.boot_generation != token.boot_generation
                    or self.store.load_session(session_id).version != token.state_version):
                raise CareError("stale_callback")
            rendered = self.renderer.render(outcome, snapshot, selection.phrase_id)
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
                    payload["summary"] = self.renderer.render_handoff(outcome.state, snapshot)
                proposals.append(replace(proposal, payload=canonical(payload), evidence_ref=request["id"]))
            outcome = replace(outcome, proposals=tuple(proposals))
            if outcome.phrase_id == "blocked":
                selection = PhraseSelection("blocked", "template")
                rendered = self.renderer.render(outcome, snapshot, "blocked")
            pending = outcome.state.pending
            result = TurnResult("pending_delivery" if proposals else "committed", session_id,
                rendered.text, outcome.intent, outcome.codes + selection.codes,
                tuple(p.effect_id for p in proposals), pending.confirmation_id if pending else None, selection.source)
            trace = {"trace_id": uuid4().hex, "run_id": self.run_id, "session_id": session_id,
                "request_id": request["id"], "phases": list(range(1, 11)), "policy_version": self.policy.version,
                "template_version": self.renderer.version, "hook_version": self.hooks.version,
                "assessment_ref": rendered.assessment_ref, "codes": result.codes, "source": result.source,
                "effect_ids": result.effect_ids, "elapsed_runtime_s": self.clock.monotonic() - started_at,
                "hook_outcomes": {"on_input": input_hook.action}}
            bundle = {"snapshot": snapshot, "session": state, "event": event,
                      "decision_codes": outcome.codes, "proposals": outcome.proposals}
            return self.store.commit_turn(request["id"], state.version, outcome, result,
                                           canonical(bundle), canonical(trace))
        except (sqlite3.DatabaseError, OSError):
            if request:
                try:
                    self.store.retry_request(request["id"], self.clock.utcnow().timestamp())
                except sqlite3.DatabaseError:
                    pass
            raise CareError("service_error", 503) from None
        except CareError:
            raise
        except Exception:
            if request:
                self.store.fail_request(request["id"], "policy_invariant_failed")
            await self.hooks.run("on_error", {"phase": "turn", "code": "policy_invariant_failed"})
            raise CareError("policy_invariant_failed", 503) from None
        finally:
            if request:
                self.owners.pop(request["id"], None)
            lock.release()

    async def drain_pending(self):
        if self.dispatcher is None:
            raise CareError("dispatcher_unavailable", 503)
        return await self.dispatcher.drain_pending()

    async def get_messages(self, session_id, ctx):
        state = self.store.load_session(session_id)
        await self.authorize(ctx, state.order_id, state.principal_id)
        messages = []
        for event in self.store.events(session_id):
            if event["visibility"] != "customer":
                continue
            payload = json.loads(event["content"])
            messages.append({"id": event["id"], "sequence": event["sequence"], "kind": event["kind"],
                "text": payload.get("text", ""),
                **({"outcome": payload["outcome"], "effect_id": payload["effect_id"]}
                   if event["kind"] == "receipt" else {})})
        effects = [{"effect_id": row["id"], "delivery_status": row["state"], "outcome": row["outcome"]}
                   for row in self.store.effects() if row["session_id"] == session_id]
        return {"messages": messages, "effects": effects, "status": state.status}

    async def get_trace(self, session_id, ctx):
        if not ctx or "care_trace" not in ctx.staff_permissions:
            raise CareError("forbidden", 403)
        state = self.store.load_session(session_id)
        await self.authorize(ctx, state.order_id, state.principal_id)
        rows = self.store.db.execute("SELECT trace FROM evidence_bundles e JOIN requests r ON e.request_id=r.id WHERE r.session_id=? ORDER BY r.rowid", (session_id,))
        return {"decisions": [json.loads(row[0]) for row in rows]}

    async def get_handoffs(self, ctx):
        if not ctx or "care_handoffs" not in ctx.staff_permissions:
            raise CareError("forbidden", 403)
        result = []
        for row in self.store.effects():
            proposal = json.loads(row["proposal"])
            if proposal["kind"] != "handoff_request":
                continue
            state = self.store.load_session(row["session_id"])
            await self.authorize(ctx, state.order_id, state.principal_id)
            result.append({"session_id": state.session_id, "order_id": state.order_id,
                "status": state.status, "delivery_status": row["state"],
                "summary": json.loads(proposal["payload"]).get("summary")})
        return {"handoffs": result}

    async def resolve(self, ref: str, server_ctx: TrustedRequestContext) -> str:
        if not server_ctx or "care_evidence" not in server_ctx.staff_permissions:
            raise CareError("forbidden", 403)
        row = self.store.db.execute("SELECT e.data,r.session_id FROM evidence_bundles e JOIN requests r ON e.request_id=r.id WHERE e.ref=?", (ref,)).fetchone()
        if row is None:
            raise CareError("not_found", 404)
        state = self.store.load_session(row["session_id"])
        await self.authorize(server_ctx, state.order_id, state.principal_id)
        return row["data"]
