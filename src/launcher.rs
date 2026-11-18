//! macOS launcher bundle: gives brewcat a place in Launchpad, Spotlight and Finder.
//!
//! brewcat is a native program, so the Dock and the menu bar already say "brewcat". The bundle in
//! `~/Applications/brewcat.app` only exists so the app can be found and started like any other: its executable is
//! a tiny script that starts the installed `brewcat`, which means `brew upgrade brewcat` is picked up without
//! rebuilding the bundle. When brewcat already runs from a `.app` (the cask or the .dmg) nothing is created.

use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use regex::Regex;

use crate::help_text::VERSION;
use crate::sys;

#[cfg(target_os = "macos")]
const ICNS: &[u8] = include_bytes!("../assets/brewcat.icns");
#[cfg(not(target_os = "macos"))]
const ICNS: &[u8] = &[];

/// What Finder and Launchpad run on double-click. `@BIN@` is replaced by the stable path of brewcat.
pub const LAUNCHER_SCRIPT: &str = r#"#!/bin/bash
# Starts the installed brewcat (see `brewcat --install-app`). Finder gives apps a minimal PATH, so the usual
# Homebrew locations are tried explicitly.
for BIN in "@BIN@" /opt/homebrew/bin/brewcat /usr/local/bin/brewcat; do
  [ -x "$BIN" ] && exec "$BIN" "$@"
done
/usr/bin/osascript -e 'display dialog "brewcat is not installed any more.\n\nInstall it again with:\n  brew install 1985epma/brewcat/brewcat" buttons {"OK"} default button "OK" with icon caution with title "brewcat"'
"#;

fn bundle_dir(home: &Path) -> PathBuf {
    home.join("Applications/brewcat.app")
}

/// Brew's stable `opt` path for a binary inside the Cellar, so the bundle keeps working after `brew upgrade`.
pub fn stable_path(exe: &Path) -> PathBuf {
    static CELLAR: OnceLock<Regex> = OnceLock::new();
    let re = CELLAR.get_or_init(|| Regex::new(r"/Cellar/brewcat/[^/]+/bin/brewcat$").expect("valid regex"));
    PathBuf::from(re.replace(&exe.to_string_lossy(), "/opt/brewcat/bin/brewcat").into_owned())
}

/// True when `exe` is the binary of a Homebrew formula install.
pub fn is_formula_install(exe: &Path) -> bool {
    exe.to_string_lossy().contains("/Cellar/brewcat/")
}

/// True when `exe` lives inside an `.app` bundle (the cask or the .dmg).
pub fn inside_app_bundle(exe: &Path) -> bool {
    exe.to_string_lossy().contains(".app/Contents/MacOS/")
}

/// None when `~/Applications/brewcat.app` (under `home`) is healthy, else why it is not (used by `brewcat doctor`).
pub fn bundle_state(home: &Path) -> Option<String> {
    let marker = bundle_dir(home).join("Contents/.brewcat-build");
    let Some((_version, bin)) =
        fs::read_to_string(marker).ok().and_then(|t| t.split_once('|').map(|(v, b)| (v.to_string(), b.to_string())))
    else {
        return Some("build marker missing".to_string());
    };
    if !Path::new(&bin).exists() {
        return Some("it points to a brewcat that has since been removed".to_string());
    }
    None
}

fn info_plist(version: &str) -> String {
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>brewcat</string>
<key>CFBundleDisplayName</key><string>brewcat</string>
<key>CFBundleIdentifier</key><string>com.github.1985epma.brewcat</string>
<key>CFBundleVersion</key><string>{version}</string>
<key>CFBundleShortVersionString</key><string>{version}</string>
<key>CFBundleExecutable</key><string>brewcat</string>
<key>CFBundleIconFile</key><string>brewcat</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
"#
    )
}

