//! Owns the optional daemon child process and the v1 control-plane client.
//!
//! This module never talks to the business database or HTTP API. All state
//! changes go through the named-pipe control protocol in
//! `contracts/daemon-control-v1.json`.

use serde_json::{json, Value};
use std::env;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

const DEFAULT_PIPE: &str = r"\\.\pipe\careerlens-daemon";

pub struct DaemonState {
    pipe_name: String,
    child: Mutex<Option<Child>>,
    stopping: AtomicBool,
}

impl DaemonState {
    pub fn from_env() -> Self {
        Self {
            pipe_name: env::var("CAREERLENS_DAEMON_PIPE")
                .ok()
                .filter(|value| !value.is_empty())
                .unwrap_or_else(|| DEFAULT_PIPE.to_string()),
            child: Mutex::new(None),
            stopping: AtomicBool::new(false),
        }
    }

    /// Start the daemon only when both executables are explicitly configured.
    /// The child's stdio is discarded so no business content reaches our stdout.
    pub fn spawn_if_configured(&self) {
        if env::var("CAREERLENS_DESKTOP_NO_DAEMON").as_deref() == Ok("1") {
            eprintln!("[careerlens] daemon autostart disabled by environment");
            return;
        }
        let daemon_exe = env::var("CAREERLENS_DAEMON_EXE").unwrap_or_default();
        if daemon_exe.is_empty() {
            eprintln!("[careerlens] daemon autostart skipped: no daemon executable configured");
            return;
        }
        if !Path::new(&daemon_exe).is_file() {
            eprintln!("[careerlens] daemon autostart skipped: daemon executable not found");
            return;
        }
        let api_exe = env::var("CAREERLENS_API_EXE").unwrap_or_default();
        if api_exe.is_empty() {
            eprintln!("[careerlens] daemon autostart skipped: api executable not configured");
            return;
        }

        let mut command = Command::new(&daemon_exe);
        command
            .arg("--api-exe")
            .arg(&api_exe)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        match command.spawn() {
            Ok(child) => {
                if let Ok(mut slot) = self.child.lock() {
                    *slot = Some(child);
                }
                eprintln!("[careerlens] daemon autostart requested");
            }
            Err(_) => eprintln!("[careerlens] daemon autostart failed"),
        }
    }

    /// Ask the daemon to stop. Idempotent from the Host's point of view.
    pub fn stop(&self) -> Result<Value, String> {
        if self.stopping.swap(true, Ordering::SeqCst) {
            return Ok(json!({ "stopping": true, "already_requested": true }));
        }
        control::send(&self.pipe_name, "stop", json!({}))
    }

    /// Exit path: send `stop`, then make sure an unreachable daemon does not
    /// leave a Host-owned daemon process behind. Never blocks on child exit.
    pub fn shutdown(&self) {
        let stop_result = self.stop();
        match stop_result {
            Ok(_) => eprintln!("[careerlens] daemon stop accepted"),
            Err(_) => {
                eprintln!("[careerlens] daemon control unavailable at exit");
                if let Ok(mut slot) = self.child.lock() {
                    if let Some(child) = slot.as_mut() {
                        let _ = child.kill();
                    }
                }
            }
        }
        if let Ok(mut slot) = self.child.lock() {
            *slot = None;
        }
    }
}

#[tauri::command]
pub fn daemon_status(state: tauri::State<'_, DaemonState>) -> Result<Value, String> {
    control::send(&state.pipe_name, "status", json!({}))
}

#[tauri::command]
pub fn daemon_restart(role: String, state: tauri::State<'_, DaemonState>) -> Result<Value, String> {
    if role != "api" && role != "worker" {
        return Err("invalid daemon role (expected api or worker)".to_string());
    }
    control::send(&state.pipe_name, "restart", json!({ "role": role }))
}

#[tauri::command]
pub fn daemon_stop(state: tauri::State<'_, DaemonState>) -> Result<Value, String> {
    state.stop()
}

#[cfg(windows)]
mod control {
    use super::*;

    const PROTOCOL: u32 = 1;
    const CLIENT: &str = "careerlens-desktop";
    const CLIENT_VERSION: &str = "0.4.0";
    const MAX_FRAME_BYTES: usize = 65_536;
    const PIPE_TIMEOUT_MS: u32 = 1500;
    const HANDSHAKE_ATTEMPTS: u32 = 3;
    const GENERIC_READ: u32 = 0x8000_0000;
    const GENERIC_WRITE: u32 = 0x4000_0000;
    const OPEN_EXISTING: u32 = 3;
    const INVALID_HANDLE_VALUE: isize = -1;

