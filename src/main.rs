//! brewcat entry point. The command line decides first (`--help`, `--version`, `doctor`, `search`, `list`,
//! `install`…); with no command the window opens.

fn main() {
    if let Some(code) = brewcat::cli::run(None) {
        std::process::exit(code);
    }
    open_window();
}

#[cfg(feature = "gui")]
fn open_window() -> ! {
    std::process::exit(brewcat::gui::run());
}

#[cfg(not(feature = "gui"))]
fn open_window() -> ! {
    eprintln!(
        "brewcat: this build has no window (it was built without the `gui` feature).\n\
         The command line works: try `brewcat doctor`, `brewcat search jq`, `brewcat --help`."
    );
    std::process::exit(1);
}
