from flask import Flask

from app.routes.checkin import checkin_bp


class FakeRunner:
    def __init__(self, checkin_result=True, reset_result=True):
        self.checkin_result = checkin_result
        self.reset_result = reset_result
        self.checkin_calls = []
        self.reset_calls = 0

    def request_checkin(self, name):
        self.checkin_calls.append(name)
        return self.checkin_result

    def request_reset(self):
        self.reset_calls += 1
        return self.reset_result


def make_client(runner):
    app = Flask(__name__)
    app.config["STATE_MACHINE_RUNNER"] = runner
    app.register_blueprint(checkin_bp)
    return app.test_client()


def test_checkin_accepted():
    runner = FakeRunner(checkin_result=True)
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"name": "Tanaka"})

    assert resp.status_code == 200
    assert runner.checkin_calls == ["Tanaka"]


def test_checkin_rejected_when_cycle_in_progress():
    runner = FakeRunner(checkin_result=False)
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"name": "Tanaka"})

    assert resp.status_code == 409


def test_checkin_requires_name():
    runner = FakeRunner()
    client = make_client(runner)

    resp = client.post("/api/checkin", json={})

    assert resp.status_code == 422
    assert runner.checkin_calls == []


def test_reset_accepted():
    runner = FakeRunner(reset_result=True)
    client = make_client(runner)

    resp = client.post("/api/reset")

    assert resp.status_code == 200
    assert runner.reset_calls == 1


def test_reset_rejected_when_not_in_error():
    runner = FakeRunner(reset_result=False)
    client = make_client(runner)

    resp = client.post("/api/reset")

    assert resp.status_code == 409
