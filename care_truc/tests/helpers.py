"""Scripted test adapters, never production defaults."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from contracts.types import OrderAssessment
from care_truc.runtime_types import (CareError, ContextSnapshot, FeedSnapshot,
    GateDecision, GuardSnapshot, Receipt, TrustedRequestContext, fingerprint)

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
CUSTOMER = TrustedRequestContext("customer")
SYSTEM = TrustedRequestContext("customer", frozenset({"care_contact"}))
STAFF = TrustedRequestContext("staff", frozenset({"care_trace", "care_handoffs"}))


def context(order_id="o1", **changes):
    assessment = OrderAssessment(order_id, NOW, "late", date(2026, 10, 28), None,
        2, 0.9, 0.9, "carrier", ("delayed",), ())
    guard = GuardSnapshot("a3", NOW, (FeedSnapshot("ops", "trusted", NOW),),
                          ("ops",), True, True)
    return replace(ContextSnapshot("customer", order_id, NOW, assessment, guard,
                                   1_000_000, False, False, True), **changes)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.wall = NOW
        self.waiters = []

    def monotonic(self):
        return self.now

    def utcnow(self):
        return self.wall

    async def wait_until(self, deadline):
        while self.now < deadline:
            event = asyncio.Event()
            self.waiters.append(event)
            await event.wait()

    def advance(self, seconds):
        self.now += seconds
        self.wall += timedelta(seconds=seconds)
        waiters, self.waiters = self.waiters, []
        for event in waiters:
            event.set()


class ContextAdapter:
    supports_deadlines = True
    def __init__(self, snapshot=None):
        self.snapshot = snapshot or context()

    async def authorize(self, ctx, order_id):
        if not ctx or not ctx.principal_id:
            raise CareError("unauthenticated", 401)
        if ctx.principal_id != "customer" and not ctx.staff_permissions:
            raise CareError("forbidden", 403)
        if order_id not in ("o1", "o2"):
            raise CareError("not_found", 404)

    async def load(self, ctx, order_id):
        return replace(self.snapshot, order_id=order_id,
            assessment=replace(self.snapshot.assessment, order_id=order_id)
            if self.snapshot.assessment else None)


class ScriptedGateway:
    supports_deadlines = True
    idempotent = True
    def __init__(self):
        self.submissions = []
        self.lookups = []
        self.receipts = {}
        self.outcome = "accepted"
        self.submit_error = None
        self.lookup_error = None

    async def submit(self, proposal, *, deadline):
        self.submissions.append(proposal)
        receipt = Receipt(proposal.effect_id, proposal.key, fingerprint(proposal.payload),
                          1, self.outcome, "remote")
        self.receipts[proposal.key] = receipt
        if self.submit_error:
            raise self.submit_error
        return receipt

    async def lookup(self, key, *, deadline):
        self.lookups.append(key)
        if self.lookup_error:
            raise self.lookup_error
        return self.receipts.get(key)


class Gate:
    supports_deadlines = True
    allowed = True
    async def check(self, proposal, ctx, *, deadline):
        return GateDecision(self.allowed, () if self.allowed else ("permission_denied",))


class BlockingSelector:
    supports_deadlines = True
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def select(self, context, *, deadline):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return b'{"phrase_id":"explain"}'
