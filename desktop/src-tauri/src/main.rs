mod daemon;
mod tray;

use daemon::DaemonState;
use tauri::{Manager, RunEvent, WindowEvent};

fn main() {
    let app = tauri::Builder::default()
        .manage(DaemonState::from_env())
        .invoke_handler(tauri::generate_handler![
            daemon::daemon_status,
            daemon::daemon_restart,
            daemon::daemon_stop
        ])
        .setup(|app| {
            app.state::<DaemonState>().spawn_if_configured();
            tray::setup(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("careerlens desktop host failed to build");

    app.run(|app, event| match event {
        // Closing the main window hides it; only the tray "退出" or the
        // OS session shutdown is allowed to end the Host and daemon.
        RunEvent::WindowEvent {
            label,
            event: WindowEvent::CloseRequested { api, .. },
            ..
        } => {
            api.prevent_close();
            if let Some(window) = app.get_webview_window(&label) {
                let _ = window.hide();
            }
            eprintln!("[careerlens] main window hidden to tray");
        }
        RunEvent::Exit => {
            app.state::<DaemonState>().shutdown();
        }
        _ => {}
    });
}
