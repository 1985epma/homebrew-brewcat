//! The logic of the Packages tab that needs no egui types: what is listed, what is selected, the list of things to
//! install, how a batch of brew commands turned out, and the small files brewcat keeps. Everything here is
//! unit-tested; the drawing code in `app.rs` only shows it.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::fs;
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use regex::Regex;

use crate::brewenv;
use crate::catalog::{self, Item, Kind, Kit, catalog};
use crate::sys;

pub const ALL: &str = "★ All";
pub const SUGGEST: &str = "✨ Suggestions";
pub const KITS: &str = "📦 Kits";
pub const CART: &str = "🛒 My list";
pub const SEARCH: &str = "🔎 Homebrew search";
/// Category of the items found with `brew search` that are not in the curated catalog.
pub const EXTRA_CAT: &str = "Homebrew search";

/// (label shown, profile id). `None` means "all profiles".
pub const PROFILES: [(&str, Option<&str>); 14] = [
    ("All", None),
    ("117-labs (by 1985epma)", Some(catalog::LABS)),
    ("Dev", Some(catalog::DEV)),
    ("SRE / Cloud", Some(catalog::SRE)),
    ("QA", Some(catalog::QA)),
    ("Data Scientist", Some(catalog::DS)),
    ("Data Engineer", Some(catalog::DE)),
    ("Support & Network", Some(catalog::NET)),
    ("Security", Some(catalog::SEC)),
    ("Design (web, video, graphics)", Some(catalog::DESIGN)),
    ("DJ / Music", Some(catalog::DJ)),
    ("Office", Some(catalog::OFFICE)),
    ("Vendors (Microsoft, Google, Amazon, Anthropic, Oracle, Apple, IBM, Red Hat…)", Some(catalog::VENDOR)),
    ("Gamer", Some(catalog::GAMER)),
];

/// The platform of this machine, as the catalog names it.
pub fn system() -> &'static str {
    if sys::is_mac() { catalog::MAC } else { catalog::LINUX }
}

/// What `brew list` says is installed.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Installed {
    pub formula: HashSet<String>,
    pub cask: HashSet<String>,
}

impl Installed {
    pub fn has(&self, kind: Kind, name: &str) -> bool {
        match kind {
            Kind::Formula => self.formula.contains(name),
            Kind::Cask => self.cask.contains(name),
        }
    }
}

/// A row of the table: a package or a kit.
#[derive(Debug, Clone, PartialEq)]
pub enum Obj {
    Item(Item),
    Kit(Kit),
}

