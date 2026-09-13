import json
import requests


class CheckinClient:
    def __init__(self, base_url, timeout=5.0):
        self._base_url = base_url
        self._timeout = timeout

    def checkin(self, name: str) -> str:
        try:
            resp = requests.post(
                f"{self._base_url}/api/checkin",
                data=json.dumps({"name": name}, ensure_ascii=False).encode('utf-8'),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout:
            return "timeout"
        except requests.exceptions.RequestException:
            return "connection_error"

        if resp.status_code == 200:
            return "accepted"
        if resp.status_code == 409:
            return "already_in_progress"
        if resp.status_code == 422:
            return "validation_error"
        return "server_error"
