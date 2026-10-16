import Link from "next/link";

type Page = "home" | "demo" | "architecture" | "start" | "workspace";

const links: { href: string; label: string; page: Page }[] = [
  { href: "/", label: "首页", page: "home" },
  { href: "/demo", label: "案例体验", page: "demo" },
  { href: "/architecture", label: "系统设计", page: "architecture" },
  { href: "/start", label: "快速开始", page: "start" },
];

export function SiteHeader({ active }: { active: Page }) {
  return (
    <header className="site-header">
      <Link className="site-brand" href="/" aria-label="CareerLens 首页">
        <span className="site-brand-mark">C<span>·</span></span>
        <span className="site-brand-word">CareerLens<small>EVIDENCE → DECISION</small></span>
      </Link>
      <nav className="site-nav" aria-label="主导航">
        {links.map((link) => (
          <Link key={link.href} href={link.href} aria-current={active === link.page ? "page" : undefined}>
            {link.label}
          </Link>
        ))}
      </nav>
      <details className="site-mobile-menu">
        <summary>菜单</summary>
        <div>{links.map((link) => <Link href={link.href} key={link.href}>{link.label}</Link>)}</div>
      </details>
      <Link className="site-nav-action" href="/workspace" aria-current={active === "workspace" ? "page" : undefined}>
        进入工作台 <span>↗</span>
      </Link>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div><strong>CareerLens<span>·</span></strong><p>把经历转为证据，把证据转为更清晰的职业判断。</p></div>
      <div className="site-footer-links">
        <Link href="/demo">案例体验</Link>
        <Link href="/architecture">系统设计</Link>
        <Link href="/start">快速开始</Link>
        <a href="https://github.com/wenmo-yu/careerlens" target="_blank" rel="noreferrer">GitHub ↗</a>
      </div>
      <span className="site-footer-bottom">© 2026 CareerLens · 开源项目 · 示例内容均为虚构</span>
    </footer>
  );
}
