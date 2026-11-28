import type { Metadata } from "next";
import { SiteSidebar } from "@/components/site-sidebar";
import "./globals.css";

// Fonts are resolved by the local CSS stacks in styles/tokens.css and
// styles/base.css. Removing next/font/google keeps offline and air-gapped
// builds deterministic; no webfont request is needed to render the product.
export const metadata: Metadata = {
  title: "CareerLens · 让每一个职业判断都有证据",
  description: "从个人证据到职业画像、岗位匹配、职业报告与可追问的决策工作台。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <SiteSidebar />
        <div className="site-main">{children}</div>
      </body>
    </html>
  );
}
