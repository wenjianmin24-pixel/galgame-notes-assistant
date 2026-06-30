// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;

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
    // Resolve project root relative to the executable:
    //   tauri/src-tauri/target/release/gna.exe
    //   → release/ → target/ → src-tauri/ → tauri/ → project root
    let exe = std::env::current_exe().unwrap();
    let project_root = exe
        .parent()       // release/ or debug/
        .unwrap()
        .parent()       // target/
        .unwrap()
        .parent()       // src-tauri/
        .unwrap()
        .parent()       // tauri/
        .unwrap()
        .parent()       // project root ← 这层之前漏了！
        .unwrap()
        .to_path_buf();

    let python_exe = find_python(&project_root);

    // Fallback: if exe-relative path fails, try CWD
    let (python, work_dir) = if python_exe.exists() {
        (python_exe, project_root.clone())
    } else {
        let cwd = std::env::current_dir().unwrap();
        let py = find_python(&cwd);
        (py, cwd)
    };

    let mut child = Command::new(&python)
        .args(["-m", "app.tauri_server"])
        .current_dir(&work_dir)
        .env("GNA_TAURI", "1")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap_or_else(|e| {
            panic!(
                "Failed to start Python ({}) from {}: {}",
                python.display(),
                work_dir.display(),
                e
            )
        });

    if !wait_for_server("127.0.0.1", 5000, 40) {
        // Check if Python already died
        match child.try_wait() {
            Ok(Some(status)) => {
                panic!(
                    "Python exited early with status {:?} (check .venv setup)",
                    status
                );
            }
            Ok(None) => {
                eprintln!("Python still running but server not reachable after 15s");
            }
            Err(e) => {
                eprintln!("Error checking Python status: {}", e);
            }
        }
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
