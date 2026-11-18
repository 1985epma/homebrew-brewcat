//! The logic of the Skills and MCP tabs that needs no egui types: which tools and scope are chosen, what a skill
//! install or an MCP server install would do, the confirmation texts and the jobs to run.

use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use crate::brewrunner::Tag;
use crate::extras_core::{self as core, MCP_PRESETS, Scope, TARGETS, TRUSTED_SOURCES};
use crate::gui::worker::{FoundSkill, ScanOk};
use crate::sys;

/// Where to install: which tools, user or project scope, and the project folder.
#[derive(Debug, Clone)]
pub struct TargetBar {
    pub on: [bool; 3],
    pub scope: Scope,
    pub project: Option<PathBuf>,
}

impl Default for TargetBar {
    fn default() -> Self {
        TargetBar { on: [true, false, false], scope: Scope::User, project: None }
    }
}

/// Why the choice on a [`TargetBar`] cannot be used yet.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BarIssue {
    NoTarget,
    NeedsProject,
}

impl TargetBar {
    /// The chosen tools (`claude`, `kiro`, `vscode`).
    pub fn targets(&self) -> Vec<&'static str> {
        TARGETS.iter().zip(self.on).filter(|(_, on)| *on).map(|((id, _), _)| *id).collect()
    }

    /// The name of the project folder, or what to show when there is none.
    pub fn project_label(&self) -> String {
        self.project
            .as_ref()
            .and_then(|p| p.file_name())
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| "(no folder)".to_string())
    }

    pub fn set_project(&mut self, folder: PathBuf) {
        self.project = Some(folder);
        self.scope = Scope::Project;
    }

    /// True when the scope is Project but no folder was picked yet (the window asks for one).
    pub fn needs_project(&self) -> bool {
        self.scope == Scope::Project && self.project.is_none()
    }

    /// The choice, ready to use.
    pub fn selection(&self) -> Result<(Vec<&'static str>, Scope, Option<&Path>), BarIssue> {
        let targets = self.targets();
        if targets.is_empty() {
            return Err(BarIssue::NoTarget);
        }
        if self.needs_project() {
            return Err(BarIssue::NeedsProject);
        }
        Ok((targets, self.scope, self.project.as_deref()))
    }
}

// ───────────────────────── skills ─────────────────────────

#[derive(Debug, Clone)]
pub struct SkillRow {
    pub folder: PathBuf,
    pub name: String,
    pub desc: String,
    pub checked: bool,
    /// "C K V" marks: where it is installed already for the chosen scope.
    pub marks: String,
}

/// One copy of a skill into one tool's folder.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SkillJob {
    pub folder: PathBuf,
    pub dest: PathBuf,
    /// The user agreed to replace what is at `dest`.
    pub replace_ok: bool,
}

/// What the user confirmed: which skills, into which tools.
#[derive(Debug, Clone)]
pub struct SkillPlan {
    pub folders: Vec<PathBuf>,
    pub targets: Vec<&'static str>,
    pub scope: Scope,
    pub project: Option<PathBuf>,
}

/// The next thing to do with the queue of skill jobs.
#[derive(Debug, PartialEq, Eq)]
pub enum JobStep {
    /// The destination exists: ask whether to replace it.
    AskReplace(PathBuf),
    Install(SkillJob),
    Done,
}

#[derive(Debug, Default)]
pub struct SkillsState {
    pub source: String,
    pub rows: Vec<SkillRow>,
    pub scanned_spec: String,
    pub scanned_commit: String,
    /// The temporary clone the listed skills live in.
    pub tmp: Option<PathBuf>,
    pub scanning: bool,
    pub bar: TargetBar,
    pub jobs: VecDeque<SkillJob>,
}

impl SkillsState {
    pub fn new() -> SkillsState {
        SkillsState { source: core::SKILL_PRESETS[0].to_string(), ..SkillsState::default() }
    }

    pub fn cleanup_tmp(&mut self) {
        if let Some(tmp) = self.tmp.take() {
            let _ = std::fs::remove_dir_all(tmp);
        }
    }

    /// Show the result of a scan (the previous temporary clone is deleted). Returns how many skills were found.
    pub fn apply_scan(&mut self, ok: ScanOk, home: &Path) -> usize {
        self.cleanup_tmp();
        self.scanned_spec = ok.spec;
        self.scanned_commit = ok.commit;
        self.tmp = ok.tmp;
        self.rows = ok
            .skills
            .into_iter()
            .map(|FoundSkill { folder, name, desc }| SkillRow { folder, name, desc, checked: false, marks: String::new() })
            .collect();
        self.refresh_marks(home);
        self.rows.len()
    }

