//! brewcat command line: argument parsing and the commands that need no window.
//!
//! Everything here works over SSH, in CI and on machines where the window cannot start.
//!
//! Exit codes: 0 success, 1 a check failed or an operation failed, 2 invalid usage, 130 cancelled with Ctrl-C.

use std::collections::{HashMap, HashSet};
use std::io::{IsTerminal, Write};
use std::process::Command;
use std::sync::Once;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use clap::builder::PossibleValuesParser;
use clap::{Args, CommandFactory, FromArgMatches, Parser, Subcommand};
use serde::Serialize;

use crate::catalog::{self, Item, Kind, Kit, catalog};
use crate::help_text::{VERSION, help};
use crate::{brewenv, doctor, launcher, plan, sys};

const USAGE: &str = "usage: brewcat [-h] [-V] [--install-app] [command]  (commands: doctor search list kits install export profiles help)";

fn default_platform() -> &'static str {
    if sys::is_mac() { catalog::MAC } else { catalog::LINUX }
}

fn profile_parser() -> PossibleValuesParser {
    PossibleValuesParser::new(catalog::profile_slugs())
}

#[derive(Parser, Debug)]
#[command(name = "brewcat", disable_help_flag = true, disable_version_flag = true, disable_help_subcommand = true)]
struct Cli {
    /// show the full help
    #[arg(short = 'h', long = "help", global = true)]
    help: bool,
    /// show the version and OS
    #[arg(short = 'V', long = "version")]
    version: bool,
    /// macOS: (re)create ~/Applications/brewcat.app for Launchpad/Spotlight
    #[arg(long = "install-app")]
    install_app: bool,
    #[command(subcommand)]
    command: Option<Cmd>,
}

#[derive(Args, Debug)]
struct Filters {
    /// limit to one profile
    #[arg(short = 'p', long, value_parser = profile_parser())]
    profile: Option<String>,
    /// mac or linux (default: this machine)
    #[arg(long, value_parser = ["mac", "linux"], default_value = default_platform())]
    platform: String,
    /// machine-readable output
    #[arg(long)]
    json: bool,
}

#[derive(Args, Debug)]
struct SearchArgs {
    /// words to look for (name, description, tags)
    query: Vec<String>,
    #[command(flatten)]
    filters: Filters,
    /// limit to one category
    #[arg(short = 'c', long)]
    category: Option<String>,
    /// only packages already installed
    #[arg(long)]
    installed: bool,
    /// only packages not installed yet
    #[arg(long)]
    not_installed: bool,
}

#[derive(Args, Debug)]
struct ListArgs {
    #[command(flatten)]
    filters: Filters,
    /// limit to one category
    #[arg(short = 'c', long)]
    category: Option<String>,
    /// only packages already installed
    #[arg(long)]
    installed: bool,
    /// only packages not installed yet
    #[arg(long)]
    not_installed: bool,
}

#[derive(Args, Debug)]
struct KitsArgs {
    /// kit name (or unique prefix) to show its packages
    name: Option<String>,
    #[command(flatten)]
    filters: Filters,
}

#[derive(Args, Debug)]
struct InstallArgs {
    /// kit name or package name (use formula:NAME or cask:NAME if ambiguous)
    target: String,
    /// mac or linux (default: this machine)
    #[arg(long, value_parser = ["mac", "linux"], default_value = default_platform())]
    platform: String,
    /// print the brew commands, run nothing
    #[arg(short = 'n', long)]
    dry_run: bool,
    /// do not ask for confirmation
    #[arg(short = 'y', long)]
    yes: bool,
}

#[derive(Args, Debug)]
struct ExportArgs {
    /// kit name, or one or more package names
    #[arg(required = true)]
    target: Vec<String>,
    /// mac or linux (default: this machine)
    #[arg(long, value_parser = ["mac", "linux"], default_value = default_platform())]
    platform: String,
    /// file to write (default: standard output)
    #[arg(short = 'o', long)]
    output: Option<String>,
}

