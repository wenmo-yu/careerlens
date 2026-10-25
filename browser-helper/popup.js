import { capturePage } from "./capture.js";
import { mergeCapture } from "./collection.js";

const kind = document.getElementById("kind");
const status = document.getElementById("status");
const groups = document.getElementById("groups");
const itemsList = document.getElementById("items");
const download = document.getElementById("download");
const clear = document.getElementById("clear");
let saved = {};
let selectedKey = "";

async function persist() {
  await chrome.storage.session.set({ careerlensCaptures: saved });
}

function render() {
  groups.replaceChildren();
  const keys = Object.keys(saved).sort();
  for (const key of keys) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = `${key} · ${saved[key].items.length} 条`;
    groups.append(option);
  }
  if (!saved[selectedKey]) selectedKey = keys[0] || "";
  groups.value = selectedKey;
  const capture = saved[selectedKey];
  const key = selectedKey;
  itemsList.replaceChildren();
  for (const [index, item] of (capture?.items || []).entries()) {
    const row = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${item.title || item.text.slice(0, 100)} — ${item.url}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "移除";
    remove.addEventListener("click", async () => {
      saved[key].items.splice(index, 1);
      if (!saved[key].items.length) delete saved[key];
      await persist();
      render();
    });
    row.append(label, remove);
    itemsList.append(row);
  }
  download.disabled = !capture?.items.length;
  clear.disabled = !capture;
}

document.getElementById("capture").addEventListener("click", async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("找不到当前页面。");
    const [execution] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: capturePage,
      args: [kind.value],
    });
    const incoming = execution.result;
    if (!incoming?.items?.length) throw new Error("未找到条目。请检查页面类型并手动滚动加载内容。");
    selectedKey = `${incoming.platform}:${incoming.kind}`;
    const merged = mergeCapture(saved[selectedKey], incoming);
    saved[selectedKey] = merged.capture;
    await persist();
    render();
    status.textContent = `本次新增 ${merged.added} 条，当前分组共 ${merged.capture.items.length} 条（上限 200）。`;
  } catch (error) {
    status.textContent = error.message || "采集失败";
  }
});

groups.addEventListener("change", () => {
  selectedKey = groups.value;
  render();
});

clear.addEventListener("click", async () => {
  if (!selectedKey) return;
  delete saved[selectedKey];
  await persist();
  render();
  status.textContent = "当前分组已清空。";
});

download.addEventListener("click", async () => {
  const capture = saved[selectedKey];
  if (!capture) return;
  const encoded = encodeURIComponent(JSON.stringify(capture, null, 2));
  const filename = `careerlens-${capture.platform}-${capture.kind}-${Date.now()}.json`;
  try {
    await chrome.downloads.download({
      url: `data:application/json;charset=utf-8,${encoded}`,
      filename,
      saveAs: true,
    });
    status.textContent = "已导出。请在 CareerLens 工作台选择文件并确认入库。";
  } catch (error) {
    status.textContent = error.message || "导出失败";
  }
});

void chrome.storage.session.get("careerlensCaptures").then((result) => {
  saved = result.careerlensCaptures || {};
  render();
});
