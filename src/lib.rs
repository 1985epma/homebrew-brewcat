//! brewcat: a visual catalog of Homebrew packages, skills and MCP servers, as a window and a command line.
//!
//! Everything that does not need a window (`--help`, `--version`, `doctor`, `search`, `list`, `install`…) lives
//! outside the `gui` module, so the command line also works on a headless box and in CI.

pub mod brewenv;
pub mod brewrunner;
pub mod catalog;
pub mod cli;
pub mod doctor;
pub mod extras_core;
#[cfg(feature = "gui")]
pub mod gui;
pub mod help_text;
pub mod launcher;
pub mod logo;
pub mod plan;
pub mod sys;