#[derive(Subcommand, Debug)]
enum Cmd {
    /// check this machine and print how to fix problems
    Doctor {
        /// machine-readable output
        #[arg(long)]
        json: bool,
        /// Markdown report for a GitHub issue (paths and user name redacted; wins over --json)
        #[arg(long)]
        report: bool,
    },
    /// show the full help
    Help,
    /// search the curated catalog
    Search(SearchArgs),
    /// list the catalog (or one profile's categories)
    List(ListArgs),
    /// list kits, or show one kit's packages
    Kits(KitsArgs),
    /// install a kit or a package
    Install(InstallArgs),
    /// write a kit (or packages) as a Brewfile
    Export(ExportArgs),
    /// list the profile names for --profile
    Profiles,
}

fn parse(args: Vec<String>) -> Result<Cli, clap::Error> {
    let command = Cli::command().mut_subcommands(|c| c.disable_help_flag(true));
    let matches = command.try_get_matches_from(std::iter::once("brewcat".to_string()).chain(args))?;
    Cli::from_arg_matches(&matches)
}

/// argparse-style usage error: the usage line, then `brewcat: error: …`. Always exit code 2.
fn usage_error(e: &clap::Error) -> i32 {
    let rendered = e.render().to_string();
    let message: Vec<&str> = rendered.lines().take_while(|l| !l.trim().is_empty()).collect();
    let message = message.join("\n").trim_start_matches("error: ").to_string();
    eprintln!("{USAGE}");
    eprintln!("brewcat: error: {message}\nTry `brewcat --help`.");
    2
}

// ───────────────────────── catalog commands (no window) ─────────────────────────

/// Which packages brew reports as installed.
struct Installed {
    formula: HashSet<String>,
    cask: HashSet<String>,
}

impl Installed {
    fn has(&self, i: &Item) -> bool {
        match i.kind {
            Kind::Formula => &self.formula,
            Kind::Cask => &self.cask,
        }
        .contains(&i.name)
    }
}

/// What brew says is installed, or None when brew is missing.
fn installed() -> Option<Installed> {
    let brew = brewenv::find_brew()?;
    let list = |kind: &str| {
        let argv = brewenv::brew_command(&brew, &["list", &format!("--{kind}"), "-1"]);
        sys::run_capture(&argv, &[], Duration::from_secs(60))
            .map(|c| c.stdout)
            .unwrap_or_default()
            .split_whitespace()
            .map(String::from)
            .collect()
    };
    Some(Installed { formula: list("formula"), cask: list("cask") })
}

#[derive(Serialize)]
struct ItemJson<'a> {
    name: String,
    kind: &'a str,
    category: &'a str,
    description: &'a str,
    profiles: &'a [String],
    platforms: &'a [String],
    #[serde(skip_serializing_if = "Option::is_none")]
    installed: Option<bool>,
}

fn terminal_width() -> usize {
    std::env::var("COLUMNS")
        .ok()
        .and_then(|c| c.trim().parse::<usize>().ok())
        .filter(|&c| c > 0)
        .or_else(|| terminal_size::terminal_size().map(|(w, _)| usize::from(w.0)))
        .unwrap_or(100)
}

fn print_items(items: &[&Item], installed: Option<&Installed>, as_json: bool) {
    if as_json {
        let rows: Vec<ItemJson> = items
            .iter()
            .map(|i| ItemJson {
                name: i.full_name(),
                kind: i.kind.as_str(),
                category: &i.category,
                description: &i.desc,
                profiles: &i.profiles,
                platforms: &i.platforms,
                installed: installed.map(|inst| inst.has(i)),
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&rows).unwrap_or_default());
        return;
    }
    let width = terminal_width().max(60);
    let name_w = items.iter().map(|i| i.full_name().chars().count()).max().unwrap_or(4);
    let cat_w = items.iter().map(|i| i.category.chars().count()).max().unwrap_or(8).min(26);
    for i in items {
        let mark = match installed {
            Some(inst) if inst.has(i) => "✓",
            _ => " ",
        };
        let category: String = i.category.chars().take(cat_w).collect();
        let line = format!(
            "{mark} {:<name_w$}  {:<7} {category:<cat_w$}  {}",
            i.full_name(),
            i.kind.as_str(),
            i.desc,
            name_w = name_w,
            cat_w = cat_w
        );
        println!("{}", line.chars().take(width).collect::<String>());
    }
}

