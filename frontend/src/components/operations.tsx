"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Input, Textarea } from "@fluentui/react-components";
import { requestRuntime, statusLabels, type Command, type Runtime } from "@/lib/runtime";
import { Shell, type View } from "./shell";

type Load = { kind: "loading" } | { kind: "ready"; value: Runtime } | { kind: "error"; message: string };
const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" }) : "Chưa có dữ liệu";

export function Operations() {
    const [view, setView] = useState<View>("overview");
    const [load, setLoad] = useState<Load>({ kind: "loading" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [query, setQuery] = useState("");
    const [text, setText] = useState("");
    const sequence = useRef(0);
    const mutationLock = useRef(false);
    const pendingMessage = useRef<Extract<Command, { kind: "say" }> | null>(null);
    useEffect(() => {
        let active = true;
        requestRuntime().then(value => { if (active) setLoad({ kind: "ready", value }); })
            .catch(error => { if (active) setLoad({ kind: "error", message: error instanceof Error ? error.message : "Không thể tải dữ liệu." }); });
        return () => { active = false; };
    }, []);
    async function run(input?: Command | { order_id?: string; session_id?: string }) {
        if (mutationLock.current) return;
        mutationLock.current = true;
        const request = ++sequence.current;
        setBusy(true); setError("");
        try {
            const value = await requestRuntime(input);
            if (request === sequence.current) setLoad({ kind: "ready", value });
            return true;
        } catch (error) {
            setError(error instanceof Error ? error.message : "Không thể thực hiện yêu cầu.");
            return false;
        } finally { mutationLock.current = false; setBusy(false); }
    }
    const value = load.kind === "ready" ? load.value : null;
    const order = value?.orders.find(item => item.order_id === value.selected_order_id);
    const rows = value?.orders.filter(item => item.order_id.toLowerCase().includes(query.toLowerCase())) ?? [];
    async function say(message: string, reply_to?: string) {
        if (!value?.chat) return;
        const previous = pendingMessage.current;
        if (previous && (previous.session_id !== value.chat.session_id || previous.text !== message || previous.reply_to !== reply_to)) {
            setError("Tin nhắn trước chưa rõ kết quả. Gửi lại đúng nội dung để đối soát trước khi gửi nội dung mới.");
            return;
        }
        const command = previous ?? { kind: "say", session_id: value.chat.session_id, text: message, request_id: crypto.randomUUID(), ...(reply_to ? { reply_to } : {}) };
        pendingMessage.current = command;
        if (await run(command)) { setText(""); pendingMessage.current = null; }
    }
    return <Shell view={view} onView={setView}>
        <div className="page-heading"><div><div className="page-kicker">CHỢ PHỐ CARE</div><h1>Phòng điều hành tích hợp.</h1><p>Dữ liệu replay → A3 → A2 → A1. Tin nhắn và hành động được lưu trong phiên local.</p></div><div className="runtime-buttons"><Button disabled={busy} onClick={() => run()}>Tải lại dữ liệu</Button><Button appearance="primary" disabled={busy || !value} onClick={() => run({ kind: "next" })}>NEXT +30 phút</Button></div></div>
        {load.kind === "loading" && <p role="status">Đang kết nối pipeline...</p>}
        {load.kind === "error" && <div className="panel error-state" role="alert"><h2>Chưa thể tải phòng điều hành</h2><p>{load.message}</p><Button disabled={busy} onClick={() => run()}>Thử lại</Button></div>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        {busy && <p role="status">Đang xử lý...</p>}
        {value?.llm && <p role="status">LLM A1 {value.llm.enabled ? `đã bật · ${value.llm.model}` : "chưa bật"}. {value.inside ? value.inside.used_llm ? "Lượt vừa rồi dùng OpenAI diễn đạt câu trả lời." : "Lượt vừa rồi dùng rules/template." : "Model diễn đạt hội thoại; dữ kiện và quyền thực thi do code kiểm soát."}</p>}
        {value && <>
            <div className={`guard-banner ${value.proactive_allowed ? "" : "guard-failure"}`} role="status"><div><strong>{value.proactive_allowed ? "A3 cho phép kiểm tra liên hệ chủ động" : "A3 đang chặn liên hệ chủ động"}</strong><p>{date(value.now)} · {value.phase_trace.join(" → ") || "Chưa chạy tick. Nhấn NEXT để đánh giá dữ liệu."}</p></div></div>
            <section className="metrics-strip" aria-label="Tổng quan runtime">{[["Đơn đã đánh giá", value.orders_total], ["Hàng đợi liên hệ", value.contact_queue_total], ["Phiên chat đang mở", value.active_chats.length], ["Bản ghi xu local", value.ledger_total]].map(([label, count]) => <div className="metric" key={label}><div className="metric-label">{label}</div><strong>{count}</strong></div>)}</section>
            {view === "guard" ? <section className="panel guard-details"><h2>Giám sát A3</h2><p>Heartbeat {value.guard_alive ? "đang hoạt động" : "không hoạt động"}. Bật lại A3 cần NEXT để cập nhật nhịp.</p><div className="runtime-buttons"><Button disabled={busy} onClick={() => run({ kind: "kill" })}>Dừng A3</Button><Button disabled={busy} onClick={() => run({ kind: "revive" })}>Bật lại A3</Button></div><h3>Nguồn dữ liệu</h3>{value.feed_health.map(feed => <p key={feed.feed}>{feed.feed} · {feed.status} · {date(feed.source_timestamp)}</p>)}<h3>Phân bố đánh giá A2</h3><pre>{JSON.stringify(value.label_counts, null, 2)}</pre></section> : <div className="operations-grid">
                <section className="panel order-panel" aria-label="Danh sách đơn hàng"><div className="panel-heading"><div><h2>Hàng đợi liên hệ A2</h2><p>{value.orders.length} đơn đang hiển thị trên {value.orders_total} đơn đã đánh giá.</p></div></div><div className="list-tools"><Input aria-label="Tìm đơn hàng" placeholder="Tìm mã đơn..." value={query} onChange={(_, data) => setQuery(data.value)} /></div><div className="order-rows">{rows.map(item => <button key={item.order_id} disabled={busy} className={`order-row ${item.order_id === order?.order_id ? "is-selected" : ""}`} onClick={() => run({ order_id: item.order_id })} aria-label={`Xem đơn ${item.order_id}`}><strong>{item.order_id}</strong><span className={`order-status status-${item.status}`}>{statusLabels[item.status]}</span><span>{item.guaranteed_date}</span><span>{Math.round(item.late_probability * 100)}%</span></button>)}</div>{!rows.length && <div className="empty-state">Chưa có đơn trong hàng đợi. Chạy NEXT hoặc tìm mã khác.</div>}<div className="list-footer">Hàng đợi ưu tiên từ backend, tối đa 30 đơn và đơn đang chọn.</div><div className="list-tools"><h3>Phiên đang mở</h3>{value.active_chats.map(chat => <Button key={chat.session_id} disabled={busy} onClick={() => run({ session_id: chat.session_id })}>{chat.order_id} · {chat.status}</Button>)}</div></section>
                <section className="panel runtime-detail" aria-label="Chi tiết đơn hàng"><div className="detail-heading"><h2>{order?.order_id ?? "Chọn đơn hàng"}</h2>{order && <p>{statusLabels[order.status]} · Bên có lỗi {order.fault_party}</p>}</div>{order && <div className="detail-body"><dl className="date-grid"><div><dt>Ngày cam kết</dt><dd>{order.guaranteed_date}</dd></div><div><dt>ETA mới</dt><dd>{date(order.revised_eta)}</dd></div><div><dt>Ngày đặt</dt><dd>{date(order.created_at)}</dd></div><div><dt>Bàn giao hãng</dt><dd>{date(order.handed_over_at)}</dd></div></dl><p>{order.late_days} ngày trễ · Độ tin {Math.round(order.confidence * 100)}%</p><p>{order.reason_codes.join(" · ")}</p><details><summary>Bằng chứng A2</summary><pre>{JSON.stringify(order.evidence, null, 2)}</pre></details><Button disabled={busy || !value.proactive_allowed || !!value.chat} onClick={() => run({ kind: "open", order_id: order.order_id })}>Mở chat A1</Button></div>}
                    <div className="detail-body"><h3>Hội thoại A1</h3>{value.chat ? <><p>Phiên {value.chat.session_id} · {value.chat.status}</p><div className="runtime-messages" aria-live="polite">{value.chat.messages.map(message => <div className="message-bubble" key={message.id}><small>{message.kind === "customer" ? "Khách" : "A1"}</small><p>{message.text}</p></div>)}</div><form onSubmit={event => { event.preventDefault(); say(text); }}><label htmlFor="customer-text">Tin nhắn khách trong phiên local</label><Textarea id="customer-text" value={text} disabled={busy || value.chat.status === "transferred"} onChange={(_, data) => setText(data.value)} /><div className="runtime-buttons"><Button type="submit" appearance="primary" disabled={busy || !text.trim() || value.chat.status === "transferred"}>Gửi text</Button><Button disabled={busy || value.chat.status === "transferred"} onClick={() => say("Tôi muốn gặp nhân viên")}>Yêu cầu gặp nhân viên</Button>{value.chat.pending && <Button disabled={busy} onClick={() => say("Đồng ý", value.chat?.pending?.reply_to)}>Xác nhận yêu cầu hủy</Button>}</div></form></> : <p>Chưa mở phiên. NEXT tự mở các liên hệ đủ điều kiện qua A1.</p>}</div>
                </section>
            </div>}
            <details className="demo-controls"><summary>Bản ghi thực thi local</summary><p>{value.outbox_total} outbox · {value.handoffs.length} chuyển nhân viên. Ledger local không phải thanh toán vào ví bên ngoài. Hủy cần xác nhận lại và chờ duyệt.</p><pre>{JSON.stringify({ ledger: value.ledger, outbox: value.outbox, cancellations: value.cancellations, handoffs: value.handoffs }, null, 2)}</pre></details>
        </>}
    </Shell>;
}
