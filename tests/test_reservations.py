import json

import pytest

from app.reservations import STATUS_CHECKED_IN, STATUS_RESERVED, ReservationStore

RECORDS = [
    {
        "reservation_id": "RSV-0001",
        "reservation_number": "DBF-1001",
        "guest_name": "田中太郎",
        "guest_name_kana": "タナカタロウ",
        "phone": "090-1234-5678",
    },
    {
        "reservation_id": "RSV-0002",
        "reservation_number": "DBF-1002",
        "guest_name": "田中太郎",
        "guest_name_kana": "タナカタロウ",
        "phone": "080-2222-3333",
    },
    {
        "reservation_id": "RSV-0003",
        "reservation_number": "DBF-1003",
        "guest_name": "鈴木翔太",
        "guest_name_kana": "スズキショウタ",
        "phone": "070-4444-5555",
    },
]


@pytest.fixture
def store():
    return ReservationStore(RECORDS)


def ids(reservations):
    return [r["reservation_id"] for r in reservations]


def test_defaults_to_reserved(store):
    assert store.get("RSV-0001")["status"] == STATUS_RESERVED


def test_search_by_reservation_number(store):
    assert ids(store.search("DBF-1003")) == ["RSV-0003"]


def test_search_by_reservation_number_ignores_case_and_hyphen(store):
    assert ids(store.search("dbf1003")) == ["RSV-0003"]


def test_search_by_phone(store):
    assert ids(store.search("090-1234-5678")) == ["RSV-0001"]


def test_search_by_phone_without_hyphens(store):
    assert ids(store.search("09012345678")) == ["RSV-0001"]


def test_search_by_name_returns_every_namesake(store):
    assert ids(store.search("田中太郎")) == ["RSV-0001", "RSV-0002"]


def test_search_by_name_ignores_spaces(store):
    assert ids(store.search(" 田中　太郎 ")) == ["RSV-0001", "RSV-0002"]


def test_search_by_kana(store):
    assert ids(store.search("スズキショウタ")) == ["RSV-0003"]


def test_search_falls_back_to_partial_name(store):
    assert ids(store.search("鈴木")) == ["RSV-0003"]


def test_exact_match_wins_over_partial():
    store = ReservationStore(
        [
            {"reservation_id": "A", "guest_name": "田中"},
            {"reservation_id": "B", "guest_name": "田中太郎"},
        ]
    )

    assert ids(store.search("田中")) == ["A"]


def test_search_returns_empty_for_unknown_query(store):
    assert store.search("存在しない予約") == []


def test_search_returns_empty_for_blank_query(store):
    assert store.search("   ") == []


def test_search_result_is_a_copy(store):
    store.search("DBF-1001")[0]["guest_name"] = "改ざん"

    assert store.get("RSV-0001")["guest_name"] == "田中太郎"


def test_mark_checked_in(store):
    assert store.mark_checked_in("RSV-0001") is True
    assert store.get("RSV-0001")["status"] == STATUS_CHECKED_IN


def test_mark_checked_in_twice_is_rejected(store):
    store.mark_checked_in("RSV-0001")

    assert store.mark_checked_in("RSV-0001") is False


def test_mark_checked_in_unknown_id(store):
    assert store.mark_checked_in("RSV-9999") is False


def test_reset_status(store):
    store.mark_checked_in("RSV-0001")

    assert store.reset_status("RSV-0001") is True
    assert store.get("RSV-0001")["status"] == STATUS_RESERVED


def test_get_unknown_id(store):
    assert store.get("RSV-9999") is None


def test_from_file(tmp_path):
    path = tmp_path / "reservations.json"
    path.write_text(json.dumps({"reservations": RECORDS}, ensure_ascii=False), "utf-8")

    store = ReservationStore.from_file(str(path))

    assert ids(store.search("DBF-1002")) == ["RSV-0002"]
