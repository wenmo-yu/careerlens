"use client";

import Link from "next/link";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="site-page state-page">
      <div className="state-card">
        <span className="site-kicker"><i /> SOMETHING BROKE</span>
        <h1>这个页面没能加载</h1>
        <p>
          可能是后端接口暂时不可用，或这次请求被中断。你的数据不会被改动；重试通常会恢复。
        </p>
        <div className="state-actions">
          <button type="button" onClick={reset}>重试</button>
          <Link className="site-button site-button-outline" href="/">回到首页</Link>
        </div>
        {error.digest && <code className="state-code">错误编号 {error.digest}</code>}
      </div>
    </main>
  );
}
