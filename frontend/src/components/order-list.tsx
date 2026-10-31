"use client";

import { useState } from "react";
import { Button, Input } from "@fluentui/react-components";
import { MagnifyingGlass, ArrowRight, Package, Funnel, X } from "@phosphor-icons/react";
import { statusLabels, type Order } from "@/lib/demo";

export function Status({ order }: { order: Order }) {
    return <span className={`order-status status-${order.status}`}>{statusLabels[order.status]}</span>;
}
type Filter = "all" | "attention" | "missing";
const filters = [{ id: "all", label: "Tất cả" }, { id: "attention", label: "Cần chú ý" }, { id: "missing", label: "Thiếu dữ liệu" }] satisfies { id: Filter; label: string }[];

export function OrderList({ orders, selected, onSelect, compact = false }: {
    orders: Order[]; selected: string; onSelect: (id: string) => void; compact?: boolean;
}) {
    const [query, setQuery] = useState("");
    const [filter, setFilter] = useState<Filter>("all");
    const visible = orders.filter((order) => {
        const match = `${order.id} ${order.name} ${order.origin} ${order.destination}`.toLocaleLowerCase("vi").includes(query.toLocaleLowerCase("vi").trim());
        return match && (filter === "all" || (filter === "attention" && (order.probability ?? 0) >= 70) || (filter === "missing" && order.status === "unknown_feed"));
    });
    return <section className={`panel order-panel ${compact ? "compact-list" : ""}`} aria-label="Danh sách đơn hàng">
        <div className="panel-heading"><div><h2>Theo dõi đơn hàng</h2><p>Ưu tiên đúng đơn, dựa trên đúng bằng chứng.</p></div><span className="count-badge">{orders.length} đơn mẫu</span></div>
        <div className="list-tools"><div className="filter-group" aria-label="Lọc đơn hàng">{filters.map((item) => <button key={item.id} onClick={() => setFilter(item.id)} aria-pressed={filter === item.id} className={filter === item.id ? "selected" : ""}>{item.label}{item.id === "attention" && <span>{orders.filter((order) => (order.probability ?? 0) >= 70).length}</span>}</button>)}</div>
            <label className="search-field"><span className="sr-only">Tìm đơn hàng</span><Input value={query} onChange={(_, data) => setQuery(data.value)} contentBefore={<MagnifyingGlass size={17} />} placeholder="Mã đơn, tên khách, tuyến đường..." aria-label="Tìm đơn hàng" /></label>
        </div>
        <div className="order-table-header" aria-hidden="true"><span>Đơn hàng / Khách hàng</span><span>Đánh giá</span><span>Cam kết</span><span>Nguy cơ trễ</span></div>
        <div className="order-rows">{visible.map((order) => <button key={order.id} className={`order-row ${selected === order.id ? "is-selected" : ""}`} onClick={() => onSelect(order.id)} aria-pressed={selected === order.id}>
            <span className="sr-only">Xem đơn </span>
            <span className="order-person"><span className="order-package"><Package size={20} weight="duotone" /></span><span><strong>{order.id}</strong><small>{order.name}</small></span></span>
            <span className="order-evaluation"><Status order={order} /><small>{order.origin} <ArrowRight size={11} /> {order.destination}</small></span>
            <span className="order-due"><span className="mobile-data-label">Cam kết </span>{order.due.slice(0, 5)}<small>2026</small></span>
            <span className={`order-probability ${order.status === "late" ? "is-late" : ""}`}><span className="mobile-data-label">Nguy cơ </span>{order.probability === null ? "Chưa rõ" : <>{order.probability}<span>%</span></>}<ArrowRight size={16} className="row-arrow" /></span>
        </button>)}</div>
        {visible.length === 0 && <div className="empty-state"><Funnel size={30} /><h3>Không tìm thấy đơn phù hợp</h3><p>Thử mã đơn, tên khách hoặc đổi bộ lọc.</p><Button icon={<X size={15} />} onClick={() => { setQuery(""); setFilter("all"); }}>Xóa bộ lọc</Button></div>}
        <div className="list-footer"><span>Hiển thị {visible.length} / {orders.length} đơn minh họa</span><span>Đánh giá bởi A2</span></div>
        <div className="list-explainer"><ShieldNote /><p>Ngày dự kiến mới không thay đổi ngày cam kết. Thiếu dữ liệu không đồng nghĩa đơn hàng bị trễ.</p></div>
    </section>;
}
function ShieldNote() { return <span className="info-letter" aria-hidden="true">i</span>; }
