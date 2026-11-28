//! Autostart on login, **default off**, opt-in from the settings page.
//!
//! Mechanism: the per-user Run key
//! (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`). It needs no
//! administrator rights, is visible in Task Manager's startup tab, and is
//! trivially reversible by the user. A machine-wide service or a Task Scheduler
//! entry would be harder to inspect and harder to undo, so it is not used here.
//!
//! What it buys: durable schedules (`agent_schedules`) only fire while a
//! scheduler process is alive. The scheduler reconciles missed due times on the
//! next start, but nothing runs while the app is closed. Autostart keeps the
//! host (and therefore the daemon/scheduler) present after login so a due time
//! actually becomes a run instead of a skipped occurrence.
//!
//! What it does not do: it does not wake a sleeping machine (that is a Task
//! Scheduler `WakeToRun` concern, see `backend/app/runtime/windows_tasks.py`)
//! and it does not run while the user is logged out.

use std::path::Path;

use serde::Serialize;
use winreg::enums::HKEY_CURRENT_USER;
use winreg::RegKey;

const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const VALUE_NAME: &str = "CareerLens";

/// Appended to the executable path so the host can start hidden in the tray.
pub const AUTOSTART_FLAG: &str = "--autostart";

#[derive(Debug, Serialize)]
pub struct AutostartStatus {
    pub supported: bool,
    pub enabled: bool,
    /// Whether the stored command still points at this executable. A moved or
    /// upgraded install keeps the old path until the user toggles it again.
    pub matches_current_exe: bool,
    pub command: String,
}

/// The exact command written to the Run key.
pub fn command_line(exe: &Path) -> String {
    format!("\"{}\" {}", exe.display(), AUTOSTART_FLAG)
}

/// True when this process was started by the autostart entry.
pub fn launched_by_autostart<I, S>(args: I) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    args.into_iter().any(|arg| arg.as_ref() == AUTOSTART_FLAG)
}

fn read_status() -> Result<AutostartStatus, String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let expected = command_line(&exe);
    let key = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey(RUN_KEY)
        .map_err(|error| error.to_string())?;
    let stored: Option<String> = key.get_value(VALUE_NAME).ok();
    Ok(AutostartStatus {
        supported: true,
        enabled: stored.is_some(),
        matches_current_exe: stored.as_deref() == Some(expected.as_str()),
        command: expected,
    })
}

fn write_enabled(enabled: bool) -> Result<AutostartStatus, String> {
    let exe = std::env::current_exe().map_err(|error| error.to_string())?;
    let key = RegKey::predef(HKEY_CURRENT_USER)
        .open_subkey_with_flags(RUN_KEY, winreg::enums::KEY_SET_VALUE | winreg::enums::KEY_QUERY_VALUE)
        .map_err(|error| error.to_string())?;
    if enabled {
        let command = command_line(&exe);
        key.set_value(VALUE_NAME, &command)
            .map_err(|error| error.to_string())?;
    } else {
        // Absent already is the desired state, not an error.
        match key.delete_value(VALUE_NAME) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.to_string()),
        }
    }
    read_status()
}

#[tauri::command]
pub fn autostart_status() -> Result<AutostartStatus, String> {
    read_status()
}

/// Enable or disable autostart. The caller must have shown the user what this
/// writes; there is no implicit enabling anywhere in the app.
#[tauri::command]
pub fn autostart_set(enabled: bool) -> Result<AutostartStatus, String> {
    write_enabled(enabled)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn command_quotes_paths_with_spaces() {
        let command = command_line(&PathBuf::from(r"C:\Program Files\CareerLens\careerlens.exe"));
        assert_eq!(
            command,
            r#""C:\Program Files\CareerLens\careerlens.exe" --autostart"#
        );
    }

    #[test]
    fn only_the_explicit_flag_counts() {
        assert!(launched_by_autostart(["careerlens.exe", "--autostart"]));
        assert!(!launched_by_autostart(["careerlens.exe"]));
        assert!(!launched_by_autostart(["careerlens.exe", "--autostart=true"]));
    }
}
