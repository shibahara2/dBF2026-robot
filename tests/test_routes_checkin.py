from flask import Flask

from app.reservations import STATUS_RESERVED, ReservationStore
from app.routes.checkin import checkin_bp

RECORDS = [
    {
        "reservation_id": "RSV-0001",
        "reservation_number": "DBF-1001",
        "guest_name": "田中太郎",
        "guest_name_kana": "タナカタロウ",
        "phone": "090-1234-5678",
        "room_number": "1203",
        "plan": "スタンダードツイン / 朝食付き",
        "check_in_date": "2026-09-25",
        "check_out_date": "2026-09-27",
        "nights": 2,
        "guests": 2,
    },
    {
        "reservation_id": "RSV-0002",
        "reservation_number": "DBF-1002",
        "guest_name": "田中太郎",
        "guest_name_kana": "タナカタロウ",
        "phone": "080-2222-3333",
        "room_number": "0805",
        "plan": "デラックスダブル / 素泊まり",
        "check_in_date": "2026-09-25",
        "check_out_date": "2026-09-26",
        "nights": 1,
        "guests": 1,
    },
]


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


def make_client(runner, store=None):
    app = Flask(__name__)
    app.config["STATE_MACHINE_RUNNER"] = runner
    app.config["RESERVATION_STORE"] = store or ReservationStore(RECORDS)
    app.register_blueprint(checkin_bp)
    return app.test_client()


def search(client, query):
    return client.post("/api/reservations/search", json={"query": query})


def test_search_returns_single_match():
    client = make_client(FakeRunner())

    resp = search(client, "DBF-1001")

    assert resp.status_code == 200
    reservations = resp.get_json()["reservations"]
    assert [r["reservation_id"] for r in reservations] == ["RSV-0001"]


def test_search_returns_every_namesake():
    client = make_client(FakeRunner())

    resp = search(client, "田中太郎")

    reservations = resp.get_json()["reservations"]
    assert [r["reservation_id"] for r in reservations] == ["RSV-0001", "RSV-0002"]


def test_search_by_phone():
    client = make_client(FakeRunner())

    resp = search(client, "080-2222-3333")

    assert [r["reservation_id"] for r in resp.get_json()["reservations"]] == ["RSV-0002"]


def test_search_with_no_match_returns_empty_list():
    client = make_client(FakeRunner())

    resp = search(client, "存在しない予約")

    assert resp.status_code == 200
    assert resp.get_json()["reservations"] == []


def test_search_requires_query():
    client = make_client(FakeRunner())

    resp = search(client, "   ")

    assert resp.status_code == 422


def test_search_masks_phone_number():
    client = make_client(FakeRunner())

    reservation = search(client, "DBF-1001").get_json()["reservations"][0]

    assert reservation["phone_masked"] == "090****5678"
    assert "phone" not in reservation


def test_checkin_by_reservation_id():
    runner = FakeRunner(checkin_result=True)
    store = ReservationStore(RECORDS)
    client = make_client(runner, store)

    resp = client.post("/api/checkin", json={"reservation_id": "RSV-0002"})

    assert resp.status_code == 200
    assert runner.checkin_calls == ["田中太郎"]
    assert resp.get_json()["reservation"]["room_number"] == "0805"


def test_checkin_with_unknown_reservation_id():
    runner = FakeRunner()
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"reservation_id": "RSV-9999"})

    assert resp.status_code == 404
    assert runner.checkin_calls == []


def test_checkin_leaves_reservation_status_untouched():
    runner = FakeRunner(checkin_result=True)
    store = ReservationStore(RECORDS)
    client = make_client(runner, store)

    resp = client.post("/api/checkin", json={"reservation_id": "RSV-0001"})

    assert resp.get_json()["reservation"]["status"] == STATUS_RESERVED
    assert store.get("RSV-0001")["status"] == STATUS_RESERVED


def test_same_reservation_can_check_in_again():
    runner = FakeRunner(checkin_result=True)
    store = ReservationStore(RECORDS)
    client = make_client(runner, store)

    client.post("/api/checkin", json={"reservation_id": "RSV-0001"})
    second = client.post("/api/checkin", json={"reservation_id": "RSV-0001"})

    assert second.status_code == 200
    assert runner.checkin_calls == ["田中太郎", "田中太郎"]


def test_checkin_by_reservation_rejected_when_cycle_in_progress():
    runner = FakeRunner(checkin_result=False)
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"reservation_id": "RSV-0001"})

    assert resp.status_code == 409


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
