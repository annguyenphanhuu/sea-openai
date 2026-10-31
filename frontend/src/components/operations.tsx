"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@fluentui/react-components";
import { ArrowClockwise, ArrowRight, Clock, Play, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { commandSchema, requestChat, requestRuntime, type Command, type Runtime, type PendingTurn } from "@/lib/runtime";
import { feedLabels, formatDate, sourceLabels, statusLabels } from "@/lib/presentation";
import { Shell, type View } from "./shell";
import { CareConversation, LogisticsDetail, OrderBrowser, Status } from "./workspace";

type Load = { kind: "loading" } | { kind: "ready"; value: Runtime } | { kind: "error"; message: string };
type MobilePane = { kind: "list" } | { kind: "detail" };
const titles: Record<View, { title: string; subtitle: string }> = {
    overview: { title: "Tổng quan vận hành", subtitle: "Từ dữ liệu đáng tin đến bước chăm sóc phù hợp." },
    logistics: { title: "Đánh giá đơn hàng", subtitle: "Ngày cam kết, mức rủi ro và căn cứ của từng đơn." },
    care: { title: "Chăm sóc khách hàng", subtitle: "Chọn đơn cần hỗ trợ và tiếp tục hội thoại." },
    guard: { title: "Giám sát dữ liệu", subtitle: "Kiểm tra nguồn dữ liệu trước khi chủ động liên hệ." },
};

export function Operations() {
    const [view, setView] = useState<View>("care");
    const [load, setLoad] = useState<Load>({ kind: "loading" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [text, setText] = useState("");
    const [pendingTurn, setPendingTurn] = useState<PendingTurn | null>(null);
    const [pane, setPane] = useState<MobilePane>({ kind: "list" });
    const mutationLock = useRef(false);
    const pendingMessage = useRef<Extract<Command, { kind: "say" }> | null>(null);
    useEffect(() => {
        let active = true;
        async function start() {
            try {
                try {
                    const cached = sessionStorage.getItem("cho-pho-pending-turn");
                    if (cached) {
                        const command = commandSchema.safeParse(JSON.parse(cached));
                        if (command.success && command.data.kind === "say") {
                            pendingMessage.current = command.data;
                            setPendingTurn({ command: command.data, status: "uncertain", reply: null, restored: true });
                            setPane({ kind: "detail" });
                        }
                    }
                } catch { pendingMessage.current = null; }
                let value = await requestRuntime(pendingMessage.current ? { session_id: pendingMessage.current.session_id } : undefined);
                const session = value.active_chats.find(item => item.status === "active");
                if (!value.chat && session && !pendingMessage.current) value = await requestRuntime({ session_id: session.session_id });
                if (active) setLoad({ kind: "ready", value });
            } catch (error) {
                if (active) setLoad({ kind: "error", message: error instanceof Error ? error.message : "Không thể tải dữ liệu." });
            }
        }
        start();
        return () => { active = false; };
    }, []);
    async function reload() {
        if (mutationLock.current) return;
        mutationLock.current = true;
        setBusy(true); setError("");
        try {
            const value = await requestRuntime(pendingMessage.current ? { session_id: pendingMessage.current.session_id } : undefined);
            setLoad({ kind: "ready", value });
            setPendingTurn(current => current ? { ...current, restored: true } : current);
        } catch (error) {
            setLoad({ kind: "error", message: error instanceof Error ? error.message : "Không thể tải dữ liệu." });
        } finally { mutationLock.current = false; setBusy(false); }
    }
    async function run(input?: Command | { order_id?: string; session_id?: string }) {
        if (mutationLock.current) return false;
        if (pendingMessage.current) { setError("Yêu cầu trước chưa rõ kết quả. Gửi lại cùng yêu cầu trong hội thoại để đối soát."); return false; }
        mutationLock.current = true;
        setBusy(true); setError("");
        try {
            const value = await requestRuntime(input);
            setLoad({ kind: "ready", value });
            return true;
        } catch (error) {
            setError(error instanceof Error ? error.message : "Không thể thực hiện yêu cầu.");
            return false;
        } finally { mutationLock.current = false; setBusy(false); }
    }
    const value = load.kind === "ready" ? load.value : null;
    const order = value?.orders.find(item => item.order_id === value.selected_order_id) ?? value?.orders[0];
    const careOrder = value?.chat ? value.orders.find(item => item.order_id === value.chat?.order_id) : order;
    function navigate(next: View) { setView(next); setPane({ kind: next === "care" && pendingMessage.current ? "detail" : "list" }); }
    async function select(input: { order_id: string } | { session_id: string }) {
        if (pendingMessage.current && (("session_id" in input && input.session_id === pendingMessage.current.session_id)
                || ("order_id" in input && input.order_id === value?.chat?.order_id))) { setPane({ kind: "detail" }); return; }
        if (await run(input)) { setPane({ kind: "detail" }); if (!pendingMessage.current) setText(""); }
    }
    async function say(message: string, reply_to?: string) {
        if (!value?.chat) return;
        const previous = pendingMessage.current;
        if (previous && (previous.session_id !== value.chat.session_id || previous.text !== message || previous.reply_to !== reply_to)) {
            setError("Tin nhắn trước chưa rõ kết quả. Gửi lại đúng nội dung để đối soát trước khi gửi nội dung mới.");
            return;
        }
        const command = previous ?? { kind: "say", session_id: value.chat.session_id, text: message, request_id: crypto.randomUUID(), ...(reply_to ? { reply_to } : {}) };
        if (mutationLock.current) return;
        try { sessionStorage.setItem("cho-pho-pending-turn", JSON.stringify(command)); }
        catch { setError("Không lưu được khóa gửi lại an toàn trong phiên trình duyệt."); return; }
        pendingMessage.current = command;
        mutationLock.current = true;
        setBusy(true); setError(""); setText("");
        setPendingTurn(current => ({ command, status: "sending", reply: null, restored: current?.restored ?? false }));
        try {
            const snapshot = await requestChat(command, event => {
                if (event.kind === "reply") setPendingTurn(current => current ? { ...current, reply: { id: event.message_id, text: event.text } } : current);
            });
            setLoad({ kind: "ready", value: snapshot });
            pendingMessage.current = null;
            setPendingTurn(null);
            try { sessionStorage.removeItem("cho-pho-pending-turn"); } catch { /* A committed reply remains successful; replay uses the same stored key. */ }
        } catch (error) {
            setError(error instanceof Error ? error.message : "Chưa xác nhận được kết quả gửi.");
            setPendingTurn(current => current ? { ...current, status: "uncertain", reply: null } : current);
        } finally { mutationLock.current = false; setBusy(false); }
    }
    function openCare() { setView("care"); setPane({ kind: "detail" }); }
    return <Shell view={view} onView={navigate}>
        <div className="page-heading"><div><h1>{titles[view].title}</h1><p>{titles[view].subtitle}</p></div><div className="header-actions"><Button appearance="subtle" icon={<ArrowClockwise size={17} />} disabled={busy} onClick={() => reload()} aria-label="Tải lại dữ liệu">Tải lại</Button><Button appearance="primary" icon={<Play size={16} weight="fill" />} disabled={busy || !value} onClick={() => run({ kind: "next" })}>Chạy tiếp +30 phút</Button></div></div>
        {load.kind === "loading" && <div className="loading-state" role="status"><span className="loading-dot" />Đang tải phòng điều hành…</div>}
        {load.kind === "error" && <div className="panel error-state" role="alert"><WarningCircle size={32} /><h2>Chưa thể kết nối hệ thống</h2><p>{load.message}</p><Button disabled={busy} onClick={() => reload()}>Thử lại</Button></div>}
        {error && <div className="inline-error" role="alert">{error}</div>}
        {value && <><div className="runtime-bar"><span className="replay-clock"><Clock size={15} />Mô phỏng <strong>{formatDate(value.now, true)}</strong></span><button className={`health-badge ${value.proactive_allowed ? "health-good" : "health-blocked"}`} onClick={() => navigate("guard")}>{value.proactive_allowed ? <ShieldCheck size={15} /> : <WarningCircle size={15} />}{value.proactive_allowed ? "Nguồn đã xác minh" : "Đang chặn liên hệ chủ động"}</button><details className="llm-badge"><summary><span className={`status-dot ${value.llm?.enabled ? "" : "dot-muted"}`} />{value.llm?.enabled ? "AI đang bật" : "Chế độ quy tắc"}</summary><div><p>Model: {value.llm?.model ?? "Chưa cấu hình"}</p><p>{value.inside ? value.inside.used_llm ? "Lượt vừa rồi có sử dụng OpenAI." : "Lượt vừa rồi dùng quy tắc hoặc câu dự phòng." : "AI diễn đạt hội thoại. Dữ kiện và quyền thực thi do hệ thống kiểm soát."}</p></div></details>{busy && <span className="busy-label" role="status">Đang xử lý...</span>}</div>
            {!value.proactive_allowed && <div className="blocking-notice" role="status"><WarningCircle size={17} /><span>{!value.orders_total ? "Chưa chạy bước mô phỏng. Chọn Chạy tiếp +30 phút để đánh giá dữ liệu." : "A3 đang chặn liên hệ chủ động. Hội thoại hiện có vẫn có thể được hỗ trợ theo quyền của phiên."}</span></div>}
            {(view === "care" || view === "logistics") && <div className={`workspace-layout ${pane.kind === "detail" ? "mobile-detail" : "mobile-list"}`}><OrderBrowser value={value} order={view === "care" ? careOrder : order} busy={busy} onOrder={id => select({ order_id: id })} onSession={id => { setView("care"); select({ session_id: id }); }} />{view === "care" ? <CareConversation pendingTurn={pendingTurn} value={value} order={careOrder} busy={busy} text={text} setText={setText} onSay={say} onOpen={id => run({ kind: "open", order_id: id })} onBack={() => setPane({ kind: "list" })} /> : <LogisticsDetail order={order} onCare={openCare} onBack={() => setPane({ kind: "list" })} />}</div>}
            {view === "overview" && <><section className="overview-metrics" aria-label="Kết quả vận hành">{[["Đơn đã đánh giá", value.orders_total], ["Đơn trong hàng đợi liên hệ", value.contact_queue_total], ["Hội thoại đang xử lý", value.active_chats.length], ["Bản ghi xu local", value.ledger_total]].map(([label, count]) => <div key={label}><span>{label}</span><strong>{count.toLocaleString("vi-VN")}</strong></div>)}</section><div className="overview-grid"><section className="panel overview-priorities"><div className="section-heading"><div><span className="eyebrow">BƯỚC TIẾP THEO</span><h2>Đơn cần chú ý</h2></div><Button appearance="subtle" onClick={() => navigate("logistics")}>Xem đánh giá <ArrowRight size={15} /></Button></div>{value.orders.slice(0, 5).map(item => <button className="priority-row" key={item.order_id} onClick={async () => { if (await run({ order_id: item.order_id })) openCare(); }} disabled={busy}><strong>{item.order_id}</strong><Status order={item} /><span>{item.late_days > 0 ? `Trễ ${item.late_days} ngày` : `Cam kết ${formatDate(item.guaranteed_date)}`}</span><ArrowRight size={17} /></button>)}{!value.orders.length && <div className="empty-content"><p>Chạy bước mô phỏng để bắt đầu đánh giá đơn hàng.</p></div>}</section><section className="panel process-summary"><span className="eyebrow">LUỒNG ĐANG CHẠY</span><h2>Dữ liệu trước, chăm sóc sau</h2><ol><li><b>A3</b><div><strong>Kiểm tra nguồn</strong><p>Xác minh nguồn dữ liệu và điều kiện liên hệ.</p></div></li><li><b>A2</b><div><strong>Đánh giá đơn</strong><p>Ưu tiên rủi ro theo bằng chứng đã có.</p></div></li><li><b>A1</b><div><strong>Hỗ trợ khách hàng</strong><p>Giải thích, tiếp nhận nhu cầu và bàn giao khi cần.</p></div></li></ol><p className="muted">{value.phase_trace.length ? `Bước gần nhất hoàn tất theo thứ tự ${value.phase_trace.join(" → ")}.` : "Chưa có bước mô phỏng nào được chạy."}</p><Button appearance="primary" onClick={() => navigate("care")}>Mở màn chăm sóc</Button></section></div></>}
            {view === "guard" && <section className="panel guard-workspace"><div className="section-heading"><div><span className="eyebrow">A3 · GIÁM SÁT</span><h2>Chất lượng nguồn dữ liệu</h2><p>{value.guard_alive ? "Nhịp giám sát đang hoạt động." : "Chưa có nhịp giám sát còn hiệu lực."} Bật lại A3 cần chạy bước tiếp để cập nhật.</p></div><div className="header-actions"><Button disabled={busy} onClick={() => run({ kind: "kill" })}>Dừng A3</Button><Button appearance="primary" disabled={busy} onClick={() => run({ kind: "revive" })}>Bật lại A3</Button></div></div><div className="feed-table"><div className="feed-row feed-heading"><span>Nguồn</span><span>Trạng thái</span><span>Dấu thời gian nguồn</span></div>{value.feed_health.map(feed => <div className="feed-row" key={feed.feed}><strong>{sourceLabels[feed.feed] ?? "Nguồn dữ liệu bổ sung"}</strong><span className={`order-status ${feed.status === "trusted" ? "status-on_track" : "status-unknown_feed"}`}>{feedLabels[feed.status] ?? "Cần kiểm tra"}</span><time>{formatDate(feed.source_timestamp, true)}</time></div>)}</div><div className="guard-distribution"><h3>Phân bố trạng thái đơn</h3><div>{statusesForCounts(value).map(([status, count]) => <p key={status}><span>{status}</span><strong>{count}</strong></p>)}</div></div><details className="technical-details"><summary>Chi tiết kỹ thuật nguồn</summary><pre>{JSON.stringify(value.feed_health, null, 2)}</pre></details></section>}
            <details className="runtime-records"><summary>Bản ghi thực thi và chi tiết kỹ thuật</summary><p>{value.outbox_total} yêu cầu · {value.handoffs.length} lượt bàn giao · {value.ledger_total} bản ghi xu local. Đây là kết quả trong phiên mô phỏng, không phải thanh toán ví bên ngoài.</p><pre>{JSON.stringify({ ledger: value.ledger, outbox: value.outbox, cancellations: value.cancellations, handoffs: value.handoffs }, null, 2)}</pre></details>
        </>}
    </Shell>;
}
function statusesForCounts(value: Runtime) {
    return Object.entries(statusLabels).map(([status, label]) => [label, value.label_counts[status] ?? 0] satisfies [string, number]);
}
