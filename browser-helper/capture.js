export function capturePage(kind) {
  const host = location.hostname.toLowerCase();
  const platform = host === "bilibili.com" || host.endsWith(".bilibili.com")
    ? "bilibili"
    : host === "weibo.com" || host.endsWith(".weibo.com") || host === "weibo.cn" || host.endsWith(".weibo.cn")
      ? "weibo"
      : host === "douyin.com" || host.endsWith(".douyin.com")
        ? "douyin"
        : null;
  if (!platform) throw new Error("请打开 Bilibili、微博或抖音的个人页面。");

  const patterns = {
    bilibili: kind === "following" ? [/^space\.bilibili\.com\/\d+/] : [/bilibili\.com\/video\/BV[\w]+/i],
    weibo: kind === "following" ? [/weibo\.(?:com|cn)\/(?:u\/)?\d+/] : [
      /weibo\.(?:com|cn)\/(?:status|detail)\//,
      /weibo\.(?:com|cn)\/\d{5,}\/[A-Za-z0-9]{5,}/,
    ],
    douyin: kind === "following" ? [/douyin\.com\/user\//] : [/douyin\.com\/video\//],
  };
  const cardSelector = [
    "article", "[data-testid*='post']", "[class*='video-card']", "[class*='VideoCard']",
    "[class*='card-wrap']", "[class*='feed-card']", "[class*='FeedCard']",
    "[class*='aweme']", "[class*='Aweme']", "li"
  ].join(",");
  const items = [];
  const seen = new Set();
  for (const anchor of document.querySelectorAll("a[href]")) {
    let url;
    try { url = new URL(anchor.getAttribute("href"), location.href); } catch { continue; }
    if (url.protocol !== "https:" || !patterns[platform].some((pattern) => pattern.test(url.hostname + url.pathname))) continue;
    url.hash = "";
    url.search = "";
    const normalized = url.toString();
    if (seen.has(normalized)) continue;
    const card = anchor.closest(cardSelector) || anchor.parentElement;
    if (!card || getComputedStyle(card).display === "none" || getComputedStyle(card).visibility === "hidden") continue;
    const title = (anchor.getAttribute("title") || anchor.getAttribute("aria-label") || anchor.textContent || "").replace(/\s+/g, " ").trim().slice(0, 300);
    const text = (card.innerText || card.textContent || "").replace(/\s+/g, " ").trim().slice(0, 1200);
    if (!title && !text) continue;
    seen.add(normalized);
    items.push({ url: normalized, title, text });
    if (items.length >= 100) break;
  }
  return {
    format: "careerlens-browser-capture-v1",
    platform,
    kind,
    source_url: location.origin + location.pathname,
    captured_at: new Date().toISOString(),
    items,
  };
}
