export function mergeCapture(existing, incoming, maxItems = 200) {
  if (existing && (existing.platform !== incoming.platform || existing.kind !== incoming.kind)) {
    throw new Error("不能合并不同平台或页面类型的记录。");
  }
  const items = new Map((existing?.items || []).map((item) => [item.url, item]));
  let added = 0;
  for (const item of incoming.items) {
    if (!item?.url || (!item.title && !item.text)) continue;
    const old = items.get(item.url);
    if (!old && items.size >= maxItems) break;
    if (!old) added += 1;
    if (!old || (item.text || "").length > (old.text || "").length) {
      items.set(item.url, item);
    }
  }
  return {
    capture: {
      format: "careerlens-browser-capture-v1",
      platform: incoming.platform,
      kind: incoming.kind,
      source_url: existing?.source_url || incoming.source_url,
      captured_at: incoming.captured_at,
      items: [...items.values()],
    },
    added,
  };
}
