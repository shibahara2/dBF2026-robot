import requests


class TurnReporter:
    """Sends each voice turn to the app's debug log; never raises."""

    def __init__(self, base_url, timeout=2.0):
        self._base_url = base_url
        self._timeout = timeout

    def report(self, turn):
        try:
            resp = requests.post(
                f"{self._base_url}/api/voice/turns", json=turn, timeout=self._timeout
            )
        except requests.exceptions.RequestException:
            return False
        return resp.status_code == 202
