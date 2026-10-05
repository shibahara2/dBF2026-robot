import os
from pathlib import Path

from dotenv import load_dotenv

from themis_video.settings import load_settings


load_dotenv(dotenv_path=Path.cwd() / ".env")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

R2_WS_URL = os.environ.get("R2_WS_URL", "ws://127.0.0.1:9002/realtime")
R2_START_REPLY_TIMEOUT_SECONDS = float(os.environ.get("R2_START_REPLY_TIMEOUT_SECONDS", "15"))
R2_WS_RECONNECT_DELAY_SECONDS = float(os.environ.get("R2_WS_RECONNECT_DELAY_SECONDS", "1"))
R2_WS_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("R2_WS_CONNECT_TIMEOUT_SECONDS", "5"))
PF_BASE_URL = os.environ.get("PF_BASE_URL", "http://localhost:5002")
PF_API_KEY = os.environ.get("PF_API_KEY", "")
PF_PROXY_URL = os.environ.get("PF_PROXY_URL", "")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))
THEMIS_VIDEO_SETTINGS = load_settings()
VISUAL_START_COOLDOWN_SECONDS = float(
    os.environ.get("VISUAL_START_COOLDOWN_SECONDS", "5")
)
ENTRY_IDLE_SECONDS = float(os.environ.get("ENTRY_IDLE_SECONDS", "60"))
RESERVATIONS_FILE = os.environ.get(
    "RESERVATIONS_FILE", os.path.join(_PROJECT_ROOT, "data", "reservations.json")
)
