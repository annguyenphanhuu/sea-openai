"""Conservative Vietnamese intent rules; quoted/reported wishes confer no authority."""
import re
import unicodedata
from care_truc.models import IntentSignals


def _normalize(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')


def classify(text: str) -> IntentSignals:
    normalized=_normalize(text)
    abusive=bool(re.search(r'\b(ngu|con me|dit|khon nan|fuck)\b',normalized))
    own=re.sub(r'"[^"\n]*"|“[^”\n]*”|\x27[^\x27\n]*\x27',' ',normalized)
    # Reported speech ends at a contrast, punctuation, or a new independent clause.
    own=re.sub(r'\b(tai xe|shipper|nhan vien|ho|anh ay|co ay)\s+(bao|noi|yeu cau)[^,;.!?]*?(?=\bnhung\b|[,;.!?]|$)',' ',own)
    clauses=re.split(r'[,;.!?]|\b(?:nhung|tuy nhien)\b',own)
    retract=any(re.search(r'\b(khong|dung|thoi)\b.{0,18}\bhuy\b|\bbo yeu cau huy\b',c) for c in clauses)
    positive=[]
    for clause in clauses:
        # Exclude negated desires, rather than finding their embedded keywords.
        positive.append(re.sub(r'\b(khong|chua|dung)\b[^,;.!?]*',' ',clause))
    active=' '.join(positive)
    human=bool(re.search(r'\b(gap|noi chuyen|chuyen|ket noi)\b.{0,25}\b(nhan vien|nguoi that|nguoi|tu van vien|human)\b',active))
    question=bool(re.search(r'\b(tai sao|vi sao|chinh sach|bao nhieu|the nao|dieu kien|ly do|why)\b',active))
    coins=any(bool(re.search(r'\b(xin|muon|yeu cau|cho toi|hay cap|cap cho|de nghi)\b.{0,30}\b(xu|coins?)\b',c)) and not re.search(r'\b(chinh sach|dieu kien|bao nhieu|neu|gia su|muon hoi|muon biet)\b',c) for c in positive)
    cancel=bool(re.search(r'\b(muon|yeu cau|hay|xin|cho toi)\b.{0,20}\bhuy\b|\bhuy don\b',active))
    more=coins or bool(re.search(r'\b(ho tro|boi thuong|den bu|them|giup)\b',active))
    accept=bool(re.search(r'\b(dong y|chap nhan|cam on|ok|duoc|vang)\b',active))
    intent=('ask_human' if human else 'want_cancel' if cancel else 'want_more' if more else
            'ask_why' if question else 'unreasonable_abusive' if abusive else 'accept' if accept else 'off_topic')
    return IntentSignals(intent,abusive,coins,retract)
