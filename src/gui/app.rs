//! The window: the app state, what happens when a worker reports back, the install flows and the drawing of
//! everything but the Skills and MCP tabs (those are in `tabs.rs`).

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver};
use std::time::{Duration, Instant};

use eframe::egui::{self, Align, Color32, Layout, RichText, Sense, TextStyle};
use egui_extras::{Column, TableBuilder};

use crate::brewenv;
use crate::brewrunner::{BrewRunner, Tag};
use crate::catalog::Item;
use crate::gui::dialogs::{self, Answer, Dialog, Then};
use crate::gui::extras::{McpState, SkillsState};
use crate::gui::state::{
    ALL, CloseAction, InstallOutcome, InstallRequest, KITS, Model, Obj, PROFILES, Row, batch_summary, brew_line, claim_welcome,
    close_action, page_url, rosetta_flag, rosetta_present, rosetta_wanted, system,
};
use crate::gui::worker::{self, Msg, Notifier};
use crate::help_text::{self, VERSION};
use crate::{catalog, doctor, launcher, logo, sys};

/// Computes the plan text for an install (the real one asks brew; tests swap it).
pub type PlanFn = Arc<dyn Fn(&str, &[Item]) -> String + Send + Sync>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tab {
    Packages,
    Skills,
    Mcp,
}

/// How the app starts: everything that touches the machine is a parameter, so tests stay in a temporary folder.
pub struct Options {
    pub brew: Option<String>,
    pub home: PathBuf,
    pub cfg_dir: PathBuf,
    /// `BREWCAT_NO_WELCOME`.
    pub no_welcome: bool,
    /// Wait this long, then show the welcome and the Rosetta question. None: never (tests drive it by hand).
    pub startup_delay: Option<Duration>,
    /// Read `brew list` right away.
    pub refresh_on_start: bool,
    /// Make sure the app shows up in Launchpad (macOS, Homebrew installs only).
    pub ensure_bundle: bool,
}

impl Options {
    pub fn from_env() -> Options {
        Options {
            brew: brewenv::find_brew(),
            home: sys::home_dir(),
            cfg_dir: sys::config_dir(),
            no_welcome: std::env::var_os("BREWCAT_NO_WELCOME").is_some_and(|v| !v.is_empty()),
            startup_delay: Some(Duration::from_millis(1500)),
            refresh_on_start: true,
            ensure_bundle: true,
        }
    }
}

fn default_plan_fn() -> PlanFn {
    Arc::new(|brew, items| {
        let refs: Vec<&Item> = items.iter().collect();
        crate::plan::format_plan(&crate::plan::build_plan(brew, &refs, Duration::from_secs(60)))
    })
}

pub struct BrewcatApp {
    pub ctx: egui::Context,
    pub tx: mpsc::Sender<Msg>,
    pub rx: Receiver<Msg>,
    pub home: PathBuf,
    pub cfg_dir: PathBuf,
    pub brew: Option<String>,
    pub model: Model,
    pub busy: bool,
    /// True while the install plan is being computed.
    pub planning: bool,
    pub runner: Arc<BrewRunner>,
    /// The install commands for the packages that failed in the last batch (what Retry failed runs).
    pub failed_cmds: Vec<Vec<String>>,
    pub status: String,
    pub log_lines: Vec<(Tag, String)>,
    pub log_text: String,
    pub dialogs: VecDeque<Dialog>,
    pub tab: Tab,
    pub show_help: bool,
    pub show_about: bool,
    pub about_os: String,
    pub about_brew: String,
    pub skills: SkillsState,
    pub mcp: McpState,
    pub search_deadline: Option<Instant>,
    pub startup_at: Option<Instant>,
    pub plan_fn: PlanFn,
    pub no_welcome: bool,
    pub quit_confirmed: bool,
    /// The last text put on the clipboard (so tests can see it).
    pub last_copied: Option<String>,
    pub logo_tex: Option<egui::TextureHandle>,
    pub opened_urls: Vec<String>,
}

