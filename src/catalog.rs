//! Curated catalog of Homebrew packages for developers, SRE, gamers and more.
//!
//! The data lives in `data/catalog.json` (compiled in): one object per package, kits, the categories of each
//! profile and the "essentials" suggested when nothing relevant is installed yet. Formulae work on macOS and
//! Linux; casks (GUI apps) are macOS only.

use std::collections::HashMap;
use std::sync::OnceLock;

use serde::{Deserialize, Deserializer};

// Profile ids as written in the catalog (the command line uses the slugs in `PROFILE_SLUGS`).
pub const DEV: &str = "dev";
pub const GAMER: &str = "gamer";
pub const SRE: &str = "sre";
pub const QA: &str = "qa";
pub const OFFICE: &str = "office";
pub const DESIGN: &str = "design";
pub const DJ: &str = "dj";
pub const DS: &str = "datascience";
pub const DE: &str = "dataeng";
pub const NET: &str = "network";
pub const SEC: &str = "security";
pub const VENDOR: &str = "vendors";
pub const LABS: &str = "117labs";
pub const MAC: &str = "mac";
pub const LINUX: &str = "linux";
pub const BOTH: [&str; 2] = [MAC, LINUX];

/// `-p/--profile` value -> profile id.
pub const PROFILE_SLUGS: [(&str, &str); 13] = [
    ("dev", DEV),
    ("sre", SRE),
    ("qa", QA),
    ("datascience", DS),
    ("dataeng", DE),
    ("network", NET),
    ("security", SEC),
    ("design", DESIGN),
    ("dj", DJ),
    ("office", OFFICE),
    ("vendors", VENDOR),
    ("gamer", GAMER),
    ("117-labs", LABS),
];

/// Profile id for a command-line slug.
pub fn profile_for_slug(slug: &str) -> Option<&'static str> {
    PROFILE_SLUGS.iter().find(|(s, _)| *s == slug).map(|(_, id)| *id)
}

/// The slugs accepted by `-p`, sorted.
pub fn profile_slugs() -> Vec<&'static str> {
    let mut slugs: Vec<_> = PROFILE_SLUGS.iter().map(|(s, _)| *s).collect();
    slugs.sort_unstable();
    slugs
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Formula,
    Cask,
}

