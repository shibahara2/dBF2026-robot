import requests


class PFClient:
    def __init__(self, base_url, timeout, api_key="", proxy_url=""):
        self._base_url = base_url
        self._timeout = timeout
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key
        self._proxies = (
            {"http": proxy_url, "https": proxy_url} if proxy_url else None
        )

    def get_guide_robot_status(self):
        try:
            resp = requests.get(
                f"{self._base_url}/api/v1/guide-robot/status",
                headers=self._headers,
                proxies=self._proxies,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout:
            return "timeout"
        except requests.exceptions.RequestException:
            return "fatal_error"

        if resp.status_code == 422:
            return "retryable_error"
        if resp.status_code != 200:
            return "fatal_error"

        try:
            status = resp.json().get("status")
        except (ValueError, AttributeError):
            return "fatal_error"

        if status == "Ready":
            return "ready"
        if status == "Initializing":
            return "initializing"
        return "fatal_error"

    def post_drink_placed(self):
        try:
            resp = requests.post(
                f"{self._base_url}/api/v1/drink/placed",
                headers=self._headers,
                json={"result": "success"},
                proxies=self._proxies,
                timeout=self._timeout,
            )
        except requests.exceptions.RequestException:
            return False

        if resp.status_code != 200:
            return False
        try:
            return resp.json().get("accepted") is True
        except (ValueError, AttributeError):
            return False
