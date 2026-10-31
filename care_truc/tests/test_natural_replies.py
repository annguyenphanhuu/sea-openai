import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import time

import httpx
import pytest

from care_truc.guardrails import Guardrails
from care_truc.natural import build_natural_context, render_template, reply_topic
from care_truc.openai_selector import OpenAIPhraseSelector
from care_truc.policy import CarePolicy
from care_truc.renderer import ResponseRenderer
from care_truc.runtime_types import CustomerEvent, NaturalDraft
from .helpers import CUSTOMER, context, NOW
from .test_policy import state
from .test_turn_loop import harness


def test_greeting_uses_natural_model_text_instead_of_clarification(tmp_path):
    class NaturalSelector:
        supports_deadlines = True
        natural_replies = True
        async def select(self, context, *, deadline):
            return json.dumps({'template': 'Chào bạn! Mình có thể hỗ trợ gì cho bạn?'}).encode()
    async def check():
        h = harness(tmp_path, selector=NaturalSelector())
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        reply = await h.handle_message(sid, 'hello', 'Xin chào', CUSTOMER)
        assert reply.source == 'model-generated'
        assert reply.text == 'Chào bạn! Mình có thể hỗ trợ gì cho bạn?'
        assert not reply.effect_ids
        h.store.close()
    asyncio.run(check())

@pytest.mark.parametrize('question,topic', [
    ('Khi nào giao hàng cho tôi?', 'eta'),
    ('Bao giờ tôi nhận được hàng?', 'eta'),
    ('Ngày giao dự kiến là ngày nào?', 'eta'),
    ('Đơn hàng của tôi đang ở đâu?', 'location'),
    ('Bạn giải thích rõ hơn được không?', 'explanation'),
    ('Xin chào', 'greeting'), ('Cảm ơn bạn', 'thanks'),
])
def test_topic_uses_actual_question_even_when_generic_intent(question, topic):
    assert reply_topic(question, 'off_topic') == topic


@pytest.mark.parametrize('text', [
    'Ngày mai bạn nhận hàng. {eta}',
    'Ngày 01/11/2026 bạn nhận hàng. {eta}',
    'Mình sẽ giao đúng hẹn. {eta}',
    'Đã cấp chín trăm xu. {eta}',
    'Đơn đang ở kho Hà Nội. {eta}',
    'Đơn bị thất lạc do tài xế. {eta}',
    'Mình cam kết miễn phí. {eta}',
    'Bạn nhận hàng vào thứ hai. {eta}',
    'Bạn nhận hàng tối nay. {eta}',
    'Bạn nhận hàng vào buổi chiều. {eta}',
    'Bạn yên tâm, mọi thứ bình thường. {eta}',
    'Bạn được tặng một triệu đồng. {eta}',
    'Kiện ở Hà Nội. {eta}',
    'Bạn nhận hàng sáng mốt. {eta}',
    'Thông tin này sai: {eta}',
    'Cảm ơn {eta} bạn',
    '{eta} {unknown}', '{status}', '{eta} {eta}',
])
def test_model_cannot_write_facts_or_remove_required_slot(text):
    with pytest.raises(ValueError):
        render_template(NaturalDraft('eta', text), context())


def test_actual_assessed_eta_is_inserted_by_code_not_model():
    ctx = context()
    ctx = replace(ctx, assessment=replace(ctx.assessment, revised_eta=NOW + timedelta(days=1)))
    text = render_template(NaturalDraft('eta', 'Mình hiểu cảm giác chờ đợi của bạn. {eta}'), ctx)
    assert '01/11/2026 19:00' in text
    assert 'chưa phải cam kết giao mới' in text
    stale = replace(ctx, guard=None)
    text = render_template(NaturalDraft('eta', '{eta}'), stale)
    assert 'chưa được xác minh' in text and '01/11/2026' not in text


def test_location_never_invents_source_location():
    assert 'chưa có vị trí hiện tại đã được xác minh' in render_template(NaturalDraft('location', '{location}'), context())


def test_whitespace_cannot_become_an_empty_reply():
    with pytest.raises(ValueError, match='natural_empty_reply'):
        render_template(NaturalDraft('help', '   '), context())


def test_natural_context_contains_latest_and_both_history_roles_without_evidence():
    ctx = context()
    out = CarePolicy().evaluate(state(), CustomerEvent('message', 'new', 'Bao giờ nhận hàng?'), ctx)
    payload = json.loads(build_natural_context(out, ctx, [
        {'role': 'user', 'text': 'Số 0901234567 và a@example.com'},
        {'role': 'assistant', 'text': 'Bạn cần hỗ trợ gì?'},
    ], 'Bao giờ nhận hàng?'))
    assert payload['customer_message'] == 'Bao giờ nhận hàng?'
    assert [item['role'] for item in payload['history']] == ['user', 'assistant']
    assert '0901234567' not in str(payload) and 'a@example.com' not in str(payload)
    assert 'record_id' not in str(payload) and 'principal' not in str(payload)


def test_guard_rejects_tampering_of_grounded_rendered_text():
    ctx = context()
    out = CarePolicy().evaluate(state(), CustomerEvent('message', 'new', 'Bao giờ nhận hàng?'), ctx)
    draft = NaturalDraft('eta', 'Mình hiểu băn khoăn của bạn. {eta}')
    rendered = ResponseRenderer().render(out, ctx, out.phrase_id, draft=draft)
    assert Guardrails().validate_output(rendered, out, ctx).allowed
    assert not Guardrails().validate_output(replace(rendered, text='Ngày mai chắc chắn nhận hàng'), out, ctx).allowed


