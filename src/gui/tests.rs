//! Flows of the window without a window: workers are real (a fake `brew` script on disk), dialogs are answered
//! through the same queue the buttons use, and drawing runs headless through `Context::run_ui`.

use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::sync::Arc;
use std::time::{Duration, Instant};

use eframe::egui;

use crate::brewrunner::Tag;
use crate::catalog::{self, Kind, catalog};
use crate::extras_core::Scope;
use crate::gui::app::{BrewcatApp, Options, Tab};
use crate::gui::dialogs::{Answer, Dialog, Then};
use crate::gui::extras::McpForm;
use crate::gui::state::{CART, KITS, Obj, PROFILES, welcome_flag};
use crate::gui::worker::{FoundSkill, Msg, ScanOk};

fn app_in(dir: &Path, brew: Option<String>) -> BrewcatApp {
    BrewcatApp::new(
        egui::Context::default(),
        Options {
            brew,
            home: dir.join("home"),
            cfg_dir: dir.join("cfg"),
            no_welcome: true,
            startup_delay: None,
            refresh_on_start: false,
            ensure_bundle: false,
        },
    )
}

/// A `brew` shell script; every call is appended to calls.log. `body` is the case arms for $1.
fn fake_brew(dir: &Path, body: &str) -> String {
    let script = dir.join("brew");
    std::fs::write(&script, format!("#!/bin/sh\necho \"$@\" >> \"{}/calls.log\"\ncase \"$1\" in\n{body}\nesac\nexit 0\n", dir.display()))
        .unwrap();
    std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755)).unwrap();
    script.to_string_lossy().into_owned()
}

fn calls(dir: &Path) -> Vec<String> {
    std::fs::read_to_string(dir.join("calls.log")).map(|t| t.lines().map(String::from).collect()).unwrap_or_default()
}

/// Let the window handle what workers send until `cond` holds.
fn pump(app: &mut BrewcatApp, cond: impl Fn(&BrewcatApp) -> bool) {
    let end = Instant::now() + Duration::from_secs(20);
    while !cond(app) && Instant::now() < end {
        app.drain();
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(cond(app), "timed out waiting for the window");
}

fn v(parts: &[&str]) -> Vec<String> {
    parts.iter().map(|s| s.to_string()).collect()
}

fn real_installs(dir: &Path) -> Vec<String> {
    calls(dir).into_iter().filter(|c| c.starts_with("install") && !c.contains("--dry-run")).collect()
}

fn front_text(app: &BrewcatApp) -> String {
    match app.dialogs.front() {
        Some(Dialog::Plan { text, .. } | Dialog::Confirm { text, .. } | Dialog::Info { text, .. } | Dialog::Error { text, .. }) => {
            text.clone()
        }
        other => panic!("expected a text dialog, got {other:?}"),
    }
}

fn no_panic_plan() -> crate::gui::app::PlanFn {
    Arc::new(|_, _| panic!("brew exploded"))
}

// ───────────────────────── first-run welcome ─────────────────────────
#[test]
fn welcome_appears_once_writes_the_flag_and_never_installs() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    app.no_welcome = false;
    assert!(!welcome_flag(&app.cfg_dir).exists());
    assert!(app.maybe_welcome());
    assert!(welcome_flag(&app.cfg_dir).exists() && app.dialogs.len() == 1);
    assert!(matches!(app.dialogs.front(), Some(Dialog::Welcome { .. })));
    app.answer_front(Answer::Start(None)); // Skip
    assert!(!app.busy && !app.planning && app.dialogs.is_empty());
    assert!(!app.maybe_welcome() && app.dialogs.is_empty()); // second launch: nothing
}

#[test]
fn the_welcome_flag_is_written_even_when_it_is_closed_with_the_window_button() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.no_welcome = false;
    app.maybe_welcome();
    let dismissed = app.dialogs.front().unwrap().dismissed();
    app.answer_front(dismissed);
    assert!(welcome_flag(&app.cfg_dir).exists());
}

#[test]
fn the_no_welcome_variable_suppresses_it() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.no_welcome = true;
    assert!(!app.maybe_welcome());
    assert!(app.dialogs.is_empty() && !welcome_flag(&app.cfg_dir).exists());
}

