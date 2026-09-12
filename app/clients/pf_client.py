import requests


class PFClient:
    def __init__(self, base_url, timeout):
        self._base_url = base_url
        self._timeout = timeout

    def get_guide_robot_status(self):
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/guide-robot/status", timeout=self._timeout
            )
        except requests.exceptions.Timeout:
            return "timeout"
        except requests.exceptions.RequestException:
            return "fatal_error"

        if resp.status_code == 422:
            return "retryable_error"
        if resp.status_code != 200:
            return "fatal_error"

        status = resp.json().get("status")
        if status == "Ready":
            return "ready"
        if status == "Initializing":
            return "initializing"
        return "fatal_error"

    def post_drink_placed(self):
        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/drink/placed", timeout=self._timeout
            )
        except requests.exceptions.RequestException:
            return False

        if resp.status_code != 200:
            return False
        return resp.json().get("accepted") is True
