"""Conservative Vietnamese intent rules; quoted/reported wishes confer no authority."""
import re
import unicodedata

from care_truc.models import IntentSignals


# A repeated desire/subject starts an independent predicate. Bare coordinated
# verbs remain together, so "khong muon gap va noi chuyen" stays negated.
CLAUSE_BOUNDARY = (
    r'[,;.!?]|\b(?:nhung|tuy nhien)\b|'
    r'\bva\b(?=\s+(?:(?:bay gio|hien tai)\s+)?'
    r'(?:toi\b|muon\b|can\b|yeu cau\b|de nghi\b|xin\b))'
)
REPORTED_WISH = (
    r'\b(tai xe|shipper|nhan vien|ho|anh ay|co ay|anh ta|co ta|'
    r'ong ay|ba ay|ong ta|ba ta|nguoi ta)\s+'
    r'(bao|noi|nhan|yeu cau)\b[^,;.!?]*?'
    r'(?=\b(?:nhung|tuy nhien)\b|\bva\s+(?:(?:bay gio|hien tai)\s+)?toi\b|[,;.!?]|$)'
)
HISTORICAL_WISH = r'\b(da tung|tung|truoc day|truoc kia|hom qua|luc truoc)\b'
COIN_REQUEST = (
    r'\b(xin|muon|yeu cau|cho toi|hay cap|cap cho|de nghi)\b'
    r'.{0,30}\b(xu|coins?)\b'
)
COMPENSATION_REQUEST = (
    r'\b(?:den(?: bu)?|boi thuong)\s+(?:(?:cho toi|cho minh)\s+)?di\b|'
    r'\b(?:yeu cau|de nghi|hay|xin)\s+(?:den(?: bu)?|boi thuong)\b'
)
DELIVERY_QUESTION = (
    r'\bsao\b.{0,35}\b(?:tre|cham|lau)\b|\blau vay\b|'
    r'\bbao gio\s+(?:toi|den|den_arrival|giao)\b|'
    r'\b(?:toi|den|den_arrival)\s+(?:chua|dau)\b|'
    r'\bkip khong\b'
)
POLICY_OR_HYPOTHESIS = (
    r'\b(chinh sach|dieu kien|bao nhieu|neu|gia su|muon hoi|muon biet)\b'
)
# Temporal/conditional scope spans omitted-subject coordination, even across a
# comma. A new customer subject starts an independent assertion; negation keeps
# its narrower predicate scope below.
REQUEST_SCOPE_BOUNDARY = (
    r'(?:[,;.!?]|\b(?:va|nhung|tuy nhien)\b)\s*'
    r'(?=(?:(?:bay gio|hien tai)\s+)?toi\b)'
)


def _normalize(text: str) -> str:
    # Arrival and compensation are distinct words even though accent folding
    # turns both into "den". Preserve explicit arrival before folding accents.
    composed = unicodedata.normalize('NFC', text.lower())
    composed = re.sub(r'\bđến\b', 'den_arrival', composed)
    decomposed = unicodedata.normalize('NFD', composed.replace('đ', 'd'))
    plain = ''.join(char for char in decomposed if unicodedata.category(char) != 'Mn')
    # Whole-token substitutions only: negation slang must remain negation.
    aliases = {'ko': 'khong', 'k': 'khong', 'khum': 'khong', 'hok': 'khong',
               'chx': 'chua', 'dc': 'duoc', 'j': 'gi', 'v': 'vay', 'z': 'vay'}
    return re.sub(r'\b\w+\b', lambda match: aliases.get(match[0], match[0]), plain)


def _current_compensation_request(scope: str, clause: str) -> bool:
    """An inquiry or a request for another benefit cannot authorize coins."""
    if re.search(r'\b(?:hom truoc|hom kia|da (?:noi|bao|nhan|yeu cau|de nghi))\b', scope):
        return False
    if '?' in scope or re.search(
        r'\b(?:voucher|hoan tien|giam gia|gi|sao|khong|chua|dung)\b', clause,
    ):
        return False
    return bool(re.search(COMPENSATION_REQUEST, clause))


def classify(text: str) -> IntentSignals:
    normalized = _normalize(text)
    abusive = bool(re.search(r'\b(ngu|con me|dit|khon nan|fuck)\b', normalized))
    own = re.sub(r'"[^"\n]*"|“[^”\n]*”|\x27[^\x27\n]*\x27', ' ', normalized)
    # Reporting spans coordinated wishes with an omitted subject. Only a
    # contrast, explicit new customer subject, or sentence boundary ends it.
    own = re.sub(REPORTED_WISH, ' ', own)
    clauses = re.split(CLAUSE_BOUNDARY, own)
    retract = any(
        re.search(r'\b(khong|dung|thoi)\b.{0,18}\bhuy\b|\bbo yeu cau huy\b', clause)
        for clause in clauses
    )
    positive = []
    for clause in clauses:
        # Negation applies to this predicate only. Independent later requests
        # have already been separated, including those joined by "va".
        positive.append(re.sub(r'\b(khong|chua|dung)\b.*', ' ', clause))
    active = ' '.join(positive)
    human = bool(re.search(
        r'\b(gap|noi chuyen|chuyen|ket noi)\b.{0,25}'
        r'\b(nhan vien|nguoi that|nguoi|tu van vien|human)\b', active,
    ))
    question = bool(re.search(
        r'\b(tai sao|vi sao|chinh sach|bao nhieu|the nao|dieu kien|ly do|why)\b', active,
    )) or bool(re.search(DELIVERY_QUESTION, own))
    coins = any(
        not re.search(POLICY_OR_HYPOTHESIS, scope)
        and not re.search(HISTORICAL_WISH, scope)
        and any(re.search(COIN_REQUEST, re.sub(r'\b(khong|chua|dung)\b.*', ' ', clause))
                or _current_compensation_request(scope, clause)
                for clause in re.split(CLAUSE_BOUNDARY, scope))
        for scope in re.split(REQUEST_SCOPE_BOUNDARY, own)
    )
    cancel = bool(re.search(
        r'\b(muon|yeu cau|hay|xin|cho toi)\b.{0,20}\bhuy\b|\bhuy don\b', active,
    ))
    more = coins or bool(re.search(
        r'\b(ho tro|boi thuong|den bu|them|giup|voucher|giam gia|hoan tien)\b', active,
    )) or (
        not re.search(r'\b(chinh sach|dieu kien)\b', active)
        and bool(re.search(r'\b(xu|coins?)\b', active))
    ) or (
        not re.search(DELIVERY_QUESTION, own)
        and bool(re.search(r'\bden\b', active))
    )
    accept = is_cancel_confirmation(text) or bool(re.search(
        r'\b(dong y|chap nhan|cam on|ok|duoc|vang)\b', active,
    ))
    if human:
        intent = 'ask_human'
    elif cancel:
        intent = 'want_cancel'
    elif more:
        intent = 'want_more'
    elif question:
        intent = 'ask_why'
    elif abusive:
        intent = 'unreasonable_abusive'
    elif accept:
        intent = 'accept'
    else:
        intent = 'off_topic'
    return IntentSignals(intent, abusive, coins, retract)


def is_cancel_confirmation(text: str) -> bool:
    """Only a complete current affirmative statement grants cancellation consent."""
    return bool(re.fullmatch(
        r'(?:(?:toi|minh)\s+)?(?:dong y|chap nhan|ok|vang|xac nhan|chac chan|chac|u|co)'
        r'(?:\s+(?:huy(?:\s+don(?:\s+hang)?)?|yeu cau huy))?(?:\s+a)?',
        _normalize(text).strip().rstrip('.!').strip(),
    ))