impl BrewcatApp {
    pub fn new(ctx: egui::Context, opts: Options) -> BrewcatApp {
        let (tx, rx) = mpsc::channel();
        if opts.ensure_bundle {
            launcher::ensure_app_bundle();
        }
        let size = 72;
        let image = egui::ColorImage::from_rgba_unmultiplied([size, size], &logo::rasterize(size, 3));
        let logo_tex = Some(ctx.load_texture("brewcat-logo", image, egui::TextureOptions::LINEAR));
        let mut app = BrewcatApp {
            ctx,
            tx,
            rx,
            home: opts.home,
            cfg_dir: opts.cfg_dir,
            brew: opts.brew,
            model: Model::new(system()),
            busy: false,
            planning: false,
            runner: Arc::new(BrewRunner::default()),
            failed_cmds: Vec::new(),
            status: String::new(),
            log_lines: Vec::new(),
            log_text: String::new(),
            dialogs: VecDeque::new(),
            tab: Tab::Packages,
            show_help: false,
            show_about: false,
            about_os: "checking…".to_string(),
            about_brew: "checking…".to_string(),
            skills: SkillsState::new(),
            mcp: McpState::new(),
            search_deadline: None,
            startup_at: opts.startup_delay.map(|d| Instant::now() + d),
            plan_fn: default_plan_fn(),
            no_welcome: opts.no_welcome,
            quit_confirmed: false,
            last_copied: None,
            logo_tex,
            opened_urls: Vec::new(),
        };
        app.mcp.refresh_marks(&app.home.clone());
        if opts.refresh_on_start {
            app.refresh_installed();
        }
        app
    }

    pub fn notifier(&self) -> Notifier {
        Notifier::new(self.tx.clone(), self.ctx.clone())
    }

    // ───────────────────────── log, status, clipboard ─────────────────────────
    pub fn log(&mut self, tag: Tag, text: &str) {
        self.log_text.push_str(text);
        for line in text.split_inclusive('\n') {
            self.log_lines.push((tag, line.trim_end_matches('\n').to_string()));
        }
    }

    pub fn set_status(&mut self, text: impl Into<String>) {
        self.status = text.into();
    }

    pub fn copy(&mut self, text: String) {
        self.ctx.copy_text(text.clone());
        self.last_copied = Some(text);
    }

    pub fn copy_log(&mut self) {
        let text = self.log_text.clone();
        self.copy(text);
        self.set_status("Log copied to clipboard.");
    }

    pub fn open_url(&mut self, url: String) {
        self.ctx.open_url(egui::OpenUrl::new_tab(url.clone()));
        self.opened_urls.push(url);
    }

    pub fn push_dialog(&mut self, dialog: Dialog) {
        self.dialogs.push_back(dialog);
        self.ctx.request_repaint();
    }

    pub fn info(&mut self, title: &str, text: &str) {
        self.push_dialog(Dialog::Info { title: title.to_string(), text: text.to_string() });
    }

    pub fn error(&mut self, title: &str, text: &str) {
        self.push_dialog(Dialog::Error { title: title.to_string(), text: text.to_string() });
    }

    // ───────────────────────── messages from workers ─────────────────────────
    /// Handle every message the workers have sent so far. Returns how many there were.
    pub fn drain(&mut self) -> usize {
        let mut n = 0;
        while let Ok(msg) = self.rx.try_recv() {
            n += 1;
            self.handle(msg);
        }
        n
    }

    pub fn handle(&mut self, msg: Msg) {
        match msg {
            Msg::Log(tag, text) => self.log(tag, &text),
            Msg::Installed(installed) => self.model.set_installed(installed),
            Msg::PlanReady { title, text, cmds, fallback } => {
                self.planning = false;
                self.set_status("");
                self.ask_and_run(&title, text, cmds, &fallback);
            }
            Msg::Search { query, found } => {
                self.model.set_extra(&query, &found);
            }
            Msg::Desc { key, text } => {
                self.model.extra_desc.insert(key, text);
            }
            Msg::AboutInfo { os, brew } => {
                self.about_os = os;
                self.about_brew = brew;
            }
            Msg::Diagnostics(report) => {
                self.copy(report);
                self.info("Diagnostics", "Copied. Paste it in your issue.");
            }
            Msg::BatchDone { result, cancelled } => {
                let summary = batch_summary(&result, cancelled);
                self.failed_cmds = summary.failed_cmds;
                self.log(Tag::Info, &summary.log);
                self.set_status(summary.line);
                self.finish();
            }
            Msg::Scan(result) => {
                self.skills.scanning = false;
                match result {
                    Ok(ok) => {
                        let n = self.skills.apply_scan(ok, &self.home.clone());
                        self.log(Tag::Info, &format!("Found {n} skill(s).\n"));
                    }
                    Err(e) => self.log(Tag::Err, &format!("Scan failed: {e}\n")),
                }
            }
            Msg::RosettaDone => self.finish(),
        }
    }

    /// A batch (or Rosetta install) ended: the window is free again and the installed list is read again.
    fn finish(&mut self) {
        self.busy = false;
        self.refresh_installed();
    }

    // ───────────────────────── what is installed, search, descriptions ─────────────────────────
    pub fn refresh_installed(&mut self) {
        let Some(brew) = self.brew.clone() else {
            self.model.refresh();
            return;
        };
        let n = self.notifier();
        std::thread::spawn(move || n.send(Msg::Installed(worker::read_installed(&brew))));
    }

