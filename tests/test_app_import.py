import pytest

pytest.importorskip("tkinter")


def test_importing_app_has_no_side_effects():
    import sys
    sys.argv = ["brewcat", "--definitely-not-a-flag"]  # would exit(2) if import parsed arguments
    import app
    assert callable(app.main)
