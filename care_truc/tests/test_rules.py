import pytest
from care_truc.rules import classify

@pytest.mark.parametrize('text,intent,coins,retracted', [
 ('Tôi muốn hủy đơn','want_cancel',False,False),
 ('tôi không muốn hủy','off_topic',False,True),
 ('tài xế bảo tôi hủy','off_topic',False,False),
 ('"tôi muốn hủy"','off_topic',False,False),
 ('Chính sách xu là gì?','ask_why',False,False),
 ('Tôi muốn nhận xu','want_more',True,False),
 ('Tôi không muốn nhận xu','off_topic',False,False),
 ('Tôi cần hỗ trợ','want_more',False,False),
 ('Tại sao trễ?','ask_why',False,False),
 ('đồng ý','accept',False,False),
 ('xin chào','off_topic',False,False),
 ('đồ ngu','unreasonable_abusive',False,False),
 ('đồ ngu, cho tôi gặp nhân viên','ask_human',False,False),
 ('không hủy nữa, tôi muốn nhận xu','want_more',True,True),
 ('tai xe bao toi huy nhung toi muon huy don','want_cancel',False,False),
])
def test_rules(text,intent,coins,retracted):
    result=classify(text)
    assert (result.intent,result.explicit_coins,result.cancel_retracted)==(intent,coins,retracted)

def test_human_preserves_abuse_and_normalization():
    import unicodedata
    result=classify(unicodedata.normalize('NFD','ĐỒ NGU, tôi muốn gặp người thật'))
    assert result.intent=='ask_human' and result.abusive

@pytest.mark.parametrize('text,coins',[
 ('Chính sách xu thế nào? Tôi muốn nhận xu',True),
 ('Tài xế nói tôi muốn nhận xu',False),
 ('Nếu tôi muốn nhận xu thì sao?',False),
 ('“Tôi muốn nhận xu” là lời tài xế',False),
 ('Tôi cần hỗ trợ bồi thường',False),
])
def test_coin_request_is_independent_of_generic_intent(text,coins):
    assert classify(text).explicit_coins is coins

@pytest.mark.parametrize('text',['Tôi muốn hỏi có nhận xu được không?', 'Nhân viên bảo tôi muốn nhận xu'])
def test_policy_or_reported_request_not_explicit(text):
    assert not classify(text).explicit_coins

@pytest.mark.parametrize('text', [
    'tôi chưa nhận được hàng và muốn gặp nhân viên',
    'toi chua nhan duoc hang va muon gap nhan vien',
    'Tôi không muốn hủy và tôi muốn gặp nhân viên',
])
def test_independent_human_request_survives_negated_other_predicate(text):
    assert classify(text).intent == 'ask_human'


@pytest.mark.parametrize('text', [
    'Tôi không muốn gặp nhân viên',
    'toi chua muon gap nhan vien',
    'Tôi không muốn gặp và nói chuyện với nhân viên',
])
def test_negated_human_request_is_not_handoff(text):
    assert classify(text).intent != 'ask_human'


@pytest.mark.parametrize('text,explicit', [
    ('tôi đã từng muốn nhận xu', False),
    ('toi da tung muon nhan xu', False),
    ('trước đây tôi muốn nhận xu', False),
    ('Hôm qua tôi muốn nhận xu', False),
    ('Tôi đã từng muốn nhận xu nhưng bây giờ tôi muốn nhận xu', True),
    ('toi da tung muon nhan xu va toi muon nhan xu', True),
    ('Tài xế nói tôi muốn nhận xu nhưng tôi không muốn nhận xu', False),
])
def test_only_present_independent_coin_request_is_explicit(text, explicit):
    assert classify(text).explicit_coins is explicit

@pytest.mark.parametrize('text', [
    'Tai xe noi toi muon huy va muon nhan xu',
    'Tài xế nói tôi muốn hủy và muốn nhận xu',
])
def test_coordinated_reported_coin_wish_not_explicit(text):
    assert not classify(text).explicit_coins


@pytest.mark.parametrize('text', [
    'Tai xe noi toi muon huy va muon gap nhan vien',
    'Tài xế nói tôi muốn hủy và muốn gặp nhân viên',
])
def test_coordinated_reported_human_wish_not_handoff(text):
    assert classify(text).intent != 'ask_human'


@pytest.mark.parametrize('text,intent,coins', [
    ('Tai xe noi toi muon huy nhung toi muon nhan xu', 'want_more', True),
    ('Tai xe noi toi muon huy va toi muon gap nhan vien', 'ask_human', False),
    ('Tài xế nói tôi muốn hủy nhưng tôi muốn gặp nhân viên', 'ask_human', False),
])
def test_new_customer_predicate_ends_reporting_scope(text, intent, coins):
    result = classify(text)
    assert result.intent == intent and result.explicit_coins is coins

@pytest.mark.parametrize('text,intent,coins', [
    ('Tai xe noi toi muon huy va bay gio toi muon gap nhan vien', 'ask_human', False),
    ('Tai xe noi toi muon huy va hien tai toi muon nhan xu', 'want_more', True),
    ('Tài xế nói tôi muốn hủy và bây giờ tôi muốn gặp nhân viên', 'ask_human', False),
    ('Tài xế nói tôi muốn hủy và hiện tại tôi muốn nhận xu', 'want_more', True),
])
def test_temporal_modifier_before_new_customer_subject(text, intent, coins):
    result = classify(text)
    assert result.intent == intent and result.explicit_coins is coins


@pytest.mark.parametrize('text', [
    'Tai xe noi toi muon huy va bay gio muon gap nhan vien',
    'Tai xe noi toi muon huy va hien tai muon nhan xu',
])
def test_temporal_modifier_without_new_subject_stays_reported(text):
    result = classify(text)
    assert result.intent != 'ask_human' and not result.explicit_coins
