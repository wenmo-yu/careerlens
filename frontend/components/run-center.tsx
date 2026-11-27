"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  BackgroundRun,
  RunEvent,
  cancelRun,
  decideRun,
  getRun,
  listRuns,
  streamRun,
  terminalRun,
} from "@/lib/api";
import { RunEventProtocolError } from "@/lib/run-events";

const operations: Record<BackgroundRun["operation"], string> = {
  file_import: "文档导入", media_import: "媒体解析", wiki_compile: "Wiki 编译",
  job_analysis: "岗位分析", report: "职业报告",
};
const statuses: Record<BackgroundRun["status"], string> = {
  queued: "排队中", running: "执行中", waiting_confirmation: "等待确认",
  succeeded: "已完成", failed: "失败", cancelled: "已取消", interrupted: "中断 · 待恢复",
};
const reasons: Record<string, string> = {
  stale_input: "资料、画像或页面版本已变化，请用最新数据重新提交。",
  invalid_input: "任务输入不可用，请检查资料、岗位说明或目标页面。",
  parser_unavailable: "Worker 缺少所需的媒体解析组件。",
  permission_revoked: "提交任务时使用的权限已撤销。",
  retries_exhausted: "已达到重试上限；检查 Worker 或模型配置后重新提交。",
  run_expired: "任务已超过排队或确认期限，请重新提交。",
};
const steps: Record<string, string> = {
  parse: "来源解析", requirement_analyst: "岗位要求分析", wiki_curator: "Wiki 整理",
  evidence_verifier: "证据引用检查", report_writer: "报告撰写", persist: "保存结果",
  profile_cartographer: "画像维度草稿", role_scout: "职业方向草稿",
  curriculum_planner: "课程资源草稿",
};
const events: Record<string, string> = {
  "run.queued": "进入队列", "run.started": "开始执行", "run.succeeded": "提交成功",
  "run.failed": "任务失败", "run.cancelled": "任务取消", "run.interrupted": "记录中断并等待恢复",
  "run.waiting_confirmation": "等待用户确认", "run.approved": "已确认并排队",
  "step.failed": "子步骤失败", "step.running": "子步骤执行中",
};

function pause(ms: number, signal: AbortSignal) {
  if (signal.aborted) return Promise.resolve();
  return new Promise<void>((resolve) => {
    function finish() {
      clearTimeout(timer);
      signal.removeEventListener("abort", finish);
      resolve();
    }
    const timer = setTimeout(finish, ms);
    signal.addEventListener("abort", finish, { once: true });
  });
}