    pub fn refresh_marks(&mut self, home: &Path) {
        let (scope, project) = (self.bar.scope, self.bar.project.clone());
        for row in &mut self.rows {
            let mut flags: HashMap<&str, bool> = HashMap::new();
            let folder_name = row.folder.file_name().map(|n| n.to_os_string()).unwrap_or_default();
            if !(scope == Scope::Project && project.is_none()) {
                for (id, _) in TARGETS {
                    if let Ok(root) = core::skill_root(home, id, scope, project.as_deref()) {
                        flags.insert(id, root.join(&folder_name).exists());
                    }
                }
            }
            row.marks = core::marks(&flags);
        }
    }

    pub fn select_all(&mut self, on: bool) {
        self.rows.iter_mut().for_each(|r| r.checked = on);
    }

    pub fn checked(&self) -> Vec<&SkillRow> {
        self.rows.iter().filter(|r| r.checked).collect()
    }

    /// The text of the confirmation: what is installed, from where, the warnings and the destinations.
    pub fn confirm_text(&self, plan: &SkillPlan, home: &Path) -> Result<String, core::Error> {
        let names: Vec<String> =
            plan.folders.iter().map(|f| f.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default()).collect();
        let mut dests = Vec::new();
        for t in &plan.targets {
            dests.push(core::skill_root(home, t, plan.scope, plan.project.as_deref())?.to_string_lossy().into_owned());
        }
        let source = if self.scanned_spec.is_empty() { "local folder" } else { self.scanned_spec.as_str() };
        let commit = if self.scanned_commit.is_empty() {
            String::new()
        } else {
            format!(" @ {}", self.scanned_commit.chars().take(10).collect::<String>())
        };
        let mut lines = vec![format!("Install skill(s): {}", names.join(", ")), format!("Source: {source}{commit}")];
        if !TRUSTED_SOURCES.contains(&self.scanned_spec.as_str()) {
            lines.push(
                "⚠ This source is not in brewcat's trusted list. A skill is a set of instructions (and sometimes scripts) your AI tool will follow. Review it before installing."
                    .to_string(),
            );
        }
        for (folder, name) in plan.folders.iter().zip(&names) {
            let scripts = core::skill_scripts(folder);
            if !scripts.is_empty() {
                let mut shown = scripts.iter().take(6).cloned().collect::<Vec<_>>().join(", ");
                if scripts.len() > 6 {
                    shown.push_str(&format!(" … (+{})", scripts.len() - 6));
                }
                lines.push(format!("⚠ {name} ships {} script(s): {shown}", scripts.len()));
            }
        }
        lines.push(String::new());
        lines.push("into:".to_string());
        lines.extend(dests);
        Ok(lines.join("\n"))
    }

    /// The jobs for a confirmed plan, and the log lines for the skills that were skipped because a symlink in them
    /// points outside the skill folder.
    pub fn build_jobs(&self, plan: &SkillPlan, home: &Path) -> (Vec<SkillJob>, Vec<(Tag, String)>) {
        let mut jobs = Vec::new();
        let mut log = Vec::new();
        for folder in &plan.folders {
            let name = folder.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            let links = core::unsafe_links(folder);
            if !links.is_empty() {
                let shown: Vec<String> =
                    links.iter().take(5).map(|l| l.strip_prefix(folder).unwrap_or(l).to_string_lossy().into_owned()).collect();
                log.push((Tag::Err, format!("✗ {name}: skipped, symlink(s) point outside the skill folder: {}\n", shown.join(", "))));
                continue;
            }
            for t in &plan.targets {
                if let Ok(root) = core::skill_root(home, t, plan.scope, plan.project.as_deref()) {
                    jobs.push(SkillJob { folder: folder.clone(), dest: root.join(&name), replace_ok: false });
                }
            }
        }
        (jobs, log)
    }

    /// Look at the front of the queue: ask, install, or finish.
    pub fn next_step(&self) -> JobStep {
        match self.jobs.front() {
            None => JobStep::Done,
            Some(job) if job.dest.exists() && !job.replace_ok => JobStep::AskReplace(job.dest.clone()),
            Some(job) => JobStep::Install(job.clone()),
        }
    }

