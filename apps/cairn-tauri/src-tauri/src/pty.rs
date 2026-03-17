//! PTY (pseudo-terminal) management for the ReOS terminal view.
//!
//! Spawns a shell in a PTY, routes output to the frontend via Tauri events,
//! and accepts input/resize commands from Tauri commands.
//!
//! Event protocol:
//!   `reos://pty-output`  — payload: String (UTF-8 lossy from raw bytes)
//!   `reos://pty-closed`  — payload: String (reason)

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use tauri::Emitter;

// ── Payload types for Tauri events ──────────────────────────────────────────

/// Payload for `reos://pty-output` events. Carries raw terminal output.
#[derive(Clone, Serialize)]
pub struct PtyOutputPayload {
    pub data: String,
}

/// Payload for `reos://pty-closed` events. Carries an exit reason string.
#[derive(Clone, Serialize)]
pub struct PtyClosedPayload {
    pub reason: String,
}

// ── PtyProcess ───────────────────────────────────────────────────────────────

/// Owns the live PTY session: the child process, the write half of the master,
/// the master handle for resize, and the background reader thread.
pub struct PtyProcess {
    /// Write half of the PTY master — used by `pty_write`.
    writer: Box<dyn Write + Send>,
    /// Master handle — kept for `pty_resize`.
    master: Box<dyn MasterPty + Send>,
    /// The spawned shell process — killed on drop.
    child: Box<dyn Child + Send>,
    /// Background thread reading PTY output and emitting Tauri events.
    reader_handle: Option<JoinHandle<()>>,
}

impl PtyProcess {
    /// Spawn a shell in a new PTY of the given size.
    ///
    /// The `app_handle` is used to emit `reos://pty-output` and
    /// `reos://pty-closed` events to all webview windows.
    pub fn start(
        app_handle: tauri::AppHandle,
        cols: u16,
        rows: u16,
    ) -> Result<Self, String> {
        let pty_system = native_pty_system();

        let size = PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        };

        let pair = pty_system
            .openpty(size)
            .map_err(|e| format!("Failed to open PTY: {e}"))?;

        // Determine the shell to launch (must be an absolute path).
        let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".to_string());
        if !std::path::Path::new(&shell).is_absolute() {
            return Err(format!("$SHELL '{shell}' is not an absolute path"));
        }
        let mut cmd = CommandBuilder::new(&shell);
        // Ensure TERM is set so applications get colour/cursor support.
        cmd.env("TERM", "xterm-256color");

        let child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| format!("Failed to spawn shell ({shell}): {e}"))?;

        // Clone the reader *before* taking the writer, since both consume the
        // pair — `take_writer` moves it.
        let mut reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| format!("Failed to clone PTY reader: {e}"))?;

        let writer = pair
            .master
            .take_writer()
            .map_err(|e| format!("Failed to take PTY writer: {e}"))?;

        // Background thread: read PTY output in 4 KiB chunks and emit events.
        let reader_handle = thread::spawn(move || {
            let mut buf = [0u8; 4096];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => {
                        // EOF — child exited or PTY was closed.
                        let _ = app_handle.emit(
                            "reos://pty-closed",
                            PtyClosedPayload {
                                reason: "Shell exited".to_string(),
                            },
                        );
                        break;
                    }
                    Ok(n) => {
                        let text = String::from_utf8_lossy(&buf[..n]).into_owned();
                        let _ = app_handle.emit(
                            "reos://pty-output",
                            PtyOutputPayload { data: text },
                        );
                    }
                    Err(e) => {
                        let _ = app_handle.emit(
                            "reos://pty-closed",
                            PtyClosedPayload {
                                reason: format!("PTY read error: {e}"),
                            },
                        );
                        break;
                    }
                }
            }
        });

        Ok(Self {
            writer,
            master: pair.master,
            child,
            reader_handle: Some(reader_handle),
        })
    }

    /// Write data bytes into the PTY (user keystrokes → shell).
    pub fn write_data(&mut self, data: &str) -> Result<(), String> {
        self.writer
            .write_all(data.as_bytes())
            .map_err(|e| format!("PTY write error: {e}"))
    }

    /// Resize the PTY window.
    pub fn resize(&self, cols: u16, rows: u16) -> Result<(), String> {
        self.master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| format!("PTY resize error: {e}"))
    }
}

impl Drop for PtyProcess {
    fn drop(&mut self) {
        // Kill the child; the reader thread will see EOF and exit on its own.
        let _ = self.child.kill();

        // Best-effort join: wait up to 500ms for the reader thread to notice
        // the EOF and exit. If it hasn't exited by then, detach it — don't
        // block the calling thread (which may be holding a Mutex guard).
        if let Some(handle) = self.reader_handle.take() {
            let (done_tx, done_rx) = std::sync::mpsc::channel::<()>();
            std::thread::spawn(move || {
                let _ = handle.join();
                let _ = done_tx.send(());
            });
            let _ = done_rx.recv_timeout(std::time::Duration::from_millis(500));
        }
    }
}

// ── PtyState ─────────────────────────────────────────────────────────────────

/// Thread-safe PTY session state managed by Tauri.
///
/// `None` means no terminal is running. `Some` holds the active session.
pub struct PtyState(pub Arc<Mutex<Option<PtyProcess>>>);

impl PtyState {
    pub fn new() -> Self {
        Self(Arc::new(Mutex::new(None)))
    }
}