    /// The profile or platform changed: refill the category list (keeping the category when it still exists).
    pub fn on_profile(&mut self) {
        if !self.model.category_entries().contains(&self.model.category) {
            self.model.category = ALL.to_string();
        }
        self.model.refresh();
    }

    pub fn on_category(&mut self, category: String) {
        self.model.category = category;
        self.model.refresh();
    }

    /// The search box changed: filter now, and ask all of Homebrew a moment later.
    pub fn on_search_changed(&mut self) {
        self.model.refresh();
        let q = self.model.search.trim().to_string();
        if q.chars().count() < 2 || self.brew.is_none() {
            self.model.extra.clear();
            self.search_deadline = None;
            return;
        }
        self.search_deadline = Some(Instant::now() + Duration::from_millis(400));
        self.ctx.request_repaint_after(Duration::from_millis(420));
    }

    fn start_remote_search(&mut self) {
        let (Some(brew), q) = (self.brew.clone(), self.model.search.trim().to_string()) else { return };
        let n = self.notifier();
        std::thread::spawn(move || {
            let found = worker::remote_search(&brew, &q);
            n.send(Msg::Search { query: q, found });
        });
    }

    /// Fetch the description of the selected package when it comes from `brew search` and is not known yet.
    pub fn ensure_desc(&mut self) {
        let Some(Obj::Item(item)) = self.model.selected_obj().cloned() else { return };
        if !self.model.needs_desc(&item) {
            return;
        }
        self.model.extra_desc.insert(item.key(), String::new()); // asked once
        let Some(brew) = self.brew.clone() else { return };
        let n = self.notifier();
        std::thread::spawn(move || n.send(Msg::Desc { key: item.key(), text: worker::fetch_desc(&brew, &item) }));
    }

    // ───────────────────────── installing ─────────────────────────
    pub fn install_selected(&mut self) {
        let Some(obj) = self.model.selected_obj().cloned() else { return };
        match self.model.install_selected(&obj) {
            InstallOutcome::Confirm(req) => self.confirm_install(req),
            InstallOutcome::Nothing(msg) => self.log(Tag::Info, msg),
        }
    }

    pub fn install_cart(&mut self) {
        match self.model.install_cart() {
            Some(req) => self.confirm_install(req),
            None => self.info("My list", "Nothing to install in the list."),
        }
    }

    /// Run again only the packages that failed, through the usual confirmation.
    pub fn retry_failed(&mut self) {
        if self.busy || self.planning || self.failed_cmds.is_empty() {
            return;
        }
        let cmds = self.failed_cmds.clone();
        let lines: Vec<String> = cmds.iter().map(|c| brew_line(c)).collect();
        let req = InstallRequest {
            title: "Retry failed installs".to_string(),
            items: self.model.items_for(&cmds),
            cmds,
            fallback: format!("Run the following?\n\n{}", lines.join("\n")),
        };
        self.confirm_install(req);
    }

    pub fn uninstall_selected(&mut self) {
        if let Some(Obj::Item(item)) = self.model.selected_obj().cloned() {
            let mut cmd = vec!["uninstall".to_string()];
            if item.kind == crate::catalog::Kind::Cask {
                cmd.push("--cask".to_string());
            }
            cmd.push(item.name.clone());
            self.push_dialog(Dialog::Confirm {
                title: "Uninstall".to_string(),
                text: format!("Uninstall {}?", item.name),
                then: Then::RunBrew(vec![cmd]),
            });
        }
    }