export function RunCenter({ userId, latest, refresh, onOpen }: {
  userId: string;
  latest: BackgroundRun | null;
  refresh: number;
  onOpen: (run: BackgroundRun) => void;
}) {
  const [rows, setRows] = useState<BackgroundRun[]>([]);
  const [selection, setSelection] = useState("");
  const [eventLog, setEventLog] = useState<RunEvent[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [changing, setChanging] = useState(false);
  const selected = selection || (latest?.user_id === userId ? latest.id : "") || rows[0]?.id;
  const stored = rows.find((row) => row.id === selected);
  const current = stored ?? (latest && latest.id === selected && latest.user_id === userId
    ? latest : null);
  const visibleEvents = eventLog.filter((event) => event.run_id === selected);

  useEffect(() => {
    const controller = new AbortController();
    void listRuns(userId, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setRows((previous) => list.map((row) => {
          const fresher = previous.find((item) => item.id === row.id && item.event_seq > row.event_seq);
          return fresher ?? row;
        }));
      })
      .catch((failure: Error) => { if (!controller.signal.aborted) setError(failure.message); });
    return () => controller.abort();
  }, [userId, refresh, latest, reload]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    let cursor = 0;
    let failures = 0;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const update = async () => {
      const snapshot = await getRun(userId, selected, controller.signal);
      if (!controller.signal.aborted) {
        setRows((list) => {
          const prior = list.find((row) => row.id === snapshot.id);
          if (prior && prior.event_seq > snapshot.event_seq) return list;
          return [snapshot, ...list.filter((row) => row.id !== snapshot.id)]
            .sort((left, right) => right.created_at.localeCompare(left.created_at));
        });
      }
      return snapshot;
    };
    const consume = async () => {
      while (!controller.signal.aborted) {
        try {
          await streamRun(userId, selected, cursor, AbortSignal.any([
            controller.signal, AbortSignal.timeout(55_000),
          ]), (event) => {
            if (controller.signal.aborted || event.seq <= cursor) return;
            if (event.run_id !== selected || event.seq !== cursor + 1) {
              throw new RunEventProtocolError("任务进度出现记录缺口。");
            }
            cursor = event.seq;
            failures = 0;
            setEventLog((items) => {
              const previous = items.filter((stored) =>
                stored.run_id === selected && stored.seq < event.seq);
              return [...previous, event].slice(-100);
            });
            clearTimeout(refreshTimer);
            refreshTimer = setTimeout(() => { void update().catch(() => undefined); }, 100);
          });
          const snapshot = await update();
          if (terminalRun(snapshot.status)) return;
        } catch (failure) {
          if (controller.signal.aborted) return;
          if (failure instanceof ApiError && [401, 403, 404, 410].includes(failure.status)) {
            setError(failure.message);
            return;
          }
          if (++failures >= 4) {
            setError("进度暂时断开。可以刷新任务重连，当前仍会低频查询状态。");
            while (!controller.signal.aborted) {
              try {
                if (terminalRun((await update()).status)) return;
              } catch (error) {
                if (error instanceof ApiError && [401, 403, 404, 410].includes(error.status)) {
                  if (!controller.signal.aborted) setError(error.message);
                  return;
                }
              }
              await pause(15_000, controller.signal);
            }
            return;
          }
        }
        await pause(Math.min(8_000, 750 * 2 ** failures) + Math.random() * 250, controller.signal);
      }
    };
    void consume();
    return () => {
      controller.abort();
      clearTimeout(refreshTimer);
    };
  }, [userId, selected, refresh, reload]);

  async function change(approve?: boolean) {
    if (!current || changing) return;
    if (approve === undefined && !window.confirm("确认取消这个后台任务？")) return;
    setChanging(true);
    setError("");
    setNotice("");
    try {
      const row = approve === undefined
        ? await cancelRun(userId, current.id) : await decideRun(userId, current.id, approve);
      if (row.cancel_outcome === "already_terminal") {
        setNotice("任务已进入终态，保留原有结果。");
      }
      setRows((list) => list.some((item) => item.id === row.id)
        ? list.map((item) => item.id === row.id ? row : item) : [row, ...list]);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "任务状态更新失败");
    } finally {
      setChanging(false);
    }
  }

  return <section className="workspace run-center" id="runs">
    <div className="section-heading"><div><span>运行记录</span><h2>后台任务</h2></div>
      <p>前台关闭后仍会运行，回来查看进度与结果。</p></div>
    <button type="button" className="secondary" onClick={() => { setError(""); setReload(reload + 1); }}>刷新任务</button>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {rows.length > 0 && <label>选择任务
      <select value={selected ?? ""} onChange={(event) => { setError(""); setSelection(event.target.value); }}>
        {rows.map((row) => <option key={row.id} value={row.id}>
          {operations[row.operation]} · {statuses[row.status]} · {new Date(row.created_at).toLocaleString()}
        </option>)}
      </select>
    </label>}
    {!current && !error && <p>提交岗位分析、报告、文件或 Wiki 后会显示任务。</p>}
    {current && <article>
      <h3>{operations[current.operation]} · {statuses[current.status]}</h3>
      <p>{current.error_code ? reasons[current.error_code] ?? statuses[current.status]
        : `已尝试 ${current.attempts} 次`}</p>
      <div className="report-actions">
        {current.status === "waiting_confirmation" && <>
          <button type="button" disabled={changing} onClick={() => change(true)}>确认执行</button>
          <button type="button" className="secondary" disabled={changing} onClick={() => change(false)}>拒绝</button>
        </>}
        {!terminalRun(current.status) && current.status !== "waiting_confirmation" &&
          <button type="button" className="secondary" disabled={changing} onClick={() => change()}>取消任务</button>}
        {current.status === "succeeded" && current.result &&
          <button type="button" onClick={() => onOpen(current)}>打开结果</button>}
      </div>
      {current.result?.count !== undefined &&
        <p>{current.result.count} 条证据 · {current.result.parse_status === "partial" ? "含待 OCR 扫描页" : "解析完成"}</p>}
      {visibleEvents.length > 0 && <ol className="run-timeline" aria-label="任务步骤时间线">
        {visibleEvents.map((event) => {
          const state = event.event_type.split(".")[1] ?? "info";
          const label = event.data.step
            ? `${steps[event.data.step] ?? event.data.step} · ${state === "running" ? "开始" : state === "failed" ? "失败" : "完成"}`
            : events[event.event_type] ?? event.event_type;
          return <li key={event.seq} className={`timeline-${state}`}>
            <span className="run-seq">#{event.seq}</span>
            <div>
              <strong>{label}</strong>
              <small>
                {event.event_type}
                {event.data.citation_count !== undefined && ` · ${event.data.citation_count} 条引用`}
                {event.data.duration_ms !== undefined && ` · ${event.data.duration_ms} ms`}
                {event.data.error_type && ` · ${event.data.error_type}`}
                {` · 代次 ${event.generation}`}
              </small>
            </div>
          </li>;
        })}
      </ol>}
    </article>}
  </section>;
}
