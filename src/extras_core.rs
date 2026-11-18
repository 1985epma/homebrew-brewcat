//! The logic behind the Skills and MCP tabs. No GUI types, so it is testable and usable on a box without a display.

use std::collections::HashMap;
use std::fs;
use std::io;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Component, Path, PathBuf};
use std::sync::OnceLock;
use std::time::Duration;

use regex::Regex;
use serde_json::{Map, Value, json};

use crate::sys;

/// (id, label) of the tools skills and MCP servers can be installed into.
pub const TARGETS: [(&str, &str); 3] = [("claude", "Claude"), ("kiro", "Kiro"), ("vscode", "VS Code")];
pub const SKILL_PRESETS: [&str; 1] = ["anthropics/skills"];
pub const TRUSTED_SOURCES: [&str; 1] = ["anthropics/skills"];
const SCRIPT_EXTS: [&str; 11] = ["sh", "bash", "zsh", "py", "js", "mjs", "ts", "rb", "pl", "ps1", "command"];
const SKIP_DIRS: [&str; 3] = [".git", "node_modules", "__pycache__"];

pub struct McpPreset {
    pub name: &'static str,
    pub command: &'static str,
    pub args: &'static str,
    pub desc: &'static str,
    pub env: &'static str,
}

const fn preset(name: &'static str, command: &'static str, args: &'static str, desc: &'static str) -> McpPreset {
    McpPreset { name, command, args, desc, env: "" }
}

pub const MCP_PRESETS: [McpPreset; 8] = [
    preset(
        "filesystem",
        "npx",
        "-y @modelcontextprotocol/server-filesystem /path/to/allow",
        "Read/write files in the directories you allow",
    ),
    preset("memory", "npx", "-y @modelcontextprotocol/server-memory", "Persistent knowledge-graph memory"),
    preset("sequential-thinking", "npx", "-y @modelcontextprotocol/server-sequential-thinking", "Step-by-step reasoning tool"),
    preset("context7", "npx", "-y @upstash/context7-mcp", "Up-to-date library docs in your prompts"),
    preset("playwright", "npx", "@playwright/mcp@latest", "Browser automation with Playwright"),
    preset("fetch", "uvx", "mcp-server-fetch", "Fetch web pages and convert them to Markdown"),
    preset("git", "uvx", "mcp-server-git", "Read and manipulate git repositories"),
    preset("time", "uvx", "mcp-server-time", "Current time and timezone conversion"),
];

/// A problem to show to the user, already worded as a sentence.
#[derive(Debug)]
pub struct Error(pub String);

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Error {}

impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Error(e.to_string())
    }
}

impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Error(e.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;

fn err<T>(msg: impl Into<String>) -> Result<T> {
    Err(Error(msg.into()))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Scope {
    User,
    Project,
}

// ───────────────────────── paths ─────────────────────────

fn base_for<'a>(home: &'a Path, scope: Scope, project: Option<&'a Path>) -> Result<&'a Path> {
    match (scope, project) {
        (Scope::User, _) => Ok(home),
        (Scope::Project, Some(p)) => Ok(p),
        (Scope::Project, None) => err("a project folder is required for project scope"),
    }
}

/// Folder that holds the skills of `target` (`home` is the user's home directory).
pub fn skill_root(home: &Path, target: &str, scope: Scope, project: Option<&Path>) -> Result<PathBuf> {
    let base = base_for(home, scope, project)?;
    let sub = match (target, scope) {
        ("claude", _) => ".claude/skills",
        ("kiro", _) => ".kiro/skills",
        ("vscode", Scope::User) => ".copilot/skills",
        ("vscode", Scope::Project) => ".github/skills",
        _ => return err(format!("unknown target '{target}'")),
    };
    Ok(base.join(sub))
}

/// The MCP config file of `target` and the JSON key that holds the servers.
pub fn mcp_file(home: &Path, target: &str, scope: Scope, project: Option<&Path>) -> Result<(PathBuf, &'static str)> {
    let base = base_for(home, scope, project)?;
    let code_user = if sys::is_mac() { home.join("Library/Application Support/Code/User") } else { home.join(".config/Code/User") };
    Ok(match (target, scope) {
        ("claude", Scope::User) => (home.join(".claude.json"), "mcpServers"),
        ("kiro", Scope::User) => (home.join(".kiro/settings/mcp.json"), "mcpServers"),
        ("vscode", Scope::User) => (code_user.join("mcp.json"), "servers"),
        ("claude", Scope::Project) => (base.join(".mcp.json"), "mcpServers"),
        ("kiro", Scope::Project) => (base.join(".kiro/settings/mcp.json"), "mcpServers"),
        ("vscode", Scope::Project) => (base.join(".vscode/mcp.json"), "servers"),
        _ => return err(format!("unknown target '{target}'")),
    })
}

/// The JSON object stored in `path`; an empty or missing file is an empty object. Anything else that is not a
/// JSON object is an error (a config is never silently replaced).
pub fn read_json(path: &Path) -> Result<Map<String, Value>> {
    let text = match fs::read_to_string(path) {
        Ok(t) => t,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(Map::new()),
        Err(e) => return Err(e.into()),
    };
    if text.trim().is_empty() {
        return Ok(Map::new());
    }
    match serde_json::from_str::<Value>(&text)? {
        Value::Object(map) => Ok(map),
        _ => err(format!("{} does not hold a JSON object", path.display())),
    }
}

fn sibling(path: &Path, suffix: &str) -> PathBuf {
    let mut name = path.file_name().map(|n| n.to_os_string()).unwrap_or_default();
    name.push(suffix);
    path.with_file_name(name)
}

/// Write `data` as pretty JSON. The old file is kept as `<name>.bak`, the new one replaces it atomically and keeps
/// the old file's permissions (a config with secrets in it stays private).
pub fn write_json(path: &Path, data: &Map<String, Value>) -> Result<()> {
    if let Some(dir) = path.parent() {
        fs::create_dir_all(dir)?;
    }
    let existing = fs::metadata(path).ok();
    if existing.is_some() {
        fs::copy(path, sibling(path, ".bak"))?;
    }
    let tmp = sibling(path, ".tmp");
    let mut text = serde_json::to_string_pretty(data)?;
    text.push('\n');
    fs::write(&tmp, text)?;
    if let Some(meta) = existing {
        fs::set_permissions(&tmp, meta.permissions())?;
    }
    fs::rename(&tmp, path)?;
    Ok(())
}

// ───────────────────────── skills ─────────────────────────

/// (name, description) from the front matter of `<folder>/SKILL.md`; the name falls back to the folder name.
pub fn parse_skill(folder: &Path) -> Result<(String, String)> {
    let bytes = fs::read(folder.join("SKILL.md"))?;
    let text = String::from_utf8_lossy(&bytes);
    static FRONT: OnceLock<Regex> = OnceLock::new();
    let front = FRONT.get_or_init(|| Regex::new(r"(?s)^---\s*\n(.*?)\n---").expect("valid regex"));
    let mut meta: HashMap<String, String> = HashMap::new();
    if let Some(m) = front.captures(&text) {
        let lines: Vec<&str> = m[1].lines().collect();
        for (i, line) in lines.iter().enumerate() {
            let Some((k, v)) = line.split_once(':').filter(|_| !line.starts_with(' ')) else { continue };
            let mut v = v.trim().trim_matches(|c| c == '"' || c == '\'').to_string();
            if matches!(v.as_str(), ">" | "|" | ">-" | "|-") {
                let block: Vec<&str> = lines[i + 1..].iter().take_while(|l| l.starts_with(' ')).map(|l| l.trim()).collect();
                v = block.join(" ");
            }
            meta.insert(k.trim().to_string(), v);
        }
    }
    let folder_name = folder.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let name = meta.remove("name").filter(|n| !n.is_empty()).unwrap_or(folder_name);
    Ok((name, meta.remove("description").unwrap_or_default()))
}

/// Folders under `root` (at most `depth` levels down) that hold a `SKILL.md`. Symlinked folders are not followed.
pub fn scan_skills(root: &Path, depth: usize) -> io::Result<Vec<PathBuf>> {
    fn walk(dir: &Path, level: usize, depth: usize, found: &mut Vec<PathBuf>) -> io::Result<()> {
        if dir.join("SKILL.md").is_file() {
            found.push(dir.to_path_buf());
            return Ok(());
        }
        if level >= depth {
            return Ok(());
        }
        let mut children: Vec<PathBuf> = fs::read_dir(dir)?.map(|e| e.map(|e| e.path())).collect::<io::Result<_>>()?;
        children.sort();
        for child in children {
            let skip = child.file_name().is_some_and(|n| SKIP_DIRS.iter().any(|s| n == *s));
            let is_real_dir = fs::symlink_metadata(&child).map(|m| m.is_dir()).unwrap_or(false);
            if is_real_dir && !skip {
                walk(&child, level + 1, depth, found)?;
            }
        }
        Ok(())
    }
    let mut found = Vec::new();
    walk(root, 0, depth, &mut found)?;
    Ok(found)
}

/// `owner/repo`, a GitHub URL or a `/tree/<branch>/<sub>` URL -> (clone url, branch, sub path).
///
/// Fails for anything that is not a plain GitHub shorthand or an https/ssh git URL, so user-typed text can
/// never be interpreted by git as an option or an exotic transport (`ext::`, `file:`).
pub fn parse_repo(spec: &str) -> Result<(String, Option<String>, String)> {
    const INVALID: &str = "Invalid source: use owner/repo, a GitHub URL or a local folder";
    let spec = spec.trim().trim_end_matches('/');
    if spec.is_empty() || spec.starts_with('-') || spec.contains([' ', '\t', '\r', '\n', '\0']) {
        return err(INVALID);
    }
    static GITHUB: OnceLock<Regex> = OnceLock::new();
    static REMOTE: OnceLock<Regex> = OnceLock::new();
    static SCHEME: OnceLock<Regex> = OnceLock::new();
    let github = GITHUB.get_or_init(|| {
        Regex::new(r"^(?:https?://github\.com/)?([\w.-]+/[\w.-]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.*))?)?$").expect("valid regex")
    });
    if let Some(m) = github.captures(spec) {
        let branch = m.get(2).map(|b| b.as_str().to_string());
        if branch.as_deref().is_some_and(|b| b.starts_with('-')) {
            return err("Invalid branch name");
        }
        let sub = m.get(3).map_or(String::new(), |s| s.as_str().to_string());
        return Ok((format!("https://github.com/{}.git", &m[1]), branch, sub));
    }
    let remote = REMOTE.get_or_init(|| Regex::new(r"^(https://|ssh://|git@)[\w.@:/~-]+$").expect("valid regex"));
    if remote.is_match(spec) {
        let rest = SCHEME.get_or_init(|| Regex::new(r"^(https://|ssh://|git@)").expect("valid regex")).replace(spec, "");
        let host = rest.rsplit('@').next().unwrap_or("");
        if rest.starts_with('-') || host.starts_with('-') {
            return err("Invalid source host"); // ssh would read it as an option
        }
        return Ok((spec.to_string(), None, String::new()));
    }
    err(INVALID)
}

/// Every file and folder under `dir` (not following symlinks), as paths relative to `dir`, sorted.
fn walk_relative(dir: &Path) -> Vec<PathBuf> {
    fn go(base: &Path, dir: &Path, out: &mut Vec<PathBuf>) {
        let Ok(entries) = fs::read_dir(dir) else { return };
        for entry in entries.flatten() {
            let path = entry.path();
            out.push(path.strip_prefix(base).unwrap_or(&path).to_path_buf());
            if fs::symlink_metadata(&path).map(|m| m.is_dir()).unwrap_or(false) {
                go(base, &path, out);
            }
        }
    }
    let mut out = Vec::new();
    go(dir, dir, &mut out);
    out.sort();
    out
}

/// Executable content shipped with a skill (scripts or files with the exec bit), relative to `folder`.
pub fn skill_scripts(folder: &Path) -> Vec<String> {
    walk_relative(folder)
        .into_iter()
        .filter(|rel| !rel.components().any(|c| c.as_os_str() == ".git"))
        .filter(|rel| {
            let Ok(meta) = fs::symlink_metadata(folder.join(rel)) else { return false };
            if !meta.is_file() {
                return false;
            }
            let ext = rel.extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
            SCRIPT_EXTS.contains(&ext.as_str()) || meta.permissions().mode() & 0o111 != 0
        })
        .map(|rel| rel.to_string_lossy().into_owned())
        .collect()
}

/// The commit `path` is at, or an empty string when it is not a git checkout.
pub fn git_head(path: &Path) -> String {
    sys::run_capture(&sys::argv(&["git", "-C", &path.to_string_lossy(), "rev-parse", "HEAD"]), &[], Duration::from_secs(15))
        .map(|c| c.stdout.trim().to_string())
        .unwrap_or_default()
}

fn normalize(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other),
        }
    }
    out
}

