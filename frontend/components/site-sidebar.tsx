"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Page = "home" | "demo" | "architecture" | "start" | "workspace";

const overview: { href: string; label: string; page: Page }[] = [
  { href: "/", label: "首页", page: "home" },
  { href: "/demo", label: "案例体验", page: "demo" },
  { href: "/architecture", label: "系统设计", page: "architecture" },
  { href: "/start", label: "快速开始", page: "start" },
];

const workspaceSections = [
  { href: "/workspace#profile", label: "导入与画像", tag: "01" },
  { href: "/workspace#matching", label: "岗位与学习", tag: "02" },
  { href: "/workspace#report", label: "职业报告", tag: "03" },
  { href: "/workspace#copilot", label: "Copilot 问答", tag: "04" },
  { href: "/workspace#assessment", label: "自我探索", tag: "05" },
  { href: "/workspace#quality", label: "质量与数据", tag: "06" },
  { href: "/agent", label: "持久 Agent", tag: "07" },
  { href: "/settings", label: "桌面设置", tag: "08" },
];

function currentPage(pathname: string): Page {
  if (
    pathname.startsWith("/workspace") ||
    pathname.startsWith("/agent") ||
    pathname.startsWith("/settings")
  )
    return "workspace";
  if (pathname.startsWith("/demo")) return "demo";
  if (pathname.startsWith("/architecture")) return "architecture";
  if (pathname.startsWith("/start")) return "start";
  return "home";
}

export function SiteSidebar() {
  const pathname = usePathname() || "/";
  const active = currentPage(pathname);

  return (
    <aside className="site-sidebar" aria-label="站点导航">
      <Link className="sidebar-brand" href="/" aria-label="CareerLens 首页">
        <span className="site-brand-mark">C<span>·</span></span>
        <span className="site-brand-word">CareerLens<small>EVIDENCE → DECISION</small></span>
      </Link>

      <nav className="sidebar-nav">
        <div className="sidebar-group">
          <span className="sidebar-label">概览</span>
          {overview.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="sidebar-link"
              aria-current={active === link.page ? "page" : undefined}
            >
              <span className="sidebar-dot" aria-hidden="true" />
              {link.label}
            </Link>
          ))}
        </div>

        <div className="sidebar-group">
          <span className="sidebar-label">工作台分区</span>
          {workspaceSections.map((section) => (
            <Link
              key={section.href}
              href={section.href}
              className={`sidebar-link sidebar-link-sub${active === "workspace" ? " is-parent-active" : ""}`}
            >
              <span className="sidebar-tag">{section.tag}</span>
              {section.label}
            </Link>
          ))}
        </div>

        <div className="sidebar-group">
          <span className="sidebar-label">资源</span>
          <a
            className="sidebar-link"
            href="https://github.com/wenmo-yu/careerlens/tree/main/docs"
            target="_blank"
            rel="noreferrer"
          >
            <span className="sidebar-dot" aria-hidden="true" />
            技术文档 <span className="sidebar-ext">↗</span>
          </a>
          <a
            className="sidebar-link"
            href="https://wenmo-yu.github.io/careerlens/"
            target="_blank"
            rel="noreferrer"
          >
            <span className="sidebar-dot" aria-hidden="true" />
            在线教程 <span className="sidebar-ext">↗</span>
          </a>
        </div>
      </nav>

      <div className="sidebar-foot">
        <Link className="site-button site-button-dark" href="/workspace" aria-current={active === "workspace" ? "page" : undefined}>
          进入工作台 <span>↗</span>
        </Link>
        <small>示例数据均为虚构 · 默认无需密钥</small>
      </div>
    </aside>
  );
}