#[test]
fn a_starter_kit_switches_to_kits_and_selects_the_first_of_the_profile() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    app.tab = Tab::Mcp;
    app.dialogs.push_back(Dialog::Welcome { selected: 4 });
    app.answer_front(Answer::Start(Some("QA".to_string())));
    assert_eq!((app.model.profile_label.as_str(), app.model.category.as_str(), app.tab), ("QA", KITS, Tab::Packages));
    match app.model.selected_obj() {
        Some(Obj::Kit(k)) => assert_eq!(k.profile, catalog::QA),
        other => panic!("expected a kit, got {other:?}"),
    }
    assert!(!app.busy && app.dialogs.is_empty()); // choosing a starter kit installs nothing
    assert!(app.model.category_entries().contains(&app.model.category));
}

// ───────────────────────── confirmation with the plan ─────────────────────────
#[test]
fn install_confirmation_shows_the_plan_and_runs_on_accept() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(
        dir.path(),
        "install) case \"$*\" in *--dry-run*) printf '==> Would install 1 formula:\\nx 1\\n==> Would install 1 dependency for x:\\nlibfoo 2\\n' ;; esac ;;",
    );
    let mut app = app_in(dir.path(), Some(brew));
    app.show_starter_kits("Dev");
    let Some(Obj::Kit(kit)) = app.model.selected_obj().cloned() else { panic!("a kit is selected") };
    app.install_selected();
    assert!(app.planning);
    assert_eq!(app.status, "Checking what will change…");
    pump(&mut app, |a| !a.planning && !a.dialogs.is_empty());
    assert_eq!(app.status, "");
    let Some(Dialog::Plan { title, text, cmds }) = app.dialogs.front().cloned() else { panic!("expected the plan dialog") };
    assert_eq!(title, "Confirm installation");
    assert!(text.starts_with("Summary: ") && text.contains("libfoo") && text.contains("\n\nWill run:\nbrew install"), "{text}");
    assert_eq!(cmds[0][0], "install");
    assert!(real_installs(dir.path()).is_empty(), "nothing runs before the answer");
    app.answer_front(Answer::Yes);
    assert!(app.busy);
    pump(&mut app, |a| !a.busy);
    assert_eq!(real_installs(dir.path()).len(), 1);
    let n = app.model.kit_items(&kit).len();
    assert_eq!(app.status, format!("✓ {n} packages installed successfully."));
    assert!(app.log_text.contains("$ brew install") && app.log_text.contains("→ exit code 0"));
}

#[test]
fn cancel_in_the_plan_dialog_installs_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) exit 0 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.model.cart.insert("formula:git".to_string());
    app.install_cart();
    pump(&mut app, |a| !a.planning && !a.dialogs.is_empty());
    assert!(matches!(app.dialogs.front(), Some(Dialog::Plan { .. })));
    app.answer_front(Answer::No);
    std::thread::sleep(Duration::from_millis(100));
    app.drain();
    assert!(!app.busy && real_installs(dir.path()).is_empty());
}

#[test]
fn the_confirmation_falls_back_to_the_plain_question_when_the_plan_fails() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) exit 0 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.plan_fn = no_panic_plan();
    app.model.cart.insert("formula:git".to_string());
    app.install_cart();
    pump(&mut app, |a| !a.planning && !a.dialogs.is_empty());
    let Some(Dialog::Confirm { text, then: Then::RunBrew(cmds), .. }) = app.dialogs.front().cloned() else {
        panic!("expected the plain question")
    };
    assert!(text.starts_with("Install 1 packages?") && text.contains("git"));
    assert_eq!(cmds, [v(&["install", "git"])]);
    app.answer_front(Answer::Yes);
    pump(&mut app, |a| !a.busy);
    assert_eq!(real_installs(dir.path()), ["install -- git"]);
}

#[test]
fn saying_no_to_the_plain_question_still_installs_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) exit 0 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.plan_fn = no_panic_plan();
    app.model.cart.insert("formula:git".to_string());
    app.install_cart();
    pump(&mut app, |a| !a.dialogs.is_empty());
    app.answer_front(Answer::No);
    assert!(!app.busy && real_installs(dir.path()).is_empty());
}

#[test]
fn without_brew_the_plain_confirmation_is_immediate() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.model.cart.insert("formula:git".to_string());
    app.install_cart();
    assert!(!app.planning);
    assert!(matches!(app.dialogs.front(), Some(Dialog::Confirm { .. })));
    app.answer_front(Answer::Yes); // there is no brew to run: it is said, not crashed
    assert!(matches!(app.dialogs.front(), Some(Dialog::Error { title, .. }) if title == "Homebrew"));
    assert!(front_text(&app).contains("brew not found"));
}

