import requests


class VoiceStartClient:
    """Asks the kiosk to open its search screen (POST /api/voice/start)."""

    def __init__(self, base_url, timeout=5.0):
        self._base_url = base_url
        self._timeout = timeout

    def start(self) -> str:
        try:
            resp = requests.post(
                f"{self._base_url}/api/voice/start", json={}, timeout=self._timeout
            )
        except requests.exceptions.Timeout:
            return "timeout"
        except requests.exceptions.RequestException:
            return "connection_error"

        if resp.status_code == 202:
            return "accepted"
        if resp.status_code == 409:
            return "not_available"
        if resp.status_code == 429:
            return "rate_limited"
        return "server_error"
