"""Fixed server hook registry and cancellable operational deadlines."""

import asyncio
import json
from types import MappingProxyType

from .runtime_types import HookDecision, canonical


def _discard(task):
    if not task.cancelled():
        task.exception()


async def bounded(awaitable, clock, seconds: float):
    task = asyncio.ensure_future(awaitable)
    timer = asyncio.create_task(clock.wait_until(clock.monotonic() + max(0, seconds)))
    try:
        done, _ = await asyncio.wait((task, timer), return_when=asyncio.FIRST_COMPLETED)
        if timer in done:
            task.cancel()
            task.add_done_callback(_discard)
            raise TimeoutError("deadline_exceeded")
        return task.result()
    finally:
        timer.cancel()
        if not task.done():
            task.cancel()
            task.add_done_callback(_discard)


def immutable(value):
    if isinstance(value, dict):
        return MappingProxyType({key: immutable(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(immutable(item) for item in value)
    return value


class RuntimeHooks:
    def __init__(self, registry, clock, version: str = "1"):
        self.registry = MappingProxyType({phase: tuple(callbacks) for phase, callbacks in registry.items()})
        self.clock = clock
        self.version = version

    async def run(self, phase, data, *, deadline=None) -> HookDecision:
        end = min(deadline, self.clock.monotonic() + .1) if deadline is not None else self.clock.monotonic() + .1
        frozen = immutable(json.loads(canonical(data)))
        decision = HookDecision()
        observer = phase in ("after_action", "on_error")
        for callback in self.registry.get(phase, ()):
            try:
                result = await bounded(callback(frozen), self.clock, end - self.clock.monotonic())
                if observer:
                    if result is not None:
                        raise ValueError("observer_result")
                else:
                    if not isinstance(result, HookDecision) or result.action not in ("continue", "veto", "use_fallback"):
                        raise ValueError("hook_schema")
                    if result.action == "use_fallback" and phase not in ("before_model", "after_model"):
                        raise ValueError("hook_capability")
                    if decision.action != "veto" and result.action != "continue":
                        decision = result
            except Exception:
                action = "continue" if observer else "use_fallback" if phase in ("before_model", "after_model") else "veto"
                decision = HookDecision("veto" if decision.action == "veto" else action,
                                        decision.codes + ("hook_failed",))
        return decision
