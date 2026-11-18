//! The brewcat window (egui/eframe). `run()` opens it; everything else is split by what it does:
//!
//! - `state`: what the Packages tab lists and how a batch of brew commands went (pure, unit-tested)
//! - `extras`: the same for the Skills and MCP tabs
//! - `worker`: work off the window's thread and the messages it sends back
//! - `dialogs`: modal questions, as values in a queue
//! - `app`, `tabs`: the app itself and its drawing

pub mod app;
pub mod dialogs;
pub mod extras;
pub mod state;
pub mod tabs;
pub mod worker;

#[cfg(test)]
mod tests;

use std::sync::Arc;

use eframe::egui;

use crate::logo;

fn cannot_open(why: &str) -> i32 {
    eprintln!("brewcat: cannot open a window ({why}).\nNo display available? Run `brewcat doctor` to diagnose.");
    1
}

/// True when there is no graphical session to open a window in (Linux without X11 or Wayland).
fn no_display() -> bool {
    let set = |name: &str| std::env::var_os(name).is_some_and(|v| !v.is_empty());
    cfg!(all(unix, not(target_os = "macos"))) && !set("DISPLAY") && !set("WAYLAND_DISPLAY")
}

/// Open the window and block until it is closed. Returns the process exit code.
pub fn run() -> i32 {
    if no_display() {
        return cannot_open("neither DISPLAY nor WAYLAND_DISPLAY is set");
    }
    let icon = egui::IconData { rgba: logo::rasterize(256, 3), width: 256, height: 256 };
    let viewport = egui::ViewportBuilder::default()
        .with_title("brewcat")
        .with_app_id("brewcat")
        .with_inner_size([1180.0, 720.0])
        .with_min_inner_size([960.0, 600.0])
        .with_icon(Arc::new(icon));
    let options = eframe::NativeOptions { viewport, ..Default::default() };
    let result = eframe::run_native(
        "brewcat",
        options,
        Box::new(|cc| Ok(Box::new(app::BrewcatApp::new(cc.egui_ctx.clone(), app::Options::from_env())))),
    );
    match result {
        Ok(()) => 0,
        Err(e) => cannot_open(&e.to_string()),
    }
}