/// The catalog items that match the filters, and what is installed when that mattered.
fn select(
    f: &Filters,
    query: &str,
    category: Option<&str>,
    installed_only: bool,
    not_installed_only: bool,
) -> (Vec<&'static Item>, Option<Installed>) {
    let profile = f.profile.as_deref().and_then(catalog::profile_for_slug);
    let items = catalog().find_items(query, profile, Some(&f.platform), category);
    let inst = installed();
    if installed_only || not_installed_only {
        let Some(inst_ref) = inst.as_ref() else {
            eprintln!("brewcat: brew not found, cannot tell what is installed");
            return (Vec::new(), inst);
        };
        let items = items.into_iter().filter(|i| inst_ref.has(i) == installed_only).collect();
        return (items, inst);
    }
    (items, inst)
}

fn cmd_search(ns: &SearchArgs) -> i32 {
    let (items, inst) = select(&ns.filters, &ns.query.join(" "), ns.category.as_deref(), ns.installed, ns.not_installed);
    if items.is_empty() {
        eprintln!("brewcat: nothing found. Try `brewcat list`, or `brew search` for all of Homebrew.");
        return 1;
    }
    print_items(&items, inst.as_ref(), ns.filters.json);
    0
}

fn cmd_list(ns: &ListArgs) -> i32 {
    let (items, inst) = select(&ns.filters, "", ns.category.as_deref(), ns.installed, ns.not_installed);
    if items.is_empty() {
        eprintln!("brewcat: nothing matches those filters.");
        return 1;
    }
    print_items(&items, inst.as_ref(), ns.filters.json);
    0
}

fn cmd_profiles() -> i32 {
    for slug in catalog::profile_slugs() {
        let id = catalog::profile_for_slug(slug).unwrap_or_default();
        let n = catalog().items.iter().filter(|i| i.in_profile(id)).count();
        println!("{slug:<12} {n} packages");
    }
    0
}

fn cmd_kits(ns: &KitsArgs) -> i32 {
    let cat = catalog();
    if let Some(name) = &ns.name {
        let Some(kit) = cat.find_kit(name) else {
            eprintln!("brewcat: no kit matches '{name}' (run `brewcat kits`)");
            return 1;
        };
        let items = cat.kit_items(kit, &ns.filters.platform);
        print_items(&items, installed().as_ref(), ns.filters.json);
        return 0;
    }
    let profile = ns.filters.profile.as_deref().and_then(catalog::profile_for_slug);
    let kits: Vec<&Kit> = cat.kits.iter().filter(|k| profile.is_none_or(|p| k.profile == p)).collect();
    if ns.filters.json {
        let rows: Vec<serde_json::Value> = kits
            .iter()
            .map(|k| {
                let packages: Vec<String> = k.keys.iter().filter_map(|x| cat.by_key(x)).map(Item::full_name).collect();
                serde_json::json!({"name": k.name, "description": k.desc, "profile": k.profile, "packages": packages})
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&rows).unwrap_or_default());
    } else {
        for k in kits {
            println!("{:<34} {:<12} {:>2} packages  {}", k.name, k.profile, k.keys.len(), k.desc);
        }
    }
    0
}

