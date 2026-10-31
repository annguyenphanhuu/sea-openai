"""Claim durable proposals before network; atomic permission gates remain external."""

import asyncio
import json

from .hooks import bounded
from .harness import tracked
from .runtime_types import (CareError, DrainReport, EffectProposal, TrustedRequestContext)


class EffectDispatcher:
    def __init__(self, harness, gateway, gate):
        self.harness = harness
        self.storage = harness.storage
        self.clock = harness.clock
        self.gateway = gateway
        self.gate = gate
        self.stopping = False
        self.drain_lock = asyncio.Lock()
        self.cursor = 0

    @tracked
    async def drain_pending(self, *, limit: int = 20, start_budget_s: float = 2.0) -> DrainReport:
        if self.drain_lock.locked() or self.stopping:
            return DrainReport(0, 0)
        started = examined = 0
        end = self.clock.monotonic() + min(2, max(0, start_budget_s))
        async with self.drain_lock:
            rows = (await self.storage.effects(deadline=self.clock.monotonic() + 2))
            start = self.cursor % len(rows) if rows else 0
            for offset in range(len(rows)):
                index = (start + offset) % len(rows)
                row = rows[index]
                if examined >= min(20, max(0, limit)) or self.clock.monotonic() >= end or self.stopping:
                    break
                if row["manual"] or row["outcome"] in ("succeeded", "rejected"):
                    continue
                if row["state"] == "blocked" and not row["attempts"]:
                    continue
                if row["next_at"] > self.clock.utcnow().timestamp():
                    continue
                examined += 1
                self.cursor = index + 1
                if row["state"] in ("in_flight", "needs_reconciliation", "delivered") or (row["state"] == "blocked" and row["attempts"]):
                    await self.reconcile(row["id"])
                    continue
                if row["state"] not in ("pending_delivery", "retry_wait"):
                    continue
                proposal = EffectProposal(**json.loads(row["proposal"]))
                lock = self.harness.lock(proposal.session_id)
                if lock.locked():
                    continue
                async with lock:
                    state = (await self.storage.load_session(proposal.session_id, deadline=self.clock.monotonic() + 2))
                    ctx = TrustedRequestContext(state.principal_id)
                    await self.harness.authorize(ctx, state.order_id, state.principal_id)
                    snapshot = await self.harness.snapshot(state, ctx)
                    decision = self.harness.guards.validate_dispatch(proposal, snapshot)
                    adapters = (self.gateway, self.gate)
                    if not decision.allowed or not all(a and getattr(a, "supports_deadlines", False) for a in adapters):
                        (await self.storage.set_effect(row["id"], state="blocked", deadline=self.clock.monotonic() + 2))
                        continue
                    if state.status in ("handoff_pending", "transferred", "completed") and proposal.kind != "handoff_request":
                        (await self.storage.set_effect(row["id"], state="blocked", deadline=self.clock.monotonic() + 2))
                        continue
                    before = await self.harness.hooks.run("before_action", {"proposal": proposal, "decision": decision})
                    await self.harness.record_observation(proposal.session_id, "before_action", before, row["id"])
                    if before.action != "continue":
                        (await self.storage.set_effect(row["id"], state="blocked", deadline=self.clock.monotonic() + 2))
                        continue
                    try:
                        gate = await bounded(self.gate.check(proposal, ctx, deadline=self.clock.monotonic() + 2), self.clock, 2)
                    except Exception:
                        (await self.storage.set_effect(row["id"], state="blocked", deadline=self.clock.monotonic() + 2))
                        continue
                    if not gate.allowed:
                        (await self.storage.set_effect(row["id"], state="blocked", deadline=self.clock.monotonic() + 2))
                        continue
                    claimed = (await self.storage.claim_effect(row["id"], state.version, row["revision"], self.clock.utcnow().timestamp(), deadline=self.clock.monotonic() + 2))
                if claimed is None:
                    continue
                started += 1
                try:
                    receipt = await bounded(self.gateway.submit(claimed, deadline=self.clock.monotonic() + 2), self.clock, 2)
                    (await self.storage.record_receipt(receipt, deadline=self.clock.monotonic() + 2))
                except Exception:
                    (await self.storage.set_effect(row["id"], state="needs_reconciliation", deadline=self.clock.monotonic() + 2))
                    continue
                observed = await self.harness.hooks.run("after_action", {"receipt": receipt})
                await self.harness.record_observation(claimed.session_id, "after_action", observed, row["id"])
        return DrainReport(started, examined)

    @tracked
    async def reconcile(self, effect_id: str) -> None:
        row = (await self.storage.effect(effect_id, deadline=self.clock.monotonic() + 2))
        if row["manual"] or row["lookups"] >= 3:
            return
        lookup = getattr(self.gateway, "lookup", None)
        if lookup is None or not getattr(self.gateway, "supports_deadlines", False):
            (await self.storage.set_effect(effect_id, state="needs_reconciliation", manual=1, deadline=self.clock.monotonic() + 2))
            return
        now = self.clock.utcnow().timestamp()
        count = await self.storage.reserve_lookup(effect_id, now, deadline=self.clock.monotonic() + 2)
        if count is None:
            return
        try:
            receipt = await bounded(lookup(row["effect_key"], deadline=self.clock.monotonic() + 2), self.clock, 2)
            if receipt is not None:
                (await self.storage.record_receipt(receipt, deadline=self.clock.monotonic() + 2))
                (await self.storage.set_effect(effect_id, lookups=0, deadline=self.clock.monotonic() + 2))
                observed = await self.harness.hooks.run("after_action", {"receipt": receipt})
                await self.harness.record_observation(row["session_id"], "after_action", observed, effect_id)
                return
        except Exception:
            if count >= 3:
                (await self.storage.set_effect(effect_id, state="needs_reconciliation", manual=1, deadline=self.clock.monotonic() + 2))
            return
        if count >= 3 or row["attempts"] >= 3:
            (await self.storage.set_effect(effect_id, state="needs_reconciliation", manual=1, deadline=self.clock.monotonic() + 2))
        elif row["state"] != "delivered" and getattr(self.gateway, "idempotent", False):
            (await self.storage.set_effect(effect_id, state="retry_wait", deadline=self.clock.monotonic() + 2))
