// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::Duration;

struct PythonBackend(Mutex<Option<Child>>);

fn find_python(project_root: &std::path::Path) -> std::path::PathBuf {
    let venv_python = project_root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        return venv_python;
    }
    std::path::PathBuf::from("python")
}

fn wait_for_server(host: &str, port: u16, max_retries: u32) -> bool {
    for i in 0..max_retries {
        if i > 0 {
            std::thread::sleep(Duration::from_millis(500));
        }
        if TcpStream::connect((host, port)).is_ok() {
            return true;
        }
    }
    false
}

fn main() {
    // Resolve project root relative to the executable
    let exe = std::env::current_exe().unwrap();
    let project_root = exe
        .parent()       // release/
        .unwrap()
        .parent()       // target/
        .unwrap()
        .parent()       // src-tauri/
        .unwrap()
        .parent()       // tauri/
        .unwrap()
        .to_path_buf();

    let python_exe = find_python(&project_root);
    println!("Starting Python backend: {}", python_exe.display());

    let child = Command::new(&python_exe)
        .args(["-m", "app.server"])
        .current_dir(&project_root)
        .spawn()
        .expect("Failed to start Python backend");

    if !wait_for_server("127.0.0.1", 5000, 20) {
        eprintln!("Python server did not start within 10s");
    }

    tauri::Builder::default()
        .manage(PythonBackend(Mutex::new(Some(child))))
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.try_state::<PythonBackend>();
                if let Some(state) = state {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(ref mut child) = *guard {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
