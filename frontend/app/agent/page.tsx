"use client";

import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import {
  createAgentSession,
  decideAgentApproval,
  getRuntimeCapabilities,
  getRuntimeStatus,
  getWorkspaceSession,
  listAgentApprovals,
  listAgentMessages,
  listAgentNotifications,
  listAgentSchedules,
  cancelAgentTask,
  listAgentSessions,
  listTeamTasks,
  retryAgentTask,
  markAgentNotificationsRead,
  searchAgentFacts,
  streamRun,
  submitAgentTurn,
  terminalRun,
  type AgentApproval,
  type AgentMessage,
  type AgentNotification,
  type AgentSchedule,
  type AgentSearchResult,
  type AgentSession,
  type AgentTask,
  type RunEvent,
  type RunStatus,
  type RuntimeCapabilities,
  type RuntimeStatus,
} from "@/lib/api";
import { desktopAvailable, notify } from "@/lib/desktop";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react";

const subscribeStorage = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
};

const readDnd = () => window.localStorage.getItem("careerlens-dnd") === "1";

export default function AgentPage() {
  const [userId, setUserId] = useState("demo-user");
  const [title, setTitle] = useState("Agent 会话");
  const [input, setInput] = useState("");
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [approvals, setApprovals] = useState<AgentApproval[]>([]);
  const [capabilities, setCapabilities] = useState<RuntimeCapabilities | null>(null);
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveRunId, setLiveRunId] = useState("");
  const [liveStatus, setLiveStatus] = useState<RunStatus | "">("");
  const [liveEvents, setLiveEvents] = useState<RunEvent[]>([]);
  const [schedules, setSchedules] = useState<AgentSchedule[]>([]);
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResult, setSearchResult] = useState<AgentSearchResult | null>(null);
  const [teamId, setTeamId] = useState("");
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  // Persisted preference read through useSyncExternalStore: no setState in an
  // effect, and the server snapshot is always "off".
  const storedDnd = useSyncExternalStore(subscribeStorage, readDnd, () => false);
  const [dndOverride, setDndOverride] = useState<boolean | null>(null);
  const dnd = dndOverride ?? storedDnd;
  const [activeNotification, setActiveNotification] = useState("");
  const liveCursor = useRef(0);

  const refresh = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const [nextSessions, nextApprovals, nextCaps, nextStatus] = await Promise.all([
        listAgentSessions(id),
        listAgentApprovals(id),
        getRuntimeCapabilities(id),
        getRuntimeStatus(id),
      ]);
      setSessions(nextSessions);
      setApprovals(nextApprovals);
      setCapabilities(nextCaps);
      setStatus(nextStatus);
      if (selectedId) {
        setMessages(await listAgentMessages(id, selectedId));
      }
      const [nextSchedules, nextNotifications] = await Promise.all([
        listAgentSchedules(id),
        listAgentNotifications(id),
      ]);
      setSchedules(nextSchedules);
      setNotifications(nextNotifications);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "刷新 Agent 状态失败。");
    }
  }, [selectedId]);

  useEffect(() => {
    const controller = new AbortController();
    void getWorkspaceSession(controller.signal).then((session) => {
      if (!controller.signal.aborted && session.user_id) setUserId(session.user_id);
    }, () => undefined);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    queueMicrotask(() => void refresh(userId));
  }, [refresh, userId]);

  useEffect(() => {
    if (!userId) return;
    const timer = window.setInterval(() => void refresh(userId), 2500);
    return () => window.clearInterval(timer);
  }, [refresh, userId]);

  // Live events for the run just submitted. The SSE endpoint replays from
  // Last-Event-ID, so a reconnect does not lose or duplicate frames; the
  // database stays the authority and the poll above still reconciles.
  // Deliver one OS toast per new unread notification. The in-app list stays the
  // source of truth; a failed toast is not retried in a loop.
  useEffect(() => {
    if (!desktopAvailable() || !notifications.length || dnd) return;
    const seen = new Set(
      JSON.parse(window.localStorage.getItem("careerlens-toast-seen") ?? "[]") as string[],
    );
    const fresh = notifications.find((item) => !item.read && !seen.has(item.fact_key));
    if (!fresh) return;
    seen.add(fresh.fact_key);
    window.localStorage.setItem(
      "careerlens-toast-seen",
      JSON.stringify([...seen].slice(-200)),
    );
    void notify(fresh.title, fresh.detail);
  }, [notifications, dnd]);

  useEffect(() => {
    if (!liveRunId || !userId) return;
    const controller = new AbortController();
    let closed = false;
    void (async () => {
      try {
        await streamRun(userId, liveRunId, liveCursor.current, controller.signal, (event) => {
          liveCursor.current = Math.max(liveCursor.current, event.seq);
          setLiveEvents((current) => [...current.slice(-40), event]);
          if (event.event_type.startsWith("run.")) {
            const status = String((event.data as { status?: string }).status ?? "");
            if (status) setLiveStatus(status as RunStatus);
          }
        });
      } catch {
        // Aborted on unmount or a transient read error; polling covers recovery.
      } finally {
        if (!closed) setNotice((current) => current || "事件流已结束；最终结果以数据库为准。");
      }
    })();
    return () => {
      closed = true;
      controller.abort();
    };
  }, [liveRunId, userId]);

  async function createSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await createAgentSession(userId, title || "Agent 会话");
      setSelectedId(created.id);
      setNotice(`已创建会话 ${created.id.slice(0, 8)}。`);
      await refresh(userId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建会话失败。");
    } finally {
      setBusy(false);
    }
  }

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !input.trim()) return;
    setBusy(true);
    setError("");
    try {
      const run = (await submitAgentTurn(
        userId, selectedId, input.trim(), crypto.randomUUID(),
      )) as { id?: string; status?: string };
      setInput("");
      if (run?.id) {
        liveCursor.current = 0;
        setLiveEvents([]);
        setLiveStatus((run.status as RunStatus) ?? "queued");
        setLiveRunId(run.id);
      }
      setNotice("已提交；Run 由 scheduler 异步执行，下面会实时显示事件。");
      await refresh(userId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交失败。");
    } finally {
      setBusy(false);
    }
  }

  async function decide(runId: string, approve: boolean) {
    setBusy(true);
    setError("");
    try {
      await decideAgentApproval(userId, runId, approve);
      setNotice(approve ? "已批准；写工具将只执行一次。" : "已拒绝；不会执行写工具。");
      await refresh(userId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审批失败。");
    } finally {
      setBusy(false);
    }
  }

  async function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchTerm.trim()) return;
    try {
      setSearchResult(await searchAgentFacts(userId, searchTerm.trim()));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "搜索失败。");
    }
  }

  async function loadTasks(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!teamId.trim()) return;
    try {
      setTasks(await listTeamTasks(userId, teamId.trim()));
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取任务树失败。");
    }
  }

  async function markOne(factKey: string) {
    try {
      await markAgentNotificationsRead(userId, [factKey]);
      setNotifications(await listAgentNotifications(userId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "标记已读失败。");
    }
  }

  function toggleDnd(next: boolean) {
    setDndOverride(next);
    window.localStorage.setItem("careerlens-dnd", next ? "1" : "0");
    setNotice(next ? "已开启免打扰：不再弹系统通知。" : "已关闭免打扰。");
  }

  async function cancelTask(taskId: string) {
    try {
      await cancelAgentTask(userId, taskId);
      await loadTasks();
      setNotice("已取消该任务及其子任务。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "取消失败。");
    }
  }

  async function retryTask(taskId: string) {
    try {
      const created = await retryAgentTask(userId, taskId);
      setTeamId(created.team_id);
      setTasks(await listTeamTasks(userId, created.team_id));
      setNotice("已创建重跑团队；原团队记录保持不变。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重跑失败。");
    }
  }

  async function markAllRead() {
    const unread = notifications.filter((item) => !item.read).map((item) => item.fact_key);
    if (!unread.length) return;
    try {
      await markAgentNotificationsRead(userId, unread);
      setNotifications(await listAgentNotifications(userId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "标记已读失败。");
    }
  }

  return (
    <main className="site-page workspace-page">
      <SiteHeader active="workspace" />
      <section className="workspace" id="agent" aria-label="Agent 工作台">
        <div className="section-heading light">
          <div><span>07 / AGENT</span><h2>持久 Agent 会话</h2></div>
          <p>会话、消息、审批与运行时状态都来自业务库；关闭窗口不会中断后台 Run。</p>
        </div>

        <div className="two-column">
          <form className="input-panel" onSubmit={createSession}>
            <div className="panel-title"><h3>连接与新建会话</h3><span>LOCAL</span></div>
            <label>用户标识<input value={userId} required onChange={(e) => setUserId(e.target.value)} /></label>
            <label>会话标题<input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></label>
            <button type="submit" disabled={busy || !userId.trim()}>新建会话</button>
          </form>

          <div className="input-panel">
            <div className="panel-title"><h3>会话列表</h3><span>{sessions.length}</span></div>
            <div className="skill-list">
              {sessions.map((session) => (
                <article key={session.id}>
                  <button type="button" className="secondary" onClick={() => setSelectedId(session.id)}>
                    <strong>{session.title || session.id.slice(0, 8)}</strong>
                  </button>
                  <small>{session.status} · rev {session.head_revision} · gen {session.runtime_generation}</small>
                </article>
              ))}
              {!sessions.length && <p>还没有会话。先新建一个，再发送消息。</p>}
            </div>
          </div>
        </div>

        <div className="two-column">
          <form className="input-panel" onSubmit={send}>
            <div className="panel-title"><h3>发送消息</h3><span>{selectedId.slice(0, 8) || "未选择"}</span></div>
            <label>
              消息
              <textarea
                value={input}
                rows={5}
                maxLength={20000}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(event) => {
                  // Ctrl/Cmd+Enter submits; plain Enter keeps newline semantics.
                  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="向 Agent 提问或让它整理证据…（Ctrl+Enter 提交）"
              />
            </label>
            <button type="submit" disabled={busy || !selectedId || !input.trim()}>提交一轮</button>
          </form>

          <div className="input-panel">
            <div className="panel-title"><h3>消息历史</h3><span>{messages.length}</span></div>
            <div className="skill-list">
              {messages.map((message) => (
                <article key={message.id}>
                  <strong>{message.role}</strong>
                  <small>{message.content}</small>
                  <small>seq {message.message_seq}{message.citations.length ? ` · ${message.citations.length} 条引用` : ""}</small>
                </article>
              ))}
              {!messages.length && <p>选择会话后这里会显示持久消息历史。</p>}
            </div>
          </div>
        </div>

        <div className="two-column">
          <div className="input-panel">
            <div className="panel-title"><h3>待审批</h3><span>{approvals.length}</span></div>
            <div className="skill-list">
              {approvals.map((item) => (
                <article key={item.id}>
                  <strong>{item.tool}</strong>
                  <small>{item.scope} · digest {item.args_digest.slice(0, 12)}</small>
                  <small>Run {item.run_id.slice(0, 8)}</small>
                  <div className="capture-review-actions">
                    <button type="button" disabled={busy} onClick={() => void decide(item.run_id, true)}>批准</button>
                    <button type="button" className="secondary" disabled={busy} onClick={() => void decide(item.run_id, false)}>拒绝</button>
                  </div>
                </article>
              ))}
              {!approvals.length && <p>没有待审批工具。</p>}
            </div>
          </div>

          <div className="input-panel">
            <div className="panel-title"><h3>运行时状态</h3><span>v1</span></div>
            <p>启用：{capabilities ? String(capabilities.agent_runtime_enabled) : "未知"} · 模型：{capabilities?.model_provider ?? "未知"}</p>
            <p>Run：{status ? JSON.stringify(status.runs) : "未知"} · 待审批：{status?.pending_approvals ?? "未知"}</p>
            <p>只读工具：{capabilities?.read_only_tools.join(", ") || "未知"}</p>
            <p>写工具：{capabilities?.write_tools.join(", ") || "未知"}</p>
            <small>未启动 scheduler 时 Run 会停在 queued，这不是成功。</small>
          </div>
        </div>

        <div className="two-column">
          <div className="input-panel">
            <div className="panel-title">
              <h3>实时事件</h3>
              <span>{liveStatus || "未连接"}</span>
            </div>
            <div className="skill-list" aria-live="polite">
              {liveEvents.map((event) => (
                <article key={`${event.seq}-${event.event_type}`}>
                  <strong>#{event.seq} {event.event_type}</strong>
                  <small>{JSON.stringify(event.data)}</small>
                </article>
              ))}
              {!liveEvents.length && (
                <p>提交一轮后，这里会按 seq 显示 SSE 事件；断线会从上次 seq 续看。</p>
              )}
            </div>
            {liveStatus && terminalRun(liveStatus as RunStatus) ? (
              <small>Run 已终态：{liveStatus}。消息与审批以上面的持久数据为准。</small>
            ) : null}
          </div>

          <div className="input-panel">
            <div className="panel-title">
              <h3>计划</h3>
              <span>{schedules.length}</span>
            </div>
            <div className="skill-list">
              {schedules.map((schedule) => (
                <article key={schedule.id}>
                  <strong>{schedule.name}</strong>
                  <small>
                    {schedule.state} · {schedule.misfire_policy} · 每 {schedule.interval_seconds}s
                  </small>
                  <small>下次到期 {new Date(schedule.next_due * 1000).toLocaleString()}</small>
                </article>
              ))}
              {!schedules.length && <p>还没有计划；计划由 API 创建，到点由 scheduler 触发。</p>}
            </div>
          </div>
        </div>

        <div className="two-column">
          <form className="input-panel" onSubmit={loadTasks}>
            <div className="panel-title">
              <h3>任务树</h3>
              <span>{tasks.length}</span>
            </div>
            <label>
              团队 ID
              <input
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                placeholder="从检索结果里选一个团队的 id"
              />
            </label>
            <button type="submit" disabled={!teamId.trim()}>读取任务树</button>
            <div className="skill-list">
              {tasks
                .filter((task) => !task.parent_id)
                .map((parent) => (
                  <article key={parent.id}>
                    <strong>{parent.title || parent.id.slice(0, 8)}</strong>
                    <small>{parent.role} · {parent.status} · 预算 {String(parent.budget?.attempts ?? 0)} 次尝试</small>
                    <small>Run {parent.run_id ? parent.run_id.slice(0, 8) : "未绑定"}</small>
                    <div className="task-actions">
                      <button type="button" className="secondary" onClick={() => void retryTask(parent.id)}>
                        重跑整个团队
                      </button>
                    </div>
                  </article>
                ))}
              {tasks
                .filter((task) => task.parent_id)
                .map((child) => (
                  <article key={child.id} className="task-child">
                    <strong>↳ {child.title || child.id.slice(0, 8)}</strong>
                    <small>{child.role} · {child.status}</small>
                    <small>{child.error ? `错误：${child.error}` : "无错误"}</small>
                    <div className="task-actions">
                      {["queued", "running", "waiting"].includes(child.status) ? (
                        <button type="button" className="secondary" onClick={() => void cancelTask(child.id)}>
                          取消
                        </button>
                      ) : null}
                      {["failed", "cancelled"].includes(child.status) ? (
                        <button type="button" onClick={() => void retryTask(child.id)}>
                          重跑
                        </button>
                      ) : null}
                    </div>
                  </article>
                ))}
              {!tasks.length && <p>输入团队 ID 后显示父子任务与各自状态；任务结果仍以任务详情为准。</p>}
            </div>
          </form>

          <div className="input-panel">
            <div className="panel-title">
              <h3>通知</h3>
              <span>{notifications.filter((item) => !item.read).length} 未读</span>
            </div>
            <div className="task-actions">
              <button
                type="button"
                className={unreadOnly ? "" : "secondary"}
                aria-pressed={unreadOnly}
                onClick={() => setUnreadOnly((current) => !current)}
              >
                只看未读
              </button>
              <button
                type="button"
                role="switch"
                aria-checked={dnd}
                aria-label="免打扰"
                className={dnd ? "" : "secondary"}
                onClick={() => toggleDnd(!dnd)}
              >
                {dnd ? "免打扰已开" : "免打扰"}
              </button>
            </div>
            <div className="skill-list" aria-live="polite">
              {(unreadOnly ? notifications.filter((item) => !item.read) : notifications)
                .slice(0, 10)
                .map((item) => (
                  <article key={item.fact_key} className={activeNotification === item.fact_key ? "is-active" : ""}>
                    <button
                      type="button"
                      className="linklike"
                      onClick={() => {
                        setActiveNotification(item.fact_key);
                        // Click-through: a run reference loads it into the live
                        // panel; the notification itself stays in the list.
                        if (item.ref_id && item.kind !== "schedule_skipped") {
                          liveCursor.current = 0;
                          setLiveEvents([]);
                          setLiveRunId(item.ref_id);
                        }
                        if (!item.read) void markOne(item.fact_key);
                      }}
                    >
                      <strong>{item.title}</strong>
                    </button>
                    <small>{item.detail}</small>
                    <small>{item.read ? "已读" : "未读"} · {item.kind}</small>
                  </article>
                ))}
              {!notifications.length && <p>没有通知。通知由待审批、失败 Run、失败任务与跳过计划派生。</p>}
              {unreadOnly && notifications.length > 0 && !notifications.some((item) => !item.read) ? (
                <p>没有未读通知。</p>
              ) : null}
            </div>
            <button type="button" className="secondary" onClick={() => void markAllRead()}>
              全部标记已读
            </button>
          </div>

          <form className="input-panel" onSubmit={runSearch}>
            <div className="panel-title">
              <h3>检索</h3>
              <span>READ ONLY</span>
            </div>
            <label>
              关键词
              <input value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="会话、任务、角色或计划" />
            </label>
            <button type="submit" disabled={!searchTerm.trim()}>搜索</button>
            {searchResult ? (
              <div className="skill-list">
                <small>会话 {searchResult.sessions.length} · 任务 {searchResult.tasks.length} · 角色 {searchResult.roles.length} · 计划 {searchResult.schedules.length}</small>
                {searchResult.sessions.map((item) => (
                  <article key={`s-${item.id}`}>
                    <strong>{item.title || item.id.slice(0, 8)}</strong>
                    <small>会话 · {item.status}</small>
                  </article>
                ))}
                {searchResult.tasks.map((item) => (
                  <article key={`t-${item.id}`}>
                    <strong>{item.title || item.id.slice(0, 8)}</strong>
                    <small>任务 · {item.status} · 团队 {item.team_id.slice(0, 8)}</small>
                  </article>
                ))}
                {searchResult.schedules.map((item) => (
                  <article key={`p-${item.id}`}>
                    <strong>{item.name}</strong>
                    <small>计划 · {item.state}</small>
                  </article>
                ))}
              </div>
            ) : (
              <p>搜索只读、按用户隔离，每类结果有上限。</p>
            )}
          </form>
        </div>

        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
      </section>
      <SiteFooter />
    </main>
  );
}