/// Where `link` really points, also when the target does not exist.
fn resolve_lenient(link: &Path) -> PathBuf {
    if let Ok(real) = fs::canonicalize(link) {
        return real;
    }
    let target = fs::read_link(link).unwrap_or_default();
    let parent = link.parent().and_then(|p| fs::canonicalize(p).ok()).unwrap_or_default();
    normalize(&parent.join(target))
}

/// Symlinks inside `folder` that point outside of it (they could expose files such as ~/.ssh keys).
pub fn unsafe_links(folder: &Path) -> Vec<PathBuf> {
    let root = fs::canonicalize(folder).unwrap_or_else(|_| folder.to_path_buf());
    walk_relative(folder)
        .into_iter()
        .map(|rel| folder.join(rel))
        .filter(|p| fs::symlink_metadata(p).map(|m| m.file_type().is_symlink()).unwrap_or(false))
        .filter(|p| !resolve_lenient(p).starts_with(&root))
        .collect()
}

fn copy_tree(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        if entry.file_name() == ".git" {
            continue;
        }
        let (from, to) = (entry.path(), dst.join(entry.file_name()));
        let meta = fs::symlink_metadata(&from)?;
        if meta.file_type().is_symlink() {
            symlink(fs::read_link(&from)?, &to)?; // copied as a link; unsafe_links() vets where it points
        } else if meta.is_dir() {
            copy_tree(&from, &to)?;
        } else {
            fs::copy(&from, &to)?;
        }
    }
    fs::set_permissions(dst, fs::metadata(src)?.permissions())
}

