"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Input, Textarea } from "@fluentui/react-components";
import { ArrowLeft, ArrowRight, MagnifyingGlass, PaperPlaneTilt, ShieldCheck, WarningCircle, ChatCircleText, CaretRight } from "@phosphor-icons/react";
import type { PendingTurn, Runtime } from "@/lib/runtime";
import { faultLabels, formatDate, isTerminal, percent, reasons, sessionLabel, statuses, statusLabels, type Order } from "@/lib/presentation";

export function Status({ order }: { order: Order }) { return <span className={`order-status status-${order.status}`}>{statusLabels[order.status]}</span>; }

export function OrderFacts({ order }: { order: Order }) {
    return <><dl className="fact-grid"><div><dt>Ngày cam kết</dt><dd>{formatDate(order.guaranteed_date)}</dd></div><div><dt>Giao dự kiến</dt><dd>{formatDate(order.revised_eta, true)}</dd></div><div><dt>Ngày đặt hàng</dt><dd>{formatDate(order.created_at)}</dd></div><div><dt>Bàn giao vận chuyển</dt><dd>{formatDate(order.handed_over_at, true)}</dd></div><div><dt>Nguy cơ trễ</dt><dd>{percent(order.late_probability)}</dd></div><div><dt>Độ tin cậy đánh giá</dt><dd>{percent(order.confidence)}</dd></div></dl><div className="reason-list">{reasons(order).map(reason => <p key={reason}>{reason}</p>)}</div><p className="muted">Bên được đánh giá có lỗi: {faultLabels[order.fault_party] ?? "Chưa đủ căn cứ"}.</p><details className="technical-details"><summary>Bằng chứng và chi tiết kỹ thuật</summary><p>Mã lý do do A2 cung cấp.</p><pre>{JSON.stringify({ reason_codes: order.reason_codes, evidence: order.evidence }, null, 2)}</pre></details></>;
}

export function OrderBrowser({ value, order, busy, onOrder, onSession }: {
    value: Runtime; order: Order | undefined; busy: boolean; onOrder: (id: string) => void; onSession: (id: string) => void;
}) {
    const [tab, setTab] = useState<"orders" | "sessions">("orders");
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState("all");
    const [page, setPage] = useState(0);
    const matches = value.orders.filter(item => item.order_id.toLowerCase().includes(query.toLowerCase()) && (filter === "all" || item.status === filter));
    const sessions = value.active_chats.filter(item => item.order_id.toLowerCase().includes(query.toLowerCase()));
    const count = tab === "orders" ? matches.length : sessions.length;
    const maxPage = Math.max(0, Math.ceil(count / 8) - 1);
    const current = Math.min(page, maxPage);
    const pageOrders = matches.slice(current * 8, (current + 1) * 8);
    const pageSessions = sessions.slice(current * 8, (current + 1) * 8);
    return <section className="panel browser-panel" aria-label="Danh sách công việc"><div className="browser-tabs" role="tablist" aria-label="Nguồn công việc"><button role="tab" aria-selected={tab === "orders"} onClick={() => { setTab("orders"); setPage(0); }}>Đơn ưu tiên <span>{value.orders.length}</span></button><button role="tab" aria-selected={tab === "sessions"} onClick={() => { setTab("sessions"); setPage(0); }}>Hội thoại <span>{value.active_chats.length}</span></button></div><div className="browser-tools"><Input contentBefore={<MagnifyingGlass size={17} />} aria-label={tab === "orders" ? "Tìm đơn hàng" : "Tìm hội thoại"} placeholder="Tìm theo mã đơn" value={query} onChange={(_, data) => { setQuery(data.value); setPage(0); }} />{tab === "orders" && <select aria-label="Lọc trạng thái đơn" value={filter} onChange={event => { setFilter(event.target.value); setPage(0); }}><option value="all">Tất cả trạng thái</option>{statuses.map(status => <option key={status} value={status}>{statusLabels[status]}</option>)}</select>}</div><div className="browser-scroll" role="tabpanel" aria-label={tab === "orders" ? "Đơn ưu tiên" : "Hội thoại"}>{tab === "orders" ? <><div className="compact-table-heading"><span>Mã đơn / Trạng thái</span><span>Cam kết / Nguy cơ trễ</span></div>{pageOrders.map(item => <button key={item.order_id} className={`work-row ${item.order_id === order?.order_id ? "is-selected" : ""}`} disabled={busy} aria-label={`Xem đơn ${item.order_id}`} onClick={() => onOrder(item.order_id)}><div><strong>{item.order_id}</strong><Status order={item} /></div><div className="work-row-data"><time>{formatDate(item.guaranteed_date)}</time><span>Nguy cơ trễ <b>{percent(item.late_probability)}</b></span></div><CaretRight size={15} className="work-row-arrow" /></button>)}</> : pageSessions.map(session => <button key={session.session_id} className={`work-row session-row ${session.session_id === value.chat?.session_id ? "is-selected" : ""}`} disabled={busy} aria-label={`Mở hội thoại đơn ${session.order_id}`} onClick={() => onSession(session.session_id)}><div><strong>{session.order_id}</strong><span className="session-state">{sessionLabel(session.status)}</span></div><ChatCircleText size={19} /></button>)}{!count && <div className="empty-content"><MagnifyingGlass size={28} /><p>Không có kết quả phù hợp.</p><small>Thử mã khác hoặc đổi bộ lọc.</small></div>}</div><div className="pagination"><span>{count ? current * 8 + 1 : 0}–{Math.min((current + 1) * 8, count)} / {count}</span><div><Button size="small" icon={<ArrowLeft size={15} />} aria-label="Trang trước" disabled={current === 0} onClick={() => setPage(current - 1)} /><Button size="small" icon={<ArrowRight size={15} />} aria-label="Trang sau" disabled={current === maxPage} onClick={() => setPage(current + 1)} /></div></div><p className="queue-scope">{tab === "orders" ? `Danh sách ưu tiên từ A2, hiển thị ${value.orders.length} / ${value.orders_total} đơn đã đánh giá.` : "Chọn một phiên để xem lịch sử và tiếp tục xử lý."}</p></section>;
}