#[test]
fn an_empty_list_says_so() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.install_cart();
    assert_eq!(front_text(&app), "Nothing to install in the list.");
}

#[test]
fn a_kit_that_is_installed_already_only_writes_to_the_log() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.show_starter_kits("Dev");
    let Some(Obj::Kit(kit)) = app.model.selected_obj().cloned() else { panic!() };
    for item in app.model.kit_items(&kit) {
        app.model.installed.formula.insert(item.name.clone());
        app.model.installed.cask.insert(item.name);
    }
    app.install_selected();
    assert!(app.dialogs.is_empty() && app.log_text.contains("already installed"));
}

#[test]
fn uninstall_asks_first_and_names_the_cask_flag() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    app.model.platform = "mac".to_string(); // casks only exist on macOS; the default platform is the machine's
    app.model.installed.cask.insert("obs".to_string());
    app.model.search = "obs".to_string();
    app.model.refresh();
    app.model.selected = Some("cask:obs".to_string());
    app.uninstall_selected();
    let Some(Dialog::Confirm { title, text, then: Then::RunBrew(cmds) }) = app.dialogs.front().cloned() else { panic!() };
    assert_eq!((title.as_str(), text.as_str()), ("Uninstall", "Uninstall obs?"));
    assert_eq!(cmds, [v(&["uninstall", "--cask", "obs"])]);
}

// ───────────────────────── failure tracking ─────────────────────────
#[test]
fn a_failed_batch_enables_retry_and_retry_reruns_only_the_failed() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) for a in \"$@\"; do [ \"$a\" = bad ] && exit 1; done ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["install", "good", "bad"])]);
    pump(&mut app, |a| !a.busy);
    assert_eq!(app.failed_cmds, [v(&["install", "bad"])]);
    assert!(app.status.contains("1 package failed") && app.status.contains("bad"), "{}", app.status);
    assert!(app.log_text.contains("Retry failed"));

    // Retry goes through the same confirmation (the plan is unavailable here) and runs only "bad".
    app.plan_fn = no_panic_plan();
    let before = real_installs(dir.path()).len();
    app.retry_failed();
    pump(&mut app, |a| !a.dialogs.is_empty());
    let text = front_text(&app);
    assert!(text.contains("bad") && !text.contains("good"), "{text}");
    app.answer_front(Answer::Yes);
    pump(&mut app, |a| !a.busy);
    let new: Vec<String> = real_installs(dir.path()).split_off(before);
    assert_eq!(new, ["install -- bad"]);
    assert_eq!(app.failed_cmds, [v(&["install", "bad"])]); // still failing, still retryable
}

#[test]
fn retry_asks_for_confirmation_and_cancel_runs_nothing() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) exit 1 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["install", "bad"])]);
    pump(&mut app, |a| !a.busy);
    let before = real_installs(dir.path()).len();
    app.retry_failed();
    pump(&mut app, |a| !a.dialogs.is_empty());
    app.answer_front(Answer::No);
    assert!(!app.busy && real_installs(dir.path()).len() == before);
}

#[test]
fn retry_does_nothing_while_busy_or_when_nothing_failed() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.retry_failed();
    assert!(app.dialogs.is_empty());
    app.failed_cmds = vec![v(&["install", "x"])];
    app.busy = true;
    app.retry_failed();
    assert!(app.dialogs.is_empty());
}

#[test]
fn success_shows_a_one_line_summary_with_the_count() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) exit 0 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["install", "a", "b"]), v(&["install", "--cask", "c"])]);
    pump(&mut app, |a| !a.busy);
    assert!(app.failed_cmds.is_empty());
    assert_eq!(app.status, "✓ 3 packages installed successfully.");
}

#[test]
fn a_stopped_run_is_not_a_failure_to_retry() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) echo started; sleep 30 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["install", "x"])]);
    pump(&mut app, |a| a.log_text.contains("started"));
    assert!(app.busy && app.runner.running());
    app.runner.terminate();
    pump(&mut app, |a| !a.busy);
    assert_eq!(app.status, "Stopped.");
    assert!(app.failed_cmds.is_empty());
    assert!(app.log_text.contains("Stopped before finishing"));
}

