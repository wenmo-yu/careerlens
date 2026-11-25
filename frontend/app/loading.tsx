export default function Loading() {
  return (
    <main className="site-page state-page" aria-busy="true" aria-live="polite">
      <div className="state-card state-skeleton">
        <span className="site-kicker"><i /> LOADING</span>
        <h1>正在加载</h1>
        <p>正在准备工作台与最新数据，请稍候。</p>
        <div className="skeleton-lines" aria-hidden="true">
          <span /><span /><span />
        </div>
      </div>
    </main>
  );
}
