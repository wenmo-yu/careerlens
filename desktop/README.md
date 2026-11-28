# CareerLens Desktop Host

Tauri 2 shell for CareerLens. It owns the window, tray and daemon process
lifecycle only. Business facts stay in FastAPI and the database; the Host never
connects to the database directly.

## Build

Prerequisites: Node 22, pnpm 10, Rust stable with MSVC, WebView2 runtime, and the
Windows SDK for the Windows bundle.

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build:desktop
cargo check --manifest-path desktop/src-tauri/Cargo.toml
cd desktop/src-tauri && pnpm dlx @tauri-apps/cli@2 build --ci
```

`frontend/next.config.ts` stays on `standalone`; the desktop build uses
`frontend/next.desktop.config.ts` through `desktop/scripts/build-frontend.mjs`
and writes only `frontend/out/` (gitignored).

## Runtime configuration

| Variable | Meaning |
| --- | --- |
| `CAREERLENS_DAEMON_EXE` | Packaged daemon executable; empty disables autostart |
| `CAREERLENS_API_EXE` | Packaged backend executable passed as `--api-exe` |
| `CAREERLENS_DAEMON_PIPE` | Named pipe override; default `\\.\pipe\careerlens-daemon` |
| `CAREERLENS_DESKTOP_NO_DAEMON` | `1` keeps the Host up without starting a daemon |

The Host sends contract-v1 JSON frames on one named-pipe connection: `hello`,
then `status`, `restart` or `stop`. It does not expose user content, tokens or
prompts in logs.

## Autostart (off by default)

The settings page (`/settings`) exposes one switch. Enabling it writes
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `CareerLens` with the
value `"<exe>" --autostart`; disabling removes the value. Nothing in startup
calls this: the user action is the only path.

- It is per-user, needs no elevation, and shows up in Task Manager's startup tab.
- `--autostart` starts the Host hidden in the tray instead of stealing focus.
- If the install directory moves, the stored command no longer matches; the
  settings page reports `matchesCurrentExe=false` and the user toggles it again.
- Waking a sleeping machine is a separate Task Scheduler `WakeToRun` definition
  (`backend/app/runtime/windows_tasks.py`). It is never registered automatically.

## Notifications

`notify(title, body)` shows a Windows toast through WinRT. The XML is built and
escaped in Rust; the helper script only receives it through an environment
variable and an encoded command payload, and runs without a console window.
Title/body are length-capped, control characters are stripped, and failures are
returned to the caller instead of being swallowed. The AUMID is
`com.careerlens.desktop`.

## Window and exit semantics

- Closing the main window hides it to the tray; the daemon and API keep running.
- Tray menu: open the window or quit.
- Quit sends `stop` to the daemon. If the control plane is unreachable, the Host
  exits anyway and only kills a daemon child it started itself.

## Current boundaries

- The installer is unsigned unless signing secrets are configured; unsigned
  builds are release candidates, not stable.
- Install/uninstall, upgrade/rollback, auto-update, code signing and a real
  packaged daemon end-to-end run are not yet verified.
- The Host is Windows-first. Non-Windows builds compile with a control-plane
  stub that returns an explicit error.