/// (label, items) of what `target` names, or the message to show when it names nothing usable.
fn resolve_install_target(target: &str, platform: &str) -> Result<(String, Vec<&'static Item>), String> {
    let cat = catalog();
    if let Some(kit) = cat.find_kit(target) {
        return Ok((kit.name.clone(), cat.kit_items(kit, platform)));
    }
    let hits: Vec<&Item> = cat.resolve_packages(target).into_iter().filter(|i| i.on(platform)).collect();
    match hits.as_slice() {
        [] => Err(format!("nothing called '{target}' in the catalog (try `brewcat search {target}`)")),
        [one] => Ok((one.full_name(), vec![*one])),
        many => Err(format!("'{target}' is ambiguous: use {}", many.iter().map(|i| i.key()).collect::<Vec<_>>().join(" or "))),
    }
}

/// The `brew install …` lines that retry only `failed` (formulae and casks need separate commands).
fn retry_commands(failed: &[String], casks: &HashSet<String>) -> Vec<String> {
    let mut out = Vec::new();
    for is_cask in [false, true] {
        let names: Vec<String> = failed
            .iter()
            .filter(|n| casks.contains(*n) == is_cask)
            .map(|n| shlex::try_quote(n).map(|q| q.into_owned()).unwrap_or_else(|_| n.clone()))
            .collect();
        if !names.is_empty() {
            out.push(format!("brew install {}{}", if is_cask { "--cask " } else { "" }, names.join(" ")));
        }
    }
    out
}

/// Packages of the failed `brew install …` command `cmd` that did not install, from the recorded exit codes: a
/// single-package command failed itself; in a batch the package-by-package retry tells which ones.
fn failed_packages(cmd: &[String], codes: &HashMap<Vec<String>, i32>) -> Vec<String> {
    let flags = brewenv::flags(cmd);
    let names = brewenv::package_names(cmd);
    if names.len() == 1 {
        return vec![names[0].to_string()];
    }
    let bad: Vec<String> = names
        .iter()
        .filter(|n| {
            let one: Vec<String> = std::iter::once("install").chain(flags.iter().copied()).chain([**n]).map(String::from).collect();
            codes.get(&one).copied().unwrap_or(0) != 0
        })
        .map(|n| n.to_string())
        .collect();
    if bad.is_empty() { names.iter().map(|n| n.to_string()).collect() } else { bad }
}

// ───────────────────────── Ctrl-C ─────────────────────────

static PROMPTING: AtomicBool = AtomicBool::new(false);

/// Ctrl-C while the confirmation question is shown cancels at once; at any other time it only raises
/// [`sys::INTERRUPTED`], so the running brew can be stopped and the exit is orderly.
fn install_interrupt_handler() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let _ = ctrlc::set_handler(|| {
            if PROMPTING.load(Ordering::SeqCst) {
                eprintln!("\nCancelled.");
                std::process::exit(130);
            }
            sys::INTERRUPTED.store(true, Ordering::SeqCst);
        });
    });
}

/// Ctrl-C was pressed (or brew itself was interrupted).
struct Cancelled;

/// Run brew attached to this terminal and wait for it. `Err(Cancelled)` when the user pressed Ctrl-C.
fn run_brew_foreground(brew: &str, args: &[String]) -> Result<i32, Cancelled> {
    let argv = brewenv::brew_command(brew, args);
    let Some((prog, rest)) = argv.split_first() else { return Ok(1) };
    let mut child = match Command::new(prog).args(rest).spawn() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("brewcat: cannot run {prog}: {e}");
            return Ok(1);
        }
    };
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let code = sys::exit_code(status);
                // brew itself was interrupted: cancel, do not retry
                if sys::interrupted() || code == -libc::SIGINT || code == 128 + libc::SIGINT {
                    return Err(Cancelled);
                }
                return Ok(code);
            }
            Ok(None) => {}
            Err(_) => return Ok(1),
        }
        if sys::interrupted() {
            // SAFETY: plain syscalls on our own child's pid.
            unsafe { libc::kill(child.id() as i32, libc::SIGINT) };
            let deadline = Instant::now() + Duration::from_secs(3);
            while Instant::now() < deadline && child.try_wait().ok().flatten().is_none() {
                thread::sleep(Duration::from_millis(20));
            }
            if child.try_wait().ok().flatten().is_none() {
                let _ = child.kill();
                let _ = child.wait();
            }
            return Err(Cancelled);
        }
        thread::sleep(Duration::from_millis(25));
    }
}

