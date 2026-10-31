"use client";

import { useEffect, useState } from "react";
import { Button, Skeleton, SkeletonItem, Switch } from "@fluentui/react-components";
import { ArrowClockwise, ShieldCheck, WarningCircle, ArrowRight, Package, ChatText, Database, ArrowUpRight } from "@phosphor-icons/react";
import { loadSnapshot } from "@/lib/api";
import type { Preview, Scenario, Snapshot } from "@/lib/demo";
import { Shell, type View } from "./shell";
import { OrderList } from "./order-list";
import { OrderWorkspace } from "./order-workspace";

type LoadState = { kind: "loading" } | { kind: "ready"; snapshot: Snapshot } | { kind: "error"; message: string };
const headings: Record<View, { title: string; description: string }> = {
    overview: { title: "Mọi đơn hàng, trong tầm nhìn.", description: "Ưu tiên đúng đơn. Hiểu bằng chứng. Liên hệ có kiểm soát." },
    guard: { title: "Dữ liệu đáng tin, quyết định an toàn.", description: "Kiểm tra điều kiện trước khi chủ động chăm sóc khách hàng." },
    logistics: { title: "Hiểu hành trình của từng đơn.", description: "Theo dõi đánh giá A2, ngày cam kết và bằng chứng vận chuyển." },
    care: { title: "Chăm sóc từ những điều đã biết.", description: "Chuẩn bị nội dung theo dữ kiện, chuyển người khi cần." },
};

export function Operations() {
    const [view, setView] = useState<View>("overview");
    const [scenario, setScenario] = useState<Scenario>("healthy");
    const [load, setLoad] = useState<LoadState>({ kind: "loading" });
    const [reload, setReload] = useState(0);
    const [selected, setSelected] = useState("DEMO-0281");
    const [previews, setPreviews] = useState<Preview[]>([]);
    useEffect(() => {
        const controller = new AbortController();
        loadSnapshot(scenario, controller.signal).then((snapshot) => {
            if (!controller.signal.aborted) setLoad({ kind: "ready", snapshot });
        }).catch((error: unknown) => {
            if (!controller.signal.aborted) setLoad({ kind: "error", message: error instanceof Error ? error.message : "Không thể tải dữ liệu." });
        });
        return () => controller.abort();
    }, [scenario, reload]);

    function refresh() { setLoad({ kind: "loading" }); setReload((value) => value + 1); }
    function changeScenario(failure: boolean) {
        setLoad({ kind: "loading" }); setScenario(failure ? "failure" : "healthy");
    }
    function savePreview(preview: Preview) {
        setPreviews((items) => items.some((item) => item.orderId === preview.orderId && item.kind === preview.kind) ? items : [...items, preview]);
    }
    const order = load.kind === "ready" ? load.snapshot.orders.find((item) => item.id === selected) ?? load.snapshot.orders[0] : undefined;
    return <Shell view={view} onView={setView}>
        <div className="page-heading"><div><div className="page-kicker">CHỢ PHỐ CARE</div><h1>{headings[view].title}</h1><p>{headings[view].description}</p></div><Button icon={<ArrowClockwise size={17} />} disabled={load.kind === "loading"} onClick={refresh}>Tải lại dữ liệu</Button></div>
        {load.kind === "loading" && <LoadingWorkspace />}
        {load.kind === "error" && <div className="panel error-state" role="alert"><WarningCircle size={38} /><h2>Chưa thể tải phòng điều hành</h2><p>{load.message}</p><Button appearance="primary" onClick={refresh}>Thử lại</Button></div>}
        {load.kind === "ready" && <>
            <div className={`guard-banner ${load.snapshot.contactGate ? "" : "guard-failure"}`} role="status"><span className="guard-icon">{load.snapshot.contactGate ? <ShieldCheck size={23} weight="duotone" /> : <WarningCircle size={23} />}</span><div><strong>{load.snapshot.contactGate ? "Nguồn ổn định trong kịch bản minh họa" : "A3 đang chặn liên hệ chủ động"}</strong><p>{load.snapshot.contactGate ? "Tiếp tục kiểm tra bằng chứng và điều kiện riêng của từng đơn." : "Nguồn dữ liệu gặp sự cố minh họa. Chưa được chuẩn bị liên hệ chủ động."}</p></div><button onClick={() => setView(view === "guard" ? "overview" : "guard")}>{view === "guard" ? "Về tổng quan" : "Xem giám sát"}<ArrowRight size={16} /></button></div>
            {view !== "guard" && <>
                <section className="metrics-strip" aria-label="Tổng quan dữ liệu minh họa">
                    <Metric label="Đơn đang theo dõi" value={load.snapshot.orders.length} icon={<Package size={18} />} note="Trong phiên minh họa" />
                    <Metric label="Đơn cần chú ý" value={load.snapshot.orders.filter((item) => (item.probability ?? 0) >= 70).length} icon={<WarningCircle size={18} />} note="Trễ hoặc có nguy cơ trễ" accent />
                    <Metric label="Bản nháp đã chuẩn bị" value={previews.filter((item) => item.kind === "draft").length} icon={<ChatText size={18} />} note="Chưa gửi đến khách hàng" />
                    <Metric label="Đơn thiếu dữ liệu" value={load.snapshot.orders.filter((item) => item.status === "unknown_feed").length} icon={<Database size={18} />} note="Cần kiểm tra nguồn" />
                </section>
                <div className={`operations-grid ${view === "care" ? "care-grid" : ""}`}>
                    <div className="list-column"><OrderList orders={load.snapshot.orders} selected={selected} onSelect={setSelected} compact={view === "care"} />
                        <div className="workflow-summary"><div><h2>Ba vai trò. Một luồng chăm sóc.</h2><p>Dữ liệu trước, đánh giá sau, rồi mới liên hệ.</p></div><div className="workflow-steps"><span><b>A3</b> Kiểm tra nguồn</span><ArrowRight size={15} /><span><b>A2</b> Đánh giá đơn</span><ArrowRight size={15} /><span><b>A1</b> Chăm sóc</span></div><button onClick={() => setView("guard")} aria-label="Xem luồng giám sát dữ liệu"><ArrowUpRight size={19} /></button></div>
                    </div>
                    {order && <OrderWorkspace key={`${order.id}:${scenario}:${view}`} order={order} scenario={scenario} onPreview={savePreview} completed={previews} initialTab={view === "logistics" ? "timeline" : view === "care" ? "conversation" : "summary"} />}
                </div>
            </>}
            {view === "guard" && <GuardDetails snapshot={load.snapshot} />}
        </>}
        <details className="demo-controls"><summary>Điều khiển phiên minh họa</summary><div><Switch checked={scenario === "failure"} disabled={load.kind === "loading"} onChange={(_, data) => changeScenario(data.checked)} label="Mô phỏng sự cố nguồn dữ liệu" /><p>Chỉ thay đổi kịch bản demo. Không chạy replay, không mở khóa cổng thực thi.</p>{load.kind === "ready" && <p>Thời điểm mẫu: {load.snapshot.assessedAt}, giờ Việt Nam.</p>}<p>Bản nháp và xem trước chuyển người mất khi tải lại trang.</p></div></details>
    </Shell>;
}

