//! Windows toast delivery for agent notifications.
//!
//! Tauri has no built-in toast for unpackaged apps, and pulling a plugin adds a
//! dependency just for this. Windows exposes toasts through WinRT; PowerShell
//! can call WinRT directly, so we hand it a fully-built XML payload through an
//! environment variable (never through string interpolation of user text) and
//! run it hidden.
//!
//! Constraints: the app's AUMID is used as the notifier id, text is length
//! capped and XML-escaped, and failures are reported rather than swallowed.

use std::process::Command;

const MAX_TITLE: usize = 120;
const MAX_BODY: usize = 300;
const AUMID: &str = "com.careerlens.desktop";

/// PowerShell that reads the payload from the environment and shows one toast.
const SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:CAREERLENS_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CAREERLENS_TOAST_AUMID).Show($toast)
"#;

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// Collapse control characters and cap length so the payload cannot break the
/// toast layout or grow without bound.
fn clean(text: &str, limit: usize) -> String {
    let filtered: String = text
        .chars()
        .map(|ch| if ch.is_control() { ' ' } else { ch })
        .collect();
    let trimmed = filtered.trim();
    if trimmed.chars().count() <= limit {
        return trimmed.to_string();
    }
    let mut out: String = trimmed.chars().take(limit.saturating_sub(1)).collect();
    out.push('…');
    out
}

pub fn build_xml(title: &str, body: &str) -> String {
    format!(
        "<toast><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual></toast>",
        escape(&clean(title, MAX_TITLE)),
        escape(&clean(body, MAX_BODY))
    )
}

/// UTF-16LE base64, which is what `-EncodedCommand` expects.
fn encode_command(script: &str) -> String {
    use base64_lite::encode;
    let utf16: Vec<u8> = script
        .encode_utf16()
        .flat_map(|unit| unit.to_le_bytes())
        .collect();
    encode(&utf16)
}

/// Minimal base64 so we do not add a crate for one call.
mod base64_lite {
    const TABLE: &[u8; 64] =
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    pub fn encode(input: &[u8]) -> String {
        let mut out = String::with_capacity((input.len() + 2) / 3 * 4);
        for chunk in input.chunks(3) {
            let b0 = chunk[0] as u32;
            let b1 = *chunk.get(1).unwrap_or(&0) as u32;
            let b2 = *chunk.get(2).unwrap_or(&0) as u32;
            let triple = (b0 << 16) | (b1 << 8) | b2;
            out.push(TABLE[(triple >> 18) as usize & 0x3F] as char);
            out.push(TABLE[(triple >> 12) as usize & 0x3F] as char);
            out.push(if chunk.len() > 1 {
                TABLE[(triple >> 6) as usize & 0x3F] as char
            } else {
                '='
            });
            out.push(if chunk.len() > 2 {
                TABLE[triple as usize & 0x3F] as char
            } else {
                '='
            });
        }
        out
    }
}

#[tauri::command]
pub fn notify(title: String, body: String) -> Result<(), String> {
    if clean(&title, MAX_TITLE).is_empty() {
        return Err("notification title is empty".into());
    }
    let xml = build_xml(&title, &body);
    let encoded = encode_command(SCRIPT);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let status = Command::new("powershell.exe")
            .args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-EncodedCommand", &encoded])
            .env("CAREERLENS_TOAST_XML", xml)
            .env("CAREERLENS_TOAST_AUMID", AUMID)
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map_err(|error| format!("failed to launch toast helper: {error}"))?;
        if status.success() {
            Ok(())
        } else {
            Err(format!("toast helper exited with {status}"))
        }
    }
    #[cfg(not(windows))]
    {
        let _ = (xml, encoded);
        Err("toast delivery is Windows-only".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn xml_escapes_markup_in_user_text() {
        let xml = build_xml("A & B", "<script>alert(1)</script>");
        assert!(xml.contains("A &amp; B"));
        assert!(!xml.contains("<script>"));
        assert!(xml.contains("&lt;script&gt;"));
    }

    #[test]
    fn long_text_is_capped() {
        let xml = build_xml(&"x".repeat(500), &"y".repeat(1000));
        assert!(xml.chars().count() < 700);
        assert!(xml.contains('…'));
    }

    #[test]
    fn control_characters_are_stripped() {
        let xml = build_xml("ti\ntle", "bo\rdy");
        assert!(!xml.contains("ti\ntle"));
        assert!(xml.contains("ti tle"));
    }

    #[test]
    fn base64_matches_known_vectors() {
        assert_eq!(base64_lite::encode(b""), "");
        assert_eq!(base64_lite::encode(b"f"), "Zg==");
        assert_eq!(base64_lite::encode(b"fo"), "Zm8=");
        assert_eq!(base64_lite::encode(b"foo"), "Zm9v");
        assert_eq!(base64_lite::encode(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn empty_title_is_rejected() {
        assert!(notify("   ".into(), "body".into()).is_err());
    }
}
