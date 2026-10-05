import pytest
from flask import Flask

from app.routes.r2_debug import r2_debug_bp


class FakeController:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def snapshot(self):
        return {"status": "completed", "connection": "connected"}

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        return self.result

    def connect(self):
        return self._call("connect")

    def disconnect(self):
        return self._call("disconnect")

    def stop(self):
        return self._call("stop")

    def reset(self):
        return self._call("reset")

    def mark(self, status):
        return self._call("mark", status)

    def resend_start(self):
        return self._call("resend_start")


class FakeRunner:
    def __init__(self, can_resume=True):
        self.can_resume = can_resume
        self.resume_calls = 0

    def can_resume_after_start(self):
        return self.can_resume

    def request_resume_after_start(self):
        self.resume_calls += 1
        return True


def make_client(controller, runner=None):
    app = Flask(__name__)
    app.config["R2_CONTROLLER"] = controller
    app.config["STATE_MACHINE_RUNNER"] = runner or FakeRunner()
    app.register_blueprint(r2_debug_bp)
    return app.test_client()


def test_get_returns_snapshot():
    resp = make_client(FakeController()).get("/api/debug/r2")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "completed", "connection": "connected"}


@pytest.mark.parametrize("action", ["connect", "disconnect", "stop", "reset"])
def test_simple_actions(action):
    controller = FakeController()
    resp = make_client(controller).post(f"/api/debug/r2/{action}")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"
    assert controller.calls == [(action,)]


def test_refused_action_returns_409_with_reason():
    controller = FakeController(result="R2に接続していません")

    resp = make_client(controller).post("/api/debug/r2/stop")

    assert resp.status_code == 409
    assert resp.get_json() == {"message": "R2に接続していません"}


def test_mark_passes_status():
    controller = FakeController()

    resp = make_client(controller).post("/api/debug/r2/mark", json={"status": "returning"})

    assert resp.status_code == 200
    assert controller.calls == [("mark", "returning")]


def test_mark_requires_status():
    resp = make_client(FakeController()).post("/api/debug/r2/mark", json={})

    assert resp.status_code == 422


def test_resend_resumes_the_state_machine():
    controller = FakeController()
    runner = FakeRunner()

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 200
    assert controller.calls == [("resend_start",)]
    assert runner.resume_calls == 1


def test_resend_rejected_unless_state_machine_stopped_at_start():
    controller = FakeController()
    runner = FakeRunner(can_resume=False)

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 409
    assert controller.calls == []
    assert runner.resume_calls == 0


def test_failed_resend_does_not_resume():
    controller = FakeController(result="R2から開始の返事がありませんでした")
    runner = FakeRunner()

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 409
    assert runner.resume_calls == 0
