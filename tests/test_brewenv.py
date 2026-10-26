import brewenv


def test_names_go_after_double_dash(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: False)
    assert brewenv.brew_command("/x/brew", "install", "--cask", "foo") == ["/x/brew", "install", "--cask", "--", "foo"]
    assert brewenv.brew_command("/x/brew", "uninstall", "bar") == ["/x/brew", "uninstall", "--", "bar"]
    assert brewenv.brew_command("/x/brew", "list", "--formula", "-1") == ["/x/brew", "list", "--formula", "-1"]


def test_option_looking_name_cannot_become_an_option(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: False)
    cmd = brewenv.brew_command("/x/brew", "install", "--cask", "good")
    assert cmd.index("--") < cmd.index("good")


def test_runs_native_arch_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: True)
    monkeypatch.setattr(brewenv.os.path, "exists", lambda p: p == "/usr/bin/arch")
    assert brewenv.brew_command("/opt/homebrew/bin/brew", "list")[:3] == ["/usr/bin/arch", "-arm64", "/opt/homebrew/bin/brew"]
    assert brewenv.brew_command("/usr/local/bin/brew", "list")[:2] == ["/usr/bin/arch", "-x86_64"]
