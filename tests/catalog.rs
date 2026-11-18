//! Structure and lookups of the curated catalog (the data is `data/catalog.json`).

use std::collections::HashSet;

use brewcat::catalog::*;
use regex::Regex;

fn key(k: &str) -> &'static Item {
    catalog().by_key(k).unwrap_or_else(|| panic!("missing {k}"))
}

fn names(items: &[&Item]) -> Vec<String> {
    items.iter().map(|i| i.name.clone()).collect()
}

#[test]
fn no_duplicate_keys() {
    let cat = catalog();
    let keys: HashSet<String> = cat.items.iter().map(Item::key).collect();
    assert_eq!(keys.len(), cat.items.len(), "duplicate kind:name keys");
}

#[test]
fn item_fields_are_sane() {
    let name = Regex::new(r"^[a-z0-9][a-z0-9@._+-]*$").unwrap();
    for i in &catalog().items {
        let k = i.key();
        assert!(name.is_match(&i.name), "{k}");
        assert!(!i.desc.trim().is_empty(), "{k}");
        assert!(!i.profiles.is_empty() && !i.platforms.is_empty(), "{k}");
        if i.kind == Kind::Cask {
            assert_eq!(i.platforms, [MAC], "casks are macOS only: {k}");
        }
        if !i.tap.is_empty() {
            assert_eq!(i.tap.matches('/').count(), 1, "{k}");
        }
    }
}

#[test]
fn kits_reference_existing_items_and_are_usable() {
    let cat = catalog();
    let kit_names: HashSet<&str> = cat.kits.iter().map(|k| k.name.as_str()).collect();
    assert_eq!(kit_names.len(), cat.kits.len(), "kit names must be unique");
    for kit in &cat.kits {
        assert!(!kit.keys.is_empty(), "{}", kit.name);
        for k in &kit.keys {
            assert!(cat.by_key(k).is_some(), "{}: unknown {k}", kit.name);
        }
        let unique: HashSet<&String> = kit.keys.iter().collect();
        assert_eq!(unique.len(), kit.keys.len(), "{}: repeated package", kit.name);
        assert!(cat.essentials.contains_key(&kit.profile), "{}", kit.name);
    }
}

#[test]
fn every_profile_has_categories_items_and_essentials() {
    let cat = catalog();
    for (slug, profile) in PROFILE_SLUGS {
        let cats = cat.categories(Some(profile));
        assert!(!cats.is_empty(), "{slug}");
        assert!(cat.essentials.contains_key(profile), "{slug}");
        assert!(cat.items.iter().any(|i| i.in_profile(profile)), "{slug}");
        for c in cats {
            assert!(cat.items.iter().any(|i| i.in_category(c) && i.in_profile(profile)), "{slug}: empty category {c}");
        }
        for k in cat.essentials_for(profile) {
            assert!(cat.by_key(k).is_some(), "{slug}: essential {k} missing");
        }
    }
}

#[test]
fn every_profile_id_used_by_an_item_is_known() {
    let known: HashSet<&str> = PROFILE_SLUGS.iter().map(|(_, id)| *id).collect();
    for i in &catalog().items {
        for p in &i.profiles {
            assert!(known.contains(p.as_str()), "{}: unknown profile {p}", i.key());
        }
    }
}

#[test]
fn find_items_and_kits() {
    let cat = catalog();
    assert!(cat.find_items("terraform", Some(SRE), Some(MAC), None).iter().any(|i| i.name == "terraform"));
    assert!(cat.find_items("zzzzzz-nothing", None, None, None).is_empty());
    assert_eq!(cat.find_kit("git pro").unwrap().name, "Git Pro");
    assert_eq!(cat.find_kit("terraform").unwrap().name, "Terraform + AWS"); // unique prefix
    assert!(cat.find_kit("no such kit").is_none());
    assert!(cat.find_kit("").is_none());
}

#[test]
fn find_items_is_sorted_by_name_then_kind() {
    let items = catalog().find_items("", None, None, None);
    let keys: Vec<(&str, &str)> = items.iter().map(|i| (i.name.as_str(), i.kind.as_str())).collect();
    let mut sorted = keys.clone();
    sorted.sort();
    assert_eq!(keys, sorted);
}

#[test]
fn install_cmd_uses_full_name_for_taps_and_cask_flag() {
    assert_eq!(key("formula:terraform").install_cmd(), ["install", "hashicorp/tap/terraform"]);
    assert_eq!(key("cask:obs").install_cmd(), ["install", "--cask", "obs"]);
}

#[test]
fn brewfile_lines_use_brew_and_cask() {
    let items = [key("formula:jq"), key("cask:obs"), key("formula:terraform")];
    assert_eq!(brewfile_lines(items), ["brew \"jq\"", "cask \"obs\"", "brew \"hashicorp/tap/terraform\""]);
}

#[test]
fn install_commands_batch_formulae_and_casks() {
    let items = ["formula:jq", "formula:git", "cask:obs", "cask:vlc", "formula:terraform"].map(key);
    assert_eq!(
        install_commands(items),
        vec![vec!["install", "jq", "git", "hashicorp/tap/terraform"], vec!["install", "--cask", "obs", "vlc"]]
    );
    assert!(install_commands([]).is_empty());
    assert_eq!(install_commands([key("cask:obs")]), vec![vec!["install", "--cask", "obs"]]);
}

#[test]
fn resolve_packages_handles_kinds() {
    let cat = catalog();
    assert_eq!(cat.resolve_packages("cask:obs").len(), 1);
    assert!(cat.resolve_packages("cask:no-such-thing").is_empty());
    assert!(!cat.resolve_packages("jq").is_empty());
}

#[test]
fn labs_products() {
    let cat = catalog();
    let labs = cat.find_items("", Some(LABS), None, None);
    let mut got = names(&labs);
    got.sort();
    assert_eq!(got, ["117terminal", "epma-system-data", "epma-windows-usb-creator", "k8scli", "terminal117"]);
    for i in &labs {
        assert!(!i.tap.is_empty() && i.homepage.starts_with("https://github.com/1985epma/"), "{}", i.name);
        assert_eq!(i.install_cmd().last().unwrap(), &format!("{}/{}", i.tap, i.name));
    }
    assert_eq!(
        cat.find_kit("117-labs").unwrap().keys,
        ["formula:k8scli", "formula:epma-windows-usb-creator", "cask:117terminal", "formula:terminal117", "formula:epma-system-data"]
    );
    // 117Terminal is a cask on macOS and a formula on Linux; System Data is macOS only.
    let mut mac = names(&cat.find_items("", Some(LABS), Some(MAC), None));
    mac.sort();
    assert_eq!(mac, ["117terminal", "epma-system-data", "epma-windows-usb-creator", "k8scli"]);
    let mut linux = names(&cat.find_items("", Some(LABS), Some(LINUX), None));
    linux.sort();
    assert_eq!(linux, ["epma-windows-usb-creator", "k8scli", "terminal117"]);
}

#[test]
fn profile_slugs_map_to_ids() {
    assert_eq!(profile_for_slug("117-labs"), Some(LABS));
    assert_eq!(profile_for_slug("bogus"), None);
    let slugs = profile_slugs();
    let mut sorted = slugs.clone();
    sorted.sort();
    assert_eq!(slugs, sorted);
}