    /// Install the front job and say how it went.
    pub fn install_front(&mut self) -> Option<(Tag, String)> {
        let job = self.jobs.pop_front()?;
        let name = job.folder.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        Some(match core::install_skill(&job.folder, &job.dest, &self.scanned_spec, &self.scanned_commit) {
            Ok(()) => (Tag::Info, format!("✓ {name} → {}\n", job.dest.display())),
            Err(e) => (Tag::Err, format!("✗ {name} → {}: {e}\n", job.dest.display())),
        })
    }
}

// ───────────────────────── MCP ─────────────────────────

/// The server definition being edited.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct McpForm {
    pub name: String,
    pub command: String,
    pub args: String,
    pub env: String,
}

/// What a confirmed MCP install will do.
#[derive(Debug, Clone)]
pub struct McpPlan {
    pub name: String,
    pub command: String,
    pub args: Vec<String>,
    pub env: Map<String, Value>,
    pub targets: Vec<&'static str>,
    pub scope: Scope,
    pub project: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum McpIssue {
    MissingNameOrCommand,
    InvalidArgs,
}

#[derive(Debug, Default)]
pub struct McpState {
    pub form: McpForm,
    pub selected: Option<usize>,
    pub marks: Vec<String>,
    pub bar: TargetBar,
}

impl McpState {
    pub fn new() -> McpState {
        McpState::default()
    }

    /// Fill the form from a preset.
    pub fn pick_preset(&mut self, index: usize) {
        if let Some(p) = MCP_PRESETS.get(index) {
            self.selected = Some(index);
            self.form =
                McpForm { name: p.name.to_string(), command: p.command.to_string(), args: p.args.to_string(), env: p.env.to_string() };
        }
    }

    pub fn refresh_marks(&mut self, home: &Path) {
        let (scope, project) = (self.bar.scope, self.bar.project.clone());
        self.marks = MCP_PRESETS
            .iter()
            .map(|p| {
                let mut flags: HashMap<&str, bool> = HashMap::new();
                if !(scope == Scope::Project && project.is_none()) {
                    for (id, _) in TARGETS {
                        if let Ok((path, key)) = core::mcp_file(home, id, scope, project.as_deref()) {
                            flags.insert(id, core::has_mcp_server(&path, key, p.name));
                        }
                    }
                }
                core::marks(&flags)
            })
            .collect();
    }

    /// Validate the form and the choice of tools. `bar_selection` is `TargetBar::selection()` already checked.
    pub fn prepare(&self, targets: Vec<&'static str>, scope: Scope, project: Option<PathBuf>) -> Result<McpPlan, McpIssue> {
        let (name, command) = (self.form.name.trim(), self.form.command.trim());
        if name.is_empty() || command.is_empty() {
            return Err(McpIssue::MissingNameOrCommand);
        }
        let args = shlex::split(&self.form.args).ok_or(McpIssue::InvalidArgs)?;
        Ok(McpPlan {
            name: name.to_string(),
            command: command.to_string(),
            args,
            env: core::parse_env(&self.form.env),
            targets,
            scope,
            project,
        })
    }
}

impl McpPlan {
    /// The text of the confirmation: the server, the warning for a custom command and the files that change.
    pub fn confirm_text(&self, home: &Path) -> Result<String, core::Error> {
        let mut files = Vec::new();
        for t in &self.targets {
            files.push(core::mcp_file(home, t, self.scope, self.project.as_deref())?.0.to_string_lossy().into_owned());
        }
        let warn = if core::is_preset(&self.name, &self.command, &self.args) {
            String::new()
        } else {
            "\n\n⚠ Custom command (not one of brewcat's built-in presets). It will run on your machine, with your permissions, whenever your AI tool starts this server. Only continue if you trust where it came from."
                .to_string()
        };
        Ok(format!("Add MCP server '{}'\n{} {}{warn}\n\nto:\n{}", self.name, self.command, self.args.join(" "), files.join("\n")))
    }