export function CareConversation({ pendingTurn, value, order, busy, text, setText, onSay, onOpen, onBack }: {
    pendingTurn: PendingTurn | null; value: Runtime; order: Order | undefined; busy: boolean; text: string; setText: (value: string) => void;
    onSay: (text: string, replyTo?: string) => void; onOpen: (id: string) => void; onBack: () => void;
}) {
    const messages = useRef<HTMLDivElement>(null);
    const chat = value.chat;
    const delivery = pendingTurn?.command.session_id === chat?.session_id ? pendingTurn : null;
    useEffect(() => {
        const element = messages.current;
        if (!element) return;
        const showLatest = () => { element.scrollTop = element.scrollHeight; };
        showLatest();
        const observer = new ResizeObserver(showLatest);
        observer.observe(element);
        return () => observer.disconnect();
    }, [chat?.session_id, chat?.messages.length, delivery?.status, delivery?.reply, delivery?.command.request_id]);
    const terminal = chat ? isTerminal(chat.status) : false;
    const locked = busy || terminal || delivery?.status === "uncertain";
    return <section className="panel conversation-panel" aria-label="Hội thoại chăm sóc"><div className="conversation-heading"><Button className="mobile-back" size="small" icon={<ArrowLeft size={16} />} onClick={onBack}>Danh sách</Button><div><span className="eyebrow">CHĂM SÓC KHÁCH HÀNG</span><h2>{order?.order_id ?? chat?.order_id ?? "Chọn một đơn để bắt đầu"}</h2></div>{order && <Status order={order} />}</div>{order && <div className="order-summary"><span>Cam kết <b>{formatDate(order.guaranteed_date)}</b></span><span>Dự kiến <b>{formatDate(order.revised_eta, true)}</b></span><details><summary>Thông tin đơn</summary><OrderFacts order={order} /></details></div>}{chat ? <><div className={`chat-state ${terminal ? "chat-state-closed" : ""}`}><span className="status-dot" /><span>{sessionLabel(chat.status)}</span>{terminal && <small>{chat.status === "transferred" ? "Nhân viên tiếp nhận từ đây. Bạn có thể chọn hội thoại khác trong danh sách." : chat.status === "handoff_pending" ? "Đang chờ nhân viên tiếp nhận. Không gửi thêm yêu cầu trong lúc bàn giao." : "Phiên này đã kết thúc. Chọn hội thoại khác để tiếp tục."}</small>}</div><div className="conversation-messages" ref={messages} aria-live="polite" aria-label="Lịch sử hội thoại">{chat.messages.map(message => <div className={`chat-message ${message.kind === "customer" ? "message-customer" : message.kind === "response" ? "message-assistant" : "message-system"}`} key={message.id}><small>{message.kind === "customer" ? "Khách hàng" : message.kind === "response" ? "Trợ lý A1" : "Hệ thống"}</small><p>{message.text}</p></div>)}{delivery && <>
                {!delivery.restored && <div className="chat-message message-customer" data-delivery={delivery.status}><small>Khách hàng · {delivery.status === "uncertain" ? "Chưa xác nhận kết quả" : "Đang gửi"}</small><p>{delivery.command.text}</p></div>}
                {delivery.reply && <div className="chat-message message-assistant"><small>Trợ lý A1 · Đang xác nhận</small><p>{delivery.reply.text}</p></div>}
                {delivery.status === "uncertain" ? <div className="delivery-uncertain" role="status"><p>Chưa xác nhận được kết quả. Gửi lại cùng yêu cầu để kiểm tra, không tạo lượt mới.</p>{delivery.restored && !chat.messages.some(message => message.kind === "customer" && message.text.trim() === delivery.command.text.trim()) && <p>{delivery.command.text}</p>}<Button disabled={busy} onClick={() => onSay(delivery.command.text, delivery.command.reply_to)}>Gửi lại cùng yêu cầu</Button></div> : !delivery.reply && <p className="reply-pending" role="status">A1 đang xử lý và kiểm tra câu trả lời…</p>}
            </>}{busy && !delivery && <p className="reply-pending" role="status">Đang xử lý yêu cầu…</p>}</div><form className="chat-composer" onSubmit={event => { event.preventDefault(); if (text.trim() && !locked) onSay(text); }}><label htmlFor="customer-text">Tin nhắn khách trong phiên local</label><Textarea onKeyDown={event => {
            if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return;
            event.preventDefault();
            if (!locked && text.trim()) event.currentTarget.closest("form")?.requestSubmit();
        }} id="customer-text" placeholder={terminal ? "Phiên không còn nhận tin nhắn" : "Nhập câu hỏi hoặc yêu cầu của khách…"} value={text} disabled={locked} onChange={(_, data) => setText(data.value)} /><div className="composer-actions"><Button appearance="subtle" size="small" disabled={locked} onClick={() => onSay("Tôi muốn gặp nhân viên")}>Yêu cầu gặp nhân viên</Button>{chat.pending && <Button disabled={locked} onClick={() => onSay("Đồng ý", chat.pending?.reply_to)}>Xác nhận yêu cầu hủy</Button>}<Button appearance="primary" icon={<PaperPlaneTilt size={16} />} type="submit" disabled={locked || !text.trim()}>Gửi text</Button></div></form></> : <div className="empty-content conversation-empty"><ChatCircleText size={38} /><h3>{order ? "Đơn này chưa có hội thoại" : "Hội thoại xuất hiện tại đây"}</h3><p>{order ? "Mở chat khi đơn đủ điều kiện liên hệ chủ động." : "Chọn đơn ưu tiên hoặc một phiên trong danh sách bên trái."}</p>{order && <><Button appearance="primary" disabled={busy || !value.proactive_allowed} onClick={() => onOpen(order.order_id)}>Mở chat A1</Button>{!value.proactive_allowed && <p className="muted">A3 đang chặn liên hệ chủ động. Kiểm tra nguồn dữ liệu ở màn Giám sát.</p>}</>}</div>}<details className="chat-technical"><summary>Chi tiết kỹ thuật phiên</summary><p>Mã phiên: {chat?.session_id ?? "Chưa có"}</p><p>Phản hồi gần nhất: {value.inside ? value.inside.used_llm ? "Có sử dụng OpenAI" : "Rules / template" : "Chưa có thông tin lượt trả lời"}.</p>{value.inside?.codes.length ? <pre>{JSON.stringify(value.inside.codes, null, 2)}</pre> : null}</details></section>;
}

export function LogisticsDetail({ order, onCare, onBack }: { order: Order | undefined; onCare: () => void; onBack: () => void }) {
    return <section className="panel logistics-detail"><div className="section-heading"><Button className="mobile-back" icon={<ArrowLeft size={16} />} size="small" onClick={onBack}>Danh sách</Button><div><span className="eyebrow">ĐÁNH GIÁ LOGISTICS</span><h2>{order?.order_id ?? "Chọn đơn để xem đánh giá"}</h2></div>{order && <Status order={order} />}</div>{order ? <div className="assessment-content"><OrderFacts order={order} /><p className="assessment-note"><ShieldCheck size={17} /> Ngày dự kiến không thay thế ngày giao cam kết.</p><Button appearance="primary" onClick={onCare}>Mở màn chăm sóc <ArrowRight size={16} /></Button></div> : <div className="empty-content"><WarningCircle size={32} /><p>Chọn một đơn trong danh sách ưu tiên.</p></div>}</section>;
}