enum Answer {
    Yes,
    No,
    Cancelled,
}

fn ask_to_install() -> Answer {
    print!("Install these? [y/N] ");
    let _ = std::io::stdout().flush();
    PROMPTING.store(true, Ordering::SeqCst);
    let mut line = String::new();
    let read = std::io::stdin().read_line(&mut line);
    PROMPTING.store(false, Ordering::SeqCst);
    match read {
        Ok(0) | Err(_) => Answer::Cancelled, // Ctrl-D at the prompt is a "no", not a crash
        Ok(_) if matches!(line.trim().to_lowercase().as_str(), "y" | "yes") => Answer::Yes,
        Ok(_) => Answer::No,
    }
}

fn cmd_install(ns: &InstallArgs) -> i32 {
    let (label, items) = match resolve_install_target(&ns.target, &ns.platform) {
        Ok(found) => found,
        Err(msg) => {
            eprintln!("brewcat: {msg}");
            return 1;
        }
    };
    install_interrupt_handler();
    let brew = brewenv::find_brew();
    let mut plan_data = None;
    if let Some(b) = &brew {
        eprintln!("Checking what brew would change…");
        plan_data = Some(plan::build_plan(b, &items, Duration::from_secs(60)));
        if sys::interrupted() {
            eprintln!("\nCancelled.");
            return 130;
        }
    }
    let todo: Vec<&Item> =
        items.iter().copied().filter(|i| plan_data.as_ref().is_none_or(|p| p.to_install.contains(&i.full_name()))).collect();
    if todo.is_empty() {
        println!("Everything in '{label}' is already installed.");
        return 0;
    }
    let cmds = catalog::install_commands(todo.iter().copied());
    println!("Plan for '{label}' ({} package(s)):", todo.len());
    for c in &cmds {
        println!("  brew {}", c.join(" "));
    }
    if let Some(p) = &plan_data {
        println!("{}", plan::format_plan(p));
    }
    if ns.dry_run {
        return 0;
    }
    let Some(brew) = brew else {
        eprintln!("brewcat: brew not found. Install Homebrew from https://brew.sh");
        return 1;
    };
    if !ns.yes {
        if !std::io::stdin().is_terminal() {
            eprintln!("brewcat: confirmation needed but there is no terminal; pass --yes to proceed.");
            return 2;
        }
        match ask_to_install() {
            Answer::Yes => {}
            Answer::No => {
                println!("Cancelled.");
                return 1;
            }
            Answer::Cancelled => {
                eprintln!("\nCancelled.");
                return 130;
            }
        }
    }

    let mut codes: HashMap<Vec<String>, i32> = HashMap::new(); // exit code of every brew install run
    let mut failed_names: Vec<String> = Vec::new();
    let mut failed = 0;
    for c in &cmds {
        println!("\n$ brew {}", c.join(" "));
        let _ = std::io::stdout().flush();
        let result = brewenv::install_with_retry(
            |args| {
                let code = run_brew_foreground(&brew, args)?;
                codes.insert(args.to_vec(), code);
                Ok(code)
            },
            c,
            || {
                println!("↻ batch failed, retrying package by package…");
                let _ = std::io::stdout().flush();
            },
        );
        match result {
            Err(Cancelled) => {
                eprintln!("\nCancelled.");
                return 130;
            }
            Ok(code) => {
                if code != 0 {
                    failed += 1;
                    failed_names.extend(failed_packages(c, &codes));
                }
            }
        }
    }
    if !failed_names.is_empty() {
        eprintln!("\nFailed: {}", failed_names.join(", "));
        eprintln!("Retry only those with:");
        let casks: HashSet<String> = items.iter().filter(|i| i.kind == Kind::Cask).map(|i| i.full_name()).collect();
        for line in retry_commands(&failed_names, &casks) {
            eprintln!("  {line}");
        }
    }
    i32::from(failed > 0)
}

