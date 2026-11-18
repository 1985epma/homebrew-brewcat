//! Check the curated catalog against Homebrew's public API.
//!
//!   cargo run --example validate_catalog                  structure + every package must exist in Homebrew
//!   cargo run --example validate_catalog -- --offline     structure only (no network)
//!
//! Errors (exit 1): unknown/disabled packages, duplicate keys, kits or essentials pointing to missing items.
//! Warnings (exit 0): deprecated packages. Packages from third-party taps (e.g. hashicorp/tap) are skipped.
//! The API is fetched with `curl`, so this needs no extra Rust dependencies.

use std::collections::HashMap;
use std::process::{Command, ExitCode};

use brewcat::catalog::{Kind, catalog};
use serde_json::Value;

const API: &str = "https://formulae.brew.sh/api";

fn structure_errors() -> Vec<String> {
    let cat = catalog();
    let mut errors = Vec::new();

    let mut counts: HashMap<String, usize> = HashMap::new();
    let mut order = Vec::new();
    for i in &cat.items {
        let key = i.key();
        let n = counts.entry(key.clone()).or_insert(0);
        *n += 1;
        if *n == 2 {
            order.push(key);
        }
    }
    errors.extend(order.into_iter().map(|k| format!("duplicate key: {k}")));

    for kit in &cat.kits {
        errors.extend(kit.keys.iter().filter(|k| cat.by_key(k).is_none()).map(|k| format!("kit '{}' references missing {k}", kit.name)));
    }
    let mut profiles: Vec<&String> = cat.essentials.keys().collect();
    profiles.sort();
    for profile in profiles {
        errors.extend(
            cat.essentials[profile]
                .iter()
                .filter(|k| cat.by_key(k).is_none())
                .map(|k| format!("essentials[{profile}] references missing {k}")),
        );
    }
    errors
}

fn fetch(kind: Kind) -> Result<Vec<Value>, String> {
    let url = format!("{API}/{}.json", kind.as_str());
    let out = Command::new("curl")
        .args(["-fsSL", "--max-time", "120", "-A", "brewcat-validate", &url])
        .output()
        .map_err(|e| format!("cannot run curl: {e}"))?;
    if !out.status.success() {
        return Err(format!("could not download {url}: {}", String::from_utf8_lossy(&out.stderr).trim()));
    }
    serde_json::from_slice(&out.stdout).map_err(|e| format!("{url} is not the JSON list expected: {e}"))
}

/// name/alias/old name -> entry (the first entry that claims a name keeps it).
fn index(entries: &[Value], kind: Kind) -> HashMap<String, &Value> {
    let strings = |e: &'_ Value, field: &str| -> Vec<String> {
        e.get(field).and_then(Value::as_array).map(|a| a.iter().filter_map(Value::as_str).map(String::from).collect()).unwrap_or_default()
    };
    let mut out = HashMap::new();
    for e in entries {
        let names: Vec<String> = match kind {
            Kind::Cask => e.get("token").and_then(Value::as_str).map(String::from).into_iter().chain(strings(e, "old_tokens")).collect(),
            Kind::Formula => e
                .get("name")
                .and_then(Value::as_str)
                .map(String::from)
                .into_iter()
                .chain(strings(e, "aliases"))
                .chain(strings(e, "oldnames"))
                .collect(),
        };
        for n in names {
            out.entry(n).or_insert(e);
        }
    }
    out
}

fn truthy(entry: &Value, field: &str) -> bool {
    entry.get(field).and_then(Value::as_bool).unwrap_or(false)
}

fn main() -> ExitCode {
    let cat = catalog();
    let mut errors = structure_errors();
    let mut warnings: Vec<String> = Vec::new();

    if !std::env::args().any(|a| a == "--offline") {
        let (formulae, casks) = match (fetch(Kind::Formula), fetch(Kind::Cask)) {
            (Ok(f), Ok(c)) => (f, c),
            (Err(e), _) | (_, Err(e)) => {
                eprintln!("ERROR {e}");
                return ExitCode::FAILURE;
            }
        };
        let (formula_idx, cask_idx) = (index(&formulae, Kind::Formula), index(&casks, Kind::Cask));
        for i in cat.items.iter().filter(|i| i.tap.is_empty()) {
            let idx = if i.kind == Kind::Cask { &cask_idx } else { &formula_idx };
            match idx.get(&i.name) {
                None => errors.push(format!("{}: not found in Homebrew (renamed or removed?)", i.key())),
                Some(e) if truthy(e, "disabled") => errors.push(format!("{}: disabled in Homebrew", i.key())),
                Some(e) if truthy(e, "deprecated") => warnings.push(format!("{}: deprecated in Homebrew", i.key())),
                Some(_) => {}
            }
        }
    }

    for w in &warnings {
        println!("WARN  {w}");
    }
    for e in &errors {
        println!("ERROR {e}");
    }
    println!("{} packages, {} kits: {} error(s), {} warning(s)", cat.items.len(), cat.kits.len(), errors.len(), warnings.len());
    if errors.is_empty() { ExitCode::SUCCESS } else { ExitCode::FAILURE }
}
