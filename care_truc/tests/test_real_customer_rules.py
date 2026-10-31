"""Real customer language must not weaken effect authorization boundaries."""
import pytest

from care_truc.rules import classify, is_cancel_confirmation


@pytest.mark.parametrize('text,intent,explicit', [
    ('sao đơn tôi trễ vậy', 'ask_why', False),
    ('có đền gì không', 'want_more', False),
    ('đền đi', 'want_more', True),
    ('chắc', 'accept', False),
    ('SAO DON TOI TRE VAY', 'ask_why', False),
    ('sao đơn tôi trễ z', 'ask_why', False),
    ('sao don toi tre v', 'ask_why', False),
    ('lâu vậy', 'ask_why', False),
    ('lau vay', 'ask_why', False),
    ('bao giờ tới', 'ask_why', False),
    ('bao gio toi', 'ask_why', False),
    ('tới chưa', 'ask_why', False),
    ('toi chx', 'ask_why', False),
    ('đến đâu', 'ask_why', False),
    ('den dau', 'ask_why', False),
    ('kịp không', 'ask_why', False),
    ('kip ko', 'ask_why', False),
    ('co den j ko', 'want_more', False),
    ('có đền bù gì khum', 'want_more', False),
    ('bồi thường thế nào', 'want_more', False),
    ('có voucher không', 'want_more', False),
    ('có xu ko', 'want_more', False),
    ('có giảm giá không', 'want_more', False),
    ('hoàn tiền được không', 'want_more', False),
    ('DEN DI', 'want_more', True),
    ('đền bù đi', 'want_more', True),
    ('bồi thường đi', 'want_more', True),
    ('CHAC', 'accept', False),
    ('chắc chắn', 'accept', False),
    ('ừ', 'accept', False),
    ('có', 'accept', False),
])
def test_real_customer_intents(text, intent, explicit):
    signals = classify(text)
    assert signals.intent == intent
    assert signals.explicit_coins is explicit


@pytest.mark.parametrize('text', [
    'chắc', 'CHAC', 'chắc chắn', 'chac chan', 'ừ', 'u', 'có', 'co',
    'đồng ý', 'dong y', 'ok', 'OK!',
])
def test_complete_affirmative_can_be_checked_against_pending_prompt(text):
    assert is_cancel_confirmation(text) is True


@pytest.mark.parametrize('text', [
    'không chắc', 'ko chac', 'chưa chắc', 'chắc không', 'chắc?',
    'tài xế nói chắc', '"chắc"', 'hôm qua tôi chắc', 'nếu chắc thì sao',
    'có đền gì không', 'có voucher không', 'không đồng ý',
])
def test_ambiguous_or_scoped_affirmative_is_not_confirmation(text):
    assert is_cancel_confirmation(text) is False


@pytest.mark.parametrize('text', [
    'không đền đi', 'ko den di', 'chưa muốn đền bù',
    'tài xế nói đền đi', 'nhân viên bảo đền đi', '"đền đi"',
    'nếu đền đi thì sao', 'giả sử đền đi', 'hôm qua đền đi',
    'trước đây đền đi', 'có đền gì không', 'đền đi được không',
    'đền voucher đi', 'hoàn tiền đi', 'xin voucher',
    'Nếu tôi muốn hỗ trợ thêm và đền đi',
    'Trước đây tôi muốn hỗ trợ thêm, đền đi',
])
def test_non_current_or_non_coin_request_never_authorizes_coins(text):
    assert classify(text).explicit_coins is False


@pytest.mark.parametrize('text', [
    'đến đi', 'hãy đến', 'xin đến', 'ĐẾN ĐI', 'đến đi',
    'anh ta nói đền đi', 'anh ta noi den di', 'cô ta nói đền đi',
    'ông ấy nói đền đi', 'bà ấy nói đền đi', 'người ta nói đền đi',
    'tai xe nhan den di', 'tài xế nhắn đền đi',
    'hom truoc toi da noi den di', 'toi da noi den di',
    'hôm trước tôi đã nói đền đi', 'tôi đã nói đền đi',
])
def test_arrival_or_reported_demand_never_authorizes_compensation(text):
    assert classify(text).explicit_coins is False


@pytest.mark.parametrize('text', [
    'đền đi', 'den di', 'ĐỀN ĐI', 'đền đi',
    'anh ta nói hãy đến nhưng tôi yêu cầu đền bù',
    'anh ta nói đền đi nhưng tôi yêu cầu đền bù',
    'hàng chưa đến, tôi yêu cầu đền bù',
])
def test_current_compensation_stays_independent_of_arrival_or_reporting(text):
    assert classify(text).explicit_coins is True