fn cmd_export(ns: &ExportArgs) -> i32 {
    let cat = catalog();
    let mut items: Vec<&Item> = Vec::new();
    let first = if ns.target.len() == 1 { cat.find_kit(&ns.target[0]) } else { None };
    if let Some(kit) = first {
        items = cat.kit_items(kit, &ns.platform);
    } else {
        for name in &ns.target {
            let hits: Vec<&Item> = cat.resolve_packages(name).into_iter().filter(|i| i.on(&ns.platform)).collect();
            if hits.len() != 1 {
                let why = if hits.len() > 1 {
                    "ambiguous (use formula:NAME or cask:NAME)".to_string()
                } else if !cat.resolve_packages(name).is_empty() {
                    format!("not available on {}", ns.platform)
                } else {
                    "not in the catalog".to_string()
                };
                eprintln!("brewcat: '{name}' is {why}");
                return 1;
            }
            items.push(hits[0]);
        }
    }
    let text = format!("{}\n", catalog::brewfile_lines(items.iter().copied()).join("\n"));
    match &ns.output {
        Some(path) => {
            if let Err(e) = std::fs::write(path, text) {
                eprintln!("brewcat: cannot write {path}: {e}");
                return 1;
            }
            eprintln!("Wrote {} package(s) to {path}  (use: brew bundle --file={path})", items.len());
        }
        None => print!("{text}"),
    }
    0
}

/// A closed pipe (`brewcat list | head`) should end the program quietly, as with any other command.
fn restore_default_sigpipe() {
    // SAFETY: resets one signal's disposition to the default, before any other thread exists.
    unsafe { libc::signal(libc::SIGPIPE, libc::SIG_DFL) };
}

// ───────────────────────── entry ─────────────────────────

