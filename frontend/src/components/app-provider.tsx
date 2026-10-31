"use client";

import { createContext, useContext, useRef, useState, useSyncExternalStore } from "react";
import { FluentProvider, createLightTheme, createDarkTheme, type BrandVariants } from "@fluentui/react-components";
import { createDOMRenderer, RendererProvider, renderToStyleElements } from "@griffel/react";
import { useServerInsertedHTML } from "next/navigation";

const ThemeContext = createContext({ dark: false, toggle: () => {} });
export const useAppTheme = () => useContext(ThemeContext);
const brand: BrandVariants = {
    10: "#071d12", 20: "#0e2b1d", 30: "#123d28", 40: "#174e34",
    50: "#1d5a3f", 60: "#236148", 70: "#2c7355", 80: "#368462",
    90: "#4e9778", 100: "#69aa8d", 110: "#86bda4", 120: "#a1ceba",
    130: "#bddfd1", 140: "#d6ece2", 150: "#e8f4ed", 160: "#f3faf5",
};
const lightTheme = createLightTheme(brand);
const darkTheme = createDarkTheme(brand);

function currentTheme() {
    try {
        const saved = localStorage.getItem("cho-pho-theme");
        if (saved === "dark" || saved === "light") return saved === "dark";
    } catch { /* System preference remains available if storage is blocked. */ }
    return matchMedia("(prefers-color-scheme: dark)").matches;
}
function subscribeTheme(callback: () => void) {
    const media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", callback);
    window.addEventListener("storage", callback);
    window.addEventListener("cho-pho-theme", callback);
    return () => {
        media.removeEventListener("change", callback);
        window.removeEventListener("storage", callback);
        window.removeEventListener("cho-pho-theme", callback);
    };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
    const [renderer] = useState(() => createDOMRenderer());
    const stylesInserted = useRef(false);
    const dark = useSyncExternalStore(subscribeTheme, currentTheme, () => false);
    useServerInsertedHTML(() => {
        if (stylesInserted.current) return;
        stylesInserted.current = true;
        return <>{renderToStyleElements(renderer)}</>;
    });
    function toggle() {
        try { localStorage.setItem("cho-pho-theme", dark ? "light" : "dark"); }
        catch { return; }
        window.dispatchEvent(new Event("cho-pho-theme"));
    }
    const theme = { ...(dark ? darkTheme : lightTheme),
        fontFamilyBase: "var(--font-geist-sans), sans-serif",
        colorBrandBackground: dark ? "#86c3a6" : "#236148",
        colorBrandBackgroundHover: dark ? "#a7d6be" : "#1b513b",
        colorBrandBackgroundPressed: dark ? "#70b493" : "#163e2f",
        colorNeutralForegroundOnBrand: dark ? "#10291e" : "#fafcfb",
        colorBrandForeground1: dark ? "#a7d6be" : "#236148",
        borderRadiusMedium: "8px",
    };
    return <RendererProvider renderer={renderer}><ThemeContext.Provider value={{ dark, toggle }}>
        <FluentProvider theme={theme} data-theme={dark ? "dark" : "light"} className="app-root">
            {children}
        </FluentProvider>
    </ThemeContext.Provider></RendererProvider>;
}
