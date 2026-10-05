import time

import requests

STATUS_PATH = "/api/v1/guide-robot/status"
DRINK_PLACED_PATH = "/api/v1/drink/placed"
DRINK_PLACED_BODY = {"result": "success"}


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
                f"{self._base_url}{STATUS_PATH}",
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
        # The real PF spells it "Initialising"; the mock and spec use "Initializing".
        if status in ("Initializing", "Initialising"):
            return "initializing"
        return "fatal_error"

    def post_drink_placed(self):
        try:
            resp = requests.post(
                f"{self._base_url}{DRINK_PLACED_PATH}",
                headers=self._headers,
                json=DRINK_PLACED_BODY,
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

    # Manual calls from the debug page: report the response as it came,
    # without reading it the way the state machine does.
    def raw_get_status(self):
        return self._raw("GET", STATUS_PATH)

    def raw_post_drink_placed(self):
        return self._raw("POST", DRINK_PLACED_PATH, DRINK_PLACED_BODY)

    def _raw(self, method, path, body=None):
        url = f"{self._base_url}{path}"
        result = {
            "method": method,
            "url": url,
            "request_body": body,
            "status_code": None,
            "body": None,
            "elapsed_ms": None,
            "error": None,
        }
        started = time.monotonic()
        try:
            resp = requests.request(
                method,
                url,
                headers=self._headers,
                json=body,
                proxies=self._proxies,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            result["error"] = f"timeout: {exc}"
        except requests.exceptions.ConnectionError as exc:
            result["error"] = f"connection_error: {exc}"
        except requests.exceptions.RequestException as exc:
            result["error"] = f"request_error: {exc}"
        else:
            result["status_code"] = resp.status_code
            result["body"] = resp.text
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        return result