    /// Write the server into each tool's config. Returns the log lines.
    pub fn execute(&self, home: &Path) -> Vec<(Tag, String)> {
        let mut log = Vec::new();
        if sys::which(&self.command).is_none() {
            log.push((Tag::Err, format!("Warning: '{}' not found in PATH (install it first).\n", self.command)));
        }
        for t in &self.targets {
            match core::mcp_file(home, t, self.scope, self.project.as_deref()) {
                Ok((path, key)) => {
                    let entry = core::mcp_entry(t, &self.command, &self.args, &self.env);
                    match core::add_mcp_server(&path, key, &self.name, entry) {
                        Ok(()) => log.push((Tag::Info, format!("✓ {} → {}\n", self.name, path.display()))),
                        Err(e) => log.push((Tag::Err, format!("✗ {}: {e}\n", path.display()))),
                    }
                }
                Err(e) => log.push((Tag::Err, format!("✗ {t}: {e}\n"))),
            }
        }
        log
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::symlink;

    fn skill(dir: &Path, name: &str) -> PathBuf {
        let f = dir.join("src").join(name);
        fs::create_dir_all(&f).unwrap();
        fs::write(f.join("SKILL.md"), format!("---\nname: {name}\n---\n")).unwrap();
        f
    }

    fn scan_ok(folders: &[PathBuf], spec: &str) -> ScanOk {
        ScanOk {
            spec: spec.to_string(),
            tmp: None,
            commit: "0123456789abcdef".to_string(),
            skills: folders
                .iter()
                .map(|f| FoundSkill { folder: f.clone(), name: f.file_name().unwrap().to_string_lossy().into_owned(), desc: String::new() })
                .collect(),
        }
    }

    #[test]
    fn the_target_bar_defaults_to_claude_for_the_user() {
        let bar = TargetBar::default();
        assert_eq!(bar.targets(), ["claude"]);
        assert_eq!(bar.selection().unwrap().1, Scope::User);
        assert_eq!(bar.project_label(), "(no folder)");
    }

    #[test]
    fn the_target_bar_reports_what_is_missing() {
        let mut bar = TargetBar { on: [false; 3], ..TargetBar::default() };
        assert_eq!(bar.selection().unwrap_err(), BarIssue::NoTarget);
        bar.on = [true, true, true];
        assert_eq!(bar.targets(), ["claude", "kiro", "vscode"]);
        bar.scope = Scope::Project;
        assert!(bar.needs_project());
        assert_eq!(bar.selection().unwrap_err(), BarIssue::NeedsProject);
        bar.set_project(PathBuf::from("/work/demo"));
        assert_eq!(bar.project_label(), "demo");
        assert!(bar.selection().is_ok());
        let mut user = TargetBar::default();
        user.set_project(PathBuf::from("/x")); // picking a folder switches to project scope
        assert_eq!(user.scope, Scope::Project);
    }

    #[test]
    fn a_scan_fills_the_list_and_marks_where_it_is_installed() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("home");
        let a = skill(dir.path(), "alpha");
        let b = skill(dir.path(), "beta");
        fs::create_dir_all(home.join(".claude/skills/alpha")).unwrap();
        fs::create_dir_all(home.join(".kiro/skills/alpha")).unwrap();
        let mut st = SkillsState::new();
        assert_eq!(st.source, "anthropics/skills");
        st.bar.on = [true, true, true];
        assert_eq!(st.apply_scan(scan_ok(&[a, b], "anthropics/skills"), &home), 2);
        assert_eq!((st.rows[0].marks.as_str(), st.rows[1].marks.as_str()), ("C K ·", "· · ·"));
        st.bar.scope = Scope::Project; // no folder yet: nothing can be known
        st.refresh_marks(&home);
        assert_eq!(st.rows[0].marks, "· · ·");
        st.select_all(true);
        assert_eq!(st.checked().len(), 2);
        st.select_all(false);
        assert!(st.checked().is_empty());
    }

    #[test]
    fn a_new_scan_deletes_the_previous_temporary_clone() {
        let dir = tempfile::tempdir().unwrap();
        let old = dir.path().join("old-clone");
        fs::create_dir_all(&old).unwrap();
        let mut st = SkillsState::new();
        st.tmp = Some(old.clone());
        st.apply_scan(ScanOk { tmp: None, ..scan_ok(&[], "x") }, dir.path());
        assert!(!old.exists() && st.tmp.is_none());
        let newer = dir.path().join("new-clone");
        fs::create_dir_all(&newer).unwrap();
        st.apply_scan(ScanOk { tmp: Some(newer.clone()), ..scan_ok(&[], "x") }, dir.path());
        st.cleanup_tmp();
        assert!(!newer.exists());
    }

