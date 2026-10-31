import asyncio
from datetime import datetime, timezone

import pytest

from care_truc.runtime_types import CustomerEvent, TrustedRequestContext, canonical, fingerprint
from care_truc.ports import SystemClock


def test_untrusted_payload_cannot_build_trusted_context():
    with pytest.raises(TypeError):
        TrustedRequestContext(principal_id="c", source="a1")
    with pytest.raises(ValueError):
        CustomerEvent("message", "r", "x" * 4001)
    assert len(CustomerEvent("message", "r", "😀" * 4000).text) == 4000


def test_shared_types_are_reused():
    from care_truc.runtime_types import Action, OrderAssessment, ContactTask
    import contracts.types as shared
    assert Action is shared.Action
    assert OrderAssessment is shared.OrderAssessment
    assert ContactTask is shared.ContactTask
    assert fingerprint({"b": 1, "a": 2}) == fingerprint({"a": 2, "b": 1})
    assert fingerprint({"text": "a"}) != fingerprint({"text": "b"})


def test_clock_is_independent_of_replay():
    async def check():
        clock = SystemClock()
        before = clock.monotonic()
        await clock.wait_until(before)
        assert clock.monotonic() >= before
        assert clock.utcnow().tzinfo is not None
    asyncio.run(check())