/// Handle command-line usage. Returns an exit code, or None to open the window. `args` excludes the program name
/// (None: the real command line).
pub fn run(args: Option<Vec<String>>) -> Option<i32> {
    let args: Vec<String> = args.unwrap_or_else(|| std::env::args().skip(1).collect());
    let args: Vec<String> = args.into_iter().filter(|a| !a.starts_with("-psn_")).collect(); // old macOS Finder launch argument
    let ns = match parse(args) {
        Ok(ns) => ns,
        Err(e) => return Some(usage_error(&e)),
    };
    if ns.command.is_some() || ns.help || ns.version || ns.install_app {
        restore_default_sigpipe();
    }
    if ns.help || matches!(ns.command, Some(Cmd::Help)) {
        println!("{}", help());
        return Some(0);
    }
    if ns.version {
        println!("brewcat {VERSION}\n{}", sys::os_description());
        return Some(0);
    }
    if ns.install_app {
        if !sys::is_mac() {
            println!("--install-app is only needed on macOS (the Linux installer adds a desktop entry).");
            return Some(0);
        }
        return Some(match launcher::install_app() {
            Ok(_) => {
                println!("Created ~/Applications/brewcat.app: open it from Launchpad or Spotlight.");
                0
            }
            Err(e) => {
                eprintln!("Could not create the app: {e}");
                1
            }
        });
    }
    let code = match ns.command? {
        Cmd::Doctor { report: true, .. } => {
            print!("{}", doctor::diagnostic_report());
            0
        }
        Cmd::Doctor { json, report: false } => doctor::doctor(json),
        Cmd::Help => 0,
        Cmd::Search(a) => cmd_search(&a),
        Cmd::List(a) => cmd_list(&a),
        Cmd::Kits(a) => cmd_kits(&a),
        Cmd::Install(a) => cmd_install(&a),
        Cmd::Export(a) => cmd_export(&a),
        Cmd::Profiles => cmd_profiles(),
    };
    Some(code)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn no_args_opens_the_window_and_psn_is_ignored() {
        assert_eq!(run(Some(vec![])), None);
        assert_eq!(run(Some(v(&["-psn_0_12345"]))), None); // old Finder launch argument
    }

    #[test]
    fn invalid_usage_is_an_error() {
        for args in
            [&["--nope"][..], &["nope"], &["search", "--profile", "bogus"], &["install"], &["export"], &["search", "--platform", "windows"]]
        {
            assert!(parse(v(args)).is_err(), "{args:?}");
        }
    }

    #[test]
    fn valid_usage_parses() {
        let ns = parse(v(&["search", "terraform", "-p", "sre", "--platform", "mac", "--json"])).unwrap();
        let Some(Cmd::Search(s)) = ns.command else { panic!("not a search") };
        assert_eq!(s.query, ["terraform"]);
        assert_eq!((s.filters.profile.as_deref(), s.filters.platform.as_str(), s.filters.json), (Some("sre"), "mac", true));
        assert!(parse(v(&["search", "--help"])).unwrap().help); // -h/--help work after a command too
        assert!(parse(v(&["-V"])).unwrap().version);
        assert!(matches!(parse(v(&["install", "jq", "-n", "--yes"])).unwrap().command, Some(Cmd::Install(i)) if i.dry_run && i.yes));
    }

    #[test]
    fn default_platform_follows_the_host() {
        assert_eq!(default_platform(), if cfg!(target_os = "macos") { "mac" } else { "linux" });
    }

    #[test]
    fn install_targets_are_resolved() {
        let (label, items) = resolve_install_target("git pro", "mac").unwrap();
        assert_eq!((label.as_str(), items.len()), ("Git Pro", 6));
        let (label, items) = resolve_install_target("jq", "mac").unwrap();
        assert_eq!((label.as_str(), items.len()), ("jq", 1));
        assert!(resolve_install_target("nonexistent-xyz", "mac").unwrap_err().contains("nothing called"));
        assert!(resolve_install_target("cask:obs", "linux").is_err()); // casks are macOS only
    }

    #[test]
    fn retry_commands_split_formulae_and_casks() {
        let casks: HashSet<String> = ["visual-studio-code".to_string()].into();
        assert_eq!(
            retry_commands(&v(&["jq", "visual-studio-code", "gh"]), &casks),
            ["brew install jq gh", "brew install --cask visual-studio-code"]
        );
        assert_eq!(retry_commands(&v(&["hashicorp/tap/terraform"]), &HashSet::new()), ["brew install hashicorp/tap/terraform"]);
        assert!(retry_commands(&[], &casks).is_empty());
    }

    #[test]
    fn failed_packages_come_from_the_recorded_codes() {
        let mut codes = HashMap::new();
        codes.insert(v(&["install", "a"]), 0);
        codes.insert(v(&["install", "b"]), 1);
        assert_eq!(failed_packages(&v(&["install", "a", "b"]), &codes), ["b"]);
        assert_eq!(failed_packages(&v(&["install", "a"]), &codes), ["a"]); // a single package failed itself
        // no per-package record at all: blame the whole batch
        assert_eq!(failed_packages(&v(&["install", "x", "y"]), &HashMap::new()), ["x", "y"]);
        // flags are part of the key, so casks look up their own retries
        codes.insert(v(&["install", "--cask", "c"]), 1);
        codes.insert(v(&["install", "--cask", "d"]), 0);
        assert_eq!(failed_packages(&v(&["install", "--cask", "c", "d"]), &codes), ["c"]);
    }
}
