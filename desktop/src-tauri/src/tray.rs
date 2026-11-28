//! System tray and "close means hide" behaviour.

use crate::daemon::DaemonState;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{App, Manager, Runtime};

const MENU_OPEN: &str = "open_main_window";
const MENU_QUIT: &str = "quit";
const MAIN_WINDOW: &str = "main";

pub fn setup<R: Runtime>(app: &App<R>) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, MENU_OPEN, "打开主窗口", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, MENU_QUIT, "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &quit])?;

    let tray = TrayIconBuilder::with_id("careerlens-main")
        .icon(icon_image())
        .tooltip("CareerLens")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            MENU_OPEN => show_main_window(app),
            MENU_QUIT => {
                app.state::<DaemonState>().shutdown();
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(&tray.app_handle());
            }
        })
        .build(app)?;

    // Keep ownership inside the app so the icon lives as long as the process.
    app.manage(tray);
    Ok(())
}

pub fn show_main_window<R: Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(window) = app.get_webview_window(MAIN_WINDOW) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn icon_image() -> tauri::image::Image<'static> {
    let size = 32usize;
    let mut rgba = vec![0u8; size * size * 4];
    for y in 0..size {
        for x in 0..size {
            let dx = x as isize - 15;
            let dy = y as isize - 15;
            let distance = dx * dx + dy * dy;
            let color = if distance <= 200 && distance >= 50 {
                [240u8, 248u8, 255u8, 255u8]
            } else if distance < 50 {
                [196u8, 110u8, 42u8, 255u8]
            } else {
                [0u8, 0u8, 0u8, 0u8]
            };
            let offset = (y * size + x) * 4;
            rgba[offset..offset + 4].copy_from_slice(&color);
        }
    }
    let pixels: &'static [u8] = Box::leak(rgba.into_boxed_slice());
    tauri::image::Image::new(pixels, size as u32, size as u32)
}