impl Obj {
    /// Identity of the row, stable across refreshes.
    pub fn id(&self) -> String {
        match self {
            Obj::Item(i) => i.key(),
            Obj::Kit(k) => format!("kit:{}", k.name),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Row {
    pub obj: Obj,
    /// "✓" (installed), "🛒" (in My list) or empty.
    pub mark: String,
    pub name: String,
    pub kind: String,
    pub category: String,
    pub desc: String,
    /// Why a suggestion is shown.
    pub reason: String,
    pub installed: bool,
}

/// What to confirm before running brew.
#[derive(Debug, Clone)]
pub struct InstallRequest {
    pub title: String,
    pub items: Vec<Item>,
    pub cmds: Vec<Vec<String>>,
    /// The plain question shown when the plan cannot be computed.
    pub fallback: String,
}

/// What a click on an install button leads to.
#[derive(Debug, Clone)]
pub enum InstallOutcome {
    Confirm(InstallRequest),
    /// Nothing to do; say so in the log.
    Nothing(&'static str),
}

pub fn brew_line(cmd: &[String]) -> String {
    format!("brew {}", cmd.join(" "))
}

fn name_ok(name: &str) -> bool {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[\w][\w.+@/-]*$").expect("valid regex")).is_match(name)
}

/// Items for the names `brew search` found: sorted, at most 60, nothing that is not a plausible package name.
pub fn extras_from_search(found: &[(Kind, String)]) -> Vec<Item> {
    let mut found: Vec<&(Kind, String)> = found.iter().collect();
    found.sort_by(|a, b| (a.1.as_str(), a.0.as_str()).cmp(&(b.1.as_str(), b.0.as_str())));
    let mut items = Vec::new();
    for (kind, full) in found.into_iter().take(60) {
        if !name_ok(full) {
            continue; // ignore anything that is not a plausible package name
        }
        let (tap, name) = match full.rsplit_once('/') {
            Some((tap, name)) => (tap, name), // tap-qualified result: user/repo/name
            None => ("", full.as_str()),
        };
        items.push(Item::external(name, *kind, EXTRA_CAT, "Not in the curated catalog", tap));
    }
    items
}

/// The page where a package can be researched before installing it.
pub fn page_url(item: &Item) -> String {
    if !item.homepage.is_empty() {
        return item.homepage.clone();
    }
    if let Some((user, repo)) = item.tap.split_once('/') {
        return format!("https://github.com/{user}/homebrew-{repo}");
    }
    format!("https://formulae.brew.sh/{}/{}", item.kind.as_str(), item.name)
}

/// Everything the Packages tab shows and lets you pick.
#[derive(Debug)]
pub struct Model {
    pub installed: Installed,
    /// Keys (`kind:name`) of the packages in My list.
    pub cart: BTreeSet<String>,
    pub profile_label: String,
    pub platform: String,
    pub search: String,
    pub category: String,
    /// Results of `brew search` outside the curated catalog.
    pub extra: Vec<Item>,
    pub extra_desc: HashMap<String, String>,
    known_extra: HashMap<String, Item>,
    pub rows: Vec<Row>,
    /// `Obj::id` of the selected row.
    pub selected: Option<String>,
}

impl Default for Model {
    fn default() -> Self {
        Model::new(system())
    }
}

impl Model {
    pub fn new(platform: &str) -> Model {
        let mut m = Model {
            installed: Installed::default(),
            cart: BTreeSet::new(),
            profile_label: "All".to_string(),
            platform: platform.to_string(),
            search: String::new(),
            category: ALL.to_string(),
            extra: Vec::new(),
            extra_desc: HashMap::new(),
            known_extra: HashMap::new(),
            rows: Vec::new(),
            selected: None,
        };
        m.refresh();
        m
    }

    pub fn visible_profile(&self) -> Option<&'static str> {
        PROFILES.iter().find(|(label, _)| *label == self.profile_label).and_then(|(_, id)| *id)
    }

    /// The entries of the category list: the special views, then the topics of the profile.
    pub fn category_entries(&self) -> Vec<String> {
        let cats = catalog().categories(self.visible_profile());
        [ALL, SUGGEST, KITS, CART, SEARCH].into_iter().chain(cats).map(String::from).collect()
    }

    pub fn is_installed(&self, item: &Item) -> bool {
        self.installed.has(item.kind, &item.name)
    }

    /// An item of the catalog, or one found with `brew search` earlier.
    pub fn lookup(&self, key: &str) -> Option<Item> {
        catalog().by_key(key).cloned().or_else(|| self.known_extra.get(key).cloned())
    }

    pub fn matches(&self, item: &Item) -> bool {
        if let Some(p) = self.visible_profile()
            && !item.in_profile(p)
        {
            return false;
        }
        if !item.on(&self.platform) {
            return false;
        }
        let q = self.search.trim().to_lowercase();
        if q.is_empty() {
            return true;
        }
        let hay = item.haystack();
        q.split_whitespace().all(|w| hay.contains(w))
    }

    /// Uninstalled items that pair with what is installed (by shared tags) or are essential for the profile,
    /// best first, with the reason.
    pub fn suggestions(&self) -> Vec<(Item, String)> {
        let cat = catalog();
        let have: Vec<&Item> = cat.items.iter().filter(|i| self.is_installed(i)).collect();
        let mut weights: HashMap<&str, i32> = HashMap::new();
        for i in &have {
            for t in &i.tags {
                *weights.entry(t.as_str()).or_insert(0) += 1;
            }
        }
        let prof = self.visible_profile();
        let essentials: HashSet<&str> = match prof {
            Some(p) => cat.essentials_for(p).iter().map(String::as_str).collect(),
            None => cat.essentials.values().flatten().map(String::as_str).collect(),
        };
        let mut out: Vec<(i32, &Item, String)> = Vec::new();
        for item in &cat.items {
            if self.is_installed(item) || !self.matches(item) {
                continue;
            }
            let shared: Vec<&str> = item.tags.iter().map(String::as_str).filter(|t| weights.contains_key(t)).collect();
            let mut score: i32 = shared.iter().map(|t| weights[t]).sum();
            let mut reason = String::new();
            if !shared.is_empty() {
                let srcs: Vec<&str> =
                    have.iter().filter(|h| h.tags.iter().any(|t| shared.contains(&t.as_str()))).map(|h| h.name.as_str()).take(3).collect();
                reason = format!("Pairs well with what you use: {}", srcs.join(", "));
            }
            if essentials.contains(item.key().as_str()) {
                score += 3;
                if reason.is_empty() {
                    reason = "Essential for this profile".to_string();
                }
            }
            if score > 0 {
                out.push((score, item, reason));
            }
        }
        out.sort_by(|a, b| (-a.0, a.1.name.as_str()).cmp(&(-b.0, b.1.name.as_str())));
        out.into_iter().take(40).map(|(_, i, r)| (i.clone(), r)).collect()
    }

    fn item_row(&self, item: &Item, reason: &str) -> Row {
        let installed = self.is_installed(item);
        let mark = if installed {
            "✓"
        } else if self.cart.contains(&item.key()) {
            "🛒"
        } else {
            ""
        };
        Row {
            obj: Obj::Item(item.clone()),
            mark: mark.to_string(),
            name: item.name.clone(),
            kind: item.kind.as_str().to_string(),
            category: item.category.clone(),
            desc: item.desc.clone(),
            reason: reason.to_string(),
            installed,
        }
    }

    fn kit_row(&self, kit: &Kit) -> Row {
        let items: Vec<Item> = kit.keys.iter().filter_map(|k| self.lookup(k)).collect();
        let done = items.iter().filter(|i| self.is_installed(i)).count();
        Row {
            obj: Obj::Kit(kit.clone()),
            mark: if done == items.len() { "✓" } else { "" }.to_string(),
            name: kit.name.clone(),
            kind: format!("{done}/{}", items.len()),
            category: format!("Kit {}", kit.profile),
            desc: kit.desc.clone(),
            reason: String::new(),
            installed: false,
        }
    }

    /// Rebuild the rows for the current profile, platform, search and category. The selection is kept when its
    /// row is still listed.
    pub fn refresh(&mut self) {
        let cat = catalog();
        let q = self.search.trim().to_lowercase();
        let mut rows = Vec::new();
        if self.category == KITS {
            let prof = self.visible_profile();
            for kit in &cat.kits {
                if prof.is_some_and(|p| kit.profile != p) {
                    continue;
                }
                if !q.is_empty() && !format!("{}{}", kit.name, kit.desc).to_lowercase().contains(&q) {
                    continue;
                }
                rows.push(self.kit_row(kit));
            }
        } else {
            let on_platform = |i: &Item| i.on(&self.platform);
            let pairs: Vec<(Item, String)> = if self.category == SUGGEST {
                self.suggestions()
            } else if self.category == CART {
                self.cart.iter().filter_map(|k| self.lookup(k)).filter(|i| self.matches(i)).map(|i| (i, String::new())).collect()
            } else if self.category == SEARCH {
                self.extra.iter().filter(|i| on_platform(i)).map(|i| (i.clone(), String::new())).collect()
            } else {
                let mut items: Vec<&Item> = cat.items.iter().collect();
                items.sort_by(|a, b| a.name.cmp(&b.name));
                let mut pairs: Vec<(Item, String)> = items
                    .into_iter()
                    .filter(|i| (self.category == ALL || i.in_category(&self.category)) && self.matches(i))
                    .map(|i| (i.clone(), String::new()))
                    .collect();
                if self.category == ALL {
                    pairs.extend(self.extra.iter().filter(|i| on_platform(i)).map(|i| (i.clone(), String::new())));
                }
                pairs
            };
            rows.extend(pairs.iter().map(|(i, r)| self.item_row(i, r)));
        }
        self.rows = rows;
        if self.selected.as_ref().is_some_and(|id| !self.rows.iter().any(|r| &r.obj.id() == id)) {
            self.selected = None;
        }
    }

    pub fn selected_row(&self) -> Option<&Row> {
        let id = self.selected.as_ref()?;
        self.rows.iter().find(|r| &r.obj.id() == id)
    }

    pub fn selected_obj(&self) -> Option<&Obj> {
        self.selected_row().map(|r| &r.obj)
    }

    pub fn select_first(&mut self) {
        self.selected = self.rows.first().map(|r| r.obj.id());
    }

    /// Show the kits of `profile_label` and select the first one. Installs nothing.
    pub fn show_starter_kits(&mut self, profile_label: &str) {
        if PROFILES.iter().any(|(label, _)| *label == profile_label) {
            self.profile_label = profile_label.to_string();
        }
        self.category = KITS.to_string();
        self.refresh();
        self.select_first();
    }

    pub fn set_installed(&mut self, installed: Installed) {
        self.installed = installed;
        self.refresh();
    }

    /// Take the results of `brew search` for `q`; a result for an older query is dropped (returns false).
    pub fn set_extra(&mut self, q: &str, found: &[(Kind, String)]) -> bool {
        if q != self.search.trim() {
            return false;
        }
        self.extra = extras_from_search(found);
        for item in &self.extra {
            self.known_extra.insert(item.key(), item.clone());
        }
        self.refresh();
        true
    }

    /// The items of a kit that exist on the chosen platform.
    pub fn kit_items(&self, kit: &Kit) -> Vec<Item> {
        kit.keys.iter().filter_map(|k| self.lookup(k)).filter(|i| i.on(&self.platform)).collect()
    }

    /// The brew lines that would install what a kit still lacks.
    pub fn kit_commands_text(&self, kit: &Kit) -> String {
        let lines: Vec<String> =
            self.kit_items(kit).iter().filter(|i| !self.is_installed(i)).map(|i| brew_line(&i.install_cmd())).collect();
        lines.join("\n")
    }

    /// The text of the command box for the selected row.
    pub fn command_text(&self, obj: &Obj) -> String {
        match obj {
            Obj::Kit(k) => self.kit_commands_text(k),
            Obj::Item(i) => brew_line(&i.install_cmd()),
        }
    }

    /// The description shown for a row: for packages found with `brew search` it is the text brew gave us.
    pub fn description(&self, item: &Item) -> String {
        if item.category == EXTRA_CAT {
            return match self.extra_desc.get(&item.key()) {
                Some(d) if !d.is_empty() => d.clone(),
                _ => "Not in the curated catalog. Loading description…".to_string(),
            };
        }
        item.desc.clone()
    }

    /// True when the description of this package from `brew search` still has to be fetched.
    pub fn needs_desc(&self, item: &Item) -> bool {
        item.category == EXTRA_CAT && !self.extra_desc.contains_key(&item.key())
    }

    pub fn toggle_cart(&mut self, obj: &Obj) {
        match obj {
            Obj::Kit(kit) => {
                let keys: Vec<String> = self.kit_items(kit).iter().map(Item::key).collect();
                self.cart.extend(keys);
            }
            Obj::Item(item) => {
                let key = item.key();
                if !self.cart.remove(&key) {
                    self.cart.insert(key);
                }
            }
        }
        self.refresh();
    }

    pub fn clear_cart(&mut self) {
        self.cart.clear();
        self.refresh();
    }

    /// Install button for the selected row.
    pub fn install_selected(&self, obj: &Obj) -> InstallOutcome {
        let (items, cmds) = match obj {
            Obj::Kit(kit) => {
                let items: Vec<Item> = self.kit_items(kit).into_iter().filter(|i| !self.is_installed(i)).collect();
                let cmds = catalog::install_commands(&items);
                (items, cmds)
            }
            Obj::Item(item) => (vec![item.clone()], vec![item.install_cmd()]),
        };
        if cmds.is_empty() {
            return InstallOutcome::Nothing("Everything in this kit is already installed.\n");
        }
        let lines: Vec<String> = cmds.iter().map(|c| brew_line(c)).collect();
        InstallOutcome::Confirm(InstallRequest {
            title: "Confirm installation".to_string(),
            items,
            cmds,
            fallback: format!("Run the following?\n\n{}", lines.join("\n")),
        })
    }

    /// "Install list": every package in My list that is not installed and exists on this platform. None when
    /// there is nothing to install.
    pub fn install_cart(&self) -> Option<InstallRequest> {
        let items: Vec<Item> =
            self.cart.iter().filter_map(|k| self.lookup(k)).filter(|i| !self.is_installed(i) && i.on(&self.platform)).collect();
        if items.is_empty() {
            return None;
        }
        let names: Vec<&str> = items.iter().map(|i| i.name.as_str()).collect();
        Some(InstallRequest {
            title: "Install list".to_string(),
            cmds: items.iter().map(Item::install_cmd).collect(),
            fallback: format!("Install {} packages?\n\n{}", items.len(), names.join(", ")),
            items: items.clone(),
        })
    }

    /// The items to put in a Brewfile: My list, or else the selected package or kit.
    pub fn export_items(&self) -> Vec<Item> {
        let mut keys: BTreeSet<String> = self.cart.clone();
        if keys.is_empty() {
            match self.selected_obj() {
                Some(Obj::Kit(kit)) => keys.extend(kit.keys.iter().cloned()),
                Some(Obj::Item(item)) => {
                    keys.insert(item.key());
                }
                None => {}
            }
        }
        keys.iter().filter_map(|k| self.lookup(k)).filter(|i| i.on(&self.platform)).collect()
    }

    /// The catalog items behind `brew install` commands (used to plan a retry).
    pub fn items_for(&self, cmds: &[Vec<String>]) -> Vec<Item> {
        let mut items: Vec<Item> = Vec::new();
        for cmd in cmds {
            let kind = if cmd.iter().any(|a| a == "--cask") { Kind::Cask } else { Kind::Formula };
            for name in brewenv::package_names(cmd) {
                let found = catalog().items.iter().chain(self.known_extra.values()).find(|i| i.kind == kind && i.full_name() == name);
                if let Some(found) = found
                    && !items.contains(found)
                {
                    items.push(found.clone());
                }
            }
        }
        items
    }
}

// ───────────────────────── how a batch of brew commands went ─────────────────────────

/// What happened in one batch of brew commands. Fed with the arguments and exit code of every brew call,
/// including the package-by-package retries `install_with_retry` makes after a failed batch.
#[derive(Debug, Clone, Default)]
pub struct BatchResult {
    pub calls: Vec<(Vec<String>, i32)>,
}

impl BatchResult {
    pub fn record(&mut self, args: &[String], code: i32) {
        self.calls.push((args.to_vec(), code));
    }

    fn is_install(args: &[String]) -> bool {
        args.first().is_some_and(|a| a == "install")
    }

    /// Packages installed by a call that exited 0.
    pub fn succeeded(&self) -> Vec<String> {
        let mut out: Vec<String> = Vec::new();
        for (args, code) in &self.calls {
            if *code == 0 && Self::is_install(args) {
                for n in brewenv::package_names(args) {
                    if !out.iter().any(|o| o == n) {
                        out.push(n.to_string());
                    }
                }
            }
        }
        out
    }

    /// A package failed when a single-package install exited non-zero (a failed batch of several is retried package
    /// by package, so the culprits show up as single-package calls).
    fn failed_with_flags(&self) -> Vec<(String, Vec<String>)> {
        let done = self.succeeded();
        let mut out: Vec<(String, Vec<String>)> = Vec::new();
        for (args, code) in &self.calls {
            let names = brewenv::package_names(args);
            if *code != 0
                && Self::is_install(args)
                && names.len() == 1
                && !done.iter().any(|d| d == names[0])
                && !out.iter().any(|(n, _)| n == names[0])
            {
                out.push((names[0].to_string(), brewenv::flags(args).into_iter().map(String::from).collect()));
            }
        }
        out
    }

    pub fn failed_installs(&self) -> Vec<String> {
        self.failed_with_flags().into_iter().map(|(n, _)| n).collect()
    }

    /// Failed commands that are not package installs (e.g. `brew update`); they are reported, not retried.
    pub fn failed_other(&self) -> Vec<String> {
        self.calls
            .iter()
            .filter(|(args, code)| *code != 0 && !args.is_empty() && !Self::is_install(args))
            .map(|(args, _)| brew_line(args))
            .collect()
    }

    /// Install commands for ONLY the failed packages, grouped by flags (so casks stay casks).
    pub fn retry_commands(&self) -> Vec<Vec<String>> {
        let mut groups: Vec<(Vec<String>, Vec<String>)> = Vec::new();
        for (name, flags) in self.failed_with_flags() {
            match groups.iter_mut().find(|(f, _)| *f == flags) {
                Some((_, names)) => names.push(name),
                None => groups.push((flags, vec![name])),
            }
        }
        groups.into_iter().map(|(flags, names)| ["install".to_string()].into_iter().chain(flags).chain(names).collect()).collect()
    }
}

/// How the window words the end of a batch.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Summary {
    /// Shown in the status line (and, with a blank line before it, in the log).
    pub line: String,
    /// Written to the log.
    pub log: String,
    /// What the Retry failed button runs (nothing for a stopped batch: that is not a failure).
    pub failed_cmds: Vec<Vec<String>>,
}

fn plural(n: usize, word: &str) -> String {
    format!("{n} {word}{}", if n == 1 { "" } else { "s" })
}

/// Say how the batch went and what failed so it can be retried (stopped runs are not failures).
pub fn batch_summary(result: &BatchResult, cancelled: bool) -> Summary {
    if cancelled {
        return Summary { line: "Stopped.".to_string(), log: "\nStopped before finishing.\n".to_string(), failed_cmds: Vec::new() };
    }
    let (failed, other, ok) = (result.failed_installs(), result.failed_other(), result.succeeded());
    let mut failed_cmds = Vec::new();
    let line = if !failed.is_empty() || !other.is_empty() {
        failed_cmds = result.retry_commands();
        let mut bits = Vec::new();
        if !failed.is_empty() {
            bits.push(format!("{} failed: {}", plural(failed.len(), "package"), failed.join(", ")));
        }
        if !other.is_empty() {
            bits.push(format!("{} failed: {}", plural(other.len(), "command"), other.join(", ")));
        }
        if !ok.is_empty() {
            bits.push(format!("{} installed", ok.len()));
        }
        let mut line = format!("✗ {}", bits.join("; "));
        line.push_str(if failed.is_empty() {
            ". Use Copy log to report it."
        } else {
            ". Use Retry failed to try those again, or Copy log to report it."
        });
        line
    } else if !ok.is_empty() {
        format!("✓ {} installed successfully.", plural(ok.len(), "package"))
    } else {
        "✓ Done.".to_string()
    };
    Summary { log: format!("\n{line}\n"), line, failed_cmds }
}

// ───────────────────────── closing the window ─────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloseAction {
    Quit,
    /// An installation is running: ask first.
    Ask,
}

/// Closing the window must not leave a brew child running unnoticed in the background.
pub fn close_action(busy: bool) -> CloseAction {
    if busy { CloseAction::Ask } else { CloseAction::Quit }
}

// ───────────────────────── small files brewcat keeps ─────────────────────────

pub fn welcome_flag(cfg: &Path) -> PathBuf {
    cfg.join("welcome_seen")
}

/// Decide whether to show the first-run welcome. The flag is written BEFORE showing it, so closing it in any way
/// (Skip, X, quit) still counts as seen. `BREWCAT_NO_WELCOME` (`suppressed`) shows nothing and writes nothing.
pub fn claim_welcome(cfg: &Path, suppressed: bool) -> bool {
    let flag = welcome_flag(cfg);
    if suppressed || flag.exists() {
        return false;
    }
    let _ = fs::create_dir_all(cfg).and_then(|()| fs::File::create(&flag).map(drop));
    true
}

pub fn rosetta_flag(cfg: &Path) -> PathBuf {
    cfg.join("rosetta_declined")
}

/// Many casks are Intel-only; without Rosetta 2 macOS shows an install prompt/error. Ask unless declined before.
pub fn rosetta_wanted(cfg: &Path, apple_silicon: bool, rosetta_present: bool) -> bool {
    apple_silicon && !rosetta_present && !rosetta_flag(cfg).exists()
}

pub fn rosetta_present() -> bool {
    Path::new("/Library/Apple/usr/share/rosetta/rosetta").exists()
}

/// The body of the SUDO_ASKPASS helper. brew runs without a terminal, so casks that need `sudo` (Microsoft Office,
/// drivers, pkg installers…) would hang; with this helper sudo asks for the password in a native dialog instead.
pub fn askpass_body(mac: bool) -> String {
    if mac {
        concat!(
            "#!/bin/bash\n",
            "/usr/bin/osascript -e 'on run argv' ",
            "-e 'set pkg to item 1 of argv' ",
            "-e 'set msg to \"brewcat: enter your macOS password\"' ",
            "-e 'if pkg is not \"\" then set msg to msg & \" to install \" & pkg' ",
            "-e 'text returned of (display dialog msg default answer \"\" with hidden answer ",
            "with icon caution with title \"brewcat\")' ",
            "-e 'end run' -- \"${BREWCAT_PKG:-}\"\n",
        )
        .to_string()
    } else {
        concat!(
            "#!/bin/bash\n",
            "if command -v zenity >/dev/null; then exec zenity --password --title=\"brewcat ${BREWCAT_PKG:-}\"\n",
            "elif command -v kdialog >/dev/null; then exec kdialog --password \"brewcat: enter your password ${BREWCAT_PKG:-}\"\n",
            "else exit 1; fi\n",
        )
        .to_string()
    }
}

/// Create the SUDO_ASKPASS helper in `cfg` (never group/world readable) and return its path.
pub fn ensure_askpass(cfg: &Path) -> Option<PathBuf> {
    let path = cfg.join("askpass.sh");
    fs::create_dir_all(cfg).ok()?;
    let mut file = fs::OpenOptions::new().write(true).create(true).truncate(true).mode(0o700).open(&path).ok()?;
    file.write_all(askpass_body(sys::is_mac()).as_bytes()).ok()?;
    drop(file);
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).ok()?;
    Some(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(k: &str) -> Item {
        catalog().by_key(k).unwrap().clone()
    }

    fn v(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    fn model() -> Model {
        Model::new(catalog::MAC)
    }

    fn names(m: &Model) -> Vec<String> {
        m.rows.iter().map(|r| r.name.clone()).collect()
    }

    // ───────────────────────── rows ─────────────────────────
    #[test]
    fn every_profile_and_category_renders_rows() {
        let mut m = model();
        for (label, _) in PROFILES {
            m.profile_label = label.to_string();
            for cat in m.category_entries() {
                m.category = cat;
                m.refresh();
            }
        }
        m.profile_label = "All".to_string();
        m.category = ALL.to_string();
        m.refresh();
        assert!(m.rows.len() > 100);
    }

    #[test]
    fn every_profile_lists_kits_and_its_own_categories() {
        let mut m = model();
        for (label, id) in PROFILES {
            m.profile_label = label.to_string();
            m.category = KITS.to_string();
            m.refresh();
            if let Some(id) = id {
                assert!(!m.rows.is_empty(), "{label} has no kits");
                assert!(m.rows.iter().all(|r| matches!(&r.obj, Obj::Kit(k) if k.profile == id)), "{label}");
                for cat in catalog().categories(Some(id)) {
                    m.category = cat.to_string();
                    m.refresh();
                    assert!(!m.rows.is_empty(), "{label}: empty category {cat}");
                }
            }
        }
    }

    #[test]
    fn search_filters_the_list() {
        let mut m = model();
        m.search = "terraform".to_string();
        m.refresh();
        let n = names(&m);
        assert!(n.contains(&"terraform".to_string()) && !n.contains(&"git".to_string()));
    }

    #[test]
    fn search_needs_every_word_and_respects_the_platform() {
        let mut m = model();
        m.search = "terraform aws".to_string();
        m.refresh();
        assert!(names(&m).iter().all(|n| catalog().items.iter().any(|i| &i.name == n)));
        m.platform = catalog::LINUX.to_string();
        m.search = String::new();
        m.refresh();
        assert!(m.rows.iter().all(|r| matches!(&r.obj, Obj::Item(i) if i.on(catalog::LINUX))));
        assert!(!names(&m).contains(&"obs".to_string())); // a cask: macOS only
    }

    #[test]
    fn all_view_is_sorted_by_name() {
        let m = model();
        let n = names(&m);
        let mut sorted = n.clone();
        sorted.sort();
        assert_eq!(n, sorted);
    }

    #[test]
    fn installed_items_are_marked_and_the_cart_shows_a_basket() {
        let mut m = model();
        m.installed.formula.insert("git".to_string());
        m.cart.insert("formula:jq".to_string());
        m.refresh();
        let row = |n: &str| m.rows.iter().find(|r| r.name == n && r.kind == "formula").unwrap();
        assert_eq!((row("git").mark.as_str(), row("git").installed), ("✓", true));
        assert_eq!((row("jq").mark.as_str(), row("jq").installed), ("🛒", false));
        assert_eq!(row("ripgrep").mark, "");
    }

    #[test]
    fn kits_show_how_many_are_installed() {
        let mut m = model();
        m.category = KITS.to_string();
        m.profile_label = "Dev".to_string();
        let kit = catalog().find_kit("git pro").unwrap().clone();
        for k in kit.keys.iter().take(2) {
            m.installed.formula.insert(catalog().by_key(k).unwrap().name.clone());
        }
        m.refresh();
        let row = m.rows.iter().find(|r| r.name == "Git Pro").unwrap();
        assert_eq!((row.kind.as_str(), row.mark.as_str(), row.category.as_str()), ("2/6", "", "Kit dev"));
        for k in &kit.keys {
            m.installed.formula.insert(catalog().by_key(k).unwrap().name.clone());
        }
        m.refresh();
        assert_eq!(m.rows.iter().find(|r| r.name == "Git Pro").unwrap().mark, "✓");
    }

    #[test]
    fn kit_search_matches_name_and_description() {
        let mut m = model();
        m.category = KITS.to_string();
        m.search = "git pro".to_string();
        m.refresh();
        assert_eq!(names(&m), ["Git Pro"]);
    }

    #[test]
    fn selection_survives_a_refresh_while_the_row_is_listed() {
        let mut m = model();
        m.select_first();
        let id = m.selected.clone().unwrap();
        m.cart.insert("formula:jq".to_string());
        m.refresh();
        assert_eq!(m.selected.as_deref(), Some(id.as_str()));
        m.search = "zzzzzz-nothing".to_string();
        m.refresh();
        assert_eq!(m.selected, None);
    }

    // ───────────────────────── welcome starter kit ─────────────────────────
    #[test]
    fn starter_kit_switches_to_kits_and_selects_the_first_of_the_profile() {
        let mut m = model();
        m.show_starter_kits("QA");
        assert_eq!((m.profile_label.as_str(), m.category.as_str()), ("QA", KITS));
        match m.selected_obj() {
            Some(Obj::Kit(k)) => assert_eq!(k.profile, catalog::QA),
            other => panic!("expected a kit, got {other:?}"),
        }
        assert_eq!(m.selected.as_deref(), m.rows.first().map(|r| r.obj.id()).as_deref());
        let mut unknown = model();
        unknown.show_starter_kits("Nonexistent");
        assert_eq!((unknown.profile_label.as_str(), unknown.category.as_str()), ("All", KITS));
    }

    // ───────────────────────── suggestions ─────────────────────────
    #[test]
    fn suggestions_pair_with_what_is_installed() {
        let mut m = model();
        m.installed.formula.insert("terraform".to_string()); // a tap formula: name only
        let got = m.suggestions();
        assert!(!got.is_empty() && got.len() <= 40);
        assert!(got.iter().all(|(i, _)| !m.is_installed(i)));
        assert!(got.iter().any(|(_, reason)| reason.starts_with("Pairs well with what you use: ")));
    }

    #[test]
    fn suggestions_fall_back_to_the_essentials_of_the_profile() {
        let mut m = model();
        m.profile_label = "Dev".to_string();
        let got = m.suggestions();
        let essential = catalog().essentials_for(catalog::DEV);
        assert!(got.iter().all(|(i, r)| essential.contains(&i.key()) && r == "Essential for this profile"));
        assert_eq!(got.len(), essential.iter().filter(|k| catalog().by_key(k).is_some_and(|i| m.matches(i))).count());
    }

    #[test]
    fn suggestions_are_sorted_by_score_then_name() {
        let mut m = model();
        m.installed.formula.extend(["git".to_string(), "tmux".to_string()]);
        let got = m.suggestions();
        let essential_first = got.first().map(|(i, _)| i.name.clone());
        assert!(essential_first.is_some());
        let again: Vec<String> = m.suggestions().into_iter().map(|(i, _)| i.name).collect();
        assert_eq!(got.into_iter().map(|(i, _)| i.name).collect::<Vec<_>>(), again);
    }

    // ───────────────────────── cart and installs ─────────────────────────
    #[test]
    fn cart_toggles_items_and_adds_kits() {
        let mut m = model();
        let jq = Obj::Item(key("formula:jq"));
        m.toggle_cart(&jq);
        assert!(m.cart.contains("formula:jq"));
        m.toggle_cart(&jq);
        assert!(m.cart.is_empty());
        let kit = Obj::Kit(catalog().find_kit("git pro").unwrap().clone());
        m.toggle_cart(&kit);
        assert_eq!(m.cart.len(), 6);
        m.toggle_cart(&kit); // adding a kit twice never removes
        assert_eq!(m.cart.len(), 6);
        m.clear_cart();
        assert!(m.cart.is_empty());
    }

    #[test]
    fn kit_cart_skips_what_the_platform_lacks() {
        let mut m = Model::new(catalog::LINUX);
        let kit = Obj::Kit(catalog().find_kit("117-labs").unwrap().clone());
        m.toggle_cart(&kit);
        assert!(m.cart.contains("formula:terminal117") && !m.cart.contains("cask:117terminal"));
    }

    #[test]
    fn install_selected_for_an_item_and_a_kit() {
        let mut m = model();
        let InstallOutcome::Confirm(req) = m.install_selected(&Obj::Item(key("cask:obs"))) else { panic!("expected a confirmation") };
        assert_eq!(req.cmds, [v(&["install", "--cask", "obs"])]);
        assert_eq!(req.fallback, "Run the following?\n\nbrew install --cask obs");
        let kit = catalog().find_kit("git pro").unwrap().clone();
        let InstallOutcome::Confirm(req) = m.install_selected(&Obj::Kit(kit.clone())) else { panic!("expected a confirmation") };
        assert_eq!(req.items.len(), 6);
        assert_eq!(req.cmds.len(), 1);
        assert_eq!(req.cmds[0][..3], v(&["install", "git", "gh"])[..]);
        for item in m.kit_items(&kit) {
            m.installed.formula.insert(item.name);
        }
        assert!(matches!(m.install_selected(&Obj::Kit(kit)), InstallOutcome::Nothing(msg) if msg.contains("already installed")));
    }

    #[test]
    fn install_cart_lists_what_is_missing_one_command_each() {
        let mut m = model();
        assert!(m.install_cart().is_none());
        m.cart.extend(["formula:git".to_string(), "formula:jq".to_string()]);
        m.installed.formula.insert("jq".to_string());
        let req = m.install_cart().unwrap();
        assert_eq!(req.cmds, [v(&["install", "git"])]);
        assert!(req.fallback.starts_with("Install 1 packages?") && req.fallback.contains("git"));
        m.installed.formula.insert("git".to_string());
        assert!(m.install_cart().is_none());
    }

    #[test]
    fn export_uses_the_cart_or_else_the_selection() {
        let mut m = model();
        assert!(m.export_items().is_empty());
        m.category = KITS.to_string();
        m.profile_label = "Dev".to_string();
        m.refresh();
        m.selected = Some("kit:Git Pro".to_string());
        assert_eq!(m.export_items().len(), 6);
        m.cart.insert("cask:obs".to_string());
        let lines = catalog::brewfile_lines(m.export_items().iter());
        assert_eq!(lines, ["cask \"obs\""]);
    }

    #[test]
    fn commands_text_and_urls() {
        let mut m = model();
        assert_eq!(m.command_text(&Obj::Item(key("cask:obs"))), "brew install --cask obs");
        let kit = catalog().find_kit("git pro").unwrap().clone();
        m.installed.formula.insert("git".to_string());
        let text = m.kit_commands_text(&kit);
        assert!(!text.contains("brew install git\n") && text.lines().count() == 5);
        assert_eq!(page_url(&key("formula:jq")), "https://formulae.brew.sh/formula/jq");
        assert_eq!(page_url(&key("cask:obs")), "https://formulae.brew.sh/cask/obs");
        assert_eq!(page_url(&key("formula:k8scli")), "https://github.com/1985epma/k8scli");
        let tap_only = Item { tap: "a/b".into(), homepage: String::new(), ..key("formula:jq") };
        assert_eq!(page_url(&tap_only), "https://github.com/a/homebrew-b");
    }

    // ───────────────────────── brew search results ─────────────────────────
    #[test]
    fn search_results_are_sanitised_sorted_and_capped() {
        let found = vec![
            (Kind::Formula, "zeta".to_string()),
            (Kind::Cask, "alpha".to_string()),
            (Kind::Formula, "--evil".to_string()),
            (Kind::Formula, "bad name".to_string()),
            (Kind::Formula, "user/repo/tool".to_string()),
        ];
        let items = extras_from_search(&found);
        let got: Vec<(String, String, String)> =
            items.iter().map(|i| (i.name.clone(), i.tap.clone(), i.kind.as_str().to_string())).collect();
        assert_eq!(
            got,
            [
                ("alpha".to_string(), String::new(), "cask".to_string()),
                ("tool".to_string(), "user/repo".to_string(), "formula".to_string()),
                ("zeta".to_string(), String::new(), "formula".to_string()),
            ]
        );
        assert!(items.iter().all(|i| i.category == EXTRA_CAT && i.desc == "Not in the curated catalog"));
        let many: Vec<(Kind, String)> = (0..100).map(|n| (Kind::Formula, format!("pkg{n:03}"))).collect();
        assert_eq!(extras_from_search(&many).len(), 60);
    }

    #[test]
    fn stale_search_results_are_dropped_and_extras_show_in_the_cart() {
        let mut m = model();
        m.search = "foo".to_string();
        assert!(!m.set_extra("fo", &[(Kind::Formula, "fooz".to_string())]));
        assert!(m.extra.is_empty());
        assert!(m.set_extra("foo", &[(Kind::Formula, "foozz".to_string())]));
        assert_eq!(m.extra.len(), 1);
        m.category = SEARCH.to_string();
        m.refresh();
        assert_eq!(names(&m), ["foozz"]);
        let item = m.extra[0].clone();
        m.toggle_cart(&Obj::Item(item.clone()));
        m.search = String::new();
        m.extra.clear();
        m.category = CART.to_string();
        m.refresh();
        assert_eq!(names(&m), ["foozz"]); // still resolvable although it is not in the catalog
        assert_eq!(m.lookup("formula:foozz"), Some(item));
    }

    #[test]
    fn extras_need_a_description_once() {
        let mut m = model();
        m.search = "foo".to_string();
        m.set_extra("foo", &[(Kind::Formula, "foozz".to_string())]);
        let item = m.extra[0].clone();
        assert!(m.needs_desc(&item));
        assert!(m.description(&item).contains("Loading description"));
        m.extra_desc.insert(item.key(), String::new());
        assert!(!m.needs_desc(&item));
        m.extra_desc.insert(item.key(), "A fine tool".to_string());
        assert_eq!(m.description(&item), "A fine tool");
        assert!(!m.needs_desc(&key("formula:jq")));
    }

    #[test]
    fn items_for_finds_the_packages_behind_retry_commands() {
        let m = model();
        let items = m.items_for(&[v(&["install", "jq", "hashicorp/tap/terraform"]), v(&["install", "--cask", "obs", "jq"])]);
        let keys: Vec<String> = items.iter().map(Item::key).collect();
        assert_eq!(keys, ["formula:jq", "formula:terraform", "cask:obs"]);
    }

    // ───────────────────────── BatchResult ─────────────────────────
    #[test]
    fn batch_result_marks_only_the_failed_packages() {
        let mut r = BatchResult::default();
        r.record(&v(&["install", "a", "b", "c"]), 1); // the batch failed ...
        r.record(&v(&["install", "a"]), 0); // ... then package by package
        r.record(&v(&["install", "b"]), 1);
        r.record(&v(&["install", "c"]), 0);
        assert_eq!((r.failed_installs(), r.succeeded()), (v(&["b"]), v(&["a", "c"])));
        assert_eq!(r.retry_commands(), [v(&["install", "b"])]);
    }

    #[test]
    fn batch_result_single_package_failure_and_cask_flags() {
        let mut r = BatchResult::default();
        r.record(&v(&["install", "--cask", "app"]), 1);
        r.record(&v(&["install", "tool"]), 1);
        r.record(&v(&["install", "--cask", "app2"]), 1);
        r.record(&v(&["update"]), 1);
        assert_eq!(r.failed_installs(), ["app", "tool", "app2"]);
        assert_eq!(r.retry_commands(), [v(&["install", "--cask", "app", "app2"]), v(&["install", "tool"])]);
        assert_eq!(r.failed_other(), ["brew update"]);
    }

    #[test]
    fn a_package_that_worked_later_is_not_blamed() {
        let mut r = BatchResult::default();
        r.record(&v(&["install", "a"]), 1);
        r.record(&v(&["install", "a"]), 0);
        assert!(r.failed_installs().is_empty());
    }

    #[test]
    fn summaries_say_how_it_went() {
        let ok = {
            let mut r = BatchResult::default();
            r.record(&v(&["install", "a", "b"]), 0);
            r.record(&v(&["install", "--cask", "c"]), 0);
            r
        };
        let s = batch_summary(&ok, false);
        assert_eq!(s.line, "✓ 3 packages installed successfully.");
        assert_eq!(s.log, "\n✓ 3 packages installed successfully.\n");
        assert!(s.failed_cmds.is_empty());
        assert_eq!(batch_summary(&BatchResult::default(), false).line, "✓ Done.");
        let mut one = BatchResult::default();
        one.record(&v(&["install", "x"]), 0);
        assert_eq!(batch_summary(&one, false).line, "✓ 1 package installed successfully.");

        let mut bad = BatchResult::default();
        bad.record(&v(&["install", "good", "bad"]), 1);
        bad.record(&v(&["install", "good"]), 0);
        bad.record(&v(&["install", "bad"]), 1);
        let s = batch_summary(&bad, false);
        assert!(s.line.contains("1 package failed: bad") && s.line.contains("1 installed") && s.line.contains("Retry failed"));
        assert_eq!(s.failed_cmds, [v(&["install", "bad"])]);

        let mut update = BatchResult::default();
        update.record(&v(&["update"]), 1);
        let s = batch_summary(&update, false);
        assert!(s.line.contains("1 command failed: brew update") && s.line.ends_with("Use Copy log to report it."));
        assert!(s.failed_cmds.is_empty());
    }

    #[test]
    fn a_cancelled_run_is_not_a_failure_to_retry() {
        let mut r = BatchResult::default();
        r.record(&v(&["install", "x"]), 1);
        let s = batch_summary(&r, true);
        assert_eq!(s.line, "Stopped.");
        assert!(s.failed_cmds.is_empty() && s.log.contains("Stopped before finishing"));
    }

    // ───────────────────────── closing and small files ─────────────────────────
    #[test]
    fn closing_asks_only_while_something_runs() {
        assert_eq!(close_action(false), CloseAction::Quit);
        assert_eq!(close_action(true), CloseAction::Ask);
    }

    #[test]
    fn welcome_appears_once_and_writes_the_flag_first() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        assert!(!welcome_flag(&cfg).exists());
        assert!(claim_welcome(&cfg, false));
        assert!(welcome_flag(&cfg).exists()); // written before it is shown: closing it any way still counts
        assert!(!claim_welcome(&cfg, false)); // second launch: nothing
    }

    #[test]
    fn the_env_var_suppresses_the_welcome_and_writes_nothing() {
        let dir = tempfile::tempdir().unwrap();
        assert!(!claim_welcome(dir.path(), true));
        assert!(!welcome_flag(dir.path()).exists());
    }

    #[test]
    fn rosetta_is_only_asked_once_on_apple_silicon_without_it() {
        let dir = tempfile::tempdir().unwrap();
        assert!(rosetta_wanted(dir.path(), true, false));
        assert!(!rosetta_wanted(dir.path(), false, false));
        assert!(!rosetta_wanted(dir.path(), true, true));
        fs::write(rosetta_flag(dir.path()), "").unwrap();
        assert!(!rosetta_wanted(dir.path(), true, false));
    }

    #[test]
    fn askpass_is_private_and_asks_natively() {
        let dir = tempfile::tempdir().unwrap();
        let path = ensure_askpass(&dir.path().join("cfg")).unwrap();
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o700);
        let text = fs::read_to_string(&path).unwrap();
        assert!(text.starts_with("#!/bin/bash\n") && text.contains("BREWCAT_PKG"));
        assert!(askpass_body(true).contains("osascript") && askpass_body(true).contains("hidden answer"));
        assert!(askpass_body(false).contains("zenity") && askpass_body(false).contains("kdialog"));
        let check = std::process::Command::new("bash").arg("-n").arg(&path).status().unwrap();
        assert!(check.success());
        assert!(ensure_askpass(&dir.path().join("cfg")).is_some()); // rewriting an existing helper works
    }
}
