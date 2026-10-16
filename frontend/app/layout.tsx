import type { Metadata } from "next";
import { Manrope, Noto_Sans_SC } from "next/font/google";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });
const noto = Noto_Sans_SC({ subsets: ["latin"], variable: "--font-noto" });

export const metadata: Metadata = {
  title: "CareerLens · 职业决策工作台",
  description: "从个人证据到职业决策的可追溯 AI 工作台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={`${manrope.variable} ${noto.variable}`}>{children}</body>
    </html>
  );
}
