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
  listAgentSessions,
  submitAgentTurn,
  type AgentApproval,
  type AgentMessage,
  type AgentSession,
  type RuntimeCapabilities,
  type RuntimeStatus,
} from "@/lib/api";
import { useCallback, useEffect, useState, type FormEvent } from "react";

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
      await submitAgentTurn(userId, selectedId, input.trim(), crypto.randomUUID());
      setInput("");
      setNotice("已提交；Run 由 scheduler 异步执行，可继续查看消息与审批。");
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
            <label>消息<textarea value={input} rows={5} maxLength={20000}
              onChange={(e) => setInput(e.target.value)} placeholder="向 Agent 提问或让它整理证据…" /></label>
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

        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
      </section>
      <SiteFooter />
    </main>
  );
}
