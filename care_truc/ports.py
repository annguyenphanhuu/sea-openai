"""Server adapter contracts. No provider or fake gateway is selected implicitly."""

import asyncio
from datetime import datetime, timezone
import time
from typing import Protocol

from .runtime_types import (ContextSnapshot, EffectProposal, GateDecision, Receipt,
                            TrustedRequestContext)


class RuntimeClock(Protocol):
    def monotonic(self) -> float: ...
    def utcnow(self) -> datetime: ...
    async def wait_until(self, deadline: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    async def wait_until(self, deadline: float) -> None:
        await asyncio.sleep(max(0, deadline - self.monotonic()))


class ContextProvider(Protocol):
    supports_deadlines: bool
    async def authorize(self, ctx: TrustedRequestContext, order_id: str) -> None: ...
    async def load(self, ctx: TrustedRequestContext, order_id: str) -> ContextSnapshot: ...


class PhraseSelector(Protocol):
    supports_deadlines: bool
    async def select(self, context: bytes, *, deadline: float) -> bytes: ...


class DispatchGate(Protocol):
    supports_deadlines: bool
    async def check(self, proposal: EffectProposal, ctx: TrustedRequestContext,
                    *, deadline: float) -> GateDecision: ...


class EffectGateway(Protocol):
    """Platform-owned submission, with atomic final permission/control and D4 recheck.

    Coin grants must enforce global once-per-order ledger uniqueness across runs,
    validate the durable evidence/current text and immutable amount, and return
    authoritative durable receipts. Local reservation is never grant authority.
    """
    supports_deadlines: bool
    idempotent: bool
    async def submit(self, proposal: EffectProposal, *, deadline: float) -> Receipt: ...
    async def lookup(self, key: str, *, deadline: float) -> Receipt | None: ...


class EvidenceResolver(Protocol):
    async def resolve(self, ref: str, server_ctx: TrustedRequestContext) -> str: ...
