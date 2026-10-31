"""Approved phrase catalog. Models choose IDs, never facts or promises."""

CATALOG = {
    "explain": "Mình ghi nhận tình trạng đơn hàng.",
    "explain_alt": "Mình xin thông tin về đơn hàng như sau.",
    "clarify": "Bạn có thể nói rõ nhu cầu hoặc yêu cầu gặp nhân viên.",
    "confirm": "Bạn vui lòng xác nhận lại yêu cầu hủy. Đây chưa phải kết quả hủy đơn.",
    "pending": "Mình đã ghi nhận yêu cầu. Hiện chưa có xác nhận thực hiện.",
    "handoff": "Mình đã ghi nhận nhu cầu gặp nhân viên. Hiện chưa có xác nhận chuyển thành công.",
    "changed_mind": "Mình đã ghi nhận thay đổi. Yêu cầu đã bắt đầu gửi vẫn có thể đang chờ kết quả.",
    "ineligible": "Hiện chưa đủ điều kiện hoặc thông tin để tạo yêu cầu xu.",
    "blocked": "Hiện chưa thể xử lý yêu cầu này.",
}


def allowed_ids(outcome) -> tuple[str, ...]:
    return ("explain", "explain_alt") if outcome.phrase_id == "explain" else (outcome.phrase_id,)
