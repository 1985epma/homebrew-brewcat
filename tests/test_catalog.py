import re
from collections import Counter

import catalog_data as cd

NAME = re.compile(r"^[a-z0-9][a-z0-9@._+-]*$")


def test_no_duplicate_keys():
    dupes = [k for k, n in Counter(i.key for i in cd.ITEMS).items() if n > 1]
    assert not dupes


def test_item_fields_are_sane():
    for i in cd.ITEMS:
        assert NAME.match(i.name), i.key
        assert i.kind in ("formula", "cask"), i.key
        assert i.desc.strip(), i.key
        assert i.profiles and i.platforms, i.key
        if i.kind == "cask":
            assert i.platforms == (cd.MAC,), f"casks are macOS only: {i.key}"
        if i.tap:
            assert i.tap.count("/") == 1, i.key


def test_kits_reference_existing_items_and_are_usable():
    names = [k.name for k in cd.KITS]
    assert len(names) == len(set(names)), "kit names must be unique"
    for kit in cd.KITS:
        assert kit.keys, kit.name
        for key in kit.keys:
            assert key in cd.BY_KEY, f"{kit.name}: unknown {key}"
        assert len(set(kit.keys)) == len(kit.keys), f"{kit.name}: repeated package"
        assert kit.profile in cd.ESSENTIALS, kit.name


def test_every_profile_has_categories_items_and_essentials():
    for slug, profile in cd.PROFILE_SLUGS.items():
        assert profile in cd.PROFILE_CATEGORIES, slug
        assert profile in cd.ESSENTIALS, slug
        assert any(profile in i.profiles for i in cd.ITEMS), slug
        for cat in cd.PROFILE_CATEGORIES[profile]:
            assert any((i.category == cat or cat in i.groups) and profile in i.profiles for i in cd.ITEMS), \
                f"{slug}: empty category {cat}"
        for key in cd.ESSENTIALS[profile]:
            assert key in cd.BY_KEY, f"{slug}: essential {key} missing"


def test_find_items_and_kits():
    assert any(i.name == "terraform" for i in cd.find_items("terraform", cd.SRE, cd.MAC))
    assert not cd.find_items("zzzzzz-nothing")
    assert cd.find_kit("git pro").name == "Git Pro"
    assert cd.find_kit("terraform").name == "Terraform + AWS"  # unique prefix
    assert cd.find_kit("no such kit") is None


def test_install_cmd_uses_full_name_for_taps_and_cask_flag():
    assert cd.BY_KEY["formula:terraform"].install_cmd == ["install", "hashicorp/tap/terraform"]
    assert cd.BY_KEY["cask:obs"].install_cmd == ["install", "--cask", "obs"]


def test_brewfile_lines():
    items = [cd.BY_KEY["formula:jq"], cd.BY_KEY["cask:obs"], cd.BY_KEY["formula:terraform"]]
    assert cd.brewfile_lines(items) == ['brew "jq"', 'cask "obs"', 'brew "hashicorp/tap/terraform"']


def test_install_commands_batch_formulae_and_casks():
    items = [cd.BY_KEY[k] for k in ("formula:jq", "formula:git", "cask:obs", "cask:vlc", "formula:terraform")]
    assert cd.install_commands(items) == [
        ["install", "jq", "git", "hashicorp/tap/terraform"],
        ["install", "--cask", "obs", "vlc"],
    ]
    assert cd.install_commands([]) == []
    assert cd.install_commands([cd.BY_KEY["cask:obs"]]) == [["install", "--cask", "obs"]]


def test_117_labs_products():
    labs = cd.find_items(profile=cd.LABS)
    assert sorted(i.name for i in labs) == ["epma-windows-usb-creator", "k8scli"]
    for i in labs:
        assert i.tap and i.homepage.startswith("https://github.com/1985epma/")
        assert i.install_cmd[-1] == f"{i.tap}/{i.name}"
    assert cd.find_kit("117-labs").keys == ("formula:k8scli", "formula:epma-windows-usb-creator")