impl Kind {
    pub fn as_str(self) -> &'static str {
        match self {
            Kind::Formula => "formula",
            Kind::Cask => "cask",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Item {
    pub name: String,
    pub kind: Kind,
    pub category: String,
    pub desc: String,
    pub profiles: Vec<String>,
    pub platforms: Vec<String>,
    #[serde(default)]
    pub tags: Vec<String>,
    /// e.g. "hashicorp/tap" for formulae outside homebrew-core.
    #[serde(default)]
    pub tap: String,
    /// Extra categories this package also appears in.
    #[serde(default)]
    pub groups: Vec<String>,
    /// Product page, used instead of formulae.brew.sh for tap-only products.
    #[serde(default)]
    pub homepage: String,
}

impl Item {
    /// A package that is not in the curated catalog (found with `brew search`).
    pub fn external(name: &str, kind: Kind, category: &str, desc: &str, tap: &str) -> Item {
        Item {
            name: name.to_string(),
            kind,
            category: category.to_string(),
            desc: desc.to_string(),
            profiles: vec![DEV.into(), SRE.into(), GAMER.into()],
            platforms: if kind == Kind::Formula { BOTH.map(String::from).to_vec() } else { vec![MAC.into()] },
            tags: vec!["search".into()],
            tap: tap.to_string(),
            groups: Vec::new(),
            homepage: String::new(),
        }
    }

    /// `tap/name` for tap-only packages, else `name`.
    pub fn full_name(&self) -> String {
        if self.tap.is_empty() { self.name.clone() } else { format!("{}/{}", self.tap, self.name) }
    }

    /// `formula:name` / `cask:name`.
    pub fn key(&self) -> String {
        format!("{}:{}", self.kind.as_str(), self.name)
    }

    /// brew arguments that install this package.
    pub fn install_cmd(&self) -> Vec<String> {
        let mut cmd = vec!["install".to_string()];
        if self.kind == Kind::Cask {
            cmd.push("--cask".into());
        }
        cmd.push(self.full_name());
        cmd
    }

    pub fn on(&self, platform: &str) -> bool {
        self.platforms.iter().any(|p| p == platform)
    }

    pub fn in_profile(&self, profile: &str) -> bool {
        self.profiles.iter().any(|p| p == profile)
    }

    /// True when the item is listed under `category` (its own or one of its extra groups).
    pub fn in_category(&self, category: &str) -> bool {
        self.category == category || self.groups.iter().any(|g| g == category)
    }

    /// Lower-case text that searches match against: name, description, category and tags.
    pub fn haystack(&self) -> String {
        let mut hay = format!("{} {} {}", self.name, self.desc, self.category);
        for t in &self.tags {
            hay.push(' ');
            hay.push_str(t);
        }
        hay.to_lowercase()
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct Kit {
    pub name: String,
    pub desc: String,
    pub profile: String,
    pub keys: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct Raw {
    items: Vec<Item>,
    kits: Vec<Kit>,
    #[serde(deserialize_with = "ordered_map")]
    profile_categories: Vec<(String, Vec<String>)>,
    essentials: HashMap<String, Vec<String>>,
}

/// A JSON object as a list of pairs, keeping the order of the file (the order of the profiles matters).
fn ordered_map<'de, D: Deserializer<'de>>(d: D) -> Result<Vec<(String, Vec<String>)>, D::Error> {
    struct V;
    impl<'de> serde::de::Visitor<'de> for V {
        type Value = Vec<(String, Vec<String>)>;
        fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
            f.write_str("an object of string lists")
        }
        fn visit_map<A: serde::de::MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
            let mut out = Vec::new();
            while let Some(entry) = map.next_entry::<String, Vec<String>>()? {
                out.push(entry);
            }
            Ok(out)
        }
    }
    d.deserialize_map(V)
}

/// The whole catalog, parsed once.
#[derive(Debug)]
pub struct Catalog {
    pub items: Vec<Item>,
    pub kits: Vec<Kit>,
    pub profile_categories: Vec<(String, Vec<String>)>,
    pub essentials: HashMap<String, Vec<String>>,
    by_key: HashMap<String, usize>,
}

const DATA: &str = include_str!("../data/catalog.json");

/// The curated catalog. Panics only if the compiled-in `data/catalog.json` is malformed, which the tests catch.
pub fn catalog() -> &'static Catalog {
    static CATALOG: OnceLock<Catalog> = OnceLock::new();
    CATALOG.get_or_init(|| Catalog::parse(DATA).expect("data/catalog.json is valid"))
}

fn slug(text: &str) -> String {
    let spaced: String = text.to_lowercase().chars().map(|c| if c.is_alphanumeric() { c } else { ' ' }).collect();
    spaced.split_whitespace().collect::<Vec<_>>().join("-")
}

impl Catalog {
    pub fn parse(json: &str) -> Result<Catalog, serde_json::Error> {
        let raw: Raw = serde_json::from_str(json)?;
        let by_key = raw.items.iter().enumerate().map(|(i, it)| (it.key(), i)).collect();
        Ok(Catalog { items: raw.items, kits: raw.kits, profile_categories: raw.profile_categories, essentials: raw.essentials, by_key })
    }

    /// Item by `kind:name`.
    pub fn by_key(&self, key: &str) -> Option<&Item> {
        self.by_key.get(key).map(|&i| &self.items[i])
    }

    /// Categories shown for a profile (all of them when `profile` is None), without repeats.
    pub fn categories(&self, profile: Option<&str>) -> Vec<&str> {
        let mut out: Vec<&str> = Vec::new();
        for (p, cats) in &self.profile_categories {
            if profile.is_some_and(|want| want != p) {
                continue;
            }
            for c in cats {
                if !out.contains(&c.as_str()) {
                    out.push(c);
                }
            }
        }
        out
    }

    pub fn essentials_for(&self, profile: &str) -> &[String] {
        self.essentials.get(profile).map(Vec::as_slice).unwrap_or(&[])
    }

    /// Curated items matching every word of `query` (name, description, category, tags), sorted by name.
    pub fn find_items(&self, query: &str, profile: Option<&str>, platform: Option<&str>, category: Option<&str>) -> Vec<&Item> {
        let words: Vec<String> = query.to_lowercase().split_whitespace().map(String::from).collect();
        let mut out: Vec<&Item> = self
            .items
            .iter()
            .filter(|i| profile.is_none_or(|p| i.in_profile(p)))
            .filter(|i| platform.is_none_or(|p| i.on(p)))
            .filter(|i| category.is_none_or(|c| i.in_category(c)))
            .filter(|i| {
                let hay = i.haystack();
                words.iter().all(|w| hay.contains(w.as_str()))
            })
            .collect();
        out.sort_by(|a, b| (a.name.as_str(), a.kind.as_str()).cmp(&(b.name.as_str(), b.kind.as_str())));
        out
    }

    /// Kit by exact name or slug, or by a unique slug prefix. None when missing or ambiguous.
    pub fn find_kit(&self, name: &str) -> Option<&Kit> {
        let want = slug(name);
        if let Some(k) = self.kits.iter().find(|k| k.name.to_lowercase() == name.to_lowercase() || slug(&k.name) == want) {
            return Some(k);
        }
        if want.is_empty() {
            return None;
        }
        let mut hits = self.kits.iter().filter(|k| slug(&k.name).starts_with(&want));
        match (hits.next(), hits.next()) {
            (Some(k), None) => Some(k),
            _ => None,
        }
    }

    /// Items called `name` (`kind:name` selects one kind).
    pub fn resolve_packages(&self, name: &str) -> Vec<&Item> {
        if name.contains(':') {
            return self.by_key(name).into_iter().collect();
        }
        self.items.iter().filter(|i| i.name == name).collect()
    }

    /// The items of a kit that exist on `platform`.
    pub fn kit_items(&self, kit: &Kit, platform: &str) -> Vec<&Item> {
        kit.keys.iter().filter_map(|k| self.by_key(k)).filter(|i| i.on(platform)).collect()
    }
}

/// Lines of a Brewfile for `items`.
pub fn brewfile_lines<'a>(items: impl IntoIterator<Item = &'a Item>) -> Vec<String> {
    items.into_iter().map(|i| format!("{} \"{}\"", if i.kind == Kind::Cask { "cask" } else { "brew" }, i.full_name())).collect()
}

/// brew arguments to install `items`, batched: one command for all formulae and one for all casks.
/// A single `brew install a b c` downloads in parallel and starts brew once, which is several times faster
/// than one `brew install` per package.
pub fn install_commands<'a>(items: impl IntoIterator<Item = &'a Item>) -> Vec<Vec<String>> {
    let (mut formulae, mut casks) = (Vec::new(), Vec::new());
    for i in items {
        match i.kind {
            Kind::Formula => formulae.push(i.full_name()),
            Kind::Cask => casks.push(i.full_name()),
        }
    }
    let mut cmds = Vec::new();
    if !formulae.is_empty() {
        cmds.push(["install".to_string()].into_iter().chain(formulae).collect());
    }
    if !casks.is_empty() {
        cmds.push(["install".to_string(), "--cask".to_string()].into_iter().chain(casks).collect());
    }
    cmds
}
