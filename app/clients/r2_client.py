import requests


class R2Client:
    def __init__(self, base_url, timeout, drink_type="water", target_robot_id="temi"):
        self._base_url = base_url
        self._timeout = timeout
        self._drink_type = drink_type
        self._target_robot_id = target_robot_id

    def get_status(self):
        try:
            resp = requests.get(
                f"{self._base_url}/v1/commands/load-drink/status", timeout=self._timeout
            )
        except requests.exceptions.Timeout:
            return {"outcome": "timeout", "request_id": None}
        except requests.exceptions.RequestException:
            return {"outcome": "fatal_error", "request_id": None}

        if resp.status_code != 200:
            return {"outcome": "fatal_error", "request_id": None}

        try:
            body = resp.json()
            request_id = body.get("request_id")
            status = body.get("status")
        except (ValueError, AttributeError):
            return {"outcome": "fatal_error", "request_id": None}
        if status in ("loading", "returning", "completed", "failed"):
            return {"outcome": status, "request_id": request_id}
        return {"outcome": "fatal_error", "request_id": request_id}

    def post_load_drink(self, request_id):
        payload = {
            "request_id": request_id,
            "drink_type": self._drink_type,
            "target_robot_id": self._target_robot_id,
        }
        try:
            resp = requests.post(
                f"{self._base_url}/v1/commands/load-drink",
                json=payload,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout:
            return "timeout"
        except requests.exceptions.RequestException:
            return "server_error"

        if resp.status_code == 200:
            return "accepted"
        if resp.status_code == 422:
            return "validation_error"
        return "server_error"
