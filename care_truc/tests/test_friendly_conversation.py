"""Conversation improvements preserve authoritative facts and action boundaries."""

import asyncio
from dataclasses import replace
from datetime import timedelta
import json
import time

import httpx

from care_truc.natural import build_natural_context, fact_slots, render_template, social_sentence
from care_truc.openai_selector import OpenAIPhraseSelector
from care_truc.policy import CarePolicy
from care_truc.runtime_types import CustomerEvent, NaturalDraft
from .helpers import context, NOW
from .test_policy import state


def test_eta_answers_arrival_before_history_and_preserves_uncertainty():
    from .test_grounded_journey import snapshot
    ctx = snapshot()
    ctx = replace(ctx, assessment=replace(ctx.assessment, revised_eta=ctx.cutoff + timedelta(hours=2)))
    text = fact_slots(ctx, 'eta')['eta']
    assert text.startswith('Bạn dự kiến nhận được hàng vào')
    assert text.index('chưa phải cam kết giao mới') < text.index('đang hoàn trả')
    assert '3 lần giao chưa thành công' in text


def test_repeated_social_opening_is_not_offered_but_direct_facts_are():
    def handler(request):
        payload = json.loads(request.content)
        choices = payload['response_format']['json_schema']['schema']['properties']['segments']['items']['enum']
        assert 'Mình hiểu băn khoăn của bạn.' not in choices
        assert 'Bạn cần hỗ trợ gì thêm không?' not in choices
        assert '{eta}' in choices
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps({'segments': ['{eta}']})}}]})

    async def check():
        ctx = context()
        outcome = CarePolicy().evaluate(state(), CustomerEvent('message', 'eta', 'Khi nào nhận được hàng?'), ctx)
        payload = build_natural_context(outcome, ctx, [{'role': 'assistant',
            'text': 'Mình hiểu băn khoăn của bạn. Bạn cần hỗ trợ gì thêm không?'}], 'Khi nào nhận được hàng?')
        selector = OpenAIPhraseSelector('test', transport=httpx.MockTransport(handler))
        reply = json.loads(await selector.select(payload, deadline=time.monotonic() + 8))
        text = render_template(NaturalDraft('eta', reply['template']), ctx)
        assert text == fact_slots(ctx, 'eta')['eta']
    asyncio.run(check())


def test_customer_address_is_not_automatically_a_question():
    assert social_sentence('Bạn cứ chia sẻ nếu cần hỗ trợ thêm nhé').endswith('.')
    assert social_sentence('Bạn muốn mình giải thích thêm phần nào').endswith('?')


def test_friendly_eta_still_hides_stale_forecast():
    ctx = context()
    ctx = replace(ctx, guard=None, assessment=replace(ctx.assessment, revised_eta=NOW + timedelta(days=1)))
    text = render_template(NaturalDraft('eta', 'Mình nói rõ hơn để bạn dễ theo dõi nhé. {eta}'), ctx)
    assert 'chưa được xác minh' in text
    assert '01/11/2026' not in text


def test_thanks_can_end_without_another_sales_question():
    from care_truc.natural import fallback_draft
    text = render_template(fallback_draft('thanks'), context())
    assert '?' not in text
    assert 'cứ nhắn nhé' in text