/// Copy the skill in `folder` to `dest` (replacing what is there, leaving out `.git`) and record where it came
/// from in `.brewcat-source.json`.
pub fn install_skill(folder: &Path, dest: &Path, source: &str, commit: &str) -> Result<()> {
    if fs::symlink_metadata(dest).is_ok() {
        fs::remove_dir_all(dest)?;
    }
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    copy_tree(folder, dest)?;
    let note = json!({"source": source, "commit": commit, "installed_by": "brewcat"});
    fs::write(dest.join(".brewcat-source.json"), serde_json::to_string_pretty(&note)?)?;
    Ok(())
}

/// "C K V"-style marks: the first letter of each target where it is installed, a dot where it is not.
pub fn marks(flags: &HashMap<&str, bool>) -> String {
    let parts: Vec<String> = TARGETS
        .iter()
        .map(
            |(k, label)| {
                if flags.get(k).copied().unwrap_or(false) { label.chars().next().unwrap_or('?').to_string() } else { "·".to_string() }
            },
        )
        .collect();
    parts.join(" ")
}

// ───────────────────────── MCP ─────────────────────────

/// True when (name, command, args) is exactly one of brewcat's built-in MCP presets.
pub fn is_preset(name: &str, command: &str, args: &[String]) -> bool {
    MCP_PRESETS.iter().any(|p| p.name == name && p.command == command && shlex::split(p.args).is_some_and(|a| a == args))
}

/// `A=1, B=2` -> `{"A": "1", "B": "2"}`; items without `=` are ignored.
pub fn parse_env(text: &str) -> Map<String, Value> {
    let mut env = Map::new();
    for part in text.split(',').map(str::trim) {
        if let Some((k, v)) = part.split_once('=') {
            env.insert(k.to_string(), Value::String(v.to_string()));
        }
    }
    env
}