    #[test]
    fn the_confirmation_names_skills_source_warnings_and_folders() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("home");
        let a = skill(dir.path(), "alpha");
        fs::create_dir_all(a.join("scripts")).unwrap();
        for n in 0..8 {
            fs::write(a.join(format!("scripts/s{n}.sh")), "echo").unwrap();
        }
        let mut st = SkillsState::new();
        st.apply_scan(scan_ok(std::slice::from_ref(&a), "someone/else"), &home);
        let plan = SkillPlan { folders: vec![a.clone()], targets: vec!["claude", "vscode"], scope: Scope::User, project: None };
        let text = st.confirm_text(&plan, &home).unwrap();
        assert!(text.starts_with("Install skill(s): alpha\nSource: someone/else @ 0123456789\n"), "{text}");
        assert!(text.contains("⚠ This source is not in brewcat's trusted list"));
        assert!(
            text.contains(
                "⚠ alpha ships 8 script(s): scripts/s0.sh, scripts/s1.sh, scripts/s2.sh, scripts/s3.sh, scripts/s4.sh, scripts/s5.sh … (+2)"
            ),
            "{text}"
        );
        assert!(text.ends_with(&format!("\ninto:\n{}\n{}", home.join(".claude/skills").display(), home.join(".copilot/skills").display())));
        st.scanned_spec = "anthropics/skills".to_string();
        assert!(!st.confirm_text(&plan, &home).unwrap().contains("trusted list"));
        st.scanned_spec = String::new();
        st.scanned_commit = String::new();
        assert!(st.confirm_text(&plan, &home).unwrap().contains("Source: local folder\n"));
    }