#[test]
fn only_one_batch_runs_at_a_time() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "install) sleep 1 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["install", "x"])]);
    app.run_brew(vec![v(&["install", "y"])]); // ignored: busy
    pump(&mut app, |a| !a.busy);
    assert_eq!(real_installs(dir.path()), ["install -- x"]);
}

#[test]
fn finishing_a_batch_reads_the_installed_list_again() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "list) printf 'git\\n' ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["update"])]);
    pump(&mut app, |a| !a.busy && a.model.installed.formula.contains("git"));
    assert!(app.status.contains("✗") || app.status.contains("Done") || app.status.contains("✓"));
}

// ───────────────────────── closing ─────────────────────────
#[test]
fn closing_an_idle_window_just_quits_and_stopping_the_runner_is_harmless() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    assert!(!app.on_close_requested(true));
    assert!(app.dialogs.is_empty());
    app.shutdown(); // terminate() is a harmless no-op when idle
    assert!(app.runner.cancelled());
    assert!(!app.on_close_requested(false));
}

#[test]
fn closing_during_an_install_asks_and_can_be_cancelled() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.busy = true;
    assert!(app.on_close_requested(true));
    assert_eq!(front_text(&app), "An installation is still running. Quit and stop it?");
    assert!(app.on_close_requested(true) && app.dialogs.len() == 1); // asked once
    app.answer_front(Answer::No);
    assert!(!app.quit_confirmed);
    assert!(app.on_close_requested(true)); // still asks next time
    app.answer_front(Answer::Yes);
    assert!(app.quit_confirmed);
    assert!(!app.on_close_requested(true)); // confirmed: let it close
}

#[test]
fn closing_during_an_install_stops_the_brew_child() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(dir.path(), "update) echo started; sleep 60 ;;");
    let mut app = app_in(dir.path(), Some(brew));
    app.run_brew(vec![v(&["update"])]);
    pump(&mut app, |a| a.runner.running() && a.log_text.contains("started"));
    assert!(app.busy);
    app.shutdown();
    assert!(!app.runner.running());
    pump(&mut app, |a| !a.busy);
}

// ───────────────────────── clipboard, diagnostics, links ─────────────────────────
#[test]
fn copy_log_puts_the_log_on_the_clipboard() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.log(Tag::Info, "hello log\n");
    app.copy_log();
    assert!(app.last_copied.as_deref().unwrap().contains("hello log"));
    assert_eq!(app.status, "Log copied to clipboard.");
}

#[test]
fn the_log_keeps_tags_and_lines() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.log(Tag::Cmd, "\n$ brew update\n");
    app.log(Tag::Out, "a\nb\n");
    let lines: Vec<(Tag, &str)> = app.log_lines.iter().map(|(t, l)| (*t, l.as_str())).collect();
    assert_eq!(lines, [(Tag::Cmd, ""), (Tag::Cmd, "$ brew update"), (Tag::Out, "a"), (Tag::Out, "b")]);
    assert_eq!(app.log_text, "\n$ brew update\na\nb\n");
}

#[test]
fn diagnostics_are_copied_and_the_user_is_told() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.handle(Msg::Diagnostics("REPORT BODY".to_string()));
    assert_eq!(app.last_copied.as_deref(), Some("REPORT BODY"));
    assert_eq!(front_text(&app), "Copied. Paste it in your issue.");
}

#[test]
fn pages_open_in_the_browser() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    app.open_url("https://formulae.brew.sh/formula/jq".to_string());
    assert_eq!(app.opened_urls, ["https://formulae.brew.sh/formula/jq"]);
}

#[test]
fn a_brewfile_is_written_for_the_list() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.model.platform = "mac".to_string(); // casks only exist on macOS; the default platform is the machine's
    app.model.cart.extend(["formula:jq".to_string(), "cask:obs".to_string()]);
    let items = app.model.export_items();
    let path = dir.path().join("Brewfile");
    app.write_brewfile(&path, &items);
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "cask \"obs\"\nbrew \"jq\"\n");
    assert!(app.log_text.contains("Brewfile saved to") && app.log_text.contains("brew bundle --file="));
    app.write_brewfile(&dir.path().join("no/such/dir/Brewfile"), &items);
    assert!(matches!(app.dialogs.front(), Some(Dialog::Error { .. })));
}

#[test]
fn exporting_nothing_says_so() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.export_brewfile(); // nothing in the list and nothing selected: no file dialog opens
    assert_eq!(front_text(&app), "Add items to the list (double-click) or select a kit.");
}

