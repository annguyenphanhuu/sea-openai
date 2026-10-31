"use client";

import { useState, useEffect, useRef } from "react";
import { Button, Tab, TabList } from "@fluentui/react-components";
import { ArrowRight, ArrowUpRight, ChatText, Check, FileText, ShieldCheck, Clock, MapPin, UserSwitch, LockSimple, Info } from "@phosphor-icons/react";
import { canPrepare, type Order, type Preview, type Scenario } from "@/lib/demo";
import { requestPreview } from "@/lib/api";
import { Status } from "./order-list";

type ActionState = { kind: "idle" } | { kind: "pending"; action: "draft" | "handoff" } | { kind: "success"; result: Preview } | { kind: "error"; message: string };
type DetailTab = "summary" | "timeline" | "conversation";

export function OrderWorkspace({ order, scenario, onPreview, completed, initialTab = "summary" }: {
    order: Order; scenario: Scenario; onPreview: (preview: Preview) => void;
    completed: Preview[]; initialTab?: DetailTab;
}) {
    const [tab, setTab] = useState<DetailTab>(initialTab);
    const [action, setAction] = useState<ActionState>({ kind: "idle" });
    const controller = useRef<AbortController | null>(null);
    useEffect(() => () => controller.current?.abort(), []);
    const draft = completed.find((item) => item.orderId === order.id && item.kind === "draft");
    const handoff = completed.some((item) => item.orderId === order.id && item.kind === "handoff");
    const allowed = canPrepare(order, scenario);

    async function prepare(kind: "draft" | "handoff") {
        controller.current?.abort();
        const request = new AbortController();
        controller.current = request;
        setAction({ kind: "pending", action: kind });
        try {
            const result = await requestPreview({ orderId: order.id, scenario, kind }, request.signal);
            if (request.signal.aborted) return;
            onPreview(result);
            setAction({ kind: "success", result });
            if (kind === "draft") setTab("conversation");
        } catch (error) {
            if (!request.signal.aborted) setAction({ kind: "error", message: error instanceof Error ? error.message : "Chưa thể thực hiện. Vui lòng thử lại." });
        }
    }

    return <section className="panel detail-panel" aria-label={`Hồ sơ ${order.id}`}>
        <div className="detail-heading"><div className="flex items-center justify-between gap-2"><span className="detail-label">Hồ sơ đơn hàng</span><Status order={order} /></div>
            <h2>{order.id}<span className="detail-package"><FileText size={22} /></span></h2><p>{order.name}</p>
            <div className="route-line"><MapPin size={15} /><span>{order.origin}</span><ArrowRight size={14} /><span>{order.destination}</span></div>
        </div>
        <TabList selectedValue={tab} className="detail-tabs" onTabSelect={(_, data) => { if (data.value === "summary" || data.value === "timeline" || data.value === "conversation") setTab(data.value); }}>
            <Tab value="summary">Tổng quan</Tab><Tab value="timeline">Dòng thời gian</Tab><Tab value="conversation">Hội thoại</Tab>
        </TabList>
        <div className="detail-body" role="tabpanel" aria-label={tab === "summary" ? "Tổng quan đơn hàng" : tab === "timeline" ? "Dòng thời gian quyết định" : "Xem trước hội thoại"}>
            {tab === "summary" && <>
                <div className={`assessment-box assessment-${order.status}`}><div className="flex gap-2 items-center"><Info size={17} /><h3>Vì sao cần chú ý?</h3></div><p>{order.reason}</p></div>
                <dl className="date-grid"><div><dt>Ngày cam kết</dt><dd>{order.due}</dd></div><div><dt>Dự kiến mới</dt><dd>{order.eta ?? "Chưa xác định"}</dd></div><div><dt>Ngày đặt hàng</dt><dd className="unavailable">{order.orderedAt ?? "Chưa có dữ liệu"}</dd></div><div><dt>Bàn giao hãng</dt><dd className="unavailable">{order.handedOverAt ?? "Chưa có dữ liệu"}</dd></div></dl>
                <div className="evidence-heading"><h3>Bằng chứng gần nhất</h3><span>A2</span></div>
                <div className="latest-event"><span className="event-icon"><TruckEvent /></span><div><strong>{order.event}</strong><p>{order.eventAt}, dữ kiện minh họa</p></div><ArrowUpRight size={16} aria-hidden="true" /></div>
                <div className="confidence-line"><span>Độ tin cậy đánh giá</span><strong>{order.confidence}%</strong></div><div className="fault-line"><span>Bên có lỗi</span><span>Chưa kết luận</span></div>
            </>}
            {tab === "timeline" && <div className="decision-timeline">
                <TimelineItem agent="A3" title="Kiểm tra dữ liệu" text={scenario === "healthy" ? "Gate minh họa cho phép kiểm tra điều kiện theo từng đơn." : "Sự cố nguồn minh họa. Chặn mọi liên hệ chủ động."} />
                <TimelineItem agent="A2" title="Đánh giá logistics" text={order.reason} />
                <TimelineItem agent="A1" title="Chọn bước chăm sóc" text={allowed ? "Có thể chuẩn bị bản nháp để xem xét. Chưa gửi khách." : "Chưa đủ điều kiện chủ động liên hệ. Có thể chuyển nhân viên xem xét."} />
                <p className="timeline-note">Ngày cam kết tính hết ngày theo giờ Việt Nam. ETA mới chỉ là dự kiến.</p>
            </div>}
            {tab === "conversation" && <div className="conversation-preview"><div className="conversation-intro"><ChatText size={22} /><div><h3>Bản nháp chăm sóc</h3><p>Xem trước nội dung, chưa gửi đến khách.</p></div></div>
                {draft ? <><div className="message-bubble">{draft.message}</div><p className="draft-caption"><Check size={14} /> Chỉ lưu trong phiên giao diện này</p></> : <div className="conversation-empty"><FileText size={30} /><p>Chưa có bản nháp cho đơn này.</p><small>Kiểm tra bằng chứng và điều kiện trước khi chuẩn bị.</small></div>}
                <div className="conversation-policy"><ShieldCheck size={16} /><p>Tin nhắn khách là dữ liệu. Yêu cầu gặp người cần được chuyển nhân viên.</p></div>
            </div>}
        </div>
        <div className="detail-actions">
            <div className={`contact-condition ${allowed ? "allowed" : "blocked"}`}>{allowed ? <ShieldCheck size={16} /> : <LockSimple size={16} />}<span>{allowed ? "Đủ điều kiện chuẩn bị bản nháp minh họa" : "Chưa đủ điều kiện liên hệ chủ động"}</span></div>
            <Button appearance="primary" size="large" icon={draft ? <Check size={18} /> : <ChatText size={18} />} disabled={!allowed || !!draft || action.kind === "pending"} onClick={() => prepare("draft")}>{action.kind === "pending" && action.action === "draft" ? "Đang chuẩn bị..." : draft ? "Đã chuẩn bị bản nháp" : "Chuẩn bị liên hệ"}</Button>
            <Button size="large" icon={handoff ? <Check size={18} /> : <UserSwitch size={18} />} disabled={handoff || action.kind === "pending"} onClick={() => prepare("handoff")}>{action.kind === "pending" && action.action === "handoff" ? "Đang xem trước..." : handoff ? "Đã xem trước chuyển người" : "Chuyển nhân viên xem xét"}</Button>
            {action.kind === "error" && <p className="inline-error" role="alert">{action.message}</p>}
            {action.kind === "success" && <p className="action-success" role="status">{action.result.kind === "draft" ? "Bản nháp đã sẵn sàng để xem. Chưa gửi tin nhắn." : action.result.message}</p>}
            <p className="action-disclaimer">Thao tác minh họa, không tạo hành động thật.</p>
        </div>
    </section>;
}
function TruckEvent() { return <Clock size={18} />; }
function TimelineItem({ agent, title, text }: { agent: string; title: string; text: string }) {
    return <article className="decision-item"><span className="agent-step">{agent}</span><div><h3>{title}</h3><p>{text}</p></div></article>;
}
