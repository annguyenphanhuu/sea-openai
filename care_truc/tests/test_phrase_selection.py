import asyncio
from dataclasses import replace
import json
import pytest

from care_truc.phrases import build_model_context, select_phrase
from care_truc.runtime_types import AttemptToken, CustomerEvent
from care_truc.policy import CarePolicy
from .helpers import FakeClock, BlockingSelector, context
from .test_policy import state


@pytest.mark.parametrize('raw', [b'{"phrase_id":"unknown"}',b'{"text":"999 xu"}',
    b'{"phrase_id":"explain","tools":[]}',b'not json', b'x'*2049])
def test_invalid_output_falls_back(raw):
    class Selector:
        supports_deadlines=True
        async def select(self,context,*,deadline): return raw
    result=asyncio.run(select_phrase(Selector(),b'{}',('explain',),AttemptToken('r',0,0),FakeClock()))
    assert result.source=='template'
    assert result.codes==('model_output_rejected',)


def test_context_pruning_does_not_modify_history():
    out=CarePolicy().evaluate(state(),CustomerEvent('message','r','tại sao'),context())
    history=['old']*5+['new']
    result=build_model_context(out,context(),history)
    assert len(json.loads(result)['history'])==4
    assert len(history)==6
    assert 'ledger' not in result.decode()
    huge=replace(out,codes=('😀'*4000,))
    assert build_model_context(huge,context(),history) is None


def test_model_timeout_uses_operational_clock():
    async def check():
        clock=FakeClock(); selector=BlockingSelector()
        task=asyncio.create_task(select_phrase(selector,b'{}',('explain',),AttemptToken('r',0,0),clock))
        await selector.started.wait()
        clock.advance(3)
        result=await task
        assert result.source=='template'
        assert result.codes==('model_timeout',)
        selector.release.set()
    asyncio.run(check())