@pytest.mark.parametrize('question', ['Tôi muốn gặp nhân viên', 'Tôi muốn hủy đơn', 'Tôi xin xu'])
def test_transactional_outcomes_do_not_call_natural_model(tmp_path, question):
    class NeverSelector:
        supports_deadlines = True
        natural_replies = True
        async def select(self, *args, **kwargs):
            raise AssertionError('transactional_model_called')
    async def check():
        h = harness(tmp_path, selector=NeverSelector())
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        reply = await h.handle_message(sid, 'action', question, CUSTOMER)
        assert reply.source == 'template'
        assert not any(code.startswith('model_') for code in reply.codes)
        h.store.close()
    asyncio.run(check())


def test_openai_natural_schema_and_current_context():
    def handler(request):
        payload = json.loads(request.content)
        assert payload['response_format']['json_schema']['schema']['required'] == ['segments']
        assert payload['max_completion_tokens'] == 300
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'segments': ['Chào bạn!', 'Mình có thể hỗ trợ gì cho bạn?']})}}]})
    async def check():
        selector = OpenAIPhraseSelector('test-key', transport=httpx.MockTransport(handler))
        out = CarePolicy().evaluate(state(), CustomerEvent('message', 'm', 'Xin chào'), context())
        payload = build_natural_context(out, context(), [], 'Xin chào')
        result = await selector.select(payload, deadline=time.monotonic() + 8)
        assert json.loads(result)['template'].startswith('Chào bạn')
    asyncio.run(check())


def test_openai_natural_schema_constrains_each_segment_to_social_or_fact_reference():
    def handler(request):
        payload = json.loads(request.content)
        choices = payload['response_format']['json_schema']['schema']['properties']['segments']['items']['enum']
        assert '{eta}' in choices
        assert 'Mình hiểu băn khoăn của bạn.' in choices
        assert 'Bạn được tặng một triệu đồng.' not in choices
        assert not any('chính sách' in choice for choice in choices)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'segments': ['Bạn được tặng một triệu đồng.', '{eta}']})}}]})

    async def check():
        selector = OpenAIPhraseSelector('test-key', transport=httpx.MockTransport(handler))
        out = CarePolicy().evaluate(state(), CustomerEvent('message', 'm', 'Bao giờ nhận hàng?'), context())
        payload = build_natural_context(out, context(), [], 'Bao giờ nhận hàng?')
        with pytest.raises(ValueError, match='model_template_rejected'):
            await selector.select(payload, deadline=time.monotonic() + 8)
    asyncio.run(check())


def test_rejected_model_falls_back_to_question_specific_grounded_answer(tmp_path):
    class UnsafeSelector:
        supports_deadlines = True
        natural_replies = True
        async def select(self, *args, **kwargs):
            return json.dumps({'template': 'Ngày mai nhận hàng. {eta}'}).encode()
    async def check():
        h = harness(tmp_path, selector=UnsafeSelector())
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        reply = await h.handle_message(sid, 'eta', 'Khi nào giao hàng?', CUSTOMER)
        assert reply.source == 'template' and 'model_output_rejected' in reply.codes
        assert 'chưa có thời gian giao dự kiến' in reply.text
        assert 'nói rõ nhu cầu' not in reply.text
        h.store.close()
    asyncio.run(check())


def test_missing_assessment_validation_codes_return_truthful_natural_facts(tmp_path):
    class GroundedSelector:
        supports_deadlines = True
        natural_replies = True
        async def select(self, *args, **kwargs):
            return json.dumps({'template': 'Mình hiểu băn khoăn của bạn. {eta}'}).encode()
    async def check():
        h = harness(tmp_path, selector=GroundedSelector())
        h.context_provider.snapshot = replace(context(), assessment=None, validation_codes=('assessment_unavailable',))
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        reply = await h.handle_message(sid, 'eta', 'Bao giờ nhận hàng?', CUSTOMER)
        assert reply.source == 'model-generated'
        assert 'assessment_unavailable' in reply.codes
        assert 'Dự báo giao hàng hiện chưa được xác minh' in reply.text
        assert not reply.effect_ids
        h.store.close()
    asyncio.run(check())


def test_model_cannot_change_server_topic_to_skip_required_facts(tmp_path):
    class MaliciousSelector:
        supports_deadlines = True
        natural_replies = True
        async def select(self, *args, **kwargs):
            return json.dumps({'template': 'Chào bạn!', 'topic': 'greeting'}).encode()
    async def check():
        h = harness(tmp_path, selector=MaliciousSelector())
        sid = (await h.open_chat('o1', 'open', CUSTOMER)).session_id
        reply = await h.handle_message(sid, 'eta', 'Khi nào giao hàng?', CUSTOMER)
        assert reply.source == 'template' and 'model_output_rejected' in reply.codes
        assert 'chưa có thời gian giao dự kiến' in reply.text
        h.store.close()
    asyncio.run(check())


@pytest.mark.parametrize('template', [
    'Bạn được tặng một triệu đồng. {eta}',
    'Kiện ở Hà Nội. {eta}',
    'Bạn nhận hàng sáng mốt. {eta}',
    'Thông tin này sai: {eta}',
])
def test_guard_rejects_unsupported_literal_claims(template):
    ctx = context()
    out = CarePolicy().evaluate(state(), CustomerEvent('message', 'eta', 'Khi nào giao hàng?'), ctx)
    original = ResponseRenderer().render(out, ctx, out.phrase_id)
    malicious = replace(original, text='claim', draft=NaturalDraft('eta', template))
    assert not Guardrails().validate_output(malicious, out, ctx).allowed