    /// Always ask before installing. The plan (what will change) is computed off the window's thread so it stays
    /// responsive; if it cannot be computed the plain question is used instead, so a plan problem never blocks an
    /// install.
    pub fn confirm_install(&mut self, req: InstallRequest) {
        if self.planning {
            return;
        }
        let InstallRequest { title, items, cmds, fallback } = req;
        let Some(brew) = self.brew.clone().filter(|_| !items.is_empty()) else {
            self.ask_and_run(&title, None, cmds, &fallback);
            return;
        };
        self.planning = true;
        self.set_status("Checking what will change…");
        let (n, plan_fn) = (self.notifier(), self.plan_fn.clone());
        std::thread::spawn(move || {
            let text = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| plan_fn(&brew, &items))).ok();
            n.send(Msg::PlanReady { title, text, cmds, fallback });
        });
    }

    fn ask_and_run(&mut self, title: &str, plan_text: Option<String>, cmds: Vec<Vec<String>>, fallback: &str) {
        match plan_text {
            Some(text) => {
                let lines: Vec<String> = cmds.iter().map(|c| brew_line(c)).collect();
                self.push_dialog(Dialog::Plan {
                    title: title.to_string(),
                    text: format!("{text}\n\nWill run:\n{}", lines.join("\n")),
                    cmds,
                });
            }
            None => self.push_dialog(Dialog::Confirm { title: title.to_string(), text: fallback.to_string(), then: Then::RunBrew(cmds) }),
        }
    }

    /// Run brew commands one after the other in a worker thread. Package failures are retried one by one.
    pub fn run_brew(&mut self, cmds: Vec<Vec<String>>) {
        let Some(brew) = self.brew.clone() else {
            self.error("Homebrew", "brew not found. Install it from https://brew.sh");
            return;
        };
        if self.busy {
            return;
        }
        self.busy = true;
        self.failed_cmds.clear();
        self.set_status("Running brew…");
        self.runner.reset();
        let (runner, cfg, n) = (self.runner.clone(), self.cfg_dir.clone(), self.notifier());
        std::thread::spawn(move || {
            let (result, cancelled) = worker::run_batch(&runner, &brew, &cfg, &cmds, &n);
            n.send(Msg::BatchDone { result, cancelled });
        });
    }

    // ───────────────────────── dialogs ─────────────────────────
    /// Answer the dialog at the front of the queue.
    pub fn answer_front(&mut self, answer: Answer) {
        let Some(dialog) = self.dialogs.pop_front() else { return };
        self.answered(dialog, answer);
    }

    pub fn answered(&mut self, dialog: Dialog, answer: Answer) {
        let yes = answer == Answer::Yes;
        match dialog {
            Dialog::Welcome { .. } => {
                if let Answer::Start(Some(label)) = answer {
                    self.show_starter_kits(&label);
                }
            }
            Dialog::Plan { cmds, .. } => {
                if yes {
                    self.run_brew(cmds);
                }
            }
            Dialog::Confirm { then, .. } => self.confirmed(then, yes),
            Dialog::Info { .. } | Dialog::Error { .. } => {}
        }
    }

    fn confirmed(&mut self, then: Then, yes: bool) {
        match then {
            Then::RunBrew(cmds) if yes => self.run_brew(cmds),
            Then::Quit if yes => {
                self.quit_confirmed = true;
                self.ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
            Then::InstallRosetta => {
                if yes {
                    self.install_rosetta();
                } else {
                    let _ =
                        std::fs::create_dir_all(&self.cfg_dir).and_then(|()| std::fs::File::create(rosetta_flag(&self.cfg_dir)).map(drop));
                    self.log(Tag::Info, "Rosetta 2 skipped. Install later with: softwareupdate --install-rosetta --agree-to-license\n");
                }
            }
            Then::Skills(plan) if yes => {
                let (jobs, log) = self.skills.build_jobs(&plan, &self.home);
                for (tag, line) in log {
                    self.log(tag, &line);
                }
                self.skills.jobs = jobs.into();
                self.pump_skill_jobs();
            }
            Then::Replace(_) => {
                if yes {
                    if let Some(job) = self.skills.jobs.front_mut() {
                        job.replace_ok = true;
                    }
                } else {
                    self.skills.jobs.pop_front();
                }
                self.pump_skill_jobs();
            }
            Then::Mcp(plan) if yes => {
                for (tag, line) in plan.execute(&self.home) {
                    self.log(tag, &line);
                }
                self.mcp.refresh_marks(&self.home.clone());
            }
            _ => {}
        }
    }

    /// Install skills until one needs an answer (its folder exists), then wait for it.
    pub fn pump_skill_jobs(&mut self) {
        use crate::gui::extras::JobStep;
        loop {
            match self.skills.next_step() {
                JobStep::Done => break,
                JobStep::AskReplace(dest) => {
                    let text = format!("{}\nalready exists. Replace it?", dest.display());
                    self.push_dialog(Dialog::Confirm { title: "Overwrite".to_string(), text, then: Then::Replace(dest) });
                    break;
                }
                JobStep::Install(_) => {
                    if let Some((tag, line)) = self.skills.install_front() {
                        self.log(tag, &line);
                    }
                }
            }
        }
        self.skills.refresh_marks(&self.home.clone());
    }

    // ───────────────────────── first run ─────────────────────────
    /// One dialog at a time: the welcome (first launch only), then the Rosetta question.
    pub fn startup_dialogs(&mut self) {
        self.maybe_welcome();
        self.check_rosetta(brewenv::apple_silicon(), rosetta_present());
    }

    /// Show the welcome on the very first launch only. It never installs anything. Returns true if shown.
    pub fn maybe_welcome(&mut self) -> bool {
        let show = claim_welcome(&self.cfg_dir, self.no_welcome);
        if show {
            self.push_dialog(Dialog::Welcome { selected: PROFILES.iter().position(|(l, _)| *l == "Dev").unwrap_or(0) });
        }
        show
    }

    /// Set the profile, switch to the Kits view and select the first kit. Does not install anything.
    pub fn show_starter_kits(&mut self, profile_label: &str) {
        self.model.show_starter_kits(profile_label);
        self.tab = Tab::Packages;
    }

    /// Many casks are Intel-only; without Rosetta 2 macOS shows an install prompt/error.
    pub fn check_rosetta(&mut self, silicon: bool, present: bool) {
        if rosetta_wanted(&self.cfg_dir, silicon, present) {
            self.push_dialog(Dialog::Confirm {
                title: "Install Rosetta 2?".to_string(),
                text: "Rosetta 2 is not installed on this Apple Silicon Mac.\n\nMany apps (especially casks) are Intel-only and need it, otherwise macOS shows an error asking to install it.\n\nInstall Rosetta 2 now? macOS will ask for your administrator password.".to_string(),
                then: Then::InstallRosetta,
            });
        }
    }

    pub fn install_rosetta(&mut self) {
        self.log(Tag::Cmd, "\n$ softwareupdate --install-rosetta --agree-to-license  (administrator)\n");
        self.busy = true;
        let n = self.notifier();
        std::thread::spawn(move || worker::install_rosetta(&n));
    }

    // ───────────────────────── help, about, diagnostics ─────────────────────────
    pub fn open_about(&mut self) {
        self.show_about = true;
        self.about_os = "checking…".to_string();
        self.about_brew = "checking…".to_string();
        let (brew, n) = (self.brew.clone(), self.notifier());
        std::thread::spawn(move || n.send(Msg::AboutInfo { os: sys::os_description(), brew: worker::brew_version(brew.as_deref()) }));
    }

    pub fn copy_diagnostics(&mut self) {
        let n = self.notifier();
        std::thread::spawn(move || n.send(Msg::Diagnostics(doctor::diagnostic_report())));
    }

    // ───────────────────────── frame ─────────────────────────
    /// Called before each frame: handle what workers sent, the timers and a request to close the window.
    pub fn tick(&mut self, ctx: &egui::Context) {
        self.drain();
        let now = Instant::now();
        if let Some(at) = self.startup_at {
            if now >= at {
                self.startup_at = None;
                self.startup_dialogs();
            } else {
                ctx.request_repaint_after(at - now);
            }
        }
        if let Some(at) = self.search_deadline {
            if now >= at {
                self.search_deadline = None;
                self.start_remote_search();
            } else {
                ctx.request_repaint_after(at - now);
            }
        }
        if self.on_close_requested(ctx.input(|i| i.viewport().close_requested())) {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
        }
    }

    /// The user asked to close the window. Returns true when the close must be cancelled because an installation is
    /// still running: the question "Quit and stop it?" is asked instead.
    pub fn on_close_requested(&mut self, requested: bool) -> bool {
        if !requested || self.quit_confirmed || close_action(self.busy) != CloseAction::Ask {
            return false;
        }
        let asked = self.dialogs.iter().any(|d| matches!(d, Dialog::Confirm { then: Then::Quit, .. }));
        if !asked {
            self.push_dialog(Dialog::Confirm {
                title: "Quit brewcat".to_string(),
                text: "An installation is still running. Quit and stop it?".to_string(),
                then: Then::Quit,
            });
        }
        true
    }

    /// The window is closing: stop the brew child and delete the temporary skill clone.
    pub fn shutdown(&mut self) {
        self.runner.terminate();
        self.skills.cleanup_tmp();
    }

    // ───────────────────────── drawing ─────────────────────────
    pub fn draw(&mut self, ui: &mut egui::Ui) {
        let ctx = ui.ctx().clone();
        if ctx.input(|i| i.key_pressed(egui::Key::F1)) {
            self.show_help = true;
        }
        egui::Panel::top("topbar").show(ui, |ui| self.top_bar(ui));
        egui::Panel::bottom("logpanel").resizable(true).default_size(150.0).min_size(100.0).show(ui, |ui| self.log_panel(ui));
        egui::CentralPanel::default().show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.selectable_value(&mut self.tab, Tab::Packages, "📦 Packages");
                ui.selectable_value(&mut self.tab, Tab::Skills, "🧠 Skills");
                ui.selectable_value(&mut self.tab, Tab::Mcp, "🔌 MCP");
            });
            ui.separator();
            match self.tab {
                Tab::Packages => self.packages_tab(ui),
                Tab::Skills => self.skills_tab(ui),
                Tab::Mcp => self.mcp_tab(ui),
            }
        });
        self.windows(&ctx);
        if let Some(dialog) = self.dialogs.front_mut()
            && let Some(answer) = dialogs::show(&ctx, dialog)
        {
            self.answer_front(answer);
        }
    }

    fn top_bar(&mut self, ui: &mut egui::Ui) {
        ui.add_space(4.0);
        ui.horizontal(|ui| {
            if let Some(tex) = &self.logo_tex {
                ui.image((tex.id(), egui::Vec2::splat(36.0)));
            }
            ui.label(RichText::new("brewcat").size(22.0).strong());
            let os = if sys::is_mac() { "macOS" } else { "Linux" };
            ui.label(RichText::new(format!("  {os} • {}", if self.brew.is_some() { "brew found" } else { "brew NOT found" })).weak());
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if ui.button("About").clicked() {
                    self.open_about();
                }
                if ui.button("Help").clicked() {
                    self.show_help = true;
                }
                if ui.button("Refresh status").clicked() {
                    self.refresh_installed();
                }
                if ui.button("brew update").clicked() {
                    self.run_brew(vec![vec!["update".to_string()]]);
                }
            });
        });
        ui.add_space(4.0);
    }

    fn log_panel(&mut self, ui: &mut egui::Ui) {
        ui.add_space(4.0);
        if self.busy || self.planning {
            ui.add(egui::ProgressBar::new(0.0).animate(true).desired_height(8.0));
        }
        ui.horizontal(|ui| {
            ui.label(&self.status);
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                if ui.button("Copy log").clicked() {
                    self.copy_log();
                }
                let can_retry = !self.failed_cmds.is_empty() && self.brew.is_some() && !self.busy && !self.planning;
                if ui.add_enabled(can_retry, egui::Button::new("Retry failed")).clicked() {
                    self.retry_failed();
                }
            });
        });
        egui::Frame::new().fill(Color32::from_rgb(0x1e, 0x1e, 0x1e)).inner_margin(6.0).show(ui, |ui| {
            let row_h = ui.text_style_height(&TextStyle::Monospace);
            egui::ScrollArea::both().id_salt("log").stick_to_bottom(true).auto_shrink([false, false]).show_rows(
                ui,
                row_h,
                self.log_lines.len(),
                |ui, range| {
                    for (tag, line) in &self.log_lines[range] {
                        let color = match tag {
                            Tag::Out => Color32::from_rgb(0xd4, 0xd4, 0xd4),
                            Tag::Cmd => Color32::from_rgb(0x4f, 0xc3, 0xf7),
                            Tag::Info => Color32::from_rgb(0x81, 0xc7, 0x84),
                            Tag::Err => Color32::from_rgb(0xef, 0x53, 0x50),
                        };
                        ui.add(egui::Label::new(RichText::new(line).monospace().color(color)).extend());
                    }
                },
            );
        });
    }

    // ───────────────────────── Packages tab ─────────────────────────
    fn packages_tab(&mut self, ui: &mut egui::Ui) {
        let (mut profile_changed, mut search_changed) = (false, false);
        ui.horizontal(|ui| {
            ui.label("Profile:");
            egui::ComboBox::from_id_salt("profile").width(230.0).selected_text(self.model.profile_label.clone()).show_ui(ui, |ui| {
                for (label, _) in PROFILES {
                    profile_changed |= ui.selectable_value(&mut self.model.profile_label, label.to_string(), label).changed();
                }
            });
            ui.label("  Platform:");
            egui::ComboBox::from_id_salt("platform").width(70.0).selected_text(self.model.platform.clone()).show_ui(ui, |ui| {
                for p in [catalog::MAC, catalog::LINUX] {
                    profile_changed |= ui.selectable_value(&mut self.model.platform, p.to_string(), p).changed();
                }
            });
            ui.with_layout(Layout::right_to_left(Align::Center), |ui| {
                search_changed = ui.add(egui::TextEdit::singleline(&mut self.model.search).desired_width(260.0)).changed();
                ui.label("🔎 Search:");
            });
        });
        ui.add_space(4.0);
        if profile_changed {
            self.on_profile();
        }
        if search_changed {
            self.on_search_changed();
        }

        let mut picked_category: Option<String> = None;
        egui::Panel::left("categories").resizable(true).default_size(190.0).min_size(120.0).show(ui, |ui| {
            egui::ScrollArea::vertical().id_salt("categories").auto_shrink([false, false]).show(ui, |ui| {
                for c in self.model.category_entries() {
                    if ui.selectable_label(self.model.category == c, &c).clicked() {
                        picked_category = Some(c);
                    }
                }
            });
        });
        if let Some(c) = picked_category {
            self.on_category(c);
        }
        egui::Panel::right("details").resizable(true).default_size(300.0).min_size(240.0).show(ui, |ui| {
            egui::ScrollArea::vertical().id_salt("details").auto_shrink([false, false]).show(ui, |ui| self.details(ui));
        });
        self.table(ui);
        self.ensure_desc();
    }

    fn table(&mut self, ui: &mut egui::Ui) {
        let selected = self.model.selected.clone();
        let kind_header = if self.model.category == KITS { "Items" } else { "Type" };
        let green = if ui.visuals().dark_mode { Color32::from_rgb(0x66, 0xbb, 0x6a) } else { Color32::from_rgb(0x2e, 0x7d, 0x32) };
        let (mut clicked, mut double): (Option<String>, bool) = (None, false);
        let rows: &[Row] = &self.model.rows;
        TableBuilder::new(ui)
            .id_salt("packages")
            .striped(true)
            .resizable(true)
            .sense(Sense::click())
            .column(Column::exact(34.0))
            .column(Column::initial(170.0).at_least(80.0).clip(true))
            .column(Column::initial(66.0).at_least(40.0).clip(true))
            .column(Column::initial(150.0).at_least(60.0).clip(true))
            .column(Column::remainder().at_least(120.0).clip(true))
            .header(24.0, |mut header| {
                for title in ["", "Package", kind_header, "Category", "Description"] {
                    header.col(|ui| {
                        ui.strong(title);
                    });
                }
            })
            .body(|body| {
                body.rows(24.0, rows.len(), |mut row| {
                    let r = &rows[row.index()];
                    row.set_selected(selected.as_deref() == Some(r.obj.id().as_str()));
                    let text = |s: &str| if r.installed { RichText::new(s).color(green) } else { RichText::new(s) };
                    row.col(|ui| {
                        ui.label(text(&r.mark));
                    });
                    row.col(|ui| {
                        ui.add(egui::Label::new(text(&r.name)).truncate());
                    });
                    row.col(|ui| {
                        ui.add(egui::Label::new(text(&r.kind)).truncate());
                    });
                    row.col(|ui| {
                        ui.add(egui::Label::new(text(&r.category)).truncate());
                    });
                    row.col(|ui| {
                        ui.add(egui::Label::new(text(&r.desc)).truncate());
                    });
                    let response = row.response();
                    if response.clicked() {
                        clicked = Some(r.obj.id());
                    }
                    if response.double_clicked() {
                        double = true;
                    }
                });
            });
        if let Some(id) = clicked {
            self.model.selected = Some(id);
        }
        if double && let Some(obj) = self.model.selected_obj().cloned() {
            self.model.toggle_cart(&obj);
        }
    }

    fn details(&mut self, ui: &mut egui::Ui) {
        let row = self.model.selected_row().cloned();
        let Some(row) = row else {
            ui.label(RichText::new("Select a package").size(18.0).strong());
            for label in ["Install", "Uninstall", "Add to list", "Copy command", "Open page"] {
                ui.add_enabled(false, egui::Button::new(label).min_size(egui::vec2(ui.available_width(), 0.0)));
            }
            self.cart_box(ui);
            return;
        };
        let can = self.brew.is_some() && !self.busy && !self.planning;
        let width = ui.available_width();
        let full = |label: &str| egui::Button::new(label.to_string()).min_size(egui::vec2(width, 0.0));
        ui.add(egui::Label::new(RichText::new(&row.name).size(18.0).strong()).wrap());
        match &row.obj {
            Obj::Kit(kit) => {
                let items: Vec<Item> = kit.keys.iter().filter_map(|k| self.model.lookup(k)).collect();
                ui.label(RichText::new(format!("Kit • {} • {} packages", kit.profile, items.len())).weak());
                ui.add_space(6.0);
                let mut text = format!("{}\n", kit.desc);
                for i in &items {
                    text.push_str(&format!("\n{} {} ({})", if self.model.is_installed(i) { "✓" } else { "•" }, i.name, i.kind.as_str()));
                }
                ui.add(egui::Label::new(text).wrap());
            }
            Obj::Item(item) => {
                let installed = if self.model.is_installed(item) { " • installed" } else { "" };
                ui.label(
                    RichText::new(format!("{} • {} • {}{installed}", item.kind.as_str(), item.category, item.platforms.join("/"))).weak(),
                );
                ui.add_space(6.0);
                ui.add(egui::Label::new(self.model.description(item)).wrap());
                ui.add_space(6.0);
                let url = page_url(item);
                ui.add(egui::Hyperlink::from_label_and_url(format!("🔗 {url}"), url));
            }
        }
        if !row.reason.is_empty() {
            ui.add_space(6.0);
            ui.add(egui::Label::new(RichText::new(&row.reason).color(Color32::from_rgb(0x42, 0x8b, 0xe0))).wrap());
        }
        ui.add_space(6.0);
        let mut command = self.model.command_text(&row.obj);
        let mut command_view: &str = &command;
        ui.add(egui::TextEdit::multiline(&mut command_view).desired_rows(3).desired_width(f32::INFINITY).font(TextStyle::Monospace));
        command.clear();
        ui.add_space(6.0);
        let is_kit = matches!(row.obj, Obj::Kit(_));
        if ui.add_enabled(can, full(if is_kit { "Install kit" } else { "Install" })).clicked() {
            self.install_selected();
        }
        let installed_item = matches!(&row.obj, Obj::Item(i) if self.model.is_installed(i));
        if ui.add_enabled(can && installed_item, full("Uninstall")).clicked() {
            self.uninstall_selected();
        }
        let cart_label = match &row.obj {
            Obj::Kit(_) => "Add kit to list",
            Obj::Item(i) if self.model.cart.contains(&i.key()) => "Remove from list",
            Obj::Item(_) => "Add to list",
        };
        if ui.add(full(cart_label)).clicked() {
            self.model.toggle_cart(&row.obj);
        }
        if ui.add(full("Copy command")).clicked() {
            let text = self.model.command_text(&row.obj);
            self.copy(text);
            self.log(Tag::Info, "Command copied to clipboard.\n");
        }
        if ui.add_enabled(can && !is_kit, full("Open page")).clicked()
            && let Obj::Item(item) = &row.obj
        {
            self.open_url(page_url(item));
        }
        self.cart_box(ui);
    }

    fn cart_box(&mut self, ui: &mut egui::Ui) {
        ui.add_space(6.0);
        ui.separator();
        ui.label(format!("List: {} items", self.model.cart.len()));
        let width = ui.available_width();
        let full = |label: &str| egui::Button::new(label.to_string()).min_size(egui::vec2(width, 0.0));
        if ui.add(full("Install list")).clicked() {
            self.install_cart();
        }
        if ui.add(full("Export Brewfile…")).clicked() {
            self.export_brewfile();
        }
        if ui.add(full("Clear list")).clicked() {
            self.model.clear_cart();
        }
    }

    /// Write a Brewfile for My list, or else the selected package or kit.
    pub fn export_brewfile(&mut self) {
        let items = self.model.export_items();
        if items.is_empty() {
            self.info("Brewfile", "Add items to the list (double-click) or select a kit.");
            return;
        }
        let Some(path) = rfd::FileDialog::new().set_title("Save Brewfile").set_file_name("Brewfile").save_file() else { return };
        self.write_brewfile(&path, &items);
    }

    pub fn write_brewfile(&mut self, path: &std::path::Path, items: &[Item]) {
        let mut text = catalog::brewfile_lines(items.iter()).join("\n");
        text.push('\n');
        match std::fs::write(path, text) {
            Ok(()) => self.log(Tag::Info, &format!("Brewfile saved to {}  (use: brew bundle --file={})\n", path.display(), path.display())),
            Err(e) => self.error("Brewfile", &format!("Could not write {}: {e}", path.display())),
        }
    }

    // ───────────────────────── Help and About windows ─────────────────────────
    fn windows(&mut self, ctx: &egui::Context) {
        let mut help_open = self.show_help;
        if help_open {
            let mut copy = false;
            egui::Window::new("brewcat Help").open(&mut help_open).default_size([820.0, 640.0]).show(ctx, |ui| {
                ui.horizontal(|ui| {
                    if ui.button("Copy diagnostics").clicked() {
                        copy = true;
                    }
                    ui.label(RichText::new("Copies a redacted report to paste into a GitHub issue.").weak());
                });
                ui.separator();
                egui::ScrollArea::both().auto_shrink([false, false]).show(ui, |ui| {
                    ui.add(egui::Label::new(RichText::new(help_text::help()).monospace()).selectable(true));
                });
            });
            if copy {
                self.copy_diagnostics();
            }
        }
        self.show_help = help_open;

        let mut about_open = self.show_about;
        if about_open {
            egui::Window::new("About brewcat").open(&mut about_open).collapsible(false).resizable(false).show(ctx, |ui| {
                ui.horizontal(|ui| {
                    if let Some(tex) = &self.logo_tex {
                        ui.image((tex.id(), egui::Vec2::splat(96.0)));
                    }
                    ui.vertical(|ui| {
                        ui.label(RichText::new("brewcat").size(22.0).strong());
                        ui.label(format!("Version {VERSION}"));
                    });
                });
                ui.add_space(8.0);
                egui::Grid::new("about-grid").num_columns(2).spacing([10.0, 4.0]).show(ui, |ui| {
                    for (k, v) in [
                        ("OS", self.about_os.as_str()),
                        ("Homebrew", self.about_brew.as_str()),
                        ("License", "MIT"),
                        ("Source", "github.com/1985epma/homebrew-brewcat"),
                    ] {
                        ui.label(RichText::new(format!("{k}:")).weak());
                        ui.label(v);
                        ui.end_row();
                    }
                });
            });
        }
        self.show_about = about_open;
    }
}

impl eframe::App for BrewcatApp {
    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.tick(ctx);
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.draw(ui);
    }

    fn on_exit(&mut self) {
        self.shutdown();
    }
}
