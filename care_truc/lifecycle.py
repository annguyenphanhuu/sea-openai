"""Run ownership, recovery, bounded shutdown and content-free health."""

import asyncio
from datetime import datetime
from pathlib import Path
import re

from .dispatcher import EffectDispatcher
from .harness import CareHarness
from .hooks import bounded
from .ports import SystemClock
from .process_lock import RunLock
from .runtime_types import CareError, CustomerEvent, Health, TrustedRequestContext
from .store import MemoryStore
from .storage_port import CareStore, StorageError
from .local_store import LocalCareStore
from contracts.types import ContactTask


class CareRuntime:
    @classmethod
    async def start(cls, run_id: str, adapters, hooks=None, *, root=Path("runs"), background=True,
                    store: CareStore | None = None):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
            raise ValueError("invalid_run_id")
        self = cls()
        self.closed = False
        self.ready = False
        self.worker = None
        self.codes = []
        self.lock = None
        self.storage = None
        self.health_cache = (0, 0)
        self.store = None
        try:
            clock = adapters.get("clock") or SystemClock()
            if store is None:
                self.lock = RunLock.acquire(Path(root) / run_id)
                self.store = MemoryStore.open(Path(root) / run_id / "care.sqlite")
                self.storage = LocalCareStore(self.store, monotonic=clock.monotonic)
            else:
                self.store = store
                self.storage = store
            await self.storage.prepare_recovery(deadline=clock.monotonic() + 2)
            context = adapters.get("context_provider")
            selector = adapters.get("selector")
            if context is None or not getattr(context, "supports_deadlines", False):
                raise CareError("context_adapter_unavailable", 503)
            if selector is not None and not getattr(selector, "supports_deadlines", False):
                raise CareError("model_deadline_unsupported", 503)
            self.harness = CareHarness(run_id, self.storage, context, clock, selector=selector, hooks=hooks)
            self.dispatcher = EffectDispatcher(self.harness, adapters.get("gateway"), adapters.get("gate"))
            self.harness.dispatcher = self.dispatcher
            await self.recover()
            self.health_cache = await self.storage.health_counts(deadline=clock.monotonic() + 2)
            self.ready = True
            if background:
                self.worker = asyncio.create_task(self._work())
            return self
        except BaseException:
            try:
                if self.storage:
                    await self.storage.close(deadline=clock.monotonic() + 2)
            finally:
                if self.lock:
                    self.lock.release()
            raise

    async def recover(self) -> None:
        import json
        now = self.harness.clock.utcnow().timestamp()
        rows = await self.storage.recovery_requests(now, deadline=self.harness.clock.monotonic() + 2)
        for row in rows:
            owner = self.harness.owners.get(row["id"])
            if owner is not None and not owner.done():
                continue
            event = CustomerEvent(**json.loads(row["payload"]))
            try:
                ctx = TrustedRequestContext(row["principal"])
                if event.kind == "open_contact":
                    data = json.loads(event.text)
                    for name in ("assessment_at", "created_at"):
                        data[name] = datetime.fromisoformat(data[name])
                    await self.harness.open_contact(ContactTask(**data),
                        TrustedRequestContext(row["principal"], frozenset({"care_contact"})))
                else:
                    await self.harness._process_event(row["session_id"], event, ctx)
            except CareError:
                # A failed request remains durable; no startup reset or invented success.
                continue

    async def _work(self):
        while not self.closed:
            try:
                await self.recover()
                await self.dispatcher.drain_pending()
            except Exception:
                if "worker_error" not in self.codes:
                    self.codes.append("worker_error")
            await self.harness.clock.wait_until(self.harness.clock.monotonic() + .1)

    def get_health(self) -> Health:
        if self.closed or not self.ready:
            return Health("not_ready", ("not_ready",))
        codes = list(self.codes)
        codes.extend(sorted(self.harness.observer_codes))
        if self.harness.selector is None:
            codes.append("model_unavailable")
        if self.dispatcher.gateway is None:
            codes.append("gateway_unavailable")
        if self.dispatcher.gate is None:
            codes.append("gate_unavailable")
        try:
            if isinstance(self.storage, LocalCareStore):
                pending, unknown = self.storage.cached_local_health()
            else:
                pending, unknown = self.health_cache
        except StorageError:
            return Health("not_ready", ("store_unavailable",))
        return Health("degraded" if codes else "ready", tuple(codes), pending, unknown)

    async def refresh_health(self) -> Health:
        try:
            self.health_cache = await self.storage.health_counts(deadline=self.harness.clock.monotonic() + 2)
        except StorageError:
            return Health("not_ready", ("store_unavailable",))
        return self.get_health()

    async def shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.ready = False
        self.harness.accepting = False
        self.dispatcher.stopping = True
        tasks = {task for task in self.harness.active_tasks if not task.done()}
        if self.worker and not self.worker.done():
            tasks.add(self.worker)
        try:
            if tasks:
                try:
                    await bounded(asyncio.gather(*tasks, return_exceptions=True), self.harness.clock, 5)
                except TimeoutError:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            try:
                await self.storage.close(deadline=self.harness.clock.monotonic() + 2)
            finally:
                if self.lock:
                    self.lock.release()