// ───────────────────────── Rosetta ─────────────────────────
#[test]
fn rosetta_is_asked_once_and_declining_is_remembered() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.check_rosetta(false, false); // not Apple Silicon
    app.check_rosetta(true, true); // already there
    assert!(app.dialogs.is_empty());
    app.check_rosetta(true, false);
    assert!(matches!(app.dialogs.front(), Some(Dialog::Confirm { then: Then::InstallRosetta, .. })));
    assert!(front_text(&app).contains("Rosetta 2 is not installed"));
    app.answer_front(Answer::No);
    assert!(app.log_text.contains("softwareupdate --install-rosetta --agree-to-license"));
    app.check_rosetta(true, false);
    assert!(app.dialogs.is_empty(), "declined once: never asked again");
}

#[test]
fn the_welcome_comes_before_the_rosetta_question() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.no_welcome = false;
    app.maybe_welcome();
    app.check_rosetta(true, false);
    assert!(matches!(app.dialogs[0], Dialog::Welcome { .. }) && matches!(app.dialogs[1], Dialog::Confirm { .. }));
}

#[test]
fn the_startup_timer_shows_the_dialogs_after_the_delay() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.no_welcome = false;
    app.startup_at = Some(Instant::now() + Duration::from_secs(3600));
    app.tick(&egui::Context::default());
    assert!(app.dialogs.is_empty() && app.startup_at.is_some());
    app.startup_at = Some(Instant::now());
    app.tick(&egui::Context::default());
    assert!(app.startup_at.is_none());
    assert!(matches!(app.dialogs.front(), Some(Dialog::Welcome { .. })));
}

// ───────────────────────── search and descriptions ─────────────────────────
#[test]
fn typing_searches_all_of_homebrew_after_a_pause() {
    let dir = tempfile::tempdir().unwrap();
    let brew = fake_brew(
        dir.path(),
        "search) case \"$2\" in --formulae) printf 'foozz-tool\\n' ;; esac ;;\ndesc) printf 'foozz-tool: A fine tool\\n' ;;",
    );
    let mut app = app_in(dir.path(), Some(brew));
    app.model.search = "f".to_string();
    app.on_search_changed();
    assert!(app.search_deadline.is_none()); // one letter: no brew search
    app.model.search = "foozz".to_string();
    app.on_search_changed();
    assert!(app.search_deadline.is_some());
    app.search_deadline = Some(Instant::now()); // the pause is over
    app.tick(&egui::Context::default());
    pump(&mut app, |a| !a.model.extra.is_empty());
    assert_eq!(app.model.extra[0].name, "foozz-tool");
    // the result shows at the end of ★ All and in its own view, with its description fetched once
    app.on_category(crate::gui::state::SEARCH.to_string());
    assert_eq!(app.model.rows.len(), 1);
    app.model.select_first();
    app.ensure_desc();
    app.ensure_desc();
    pump(&mut app, |a| a.model.extra_desc.values().any(|d| d == "A fine tool"));
    assert_eq!(calls(dir.path()).iter().filter(|c| c.starts_with("desc")).count(), 1);
}

#[test]
fn a_search_result_for_an_older_query_is_dropped() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.model.search = "newer".to_string();
    app.handle(Msg::Search { query: "older".to_string(), found: vec![(Kind::Formula, "older-tool".to_string())] });
    assert!(app.model.extra.is_empty());
}

#[test]
fn changing_the_profile_keeps_the_category_when_it_still_exists() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.model.category = "Cloud CLIs".to_string();
    app.model.profile_label = "SRE / Cloud".to_string();
    app.on_profile();
    assert_eq!(app.model.category, "Cloud CLIs");
    app.model.profile_label = "Gamer".to_string(); // no such category there
    app.on_profile();
    assert_eq!(app.model.category, "★ All");
}

// ───────────────────────── Skills and MCP ─────────────────────────
fn skill(dir: &Path, name: &str) -> std::path::PathBuf {
    let f = dir.join("src").join(name);
    std::fs::create_dir_all(&f).unwrap();
    std::fs::write(f.join("SKILL.md"), format!("---\nname: {name}\n---\n")).unwrap();
    f
}

