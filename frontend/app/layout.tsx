import type { Metadata } from "next";
import { Manrope, Noto_Sans_SC } from "next/font/google";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });
const noto = Noto_Sans_SC({ subsets: ["latin"], variable: "--font-noto" });

export const metadata: Metadata = {
  title: "CareerLens · 让每一个职业判断都有证据",
  description: "从个人证据到职业画像、岗位匹配、职业报告与可追问的决策工作台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body className={`${manrope.variable} ${noto.variable}`}>{children}</body>
    </html>
  );
}
