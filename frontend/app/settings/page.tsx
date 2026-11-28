"use client";

import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import {
  desktopAvailable,
  getAutostartStatus,
  setAutostart,
  type AutostartStatus,
} from "@/lib/desktop";
import { useEffect, useState, useSyncExternalStore } from "react";

// The desktop bridge only exists after hydration. useSyncExternalStore gives a
// server snapshot (false) and a client snapshot without a setState-in-effect.
const noopSubscribe = () => () => {};

export default function SettingsPage() {
  const inDesktop = useSyncExternalStore(noopSubscribe, desktopAvailable, () => false);
  const [status, setStatus] = useState<AutostartStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!inDesktop) return;
    let live = true;
    void getAutostartStatus().then((next) => {
      if (live) setStatus(next);
    });
    return () => {
      live = false;
    };
  }, [inDesktop]);

  async function toggle(next: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await setAutostart(next);
      if (!updated) {
        setError("写入启动项失败；请确认应用有当前用户注册表写权限。");
        return;
      }
      setStatus(updated);
      setNotice(next ? "已开启：下次登录会自动在托盘启动。" : "已关闭：登录时不再自动启动。");
    } finally {
      setBusy(false);
    }
  }

  const enabled = status?.enabled ?? false;

  return (
    <main className="site-page workspace-page">
      <SiteHeader active="workspace" />
      <section className="workspace" id="settings" aria-label="桌面设置">
        <div className="section-heading light">
          <div>
            <span>08 / SETTINGS</span>
            <h2>桌面与后台</h2>
          </div>
          <p>这些开关只影响本机桌面宿主，不改动业务数据；浏览器里打开时全部只读。</p>
        </div>

        <div className="two-column">
          <div className="input-panel">
            <div className="panel-title">
              <h3>开机自启</h3>
              <span>{enabled ? "已开启" : "已关闭"}</span>
            </div>
            <p>
              开启后，登录 Windows 时会在托盘启动 CareerLens，持久计划才能在到期时真正执行；
              关闭时只有你手动打开应用后才会补跑错过的计划。
            </p>
            <p>
              实现方式是当前用户的启动项（注册表
              <code> HKCU\Software\Microsoft\Windows\CurrentVersion\Run </code>
              下的 <code>CareerLens</code> 值），不需要管理员权限，可在任务管理器“启动”标签里随时禁用。
            </p>
            {inDesktop ? (
              <button
                type="button"
                role="switch"
                aria-checked={enabled}
                aria-label="开机自启"
                className={enabled ? "" : "secondary"}
                disabled={busy}
                onClick={() => void toggle(!enabled)}
              >
                {enabled ? "关闭开机自启" : "开启开机自启"}
              </button>
            ) : (
              <p className="settings-hint">仅在桌面应用中可修改；当前是浏览器访问。</p>
            )}
            {status && !status.matchesCurrentExe && enabled ? (
              <p className="settings-hint">
                记录的启动路径与当前程序位置不一致（可能是升级或移动了安装目录）。关闭再开启即可刷新。
              </p>
            ) : null}
            {status?.command ? <pre className="settings-command">{status.command}</pre> : null}
            {error ? <p className="settings-error" role="alert">{error}</p> : null}
            {notice ? <p className="settings-notice" role="status">{notice}</p> : null}
          </div>

          <div className="input-panel">
            <div className="panel-title">
              <h3>计划与唤醒</h3>
              <span>未注册</span>
            </div>
            <p>
              自启解决“登录后是否在跑”，唤醒解决“到点时机器在睡眠”。后者需要 Windows
              计划任务的 <code>WakeToRun</code> 能力，配置为当前用户、最低权限、每 30 分钟一次。
            </p>
            <p>
              当前版本只提供任务定义与显式注册入口，<strong>不会自动注册</strong>；真实睡眠/唤醒与
              跨时区行为仍未在本机验证，所以这里不声称已生效。
            </p>
            <p className="settings-hint">
              未实现前，睡眠期间到期的计划会在下次启动时按 <code>skip</code> /{" "}
              <code>run_once</code> 策略对账。
            </p>
          </div>
        </div>

        <div className="two-column">
          <div className="input-panel">
            <div className="panel-title">
              <h3>关闭窗口的行为</h3>
              <span>隐藏到托盘</span>
            </div>
            <p>
              点击窗口关闭按钮只会隐藏窗口，后台会话与 Run 不中断；真正退出请用托盘菜单的“退出”，
              退出时会先停止 daemon 再结束进程。
            </p>
          </div>

          <div className="input-panel">
            <div className="panel-title">
              <h3>范围说明</h3>
              <span>LOCAL</span>
            </div>
            <p>
              以上设置都只作用于本机，不写业务库、不同步到其他设备。Agent 的工具权限、审批与
              数据访问仍由服务端 scope 与工具账本决定，不受这里的开关影响。
            </p>
          </div>
        </div>
      </section>
      <SiteFooter />
    </main>
  );
}
