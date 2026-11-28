/**
 * Bridge to the Tauri host.
 *
 * The same bundle runs in a browser and inside the desktop shell, so every call
 * degrades to `null` outside Tauri instead of throwing. No new dependency: the
 * v2 runtime exposes `__TAURI_INTERNALS__.invoke`, which is what the official
 * `@tauri-apps/api` wraps anyway.
 */

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

export type AutostartStatus = {
  supported: boolean;
  enabled: boolean;
  matchesCurrentExe: boolean;
  command: string;
};

type RawAutostartStatus = {
  supported: boolean;
  enabled: boolean;
  matches_current_exe: boolean;
  command: string;
};

function bridge(): Invoke | null {
  const internals = (globalThis as { __TAURI_INTERNALS__?: { invoke?: Invoke } })
    .__TAURI_INTERNALS__;
  return typeof internals?.invoke === "function" ? internals.invoke.bind(internals) : null;
}

export function desktopAvailable(): boolean {
  return bridge() !== null;
}

function normalize(raw: unknown): AutostartStatus | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as RawAutostartStatus;
  if (typeof value.enabled !== "boolean") return null;
  return {
    supported: Boolean(value.supported),
    enabled: value.enabled,
    matchesCurrentExe: Boolean(value.matches_current_exe),
    command: String(value.command ?? ""),
  };
}

export async function getAutostartStatus(): Promise<AutostartStatus | null> {
  const invoke = bridge();
  if (!invoke) return null;
  try {
    return normalize(await invoke("autostart_status"));
  } catch {
    return null;
  }
}

export async function setAutostart(enabled: boolean): Promise<AutostartStatus | null> {
  const invoke = bridge();
  if (!invoke) return null;
  try {
    return normalize(await invoke("autostart_set", { enabled }));
  } catch {
    return null;
  }
}

/**
 * Show a Windows toast. Returns false outside the desktop shell or when the
 * helper fails; callers must not treat a failed toast as a lost notification —
 * the in-app list is still the source of truth.
 */
export async function notify(title: string, body: string): Promise<boolean> {
  const invoke = bridge();
  if (!invoke) return false;
  try {
    await invoke("notify", { title, body });
    return true;
  } catch {
    return false;
  }
}