    type Handle = isize;

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateFileW(
            lp_file_name: *const u16,
            dw_desired_access: u32,
            dw_share_mode: u32,
            lp_security_attributes: *mut std::ffi::c_void,
            dw_creation_disposition: u32,
            dw_flags_and_attributes: u32,
            h_template_file: Handle,
        ) -> Handle;
        fn WaitNamedPipeW(lp_named_pipe_name: *const u16, n_time_out: u32) -> i32;
        fn WriteFile(
            h_file: Handle,
            lp_buffer: *const u8,
            n_number_of_bytes_to_write: u32,
            lp_number_of_bytes_written: *mut u32,
            lp_overlapped: *mut std::ffi::c_void,
        ) -> i32;
        fn ReadFile(
            h_file: Handle,
            lp_buffer: *mut u8,
            n_number_of_bytes_to_read: u32,
            lp_number_of_bytes_read: *mut u32,
            lp_overlapped: *mut std::ffi::c_void,
        ) -> i32;
        fn CloseHandle(h_object: Handle) -> i32;
    }

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn open_pipe(pipe_name: &str) -> Result<Handle, String> {
        let name = wide(pipe_name);
        let handle = unsafe {
            CreateFileW(
                name.as_ptr(),
                GENERIC_READ | GENERIC_WRITE,
                0,
                std::ptr::null_mut(),
                OPEN_EXISTING,
                0,
                0,
            )
        };
        if handle == INVALID_HANDLE_VALUE {
            // A single-instance server may briefly be busy between accepts.
            unsafe {
                WaitNamedPipeW(name.as_ptr(), PIPE_TIMEOUT_MS);
                let retry = CreateFileW(
                    name.as_ptr(),
                    GENERIC_READ | GENERIC_WRITE,
                    0,
                    std::ptr::null_mut(),
                    OPEN_EXISTING,
                    0,
                    0,
                );
                if retry == INVALID_HANDLE_VALUE {
                    return Err("daemon pipe unavailable".to_string());
                }
                return Ok(retry);
            }
        }
        Ok(handle)
    }

    fn exchange(handle: Handle, frame: &Value) -> Result<Value, String> {
        let mut request = serde_json::to_vec(frame).map_err(|_| "control frame encoding failed")?;
        if request.len() >= MAX_FRAME_BYTES {
            return Err("control frame too large".to_string());
        }
        request.push(b'\n');

        let mut written: u32 = 0;
        let ok = unsafe {
            WriteFile(
                handle,
                request.as_ptr(),
                request.len() as u32,
                &mut written,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 || written as usize != request.len() {
            return Err("daemon pipe write failed".to_string());
        }

        let mut response = vec![0u8; MAX_FRAME_BYTES];
        let mut read: u32 = 0;
        let ok = unsafe {
            ReadFile(
                handle,
                response.as_mut_ptr(),
                response.len() as u32,
                &mut read,
                std::ptr::null_mut(),
            )
        };
        if ok == 0 || read as usize > response.len() {
            return Err("daemon pipe read failed".to_string());
        }
        serde_json::from_slice(&response[..read as usize])
            .map_err(|_| "invalid control response".to_string())
    }

    fn close(handle: Handle) {
        unsafe {
            CloseHandle(handle);
        }
    }

    /// One connection carries `hello` and the actual command. The daemon's
    /// session state is per connection, so splitting frames across connections
    /// would always produce `not_ready`.
    pub fn send(pipe_name: &str, command: &str, params: Value) -> Result<Value, String> {
        let hello = json!({
            "command": "hello",
            "params": {
                "protocol": PROTOCOL,
                "client": CLIENT,
                "client_version": CLIENT_VERSION
            }
        });
        let request = json!({ "command": command, "params": params });

        for _ in 0..HANDSHAKE_ATTEMPTS {
            let handle = open_pipe(pipe_name)?;
            let handshake = exchange(handle, &hello);
            match handshake {
                Ok(response) if response.get("ok") == Some(&Value::Bool(true)) => {
                    if response.get("protocol") != Some(&json!(PROTOCOL)) {
                        close(handle);
                        return Err("daemon protocol mismatch".to_string());
                    }
                    let result = exchange(handle, &request);
                    close(handle);
                    let response = result?;
                    if response.get("ok") != Some(&Value::Bool(true)) {
                        let code = response
                            .get("code")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown_error");
                        return Err(format!("daemon rejected command: {}", code));
                    }
                    return Ok(response);
                }
                Ok(response)
                    if response.get("code")
                        == Some(&Value::String("protocol_mismatch".to_string())) =>
                {
                    close(handle);
                    return Err("daemon protocol mismatch".to_string());
                }
                _ => {
                    close(handle);
                    continue;
                }
            }
        }
        Err("daemon handshake unavailable".to_string())
    }
}

#[cfg(not(windows))]
mod control {
    use super::*;

    pub fn send(_pipe_name: &str, _command: &str, _params: Value) -> Result<Value, String> {
        // No named pipes off Windows: the Host remains fully compilable and
        // the commands fail cleanly instead of touching any local process.
        Err("daemon control requires Windows named pipes".to_string())
    }
}