    #[test]
    fn skills_with_links_leaving_the_folder_are_skipped_and_logged() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("home");
        let good = skill(dir.path(), "good");
        let evil = skill(dir.path(), "evil");
        symlink("/etc/hosts", evil.join("leak")).unwrap();
        let st = SkillsState::new();
        let plan = SkillPlan { folders: vec![good.clone(), evil], targets: vec!["claude", "kiro"], scope: Scope::User, project: None };
        let (jobs, log) = st.build_jobs(&plan, &home);
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].dest, home.join(".claude/skills/good"));
        assert_eq!(jobs[1].dest, home.join(".kiro/skills/good"));
        assert_eq!(log.len(), 1);
        assert_eq!(log[0].0, Tag::Err);
        assert!(log[0].1.starts_with("✗ evil: skipped, symlink(s) point outside the skill folder: leak"));
    }

    #[test]
    fn existing_destinations_are_asked_about_one_at_a_time() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("home");
        let a = skill(dir.path(), "alpha");
        let b = skill(dir.path(), "beta");
        fs::create_dir_all(home.join(".claude/skills/alpha")).unwrap();
        fs::write(home.join(".claude/skills/alpha/old.txt"), "old").unwrap();
        let mut st = SkillsState::new();
        st.scanned_spec = "anthropics/skills".to_string();
        let plan = SkillPlan { folders: vec![a, b], targets: vec!["claude"], scope: Scope::User, project: None };
        st.jobs = st.build_jobs(&plan, &home).0.into();
        let dest_a = home.join(".claude/skills/alpha");
        assert_eq!(st.next_step(), JobStep::AskReplace(dest_a.clone()));
        st.jobs.pop_front(); // the user said no: skip it
        let JobStep::Install(job) = st.next_step() else { panic!("beta installs without a question") };
        assert_eq!(job.dest, home.join(".claude/skills/beta"));
        let (tag, line) = st.install_front().unwrap();
        assert_eq!(tag, Tag::Info);
        assert!(line.starts_with("✓ beta → ") && home.join(".claude/skills/beta/SKILL.md").exists());
        assert!(home.join(".claude/skills/alpha/old.txt").exists()); // untouched
        assert_eq!(st.next_step(), JobStep::Done);
        assert!(st.install_front().is_none());
    }

    #[test]
    fn agreeing_to_replace_installs_over_the_old_folder() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path().join("home");
        let a = skill(dir.path(), "alpha");
        fs::create_dir_all(home.join(".claude/skills/alpha")).unwrap();
        fs::write(home.join(".claude/skills/alpha/old.txt"), "old").unwrap();
        let mut st = SkillsState::new();
        let plan = SkillPlan { folders: vec![a], targets: vec!["claude"], scope: Scope::User, project: None };
        st.jobs = st.build_jobs(&plan, &home).0.into();
        st.jobs.front_mut().unwrap().replace_ok = true;
        assert!(matches!(st.next_step(), JobStep::Install(_)));
        st.install_front().unwrap();
        assert!(!home.join(".claude/skills/alpha/old.txt").exists() && home.join(".claude/skills/alpha/.brewcat-source.json").exists());
    }

    #[test]
    fn presets_fill_the_form_and_show_where_they_are_installed() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path();
        let mut st = McpState::new();
        st.pick_preset(1);
        assert_eq!(
            (st.form.name.as_str(), st.form.command.as_str(), st.form.args.as_str()),
            ("memory", "npx", "-y @modelcontextprotocol/server-memory")
        );
        st.pick_preset(99); // out of range: nothing changes
        assert_eq!(st.selected, Some(1));
        fs::write(home.join(".claude.json"), r#"{"mcpServers": {"memory": {}}}"#).unwrap();
        st.refresh_marks(home);
        assert_eq!(st.marks.len(), MCP_PRESETS.len());
        assert_eq!((st.marks[0].as_str(), st.marks[1].as_str()), ("· · ·", "C · ·"));
        st.bar.scope = Scope::Project;
        st.refresh_marks(home);
        assert_eq!(st.marks[1], "· · ·");
    }

    #[test]
    fn the_form_is_validated_before_anything_is_written() {
        let mut st = McpState::new();
        assert_eq!(st.prepare(vec!["claude"], Scope::User, None).unwrap_err(), McpIssue::MissingNameOrCommand);
        st.form = McpForm { name: "x".into(), command: "  ".into(), ..McpForm::default() };
        assert_eq!(st.prepare(vec!["claude"], Scope::User, None).unwrap_err(), McpIssue::MissingNameOrCommand);
        st.form = McpForm { name: "x".into(), command: "npx".into(), args: "\"unterminated".into(), env: String::new() };
        assert_eq!(st.prepare(vec!["claude"], Scope::User, None).unwrap_err(), McpIssue::InvalidArgs);
        st.form.args = "-y 'my pkg'".to_string();
        st.form.env = "A=1, junk".to_string();
        let plan = st.prepare(vec!["claude"], Scope::User, None).unwrap();
        assert_eq!(plan.args, ["-y", "my pkg"]);
        assert_eq!(plan.env.len(), 1);
    }

    #[test]
    fn a_custom_command_gets_a_warning_and_a_preset_does_not() {
        let home = Path::new("/home/u");
        let mut st = McpState::new();
        st.pick_preset(1);
        let preset = st.prepare(vec!["claude", "kiro"], Scope::User, None).unwrap();
        let text = preset.confirm_text(home).unwrap();
        assert_eq!(
            text,
            "Add MCP server 'memory'\nnpx -y @modelcontextprotocol/server-memory\n\nto:\n/home/u/.claude.json\n/home/u/.kiro/settings/mcp.json"
        );
        st.form.args.push_str(" --evil");
        let custom = st.prepare(vec!["claude"], Scope::User, None).unwrap();
        assert!(custom.confirm_text(home).unwrap().contains("⚠ Custom command (not one of brewcat's built-in presets)"));
    }

    #[test]
    fn installing_writes_each_config_and_reports_every_file() {
        let dir = tempfile::tempdir().unwrap();
        let home = dir.path();
        let mut st = McpState::new();
        st.form = McpForm { name: "demo".into(), command: "definitely-not-a-command-xyz".into(), args: "-y pkg".into(), env: "K=v".into() };
        let plan = st.prepare(vec!["claude", "kiro", "vscode"], Scope::User, None).unwrap();
        let log = plan.execute(home);
        assert_eq!(log[0].0, Tag::Err);
        assert!(log[0].1.contains("'definitely-not-a-command-xyz' not found in PATH"));
        assert_eq!(log.iter().filter(|(t, l)| *t == Tag::Info && l.starts_with("✓ demo → ")).count(), 3);
        let claude: Value = serde_json::from_str(&fs::read_to_string(home.join(".claude.json")).unwrap()).unwrap();
        assert_eq!(claude["mcpServers"]["demo"]["type"], "stdio");
        let kiro: Value = serde_json::from_str(&fs::read_to_string(home.join(".kiro/settings/mcp.json")).unwrap()).unwrap();
        assert!(kiro["mcpServers"]["demo"].get("type").is_none() && kiro["mcpServers"]["demo"]["env"]["K"] == "v");
        fs::write(home.join(".claude.json"), "{broken").unwrap(); // a corrupt config is reported, never overwritten
        let log = plan.execute(home);
        assert!(log.iter().any(|(t, l)| *t == Tag::Err && l.starts_with("✗ ") && l.contains(".claude.json")));
        assert_eq!(fs::read_to_string(home.join(".claude.json")).unwrap(), "{broken");
    }
}