/// Create (or refresh) `<home>/Applications/brewcat.app` so that it starts `target`. Nothing is rewritten when
/// the bundle is already up to date. Returns the path of the bundle.
pub fn build_bundle(home: &Path, target: &Path, version: &str, icns: &[u8]) -> io::Result<PathBuf> {
    let base = bundle_dir(home);
    let macos = base.join("Contents/MacOS");
    let launcher = macos.join("brewcat");
    let marker = base.join("Contents/.brewcat-build");
    let want = format!("{version}|{}", target.display());
    if launcher.exists() && fs::read_to_string(&marker).ok().as_deref() == Some(want.as_str()) {
        return Ok(base);
    }
    let _ = fs::remove_dir_all(&base);
    fs::create_dir_all(&macos)?;
    fs::create_dir_all(base.join("Contents/Resources"))?;
    if !icns.is_empty() {
        fs::write(base.join("Contents/Resources/brewcat.icns"), icns)?;
    }
    fs::write(&launcher, LAUNCHER_SCRIPT.replace("@BIN@", &target.to_string_lossy()))?;
    fs::set_permissions(&launcher, fs::Permissions::from_mode(0o755))?;
    fs::write(base.join("Contents/Info.plist"), info_plist(version))?;
    fs::write(&marker, want)?;
    Ok(base)
}

/// `brewcat --install-app`: (re)create `~/Applications/brewcat.app` for the brewcat that is running now.
pub fn install_app() -> io::Result<PathBuf> {
    let exe = fs::canonicalize(std::env::current_exe()?)?;
    build_bundle(&sys::home_dir(), &stable_path(&exe), VERSION, ICNS)
}

