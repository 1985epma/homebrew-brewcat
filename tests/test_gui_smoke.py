"""Opens the real window (skipped when there is no display, e.g. a headless Linux box without xvfb)."""
import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def window():
    import app
    try:
        win = app.App()
    except tk.TclError as exc:
        pytest.skip(f"no display: {exc}")
    win.update()
    yield win
    win.destroy()


def test_every_profile_and_category_renders(window):
    import app
    for label, _ in app.PROFILES:
        window.profile.set(label)
        window._on_profile()
        for cat in window.cat_entries:
            window.category = cat
            window.refresh()
    window.profile.set("All")
    window._on_profile()
    assert len(window.tree.get_children()) > 0


def test_help_and_about_open(window):
    window.show_help()
    window.show_about()
    window.update()
    assert len([w for w in window.winfo_children() if w.winfo_class() == "Toplevel"]) == 2


def test_search_filters_the_list(window):
    window.category = "★ All"
    window.search.set("terraform")
    window.refresh()
    names = [window.tree.item(i)["values"][1] for i in window.tree.get_children()]
    assert "terraform" in names and "git" not in names
