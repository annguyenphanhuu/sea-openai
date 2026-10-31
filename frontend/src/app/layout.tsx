import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppProvider } from "@/components/app-provider";
import "./globals.css";

const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "vietnamese"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
    title: "Chợ Phố | Phòng điều hành",
    description: "Không gian vận hành đơn hàng và chăm sóc khách hàng Chợ Phố. Dữ liệu minh họa.",
    robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return <html lang="vi" className={`${sans.variable} ${mono.variable}`}>
        <body><AppProvider>{children}</AppProvider></body>
    </html>;
}
