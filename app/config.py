import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

R2_BASE_URL = os.environ.get("R2_BASE_URL", "http://localhost:5001")
PF_BASE_URL = os.environ.get("PF_BASE_URL", "http://localhost:5002")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))
DRINK_TYPE = os.environ.get("DRINK_TYPE", "water")
TARGET_ROBOT_ID = os.environ.get("TARGET_ROBOT_ID", "temi")
RESERVATIONS_FILE = os.environ.get(
    "RESERVATIONS_FILE", os.path.join(_PROJECT_ROOT, "data", "reservations.json")
)
