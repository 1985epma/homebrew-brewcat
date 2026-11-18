//! Help text for brewcat, shared by `brewcat --help` and the in-app Help window.

/// The version lives in `Cargo.toml` only.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// The full help, with the version filled in.
pub fn help() -> String {
    include_str!("help.txt").replace("{version}", VERSION)
}

pub use crate::sys::os_description;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn help_has_the_version_and_the_sections() {
        let text = help();
        assert!(text.starts_with(&format!("brewcat {VERSION} — ")));
        for section in ["USAGE", "PACKAGES TAB", "SKILLS TAB", "MCP TAB", "SAFETY", "TROUBLESHOOTING"] {
            assert!(text.contains(section), "{section}");
        }
        assert!(!text.contains("{version}"));
    }

    #[test]
    fn help_no_longer_mentions_python_or_tk() {
        let text = help();
        assert!(!text.contains("python-tk") && !text.contains("Tk 8.5") && !text.contains("Python/Tk"));
    }
}
