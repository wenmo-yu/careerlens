import Link from "next/link";

export default function NotFound() {
  return (
    <main className="site-page state-page">
      <div className="state-card">
        <span className="site-kicker"><i /> 404 / NOT FOUND</span>
        <h1>没有这个页面</h1>
        <p>链接可能已经改变，或者这个地址从未存在。工作台与案例体验都还在。</p>
        <div className="state-actions">
          <Link className="site-button site-button-dark" href="/workspace">进入工作台</Link>
          <Link className="site-button site-button-outline" href="/">回到首页</Link>
        </div>
      </div>
    </main>
  );
}
