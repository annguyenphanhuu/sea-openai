from dataclasses import replace
from datetime import timedelta
import pytest

from care_truc.guardrails import Guardrails
from care_truc.renderer import ResponseRenderer
from care_truc.policy import CarePolicy
from care_truc.runtime_types import CustomerEvent
from .helpers import context, NOW
from .test_policy import state


@pytest.mark.parametrize('minutes,allowed', [(30,True),(30.000001,False),(-1,False)])
def test_freshness_boundaries(minutes,allowed):
    ctx = context()
    feed = replace(ctx.guard.feeds[0], source_timestamp=NOW-timedelta(minutes=minutes))
    assert Guardrails().proactive(replace(ctx, guard=replace(ctx.guard, feeds=(feed,)))).allowed == allowed


@pytest.mark.parametrize('minutes,allowed', [(60,True),(60.000001,False),(-1,False)])
def test_heartbeat_boundaries(minutes,allowed):
    ctx = context()
    assert Guardrails().proactive(replace(ctx, guard=replace(ctx.guard, heartbeat=NOW-timedelta(minutes=minutes)))).allowed == allowed


def test_invalid_context_never_grants_authority():
    ctx = context()
    for bad in (replace(ctx,guard=None), replace(ctx,assessment=None),
                replace(ctx,assessment=replace(ctx.assessment,assessed_at=NOW+timedelta(seconds=1))),
                replace(ctx,assessment=replace(ctx.assessment,assessed_at=NOW-timedelta(minutes=31)))):
        assert not Guardrails().validate_context(bad).allowed
        out = CarePolicy().evaluate(state(),CustomerEvent('request_handoff','h'),bad)
        assert out.state.status == 'handoff_pending'


def test_renderer_does_not_invent_eta_or_expose_raw_text():
    ctx=context()
    out=CarePolicy().evaluate(state(),CustomerEvent('message','m','tại sao secret phone driver'),ctx)
    rendered=ResponseRenderer().render(out,ctx,'explain')
    assert 'chưa xác định' in rendered.text
    assert 'secret' not in rendered.text
    assert Guardrails().validate_output(rendered,out,ctx).allowed
    assert not Guardrails().validate_output(replace(rendered,text='đã cấp 999999 xu'),out,ctx).allowed