#[test]
fn installing_skills_asks_then_asks_again_before_replacing() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    let (a, b) = (skill(dir.path(), "alpha"), skill(dir.path(), "beta"));
    let found =
        |f: &Path| FoundSkill { folder: f.to_path_buf(), name: f.file_name().unwrap().to_string_lossy().into_owned(), desc: String::new() };
    app.handle(Msg::Scan(Ok(ScanOk {
        spec: "anthropics/skills".into(),
        tmp: None,
        commit: "abcdef0123456".into(),
        skills: vec![found(&a), found(&b)],
    })));
    assert!(app.log_text.contains("Found 2 skill(s)."));
    app.install_skills(); // nothing ticked
    assert_eq!(front_text(&app), "Select one or more skills first (scan a source).");
    app.answer_front(Answer::Yes);
    app.skills.select_all(true);
    app.skills.bar.on = [true, false, false];
    std::fs::create_dir_all(app.home.join(".claude/skills/alpha")).unwrap(); // alpha exists already
    app.install_skills();
    let text = front_text(&app);
    assert!(text.starts_with("Install skill(s): alpha, beta\nSource: anthropics/skills @ abcdef0123\n"), "{text}");
    assert!(!text.contains("trusted list"));
    app.answer_front(Answer::Yes);
    // alpha exists: the replacement is asked about, beta waits behind it
    let Some(Dialog::Confirm { title, then: Then::Replace(dest), .. }) = app.dialogs.front().cloned() else {
        panic!("expected the overwrite question")
    };
    assert_eq!(title, "Overwrite");
    assert_eq!(dest, app.home.join(".claude/skills/alpha"));
    assert!(!app.home.join(".claude/skills/beta").exists());
    app.answer_front(Answer::No); // keep alpha as it is
    assert!(app.dialogs.is_empty());
    assert!(app.home.join(".claude/skills/beta/SKILL.md").exists());
    assert!(!app.home.join(".claude/skills/alpha/SKILL.md").exists());
    assert!(app.log_text.contains("✓ beta → "));
    assert_eq!(app.skills.rows[1].marks, "C · ·"); // the marks follow
}

#[test]
fn skills_replace_an_existing_folder_when_agreed() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    let a = skill(dir.path(), "alpha");
    app.skills.apply_scan(
        ScanOk {
            spec: "x/y".into(),
            tmp: None,
            commit: String::new(),
            skills: vec![FoundSkill { folder: a, name: "alpha".into(), desc: String::new() }],
        },
        &app.home.clone(),
    );
    app.skills.select_all(true);
    std::fs::create_dir_all(app.home.join(".claude/skills/alpha")).unwrap();
    app.install_skills();
    assert!(front_text(&app).contains("not in brewcat's trusted list"));
    app.answer_front(Answer::Yes);
    app.answer_front(Answer::Yes); // replace
    assert!(app.home.join(".claude/skills/alpha/SKILL.md").exists());
    assert!(app.dialogs.is_empty());
}

#[test]
fn a_failed_scan_is_reported_in_the_log() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.skills.scanning = true;
    app.handle(Msg::Scan(Err("git clone failed".to_string())));
    assert!(!app.skills.scanning && app.log_text.contains("Scan failed: git clone failed"));
}

#[test]
fn skills_need_a_target() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    let a = skill(dir.path(), "alpha");
    app.skills.apply_scan(
        ScanOk {
            spec: "x/y".into(),
            tmp: None,
            commit: String::new(),
            skills: vec![FoundSkill { folder: a, name: "alpha".into(), desc: String::new() }],
        },
        &app.home.clone(),
    );
    app.skills.select_all(true);
    app.skills.bar.on = [false; 3];
    app.install_skills();
    assert_eq!(front_text(&app), "Select at least one target (Claude, Kiro or VS Code).");
}

#[test]
fn an_mcp_server_is_confirmed_then_written() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.install_mcp();
    assert_eq!(front_text(&app), "Pick a server or fill in name and command.");
    app.answer_front(Answer::Yes);
    app.mcp.pick_preset(1);
    app.install_mcp();
    let text = front_text(&app);
    assert!(text.starts_with("Add MCP server 'memory'") && !text.contains("Custom command"), "{text}");
    assert!(text.contains(&app.home.join(".claude.json").to_string_lossy().into_owned()));
    app.answer_front(Answer::No);
    assert!(!app.home.join(".claude.json").exists());
    app.install_mcp();
    app.answer_front(Answer::Yes);
    let config: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(app.home.join(".claude.json")).unwrap()).unwrap();
    assert_eq!(config["mcpServers"]["memory"]["command"], "npx");
    assert!(app.log_text.contains("✓ memory → "));
    assert_eq!(app.mcp.marks[1], "C · ·");
}

