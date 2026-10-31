"use client";

import { useEffect, useRef, useState, type ReactNode, type KeyboardEvent } from "react";
import { Button } from "@fluentui/react-components";
import Link from "next/link";
import { SquaresFour, ShieldCheck, Truck, ChatsCircle, ArrowUpRight, Moon, Sun, List, X, Flask, CaretRight } from "@phosphor-icons/react";
import { useAppTheme } from "./app-provider";

export type View = "overview" | "guard" | "logistics" | "care";
const navigation = [
    { id: "overview", label: "Phòng điều hành", icon: SquaresFour },
    { id: "guard", label: "Giám sát dữ liệu", icon: ShieldCheck },
    { id: "logistics", label: "Phân tích logistics", icon: Truck },
    { id: "care", label: "Chăm sóc khách hàng", icon: ChatsCircle },
] satisfies { id: View; label: string; icon: typeof SquaresFour }[];

export function Shell({ view, onView, children }: { view: View; onView: (view: View) => void; children: ReactNode }) {
    const [menu, setMenu] = useState(false);
    const sidebar = useRef<HTMLElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const closeButton = useRef<HTMLButtonElement>(null);
    const previouslyOpen = useRef(false);
    const { dark, toggle } = useAppTheme();
    useEffect(() => {
        if (menu) closeButton.current?.focus();
        else if (previouslyOpen.current) trigger.current?.focus();
        previouslyOpen.current = menu;
    }, [menu]);
    useEffect(() => {
        const desktop = matchMedia("(min-width: 768px)");
        const close = () => { if (desktop.matches) setMenu(false); };
        desktop.addEventListener("change", close);
        return () => desktop.removeEventListener("change", close);
    }, []);
    function containMenuFocus(event: KeyboardEvent<HTMLElement>) {
        if (!menu) return;
        if (event.key === "Escape") { event.preventDefault(); setMenu(false); }
        if (event.key !== "Tab") return;
        const targets = sidebar.current?.querySelectorAll<HTMLElement>("a[href],button:not([disabled])");
        const first = targets?.[0];
        const last = targets?.[targets.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    return <div className="application-shell">
        <a href="#main-content" className="skip-link">Đến nội dung chính</a>
        <aside ref={sidebar} className={`sidebar ${menu ? "is-open" : ""}`} aria-label="Điều hướng chính" onKeyDown={containMenuFocus}>
            <div className="brand-row"><Link href="/" className="wordmark" aria-label="Chợ Phố, trang chủ">chợ phố<span>.</span></Link>
                <Button ref={closeButton} appearance="subtle" className="mobile-menu-close" icon={<X size={20} />} aria-label="Đóng menu" onClick={() => setMenu(false)} />
            </div>
            <div className="workspace-name">Không gian vận hành</div>
            <nav className="nav-items">{navigation.map(({ id, label, icon: Icon }, index) =>
                <button key={id} className={`nav-link ${view === id ? "active" : ""}`} aria-current={view === id ? "page" : undefined}
                    onClick={() => { onView(id); setMenu(false); }}><Icon size={20} weight={view === id ? "fill" : "regular"} />
                    <span>{label}</span>{index > 0 && <small>A{4 - index}</small>}
                </button>)}
            </nav>
            <div className="sidebar-note"><div className="note-symbol"><ShieldCheck size={23} /></div>
                <h2>Hiểu đúng. Chăm sóc đúng.</h2><p>Mỗi quyết định bắt đầu từ dữ liệu được kiểm chứng.</p>
                <button onClick={() => { onView("guard"); setMenu(false); }}>Xem điều kiện liên hệ <ArrowUpRight size={16} /></button>
            </div>
            <div className="team-profile"><span className="team-avatar">CP</span><div><strong>Nhóm Chợ Phố</strong><small>Care operations</small></div></div>
        </aside>
        <div className="main-column" inert={menu}>
            <header className="topbar">
                <div className="flex items-center gap-3 min-w-0"><Button ref={trigger} appearance="subtle" className="mobile-menu" icon={<List size={22} />} aria-label="Mở menu" aria-expanded={menu} onClick={() => setMenu(!menu)} />
                    <span className="breadcrumb-root">Không gian làm việc</span><CaretRight size={13} className="breadcrumb-root" /><span className="breadcrumb-current">{navigation.find((item) => item.id === view)?.label}</span></div>
                <div className="flex items-center gap-3"><span className="demo-badge"><Flask size={14} /> Phiên minh họa</span>
                    <Button appearance="subtle" icon={dark ? <Sun size={19} /> : <Moon size={19} />} aria-label={dark ? "Dùng giao diện sáng" : "Dùng giao diện tối"} onClick={toggle} />
                </div>
            </header>
            <main id="main-content" className="workspace-container">{children}</main>
            <footer className="app-footer"><span>Chợ Phố Care Operations</span><span>Dữ liệu mẫu từ prototype. Không kết nối hệ thống thật.</span></footer>
        </div>
    </div>;
}
