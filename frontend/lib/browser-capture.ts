export type BrowserCaptureDraft = {
  format: "careerlens-browser-capture-v1";
  platform: "bilibili" | "weibo" | "douyin";
  kind: "published" | "liked" | "favorite" | "following";
  source_url: string;
  captured_at: string;
  items: { url: string; title: string; text: string }[];
};

export function parseBrowserCaptureDraft(raw: string): BrowserCaptureDraft {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error("采集文件不是有效的 JSON。");
  }
  if (!value || typeof value !== "object") throw new Error("采集文件结构不正确。");
  const capture = value as Record<string, unknown>;
  const platforms = ["bilibili", "weibo", "douyin"];
  const kinds = ["published", "liked", "favorite", "following"];
  if (
    capture.format !== "careerlens-browser-capture-v1" ||
    !platforms.includes(String(capture.platform)) ||
    !kinds.includes(String(capture.kind)) ||
    typeof capture.source_url !== "string" ||
    typeof capture.captured_at !== "string" ||
    !Array.isArray(capture.items) ||
    capture.items.length < 1 || capture.items.length > 200 ||
    !capture.items.every((item: unknown) => {
      if (!item || typeof item !== "object") return false;
      const row = item as Record<string, unknown>;
      return typeof row.url === "string" && typeof row.title === "string" && typeof row.text === "string";
    })
  ) throw new Error("采集文件格式或条目数量不符合要求（1–200 条）。");
  return {
    format: "careerlens-browser-capture-v1",
    platform: capture.platform as BrowserCaptureDraft["platform"],
    kind: capture.kind as BrowserCaptureDraft["kind"],
    source_url: capture.source_url,
    captured_at: capture.captured_at,
    items: capture.items.map((item: Record<string, string>) => ({
      url: item.url,
      title: item.title,
      text: item.text,
    })),
  };
}
