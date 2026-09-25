import json
import threading
import unicodedata

STATUS_RESERVED = "reserved"
STATUS_CHECKED_IN = "checked_in"

_WHITESPACE = " \t　"


def _normalize_name(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    for ch in _WHITESPACE:
        normalized = normalized.replace(ch, "")
    return normalized.casefold()


def _normalize_number(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if ch.isalnum()).upper()


def _normalize_phone(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(ch for ch in normalized if ch.isdigit())


class ReservationStore:
    """Read-only reservation directory seeded from a JSON file.

    Checking in never writes back here, so ``status`` always reflects the seed
    data and the same reservation can be checked in repeatedly.
    """

    def __init__(self, reservations):
        self._lock = threading.Lock()
        self._reservations = []
        for raw in reservations:
            record = dict(raw)
            record.setdefault("status", STATUS_RESERVED)
            self._reservations.append(record)

    @classmethod
    def from_file(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data["reservations"])

    def all(self):
        with self._lock:
            return [dict(record) for record in self._reservations]

    def get(self, reservation_id):
        with self._lock:
            for record in self._reservations:
                if record["reservation_id"] == reservation_id:
                    return dict(record)
        return None

    def search(self, query):
        """Return reservations matching a name, reservation number or phone.

        Exact matches win; only when nothing matches exactly do we fall back to
        a partial name match, so a full name never drags in unrelated guests.
        """
        name_key = _normalize_name(query)
        number_key = _normalize_number(query)
        phone_key = _normalize_phone(query)
        if not name_key:
            return []

        exact = []
        partial = []
        for record in self.all():
            if self._matches_exactly(record, name_key, number_key, phone_key):
                exact.append(record)
            elif self._matches_partially(record, name_key):
                partial.append(record)
        return exact or partial

    @staticmethod
    def _matches_exactly(record, name_key, number_key, phone_key):
        if number_key and _normalize_number(record.get("reservation_number")) == number_key:
            return True
        if phone_key and _normalize_phone(record.get("phone")) == phone_key:
            return True
        for field in ("guest_name", "guest_name_kana"):
            if _normalize_name(record.get(field)) == name_key:
                return True
        return False

    @staticmethod
    def _matches_partially(record, name_key):
        for field in ("guest_name", "guest_name_kana"):
            value = _normalize_name(record.get(field))
            if value and name_key in value:
                return True
        return False