/// At window start-up on macOS: make sure the app shows up in Launchpad. Only for a Homebrew formula install
/// (a development build or a copy inside an `.app` needs none), never fatal, and `BREWCAT_NO_APP=1` opts out.
pub fn ensure_app_bundle() {
    if !sys::is_mac() || std::env::var_os("BREWCAT_NO_APP").is_some() {
        return;
    }
    let Ok(exe) = std::env::current_exe().and_then(fs::canonicalize) else { return };
    if inside_app_bundle(&exe) || !is_formula_install(&exe) {
        return;
    }
    let _ = build_bundle(&sys::home_dir(), &stable_path(&exe), VERSION, ICNS); // cosmetic: never block start-up
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    fn exe(path: &Path, body: &str) {
        fs::write(path, format!("#!/bin/sh\n{body}")).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
    }

    #[test]
    fn stable_path_uses_brews_opt_prefix() {
        assert_eq!(
            stable_path(Path::new("/opt/homebrew/Cellar/brewcat/0.2.0/bin/brewcat")),
            Path::new("/opt/homebrew/opt/brewcat/bin/brewcat")
        );
        assert_eq!(stable_path(Path::new("/x/target/debug/brewcat")), Path::new("/x/target/debug/brewcat"));
    }

    #[test]
    fn where_brewcat_runs_from_is_recognised() {
        assert!(is_formula_install(Path::new("/opt/homebrew/Cellar/brewcat/0.2.0/bin/brewcat")));
        assert!(!is_formula_install(Path::new("/x/target/debug/brewcat")));
        assert!(inside_app_bundle(Path::new("/Applications/brewcat.app/Contents/MacOS/brewcat")));
        assert!(!inside_app_bundle(Path::new("/opt/homebrew/bin/brewcat")));
    }

    // ───────────────────────── bundle_state ─────────────────────────
    fn marker(home: &Path, body: &str) {
        let m = home.join("Applications/brewcat.app/Contents/.brewcat-build");
        fs::create_dir_all(m.parent().unwrap()).unwrap();
        fs::write(m, body).unwrap();
    }

    #[test]
    fn bundle_state_healthy() {
        let home = tempfile::tempdir().unwrap();
        let bin = home.path().join("brewcat");
        exe(&bin, "exit 0\n");
        marker(home.path(), &format!("{VERSION}|{}", bin.display()));
        assert_eq!(bundle_state(home.path()), None);
    }

    #[test]
    fn bundle_state_marker_missing_or_malformed() {
        let home = tempfile::tempdir().unwrap();
        assert!(bundle_state(home.path()).unwrap().contains("marker missing"));
        marker(home.path(), "garbage");
        assert!(bundle_state(home.path()).unwrap().contains("marker missing"));
    }

    #[test]
    fn bundle_state_target_removed() {
        let home = tempfile::tempdir().unwrap();
        marker(home.path(), &format!("{VERSION}|{}/gone/brewcat", home.path().display()));
        assert!(bundle_state(home.path()).unwrap().contains("removed"));
    }

    // ───────────────────────── LAUNCHER_SCRIPT ─────────────────────────
    #[test]
    fn script_has_no_placeholder_left_once_filled() {
        assert!(LAUNCHER_SCRIPT.contains("@BIN@"));
        let left = Regex::new(r"@[A-Z_]+@").unwrap();
        assert!(!left.is_match(&LAUNCHER_SCRIPT.replace("@BIN@", "/some/brewcat")));
    }

    #[test]
    fn script_is_valid_bash() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("brewcat");
        fs::write(&f, LAUNCHER_SCRIPT.replace("@BIN@", "/some/brewcat")).unwrap();
        assert!(Command::new("bash").arg("-n").arg(&f).status().unwrap().success());
    }

    // ───────────────────────── build_bundle ─────────────────────────
    #[test]
    fn build_bundle_makes_a_runnable_launcher() {
        let home = tempfile::tempdir().unwrap();
        let out = home.path().join("out");
        let bin = home.path().join("fake-brewcat");
        exe(&bin, &format!("echo \"started $*\" > \"{}\"\n", out.display()));
        let base = build_bundle(home.path(), &bin, VERSION, b"icns").unwrap();
        assert_eq!(base, home.path().join("Applications/brewcat.app"));
        let launcher = base.join("Contents/MacOS/brewcat");
        assert_ne!(fs::metadata(&launcher).unwrap().permissions().mode() & 0o100, 0);
        assert_eq!(fs::read(base.join("Contents/Resources/brewcat.icns")).unwrap(), b"icns");
        let plist = fs::read_to_string(base.join("Contents/Info.plist")).unwrap();
        assert!(plist.contains(&format!("<string>{VERSION}</string>")) && plist.contains("CFBundleIconFile"));
        assert_eq!(bundle_state(home.path()), None); // what it just built is healthy
        let status = Command::new(&launcher).arg("--flag").env("PATH", "/usr/bin:/bin").status().unwrap();
        assert!(status.success());
        assert_eq!(fs::read_to_string(out).unwrap().trim(), "started --flag");
    }

    #[test]
    fn launcher_shows_a_dialog_when_brewcat_is_gone() {
        let home = tempfile::tempdir().unwrap();
        let base = build_bundle(home.path(), &home.path().join("gone"), VERSION, b"").unwrap();
        let log = home.path().join("log");
        // swap the real osascript for one that records the call (and the hard-coded fallbacks are not installed here)
        let script = fs::read_to_string(base.join("Contents/MacOS/brewcat")).unwrap();
        let fake_osascript = home.path().join("osascript");
        exe(&fake_osascript, &format!("echo dialog >> \"{}\"\n", log.display()));
        let patched = script
            .replace("/usr/bin/osascript", &fake_osascript.to_string_lossy())
            .replace("/opt/homebrew/bin/brewcat /usr/local/bin/brewcat", "");
        let f = home.path().join("launcher");
        fs::write(&f, patched).unwrap();
        fs::set_permissions(&f, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(Command::new(&f).env("PATH", "/usr/bin:/bin").status().unwrap().success());
        assert_eq!(fs::read_to_string(log).unwrap().trim(), "dialog");
    }

    #[test]
    fn build_bundle_is_not_rebuilt_when_up_to_date_but_is_when_it_changes() {
        let home = tempfile::tempdir().unwrap();
        let bin = home.path().join("brewcat");
        exe(&bin, "exit 0\n");
        let base = build_bundle(home.path(), &bin, "1.0.0", b"").unwrap();
        let launcher = base.join("Contents/MacOS/brewcat");
        fs::write(&launcher, "sentinel").unwrap();
        build_bundle(home.path(), &bin, "1.0.0", b"").unwrap();
        assert_eq!(fs::read_to_string(&launcher).unwrap(), "sentinel");
        build_bundle(home.path(), &bin, "1.0.1", b"").unwrap(); // new version: rebuilt
        assert_ne!(fs::read_to_string(&launcher).unwrap(), "sentinel");
    }
}