/// The server definition as each tool wants it (Kiro has no `"type"` field).
pub fn mcp_entry(target: &str, command: &str, args: &[String], env: &Map<String, Value>) -> Value {
    let mut entry = Map::new();
    if target != "kiro" {
        entry.insert("type".into(), json!("stdio"));
    }
    entry.insert("command".into(), json!(command));
    entry.insert("args".into(), json!(args));
    if !env.is_empty() {
        entry.insert("env".into(), Value::Object(env.clone()));
    }
    Value::Object(entry)
}

/// Merge one server into the JSON config at `path` under `key` (a `.bak` copy of the old file is kept). A config
/// that is not valid JSON is never overwritten.
pub fn add_mcp_server(path: &Path, key: &str, name: &str, entry: Value) -> Result<()> {
    let mut data = read_json(path)?;
    let servers = data.entry(key).or_insert_with(|| Value::Object(Map::new()));
    match servers.as_object_mut() {
        Some(map) => map.insert(name.to_string(), entry),
        None => return err(format!("\"{key}\" in {} is not a JSON object", path.display())),
    };
    write_json(path, &data)
}

/// True when `name` is already configured under `key` in the config at `path`.
pub fn has_mcp_server(path: &Path, key: &str, name: &str) -> bool {
    read_json(path).ok().and_then(|d| d.get(key).and_then(|s| s.get(name)).map(|_| true)).unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::str::FromStr;

    fn v(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    fn json_file(path: &Path) -> Value {
        Value::from_str(&fs::read_to_string(path).unwrap()).unwrap()
    }

    #[test]
    fn trusted_sources_are_only_the_vetted_one() {
        assert_eq!(TRUSTED_SOURCES, ["anthropics/skills"]);
        assert!(TRUSTED_SOURCES.contains(&SKILL_PRESETS[0]));
    }

    #[test]
    fn skill_root_per_target_and_scope() {
        let (home, p) = (Path::new("/home/u"), Path::new("/proj"));
        assert_eq!(skill_root(home, "claude", Scope::Project, Some(p)).unwrap(), p.join(".claude/skills"));
        assert_eq!(skill_root(home, "kiro", Scope::Project, Some(p)).unwrap(), p.join(".kiro/skills"));
        assert_eq!(skill_root(home, "vscode", Scope::Project, Some(p)).unwrap(), p.join(".github/skills"));
        assert_eq!(skill_root(home, "vscode", Scope::User, None).unwrap(), home.join(".copilot/skills"));
        assert_eq!(skill_root(home, "claude", Scope::User, None).unwrap(), home.join(".claude/skills"));
    }

    #[test]
    fn project_scope_without_a_folder_is_a_clear_error() {
        let home = Path::new("/home/u");
        assert!(skill_root(home, "claude", Scope::Project, None).unwrap_err().0.contains("project folder"));
        assert!(mcp_file(home, "claude", Scope::Project, None).unwrap_err().0.contains("project folder"));
        assert!(skill_root(home, "nope", Scope::User, None).is_err());
    }

    #[test]
    fn mcp_file_per_target_and_scope() {
        let (home, p) = (Path::new("/home/u"), Path::new("/proj"));
        assert_eq!(mcp_file(home, "claude", Scope::Project, Some(p)).unwrap(), (p.join(".mcp.json"), "mcpServers"));
        assert_eq!(mcp_file(home, "kiro", Scope::Project, Some(p)).unwrap(), (p.join(".kiro/settings/mcp.json"), "mcpServers"));
        assert_eq!(mcp_file(home, "vscode", Scope::Project, Some(p)).unwrap(), (p.join(".vscode/mcp.json"), "servers"));
        assert_eq!(mcp_file(home, "claude", Scope::User, None).unwrap(), (home.join(".claude.json"), "mcpServers"));
        assert_eq!(mcp_file(home, "kiro", Scope::User, None).unwrap().0, home.join(".kiro/settings/mcp.json"));
        let (code, key) = mcp_file(home, "vscode", Scope::User, None).unwrap();
        assert!(code.ends_with("Code/User/mcp.json") && key == "servers");
    }

    #[test]
    fn git_head_of_a_non_repo_is_empty() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(git_head(dir.path()), "");
    }

    #[test]
    fn is_preset_requires_exact_name_command_and_args() {
        assert!(is_preset("memory", "npx", &v(&["-y", "@modelcontextprotocol/server-memory"])));
        assert!(!is_preset("memory", "sh", &v(&["-y", "@modelcontextprotocol/server-memory"])));
        assert!(!is_preset("memory", "npx", &v(&["-y", "@modelcontextprotocol/server-memory", "--evil"])));
        assert!(!is_preset("custom", "npx", &v(&["-y", "@modelcontextprotocol/server-memory"])));
    }

    #[test]
    fn parse_env_ignores_items_without_equals() {
        assert_eq!(Value::Object(parse_env("A=1, B=x=y, junk, ")), json!({"A": "1", "B": "x=y"}));
        assert!(parse_env("").is_empty());
    }

    #[test]
    fn mcp_entry_kiro_has_no_type() {
        assert_eq!(
            mcp_entry("claude", "npx", &v(&["-y", "x"]), &Map::new()),
            json!({"type": "stdio", "command": "npx", "args": ["-y", "x"]})
        );
        let env = parse_env("K=v");
        assert_eq!(mcp_entry("kiro", "npx", &v(&["-y", "x"]), &env), json!({"command": "npx", "args": ["-y", "x"], "env": {"K": "v"}}));
    }

    #[test]
    fn add_mcp_server_merges_and_keeps_backup() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("mcp.json");
        fs::write(&f, json!({"mcpServers": {"old": {"command": "x"}}, "other": 1}).to_string()).unwrap();
        add_mcp_server(&f, "mcpServers", "new", mcp_entry("claude", "uvx", &v(&["mcp-server-time"]), &Map::new())).unwrap();
        let data = json_file(&f);
        let servers: Vec<&String> = data["mcpServers"].as_object().unwrap().keys().collect();
        assert_eq!(servers, ["old", "new"]); // the order of the user's file is kept
        assert_eq!(data["other"], 1);
        let backup = json_file(&dir.path().join("mcp.json.bak"));
        assert_eq!(backup["mcpServers"].as_object().unwrap().keys().collect::<Vec<_>>(), ["old"]);
    }

    #[test]
    fn add_mcp_server_creates_missing_file_and_rejects_garbage() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("sub/.mcp.json");
        add_mcp_server(&f, "servers", "a", json!({"command": "x", "args": []})).unwrap();
        assert_eq!(json_file(&f), json!({"servers": {"a": {"command": "x", "args": []}}}));
        fs::write(&f, "{not json").unwrap();
        assert!(add_mcp_server(&f, "servers", "b", json!({})).is_err());
        assert_eq!(fs::read_to_string(&f).unwrap(), "{not json"); // a corrupt config is never overwritten
        fs::write(&f, "[1, 2]").unwrap();
        assert!(add_mcp_server(&f, "servers", "b", json!({})).is_err());
        fs::write(&f, r#"{"servers": 5}"#).unwrap();
        assert!(add_mcp_server(&f, "servers", "b", json!({})).is_err());
    }

    #[test]
    fn write_json_keeps_the_permissions_of_the_old_file() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("claude.json");
        fs::write(&f, "{}").unwrap();
        fs::set_permissions(&f, fs::Permissions::from_mode(0o600)).unwrap();
        add_mcp_server(&f, "mcpServers", "a", json!({"command": "x"})).unwrap();
        assert_eq!(fs::metadata(&f).unwrap().permissions().mode() & 0o777, 0o600);
    }

    #[test]
    fn numbers_in_a_config_survive_a_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("c.json");
        fs::write(&f, r#"{"big": 12345678901234567890123, "f": 1.50, "mcpServers": {}}"#).unwrap();
        add_mcp_server(&f, "mcpServers", "a", json!({"command": "x"})).unwrap();
        let text = fs::read_to_string(&f).unwrap();
        assert!(text.contains("12345678901234567890123") && text.contains("1.50"), "{text}");
    }

    #[test]
    fn marks_show_where_something_is_installed() {
        assert_eq!(marks(&HashMap::from([("claude", true), ("vscode", true)])), "C · V");
        assert_eq!(marks(&HashMap::new()), "· · ·");
    }

    #[test]
    fn parse_repo_accepts() {
        for spec in [
            "anthropics/skills",
            "https://github.com/anthropics/skills",
            "https://github.com/anthropics/skills/tree/main/skills",
            "git@github.com:a/b.git",
            "ssh://git@github.com/a/b.git",
            "https://example.com/r.git",
        ] {
            let (url, ..) = parse_repo(spec).unwrap_or_else(|e| panic!("{spec}: {e}"));
            assert!(url.starts_with("https://") || url.starts_with("ssh://") || url.starts_with("git@"), "{spec}");
        }
    }

    #[test]
    fn parse_repo_rejects() {
        for spec in [
            "",
            "-x",
            "--upload-pack=touch /tmp/x",
            "ext::sh -c id",
            "file:///etc",
            "a/b c",
            "ssh://-oProxyCommand/x",
            "git@-evil:a/b",
            "ssh://u@-evil/x",
            "https://github.com/a/b/tree/-bad/x",
        ] {
            assert!(parse_repo(spec).is_err(), "{spec:?} must be rejected");
        }
    }

    #[test]
    fn parse_repo_branch_and_subpath() {
        assert_eq!(
            parse_repo("https://github.com/o/r/tree/main/skills/x").unwrap(),
            ("https://github.com/o/r.git".to_string(), Some("main".to_string()), "skills/x".to_string())
        );
        assert_eq!(parse_repo("owner/repo/").unwrap(), ("https://github.com/owner/repo.git".to_string(), None, String::new()));
    }

    #[test]
    fn unsafe_links_detects_symlink_leaving_the_skill() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("SKILL.md"), "x").unwrap();
        symlink("/etc/hosts", dir.path().join("leak")).unwrap();
        symlink("SKILL.md", dir.path().join("inside")).unwrap();
        symlink("../outside-that-does-not-exist", dir.path().join("dangling")).unwrap();
        let mut bad: Vec<String> = unsafe_links(dir.path()).iter().map(|p| p.file_name().unwrap().to_string_lossy().into_owned()).collect();
        bad.sort();
        assert_eq!(bad, ["dangling", "leak"]);
    }

    #[test]
    fn skill_scripts_lists_executable_content() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("SKILL.md"), "x").unwrap();
        fs::create_dir(dir.path().join("scripts")).unwrap();
        fs::write(dir.path().join("scripts/run.sh"), "echo").unwrap();
        fs::write(dir.path().join("notes.txt"), "plain").unwrap();
        fs::write(dir.path().join("tool"), "bin").unwrap();
        fs::set_permissions(dir.path().join("tool"), fs::Permissions::from_mode(0o755)).unwrap();
        fs::create_dir(dir.path().join(".git")).unwrap();
        fs::write(dir.path().join(".git/hook.sh"), "x").unwrap();
        assert_eq!(skill_scripts(dir.path()), ["scripts/run.sh", "tool"]);
    }

    #[test]
    fn parse_skill_folded_description() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("SKILL.md"), "---\nname: demo\ndescription: >\n  line one\n  line two\n---\nbody").unwrap();
        assert_eq!(parse_skill(dir.path()).unwrap(), ("demo".to_string(), "line one line two".to_string()));
    }

    #[test]
    fn parse_skill_quotes_and_missing_front_matter() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("SKILL.md"), "---\nname: \"quoted\"\ndescription: 'single'\n---\n").unwrap();
        assert_eq!(parse_skill(dir.path()).unwrap(), ("quoted".to_string(), "single".to_string()));
        fs::write(dir.path().join("SKILL.md"), "no front matter").unwrap();
        let (name, desc) = parse_skill(dir.path()).unwrap();
        assert_eq!(name, dir.path().file_name().unwrap().to_string_lossy());
        assert_eq!(desc, "");
    }

    #[test]
    fn scan_skills_ignores_symlinked_dirs_and_skip_dirs() {
        let dir = tempfile::tempdir().unwrap();
        let real = dir.path().join("real/a");
        fs::create_dir_all(&real).unwrap();
        fs::write(real.join("SKILL.md"), "---\nname: a\n---\n").unwrap();
        let root = dir.path().join("root");
        fs::create_dir_all(root.join("node_modules/x")).unwrap();
        fs::write(root.join("node_modules/x/SKILL.md"), "x").unwrap();
        symlink(dir.path().join("real"), root.join("link")).unwrap();
        assert!(scan_skills(&root, 4).unwrap().is_empty());
        fs::create_dir_all(root.join("skills/b")).unwrap();
        fs::write(root.join("skills/b/SKILL.md"), "x").unwrap();
        assert_eq!(scan_skills(&root, 4).unwrap(), [root.join("skills/b")]);
        assert!(scan_skills(&root, 1).unwrap().is_empty()); // too deep for depth 1
    }

    #[test]
    fn write_json_keeps_backup_and_read_json_rejects_garbage() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("mcp.json");
        fs::write(&f, r#"{"mcpServers": {"a": {}}}"#).unwrap();
        let mut data = read_json(&f).unwrap();
        data["mcpServers"].as_object_mut().unwrap().insert("b".into(), json!({}));
        write_json(&f, &data).unwrap();
        assert_eq!(json_file(&f)["mcpServers"].as_object().unwrap().len(), 2);
        assert_eq!(json_file(&dir.path().join("mcp.json.bak"))["mcpServers"].as_object().unwrap().len(), 1);
        fs::write(&f, "{not json").unwrap();
        assert!(read_json(&f).is_err());
        fs::write(&f, "  \n").unwrap();
        assert!(read_json(&f).unwrap().is_empty());
        assert!(read_json(&dir.path().join("missing.json")).unwrap().is_empty());
    }

    #[test]
    fn install_skill_copies_without_git_and_records_the_source() {
        let dir = tempfile::tempdir().unwrap();
        let src = dir.path().join("src/demo");
        fs::create_dir_all(src.join("sub")).unwrap();
        fs::create_dir_all(src.join(".git")).unwrap();
        fs::write(src.join("SKILL.md"), "x").unwrap();
        fs::write(src.join("sub/f.txt"), "y").unwrap();
        fs::write(src.join(".git/config"), "z").unwrap();
        symlink("SKILL.md", src.join("alias")).unwrap();
        let dest = dir.path().join("home/.claude/skills/demo");
        fs::create_dir_all(&dest).unwrap();
        fs::write(dest.join("stale.txt"), "old").unwrap();
        install_skill(&src, &dest, "o/r", "abc123").unwrap();
        assert!(dest.join("SKILL.md").is_file() && dest.join("sub/f.txt").is_file());
        assert!(!dest.join(".git").exists() && !dest.join("stale.txt").exists());
        assert!(fs::symlink_metadata(dest.join("alias")).unwrap().file_type().is_symlink());
        let note = json_file(&dest.join(".brewcat-source.json"));
        assert_eq!(note, json!({"source": "o/r", "commit": "abc123", "installed_by": "brewcat"}));
    }

    #[test]
    fn every_mcp_preset_is_well_formed() {
        for p in &MCP_PRESETS {
            assert!(!p.name.is_empty() && !p.command.is_empty() && !p.desc.is_empty());
            assert!(!shlex::split(p.args).unwrap().is_empty(), "{}", p.name);
        }
    }

    #[test]
    fn has_mcp_server_reads_the_config() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("c.json");
        assert!(!has_mcp_server(&f, "mcpServers", "a"));
        fs::write(&f, r#"{"mcpServers": {"a": {}}}"#).unwrap();
        assert!(has_mcp_server(&f, "mcpServers", "a") && !has_mcp_server(&f, "mcpServers", "b"));
        fs::write(&f, "{broken").unwrap();
        assert!(!has_mcp_server(&f, "mcpServers", "a"));
    }
}
