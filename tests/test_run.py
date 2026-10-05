import importlib
import sys


def test_run_module_does_not_start_r2_outside_reloader_child(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    sys.modules.pop("run", None)

    run = importlib.import_module("run")

    assert run.app.config["R2_LINK"].state()[0] == "stopped"