function Metric({ label, value, icon, note, accent = false }: { label: string; value: number; icon: React.ReactNode; note: string; accent?: boolean }) {
    return <div className={`metric ${accent ? "metric-accent" : ""}`}><div className="metric-label">{label}{icon}</div><strong>{String(value).padStart(2, "0")}</strong><small>{note}</small></div>;
}
function LoadingWorkspace() {
    return <Skeleton aria-label="Đang tải phòng điều hành" className="loading-workspace"><SkeletonItem shape="rectangle" style={{ height: 74 }} /><div className="grid grid-cols-2 md:grid-cols-4 gap-6 py-8">{[1, 2, 3, 4].map((item) => <SkeletonItem key={item} shape="rectangle" style={{ height: 100 }} />)}</div><div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6"><SkeletonItem shape="rectangle" style={{ height: 430 }} /><SkeletonItem shape="rectangle" style={{ height: 600 }} /></div></Skeleton>;
}
function GuardDetails({ snapshot }: { snapshot: Snapshot }) {
    return <section className="panel guard-details"><div className="guard-detail-title"><ShieldCheck size={28} /><h2>Điều kiện liên hệ chủ động</h2><p>Đây là trạng thái kịch bản UI, chưa phải kết quả A3 chạy thật.</p></div><div className="guard-rules"><article><span>A3</span><h3>Nguồn dữ liệu và heartbeat</h3><p>Nguồn stale, corrupt, missing hoặc heartbeat thiếu / quá 60 phút đều chặn liên hệ chủ động.</p><strong>{snapshot.contactGate ? "Kịch bản: gate ổn định" : "Kịch bản: gate đang chặn"}</strong></article><article><span>A2</span><h3>Đánh giá theo từng đơn</h3><p>Không tự đổi fault hoặc ETA. Dữ liệu thiếu phải được hiển thị rõ; không suy đoán ngày giao.</p><strong>{snapshot.orders.filter((item) => item.status === "unknown_feed").length} đơn mẫu thiếu dữ liệu</strong></article><article><span>A1</span><h3>Chăm sóc có kiểm soát</h3><p>Chỉ xem trước nội dung dựa trên dữ kiện. Không cấp tiền từ giao diện; voice không cấp xu.</p><strong>Chưa kết nối gửi tin nhắn</strong></article></div></section>;
}
