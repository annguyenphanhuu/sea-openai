"""Claim durable proposals before network; atomic permission gates remain external."""

import asyncio
import json

from .hooks import bounded
from .runtime_types import (CareError, DrainReport, EffectProposal, TrustedRequestContext)


class EffectDispatcher:
    def __init__(self, harness, gateway, gate):
        self.harness = harness
        self.store = harness.store
        self.clock = harness.clock
        self.gateway = gateway
        self.gate = gate
        self.stopping = False
        self.drain_lock = asyncio.Lock()

    async def drain_pending(self, *, limit: int = 20, start_budget_s: float = 2.0) -> DrainReport:
        if self.drain_lock.locked() or self.stopping:
            return DrainReport(0, 0)
        started = examined = 0
        end = self.clock.monotonic() + min(2, max(0, start_budget_s))
        async with self.drain_lock:
            for row in self.store.effects():
                if examined >= min(20, max(0, limit)) or self.clock.monotonic() >= end or self.stopping:
                    break
                if row["state"] not in ("pending_delivery", "retry_wait"):
                    continue
                if row["next_at"] > self.clock.utcnow().timestamp():
                    continue
                examined += 1
                proposal = EffectProposal(**json.loads(row["proposal"]))
                lock = self.harness.lock(proposal.session_id)
                if lock.locked():
                    continue
                async with lock:
                    state = self.store.load_session(proposal.session_id)
                    ctx = TrustedRequestContext(state.principal_id)
                    await self.harness.authorize(ctx, state.order_id, state.principal_id)
                    snapshot = await self.harness.snapshot(state, ctx)
                    decision = self.harness.guards.validate_dispatch(proposal, snapshot)
                    adapters = (self.gateway, self.gate)
                    if not decision.allowed or not all(a and getattr(a, "supports_deadlines", False) for a in adapters):
                        self.store.set_effect(row["id"], state="blocked")
                        continue
                    if state.status in ("handoff_pending", "transferred", "completed") and proposal.kind != "handoff_request":
                        self.store.set_effect(row["id"], state="blocked")
                        continue
                    before = await self.harness.hooks.run("before_action", {"proposal": proposal, "decision": decision})
                    if before.action != "continue":
                        self.store.set_effect(row["id"], state="blocked")
                        continue
                    try:
                        gate = await bounded(self.gate.check(proposal, ctx, deadline=self.clock.monotonic() + 2), self.clock, 2)
                    except Exception:
                        self.store.set_effect(row["id"], state="blocked")
                        continue
                    if not gate.allowed:
                        self.store.set_effect(row["id"], state="blocked")
                        continue
                    claimed = self.store.claim_effect(row["id"], state.version, row["revision"], self.clock.utcnow().timestamp())
                if claimed is None:
                    continue
                started += 1
                try:
                    receipt = await bounded(self.gateway.submit(claimed, deadline=self.clock.monotonic() + 2), self.clock, 2)
                    self.store.record_receipt(receipt)
                    await self.harness.hooks.run("after_action", {"receipt": receipt})
                except Exception:
                    self.store.set_effect(row["id"], state="needs_reconciliation")
        return DrainReport(started, examined)