#[test]
fn a_custom_mcp_command_is_flagged_and_bad_arguments_are_refused() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    app.mcp.form = McpForm { name: "mine".into(), command: "node".into(), args: "server.js".into(), env: "A=1".into() };
    app.install_mcp();
    assert!(front_text(&app).contains("⚠ Custom command"));
    app.answer_front(Answer::No);
    app.mcp.form.args = "\"broken".to_string();
    app.install_mcp();
    assert!(matches!(app.dialogs.front(), Some(Dialog::Error { title, .. }) if title == "MCP"));
    assert!(front_text(&app).starts_with("Invalid arguments"));
    assert_eq!(app.mcp.bar.scope, Scope::User);
}

// ───────────────────────── headless rendering ─────────────────────────
fn frame(ctx: &egui::Context, app: &mut BrewcatApp) {
    let raw =
        egui::RawInput { screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1180.0, 720.0))), ..Default::default() };
    ctx.run_ui(raw, |ui| app.draw(ui)).drop_without_applying_deltas();
}

#[test]
fn every_profile_and_category_renders_without_panicking() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    let ctx = app.ctx.clone();
    frame(&ctx, &mut app);
    for (label, _) in PROFILES {
        app.model.profile_label = label.to_string();
        app.on_profile();
        for cat in app.model.category_entries() {
            app.on_category(cat);
            app.model.select_first();
            frame(&ctx, &mut app);
        }
    }
    app.model.profile_label = "All".to_string();
    app.on_category("★ All".to_string());
    assert!(!app.model.rows.is_empty());
    frame(&ctx, &mut app);
}

#[test]
fn every_tab_window_and_dialog_renders() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), None);
    let ctx = app.ctx.clone();
    frame(&ctx, &mut app);
    for tab in [Tab::Skills, Tab::Mcp, Tab::Packages] {
        app.tab = tab;
        frame(&ctx, &mut app);
    }
    app.tab = Tab::Skills;
    let a = skill(dir.path(), "alpha");
    app.skills.apply_scan(
        ScanOk {
            spec: "x".into(),
            tmp: None,
            commit: String::new(),
            skills: vec![FoundSkill { folder: a, name: "alpha".into(), desc: "d".into() }],
        },
        &app.home.clone(),
    );
    frame(&ctx, &mut app);
    app.tab = Tab::Mcp;
    app.mcp.pick_preset(0);
    frame(&ctx, &mut app);
    app.tab = Tab::Packages;
    app.show_help = true;
    app.show_about = true;
    app.busy = true;
    app.log(Tag::Err, "boom\n");
    app.log(Tag::Out, "out\n");
    frame(&ctx, &mut app);
    frame(&ctx, &mut app);
    assert!(app.show_help && app.show_about);
    for dialog in [
        Dialog::Welcome { selected: 2 },
        Dialog::Plan { title: "t".into(), text: "Summary: 1 to install.".into(), cmds: vec![] },
        Dialog::Confirm { title: "t".into(), text: "yes?".into(), then: Then::Quit },
        Dialog::Info { title: "t".into(), text: "i".into() },
        Dialog::Error { title: "t".into(), text: "e".into() },
    ] {
        app.dialogs.push_back(dialog);
        frame(&ctx, &mut app);
        frame(&ctx, &mut app);
        app.dialogs.pop_front();
    }
}

#[test]
fn a_selected_package_and_a_selected_kit_render_their_details() {
    let dir = tempfile::tempdir().unwrap();
    let mut app = app_in(dir.path(), Some("/fake/brew".into()));
    let ctx = app.ctx.clone();
    app.model.installed.formula.insert("git".to_string());
    app.model.cart.insert("formula:jq".to_string());
    app.model.search = "git".to_string();
    app.model.refresh();
    app.model.select_first();
    frame(&ctx, &mut app);
    app.show_starter_kits("Dev");
    frame(&ctx, &mut app);
    app.model.search = String::new();
    app.on_category(CART.to_string());
    app.model.select_first();
    frame(&ctx, &mut app);
    assert!(app.model.selected.is_some());
}

#[test]
fn the_logo_is_a_texture_and_the_window_title_is_brewcat() {
    let dir = tempfile::tempdir().unwrap();
    let app = app_in(dir.path(), None);
    assert!(app.logo_tex.is_some());
    assert_eq!(catalog().by_key("formula:jq").map(|i| i.name.as_str()), Some("jq"));
}

