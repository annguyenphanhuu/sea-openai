import asyncio
import pytest

from care_truc.hooks import RuntimeHooks, bounded
from care_truc.runtime_types import HookDecision
from .helpers import FakeClock


@pytest.mark.parametrize('phase,action', [('on_input','veto'),('before_model','use_fallback'),
    ('after_model','use_fallback'),('before_action','veto'),('after_action','continue'),('on_error','continue')])
def test_hook_failures_have_phase_specific_result(phase,action):
    async def fail(data):
        raise ValueError('secret')
    async def check():
        hooks=RuntimeHooks({phase:(fail,)},FakeClock())
        result=await hooks.run(phase,{'nested':{'x':1}})
        assert result.action == action
        assert result.codes == ('hook_failed',)
    asyncio.run(check())


def test_hook_order_veto_and_immutable_input():
    async def check():
        seen=[]
        async def veto(data):
            seen.append(1)
            with pytest.raises(TypeError):
                data['nested']['x']=2
            return HookDecision('veto')
        async def later(data):
            seen.append(2)
            return HookDecision()
        registry={'on_input':(veto,later)}
        hooks=RuntimeHooks(registry,FakeClock())
        registry.clear()
        result=await hooks.run('on_input',{'nested':{'x':1}})
        assert result.action=='veto'
        assert seen==[1,2]
    asyncio.run(check())


def test_phase_timeout_is_total_and_late_completion_is_ignored():
    async def check():
        clock=FakeClock()
        started=asyncio.Event()
        async def stuck(data):
            started.set()
            await asyncio.Event().wait()
        task=asyncio.create_task(RuntimeHooks({'before_action':(stuck,)},clock).run('before_action',{}))
        await started.wait()
        clock.advance(.101)
        assert (await task).action=='veto'
    asyncio.run(check())