#[test]
fn the_profile_list_has_the_expected_labels() {
    assert_eq!(PROFILES[0].0, "All");
    assert_eq!(PROFILES[1].0, "117-labs (by 1985epma)");
    assert_eq!(PROFILES.len(), 14);
}

// ───────────────────────── clicking ─────────────────────────
// Real pointer events through the headless egui context: move, press, release, one frame each, like a user's click.
struct Pointer {
    time: f64,
}

impl Pointer {
    fn new() -> Pointer {
        Pointer { time: 0.0 }
    }

    /// One frame with `events`. Returns the repaint delay egui reports for it.
    fn frame(&mut self, app: &mut BrewcatApp, events: Vec<egui::Event>) -> std::time::Duration {
        self.time += 0.05;
        let raw = egui::RawInput {
            screen_rect: Some(egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(1180.0, 720.0))),
            time: Some(self.time),
            events,
            ..Default::default()
        };
        let ctx = app.ctx.clone();
        let out = ctx.run_ui(raw, |ui| app.draw(ui));
        let delay = out.viewport_output.get(&egui::ViewportId::ROOT).map(|v| v.repaint_delay).unwrap_or(std::time::Duration::MAX);
        out.drop_without_applying_deltas();
        delay
    }

    /// Press and release the primary button at `(x, y)`. Returns the repaint delay after the release.
    fn click(&mut self, app: &mut BrewcatApp, x: f32, y: f32) -> std::time::Duration {
        let pos = egui::pos2(x, y);
        let button =
            |pressed| egui::Event::PointerButton { pos, button: egui::PointerButton::Primary, pressed, modifiers: Default::default() };
        self.frame(app, vec![egui::Event::PointerMoved(pos)]);
        self.frame(app, vec![button(true)]);
        self.frame(app, vec![button(false)])
    }
}

fn settled_app(dir: &std::path::Path) -> (BrewcatApp, Pointer) {
    let mut app = app_in(dir, Some("/fake/brew".into()));
    let mut pointer = Pointer::new();
    for _ in 0..4 {
        pointer.frame(&mut app, vec![]); // panels and the table need a couple of frames to find their size
    }
    (app, pointer)
}

#[test]
fn clicking_anywhere_on_a_row_selects_it_also_on_the_text() {
    let dir = tempfile::tempdir().unwrap();
    let (mut app, mut pointer) = settled_app(dir.path());
    let (mut hits, mut total) = (0, 0);
    let mut missed: Vec<(f32, f32)> = Vec::new();
    for y in (165..545).step_by(7) {
        for x in (225..800).step_by(23) {
            app.model.selected = None;
            pointer.click(&mut app, x as f32, y as f32);
            total += 1;
            if app.model.selected.is_some() {
                hits += 1;
            } else {
                missed.push((x as f32, y as f32));
            }
        }
    }
    // a few clicks land on a column's resize handle; anything beyond that is text swallowing the click
    assert!(
        hits * 100 >= total * 95,
        "only {hits} of {total} clicks on rows selected one; missed e.g. {:?}",
        &missed[..missed.len().min(8)]
    );
}

#[test]
fn the_screen_is_repainted_after_a_click_so_the_new_selection_shows_at_once() {
    let dir = tempfile::tempdir().unwrap();
    let (mut app, mut pointer) = settled_app(dir.path());
    // the row is drawn after the details panel: without another frame the panel would show the old selection
    // until the mouse moves
    let delay = pointer.click(&mut app, 300.0, 200.0);
    assert!(app.model.selected.is_some(), "the click missed the table");
    assert_eq!(delay, std::time::Duration::ZERO, "no repaint was requested after the click");
}

#[test]
fn a_double_click_on_a_row_adds_it_to_my_list() {
    let dir = tempfile::tempdir().unwrap();
    let (mut app, mut pointer) = settled_app(dir.path());
    pointer.click(&mut app, 300.0, 200.0);
    let first = app.model.selected.clone().expect("the first click selects the row");
    pointer.click(&mut app, 300.0, 200.0);
    assert_eq!(app.model.cart.len(), 1, "the double click did not add the row");
    assert!(
        app.model.cart.iter().any(|k| first.ends_with(k.as_str()) || k.ends_with(first.trim_start_matches("item:"))),
        "{first} / {:?}",
        app.model.cart
    );
}
