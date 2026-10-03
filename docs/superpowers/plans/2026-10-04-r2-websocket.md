# R2 WebSocket 直接操作 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** R2（THEMIS）の積み込み操作を、ベンダーの UI-DRP と同じ WebSocket のやり取りで Flask から直接行い、HTTP の R2 クライアントとモックを置き換える。

**Architecture:** `R2Link`（WebSocket 接続、自動再接続、MessagePack 受信）の上に `R2Controller`（UI-DRP の手順と status `completed/loading/returning/failed`）を置く。ステートマシンの R2 部分は `R2Controller.wait_until()` で状態変化を待つ形にし、AI 管制PF 部分はポーリングのまま残す。`/debug` は `R2Controller` を操作する API と、SSE の種類付きイベント `r2_state` で R2 パネルを表示する。

**Tech Stack:** Python 3.12, Flask 3.0, websocket-client 1.8（クライアント）, websockets 13.1（モックサーバー、legacy API）, msgpack 1.2.3, pytest。

**Spec:** `docs/superpowers/specs/2026-10-03-r2-websocket-design.md`

## Global Constraints

- ロボットに送る JSON は UI-DRP（`~/Linux/DRP-src/dist/assets/index-A2dmxSaZ.js`）と1文字単位で同じにする。`json.dumps(obj, separators=(",", ":"))`。
- 開始：`gamepad(button=[0]*16, combo=[0,0,1,0,0])` → 2秒 → `{"type":"play_navigation5","data":{"value":true}}`。
- STOP：`gamepad(button[8]=button[9]=1, combo=[1,0,0,0,0])` を4回 → `gamepad([0]*16, [0,0,0,0,0])` → 2秒 → `{"type":"play_navigation5","data":{"value":false}}`。
- gamepad の形：`{"type":"gamepad","data":{"button":<16>,"axis":[0,0,0,0,0,0],"combo":<5>}}`（キー順もこのとおり）。
- `under_mode` は `data.under_mode.data.data`。`_m` で split した2番目が前回から変わったときだけ判断し、`5` かつ `loading` → `returning`、`1` かつ `returning` → `completed`。
- 開始の返事の待ち時間の既定は 15 秒（`R2_START_REPLY_TIMEOUT_SECONDS`）。
- 設定：`R2_WS_URL`（既定 `ws://127.0.0.1:9002/realtime`）、`R2_START_REPLY_TIMEOUT_SECONDS`（15）、`R2_WS_RECONNECT_DELAY_SECONDS`（1）、`R2_WS_CONNECT_TIMEOUT_SECONDS`（5）。`R2_BASE_URL`、`DRINK_TYPE`、`TARGET_ROBOT_ID` は消す。
- step の名前：`waiting_r2_ready`、`starting_r2`、`waiting_r2_placed`（旧 `polling_r2_ready`、`sending_load_drink`、`polling_r2_active`）。
- ロボット本体（AOS、gamepad-server）は変えない。
- テストの実行：`.venv/bin/python -m pytest -q` に、README の「Test」節の `--ignore` 5つを付ける（GPU と音声デバイスが要るテストを除く）。この計画では `PYTEST` と書く：
  `.venv/bin/python -m pytest -q --ignore=tests/test_voice_ui_main.py --ignore=tests/test_voice_ui_tts.py --ignore=tests/test_voice_ui_vad_segmenter.py --ignore=tests/test_voice_ui_stt_transcriber.py --ignore=tests/test_integration_mocks.py`
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

1. **STOP が開始の返事待ちと重なったとき**：開始の処理は止まり、status は `failed`（`stopped`）のままで、遅れて届いた返事で `loading` に戻らないこと。→ Task 2 の `test_stop_during_start_aborts_the_start` で確かめる。
2. **切断中に `under_mode` が `_m5` を飛び越えて `_m1` になったとき**：spec では切断で `failed` になるので、つなぎ直した後の `_m1` で `completed` にならないこと。→ Task 2 の `test_disconnect_while_loading_fails_and_later_m1_is_ignored`。
3. **`_m5` → `_m1` が、ステートマシンが起きる前に続けて届いたとき**：`waiting_r2_placed` が `completed` を「置き終わった」とみなして先へ進むこと（`returning` だけを待つと永久に止まる）。→ Task 4 の `test_placed_wait_accepts_completed_after_a_quick_return`。
4. **開始の再送をステートマシンが止まっていないときに押したとき**：ロボットに何も送らずに 409 を返すこと。→ Task 5 の `test_resend_rejected_unless_state_machine_stopped_at_start`。
5. **Flask のリローダーの親プロセス**：R2 に接続しないこと（同じホストから2本つながない）。→ Task 5 の `test_run_module_does_not_start_r2_outside_reloader_child`。

---

## File Structure

| ファイル | 役割 |
|---|---|
| `app/clients/r2_link.py`（新規） | WebSocket 接続、自動再接続、手動切断、MessagePack 受信、JSON 送信 |
| `app/clients/r2_controller.py`（新規） | UI-DRP の手順、status、`under_mode` の解釈、手動操作、`wait_until` |
| `mocks/r2_realtime_mock.py`（新規） | `/realtime` のモック |
| `mocks/themis_video_mock.py`（変更） | パスで `/realtime` とそれ以外（映像）を振り分ける |
| `run_mocks.py`（変更） | PF モックと Themis WebSocket モック（:9002）を起動 |
| `app/state_machine.py`（変更） | R2 部分を `R2Controller` 待ちに。スキップを再送からの再開に |
| `app/__init__.py`（変更） | `R2Link` と `R2Controller` を組み立て、SSE に `r2_state` を流す |
| `app/config.py`、`.env.example`（変更） | R2 の設定 |
| `app/routes/r2_debug.py`（新規） | `/api/debug/r2*` |
| `app/routes/checkin.py`（変更） | スキップの API を消す |
| `app/routes/ui.py`、`app/templates/debug.html`、`app/static/debug.js`、`app/static/debug.css`（変更） | R2 パネル、シーケンス図 |
| `app/static/app.js`（変更） | step 名の対応表 |
| `run.py`（変更） | リローダーの親では R2 につながない |
| 消す | `app/clients/r2_client.py`、`mocks/r2_mock.py`、`tests/test_r2_client.py`、`tests/test_r2_mock.py`、`tests/test_integration_mocks.py` の R2 部分 |
| `README.md`、`docs/superpowers/plans/manual-e2e-check.md`（変更） | 手順 |

---

### Task 1: `R2Link`（WebSocket 接続）

**Files:**
- Create: `app/clients/r2_link.py`
- Modify: `requirements-core.txt`
- Test: `tests/test_r2_link.py`

**Interfaces:**
- Produces:
  - 定数 `STATE_CONNECTING="connecting"`, `STATE_CONNECTED="connected"`, `STATE_DISCONNECTED="disconnected"`, `STATE_STOPPED="stopped"`
  - `encode_json(obj) -> str`（空白なし JSON）
  - `R2Link(url, *, websocket_factory=None, reconnect_delay=1.0, connect_timeout=5.0, now=default_now)`
    - 属性 `url: str`, `on_message: Callable[[dict], None] | None`, `on_state_change: Callable[[str], None] | None`
    - `state() -> tuple[str, str | None]`（状態と、変わった時刻の ISO 文字列）
    - `start()`（スレッド開始＋自動接続）、`connect()`、`disconnect()`、`close()`（テスト用の後始末）
    - `send_json(obj) -> bool`（未接続なら False）

- [ ] **Step 1: msgpack を依存に足してインストールする**

`requirements-core.txt` の `websockets==13.1` の次の行に足す：

```
msgpack==1.2.3
```

Run: `uv pip install -r requirements-core.txt --python .venv/bin/python`
Expected: `msgpack==1.2.3` がインストールされる。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_r2_link.py`：

```python
import queue
import threading
import time

import msgpack

from app.clients.r2_link import (
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    STATE_STOPPED,
    R2Link,
    encode_json,
)


class FakeSocket:
    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = False
        self.connected = True

    def recv(self):
        item = self.incoming.get(timeout=2)
        if isinstance(item, Exception):
            raise item
        return item

    def send(self, text):
        self.sent.append(text)

    def close(self):
        self.closed = True
        self.connected = False
        self.incoming.put(ConnectionError("closed"))


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def make_link(sockets, attempts=None):
    sockets = iter(sockets)

    def factory(url, timeout):
        if attempts is not None:
            attempts.append((url, timeout))
        item = next(sockets)
        if isinstance(item, Exception):
            raise item
        return item

    return R2Link(
        "ws://r2.test:9002/realtime",
        websocket_factory=factory,
        reconnect_delay=0.01,
        connect_timeout=5.0,
    )


def test_encode_json_matches_javascript_json_stringify():
    assert encode_json({"type": "play_navigation5", "data": {"value": True}}) == (
        '{"type":"play_navigation5","data":{"value":true}}'
    )


def test_start_connects_and_reports_states():
    socket = FakeSocket()
    link = make_link([socket])
    states = []
    link.on_state_change = states.append

    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()

    assert states[:2] == [STATE_CONNECTING, STATE_CONNECTED]
    assert link.state()[1] is not None


def test_decodes_msgpack_frames_and_skips_text_and_garbage():
    socket = FakeSocket()
    link = make_link([socket])
    received = []
    link.on_message = received.append
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    socket.incoming.put("text frame")
    socket.incoming.put(b"\xc1")  # 0xc1 is never valid MessagePack
    socket.incoming.put(msgpack.packb({"type": "robot_aggregator", "data": {}}))

    wait_until(lambda: received == [{"type": "robot_aggregator", "data": {}}])
    link.close()


def test_send_json_sends_compact_json_while_connected():
    socket = FakeSocket()
    link = make_link([socket])
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    assert link.send_json({"type": "gamepad", "data": {"combo": [0, 0, 1, 0, 0]}}) is True
    link.close()

    assert socket.sent == ['{"type":"gamepad","data":{"combo":[0,0,1,0,0]}}']


def test_send_json_returns_false_when_not_connected():
    link = make_link([])

    assert link.send_json({"type": "gamepad"}) is False


def test_reconnects_after_connection_lost():
    first, second = FakeSocket(), FakeSocket()
    attempts = []
    link = make_link([first, second], attempts)
    states = []
    link.on_state_change = states.append
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    first.incoming.put(ConnectionError("dropped"))

    wait_until(lambda: len(attempts) == 2 and link.state()[0] == STATE_CONNECTED)
    link.close()
    assert STATE_DISCONNECTED in states
    assert attempts[0] == ("ws://r2.test:9002/realtime", 5.0)


def test_retries_when_connecting_fails():
    socket = FakeSocket()
    attempts = []
    link = make_link([ConnectionRefusedError("refused"), socket], attempts)

    link.start()

    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()
    assert len(attempts) == 2


def test_manual_disconnect_stops_reconnecting_until_connect():
    first, second = FakeSocket(), FakeSocket()
    attempts = []
    link = make_link([first, second], attempts)
    link.start()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)

    link.disconnect()
    wait_until(lambda: link.state()[0] == STATE_STOPPED)
    time.sleep(0.1)  # ten reconnect delays
    assert len(attempts) == 1
    assert first.closed

    link.connect()
    wait_until(lambda: link.state()[0] == STATE_CONNECTED)
    link.close()
    assert len(attempts) == 2
```

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_link.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.clients.r2_link'`）

- [ ] **Step 4: 実装する**

`app/clients/r2_link.py`：

```python
"""WebSocket link to R2's gamepad-server (``/realtime``).

R2 sends MessagePack binary frames and takes JSON text frames, the same way
the vendor's UI-DRP talks to it.
"""

import json
import logging
import socket
import threading
from datetime import datetime, timezone

import msgpack

logger = logging.getLogger(__name__)

STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_DISCONNECTED = "disconnected"
STATE_STOPPED = "stopped"

# Notice a dead peer (e.g. the exhibit PC dropping off THEMIS_5G) within ~11s
# instead of the kernel's two-hour default.
_KEEPALIVE_SOCKOPT = (
    (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 5),
    (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 2),
    (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3),
)


def _default_websocket_factory(url, timeout):
    import websocket

    ws = websocket.create_connection(url, timeout=timeout, sockopt=_KEEPALIVE_SOCKOPT)
    # The timeout only bounds the handshake; R2 may stay quiet for a while.
    ws.settimeout(None)
    return ws


def default_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def encode_json(obj):
    """Serialize like JavaScript's JSON.stringify, as UI-DRP does."""
    return json.dumps(obj, separators=(",", ":"))


def _close_quietly(sock):
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass


class R2Link:
    def __init__(
        self,
        url,
        *,
        websocket_factory=None,
        reconnect_delay=1.0,
        connect_timeout=5.0,
        now=default_now,
    ):
        self.url = url
        self.on_message = None
        self.on_state_change = None
        self._factory = websocket_factory or _default_websocket_factory
        self._reconnect_delay = reconnect_delay
        self._connect_timeout = connect_timeout
        self._now = now
        self._lock = threading.Lock()
        self._state = STATE_STOPPED
        self._state_at = None
        self._socket = None
        self._enabled = False
        self._closed = False
        self._wake = threading.Event()
        self._thread = None
        self._failure_logged = False

    def state(self):
        with self._lock:
            return self._state, self._state_at

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="r2-link", daemon=True)
        self._thread.start()
        self.connect()

    def connect(self):
        with self._lock:
            self._enabled = True
        self._wake.set()

    def disconnect(self):
        with self._lock:
            self._enabled = False
            sock = self._socket
        self._wake.set()
        _close_quietly(sock)

    def close(self):
        with self._lock:
            self._closed = True
            self._enabled = False
            sock = self._socket
        self._wake.set()
        _close_quietly(sock)
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def send_json(self, obj):
        text = encode_json(obj)
        with self._lock:
            sock = self._socket if self._state == STATE_CONNECTED else None
        if sock is None:
            return False
        try:
            sock.send(text)
        except Exception as exc:
            logger.warning("R2 send failed: %s", exc)
            return False
        return True

    def _enabled_and_open(self):
        with self._lock:
            return self._enabled and not self._closed

    def _run(self):
        while True:
            with self._lock:
                if self._closed:
                    break
                enabled = self._enabled
            if not enabled:
                self._set_state(STATE_STOPPED)
                self._wake.wait()
                self._wake.clear()
                continue

            self._set_state(STATE_CONNECTING)
            try:
                sock = self._factory(self.url, self._connect_timeout)
            except Exception as exc:
                if not self._failure_logged:
                    logger.warning("R2 connect to %s failed: %s", self.url, exc)
                    self._failure_logged = True
                self._set_state(STATE_DISCONNECTED)
                self._pause()
                continue

            with self._lock:
                keep = self._enabled and not self._closed
                if keep:
                    self._socket = sock
            if not keep:
                _close_quietly(sock)
                continue

            self._failure_logged = False
            logger.info("R2 connected to %s", self.url)
            self._set_state(STATE_CONNECTED)
            try:
                self._receive(sock)
            except Exception as exc:
                if self._enabled_and_open():
                    logger.warning("R2 connection lost: %s", exc)
            finally:
                with self._lock:
                    self._socket = None
                _close_quietly(sock)

            if self._enabled_and_open():
                self._set_state(STATE_DISCONNECTED)
                self._pause()
        self._set_state(STATE_STOPPED)

    def _pause(self):
        self._wake.wait(self._reconnect_delay)
        self._wake.clear()

    def _set_state(self, state):
        with self._lock:
            if self._state == state:
                return
            self._state = state
            self._state_at = self._now()
        callback = self.on_state_change
        if callback is None:
            return
        try:
            callback(state)
        except Exception:
            logger.exception("R2 state callback failed")

    def _receive(self, sock):
        while True:
            message = sock.recv()
            if isinstance(message, (bytes, bytearray)):
                if message:
                    self._dispatch(bytes(message))
                continue
            if message is None or not getattr(sock, "connected", True):
                return
            # Text frames are not part of what UI-DRP reads from R2.

    def _dispatch(self, payload):
        try:
            message = msgpack.unpackb(payload, raw=False, strict_map_key=False)
        except Exception:
            logger.warning("R2 sent a frame that is not MessagePack (%d bytes)", len(payload))
            return
        if not isinstance(message, dict):
            return
        callback = self.on_message
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            logger.exception("R2 message handling failed")
```

- [ ] **Step 5: テストが通ることを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_link.py -q`
Expected: 8 passed

- [ ] **Step 6: コミットする**

```bash
git add requirements-core.txt app/clients/r2_link.py tests/test_r2_link.py
git commit -m "feat: add a WebSocket link to R2's gamepad-server

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `R2Controller`（UI-DRP の手順と status）

**Files:**
- Create: `app/clients/r2_controller.py`
- Test: `tests/test_r2_controller.py`

**Interfaces:**
- Consumes（Task 1）：`STATE_CONNECTED`、`encode_json`。リンクは次を持つもの：`url`、`on_message`、`on_state_change`、`state()`、`send_json(obj) -> bool`、`connect()`、`disconnect()`。
- Produces:
  - 定数 `STATUS_COMPLETED`, `STATUS_LOADING`, `STATUS_RETURNING`, `STATUS_FAILED`、`FAILURE_*`、`FAILURE_MESSAGES: dict[str, str]`
  - `R2Controller(link, *, start_reply_timeout=15.0, sleep=time.sleep, now=default_now)`
  - `snapshot() -> dict`：キー `url, connection, connection_at, status, status_at, failure, failure_message, starting, under_mode, under_mode_at, last_reply, last_reply_at, last_reply_seconds`
  - `wait_until(predicate: Callable[[dict], bool]) -> dict`
  - 操作（成功なら `None`、断るときは理由の文字列）：`start_load_drink()`, `resend_start()`, `stop()`, `mark(status)`, `reset()`, `connect()`, `disconnect()`
  - `add_listener(fn: Callable[[dict], None])`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_r2_controller.py`：

```python
import threading
import time

import pytest

from app.clients.r2_controller import (
    FAILURE_DISCONNECTED,
    FAILURE_MANUAL,
    FAILURE_START_DISCONNECTED,
    FAILURE_START_NO_REPLY,
    FAILURE_START_REJECTED,
    FAILURE_STOPPED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_LOADING,
    STATUS_RETURNING,
    R2Controller,
)
from app.clients.r2_link import encode_json

# Copied from what UI-DRP's JSON.stringify sends; must match byte for byte.
ENTER_NAV = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[0,0,1,0,0]}}'
)
LEAVE_NAV = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[1,0,0,0,0]}}'
)
RELEASE = (
    '{"type":"gamepad","data":{"button":[0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],'
    '"axis":[0,0,0,0,0,0],"combo":[0,0,0,0,0]}}'
)
PLAY_TRUE = '{"type":"play_navigation5","data":{"value":true}}'
PLAY_FALSE = '{"type":"play_navigation5","data":{"value":false}}'


class FakeLink:
    def __init__(self, state="connected"):
        self.url = "ws://r2.test:9002/realtime"
        self.on_message = None
        self.on_state_change = None
        self._state = state
        self.sent = []
        self.on_send = None
        self.connect_calls = 0
        self.disconnect_calls = 0

    def state(self):
        return self._state, "2026-10-04T00:00:00Z"

    def send_json(self, obj):
        if self._state != "connected":
            return False
        self.sent.append(encode_json(obj))
        if self.on_send is not None:
            self.on_send(obj)
        return True

    def connect(self):
        self.connect_calls += 1

    def disconnect(self):
        self.disconnect_calls += 1

    def set_state(self, state):
        self._state = state
        self.on_state_change(state)

    def receive(self, message):
        self.on_message(message)


def reply(success):
    return {"type": "play_navigation5_rp", "data": {"success": success}}


def aggregator(under_mode):
    return {"type": "robot_aggregator", "data": {"under_mode": {"data": {"data": under_mode}}}}


def replies_with(link, success):
    def on_send(obj):
        if obj == {"type": "play_navigation5", "data": {"value": True}}:
            link.receive(reply(success))

    link.on_send = on_send


def make_controller(link=None, sleeps=None):
    link = link or FakeLink()
    controller = R2Controller(
        link,
        start_reply_timeout=0.05,
        sleep=(sleeps if sleeps is not None else []).append,
        now=lambda: "2026-10-04T00:00:00Z",
    )
    return link, controller


def loading_controller():
    link, controller = make_controller()
    replies_with(link, True)
    assert controller.start_load_drink() is None
    link.on_send = None
    link.sent.clear()
    return link, controller


def test_initial_snapshot():
    _, controller = make_controller()

    snap = controller.snapshot()

    assert snap["url"] == "ws://r2.test:9002/realtime"
    assert snap["connection"] == "connected"
    assert snap["status"] == STATUS_COMPLETED
    assert snap["failure"] is None
    assert snap["starting"] is False
    assert snap["under_mode"] is None


def test_start_sends_what_ui_drp_sends_and_starts_loading():
    sleeps = []
    link, controller = make_controller(sleeps=sleeps)
    replies_with(link, True)

    assert controller.start_load_drink() is None

    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    assert sleeps == [2.0]
    snap = controller.snapshot()
    assert snap["status"] == STATUS_LOADING
    assert snap["last_reply"] == {"success": True}
    assert snap["last_reply_seconds"] is not None
    assert snap["starting"] is False


def test_start_rejected_fails():
    link, controller = make_controller()
    replies_with(link, False)

    reason = controller.start_load_drink()

    assert reason
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_REJECTED)


def test_start_without_reply_times_out():
    link, controller = make_controller()

    reason = controller.start_load_drink()

    assert reason
    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_NO_REPLY)


def test_start_disconnected_while_waiting_for_reply():
    link, controller = make_controller()

    def drop_on_play(obj):
        if obj["type"] == "play_navigation5":
            link.set_state("disconnected")

    link.on_send = drop_on_play

    assert controller.start_load_drink()
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_START_DISCONNECTED)


def test_start_refused_when_not_connected_or_not_completed():
    link, controller = make_controller(FakeLink(state="disconnected"))
    assert controller.start_load_drink()
    assert link.sent == []

    link, controller = loading_controller()
    assert controller.start_load_drink()
    assert link.sent == []


def test_late_reply_does_not_change_a_timed_out_start():
    link, controller = make_controller()
    controller.start_load_drink()

    link.receive(reply(True))

    snap = controller.snapshot()
    assert snap["status"] == STATUS_FAILED
    assert snap["last_reply"] == {"success": True}


def test_under_mode_m5_while_loading_then_m1_while_returning():
    link, controller = loading_controller()

    link.receive(aggregator("nav_m3"))
    assert controller.snapshot()["status"] == STATUS_LOADING
    link.receive(aggregator("nav_m5"))
    assert controller.snapshot()["status"] == STATUS_RETURNING
    link.receive(aggregator("nav_m1"))

    snap = controller.snapshot()
    assert snap["status"] == STATUS_COMPLETED
    assert snap["under_mode"] == "nav_m1"
    assert snap["under_mode_at"] == "2026-10-04T00:00:00Z"


def test_under_mode_ignored_outside_matching_status():
    link, controller = make_controller()
    link.receive(aggregator("nav_m5"))
    assert controller.snapshot()["status"] == STATUS_COMPLETED

    link, controller = loading_controller()
    link.receive(aggregator("nav_m1"))
    assert controller.snapshot()["status"] == STATUS_LOADING


def test_m5_that_was_already_current_does_not_count_again():
    link, controller = make_controller()
    link.receive(aggregator("nav_m5"))
    replies_with(link, True)
    controller.start_load_drink()

    link.receive(aggregator("nav_m5"))

    assert controller.snapshot()["status"] == STATUS_LOADING


def test_empty_or_missing_under_mode_is_ignored():
    link, controller = loading_controller()
    link.receive(aggregator("nav_m3"))

    link.receive(aggregator(""))
    link.receive({"type": "robot_aggregator", "data": {"battery_state": {}}})

    assert controller.snapshot()["under_mode"] == "nav_m3"


def test_disconnect_while_loading_fails_and_later_m1_is_ignored():
    link, controller = loading_controller()

    link.set_state("disconnected")
    link.set_state("connected")
    link.receive(aggregator("nav_m1"))

    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_DISCONNECTED)


def test_disconnect_while_completed_keeps_completed():
    link, controller = make_controller()

    link.set_state("disconnected")

    assert controller.snapshot()["status"] == STATUS_COMPLETED


def test_stop_sends_what_ui_drp_sends_and_fails():
    sleeps = []
    link, controller = make_controller(sleeps=sleeps)

    assert controller.stop() is None

    assert link.sent == [LEAVE_NAV] * 4 + [RELEASE, PLAY_FALSE]
    assert sleeps == [2.0]
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_STOPPED)


def test_stop_refused_when_disconnected():
    link, controller = make_controller(FakeLink(state="disconnected"))

    assert controller.stop()
    assert controller.snapshot()["status"] == STATUS_COMPLETED


def test_stop_during_start_aborts_the_start():
    link, controller = make_controller()
    sleeps = []
    results = {}

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:  # the 2s wait inside the start
            results["stop"] = controller.stop()

    controller._sleep = sleep

    reason = controller.start_load_drink()
    link.receive(reply(True))

    assert reason
    assert results["stop"] is None
    assert PLAY_TRUE not in link.sent
    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_FAILED, FAILURE_STOPPED)


@pytest.mark.parametrize(
    "start_status, target, allowed",
    [
        (STATUS_LOADING, STATUS_RETURNING, True),
        (STATUS_COMPLETED, STATUS_RETURNING, False),
        (STATUS_RETURNING, STATUS_COMPLETED, True),
        (STATUS_LOADING, STATUS_COMPLETED, False),
        (STATUS_LOADING, STATUS_FAILED, True),
        (STATUS_RETURNING, STATUS_FAILED, True),
        (STATUS_COMPLETED, STATUS_FAILED, False),
        (STATUS_LOADING, STATUS_LOADING, False),
    ],
)
def test_mark_rules(start_status, target, allowed):
    link, controller = loading_controller()
    if start_status == STATUS_RETURNING:
        link.receive(aggregator("nav_m5"))
    elif start_status == STATUS_COMPLETED:
        _, controller = make_controller()
    assert controller.snapshot()["status"] == start_status

    reason = controller.mark(target)

    assert (reason is None) is allowed
    snap = controller.snapshot()
    assert snap["status"] == (target if allowed else start_status)
    if allowed and target == STATUS_FAILED:
        assert snap["failure"] == FAILURE_MANUAL
    assert link.sent == []


def test_reset_only_from_failed():
    link, controller = make_controller()
    assert controller.reset()

    controller.stop()
    assert controller.reset() is None

    snap = controller.snapshot()
    assert (snap["status"], snap["failure"]) == (STATUS_COMPLETED, None)


def test_resend_requires_a_start_failure_and_m1():
    link, controller = make_controller()
    controller.stop()
    assert controller.resend_start()  # stopped is not a start failure

    link, controller = make_controller()
    controller.start_load_drink()  # times out
    link.receive(aggregator("nav_m3"))
    assert controller.resend_start()  # not at A
    link.sent.clear()

    link.receive(aggregator("nav_m1"))
    replies_with(link, True)
    assert controller.resend_start() is None

    assert link.sent == [ENTER_NAV, PLAY_TRUE]
    assert controller.snapshot()["status"] == STATUS_LOADING


def test_connect_and_disconnect_are_passed_to_the_link():
    link, controller = make_controller()

    assert controller.connect() is None
    assert controller.disconnect() is None

    assert (link.connect_calls, link.disconnect_calls) == (1, 1)


def test_listeners_get_a_snapshot_on_every_change():
    link, controller = make_controller()
    seen = []
    controller.add_listener(lambda snap: seen.append(snap["status"]))

    link.receive(aggregator("nav_m1"))
    controller.stop()

    assert seen[-1] == STATUS_FAILED
    assert len(seen) >= 2


def test_wait_until_wakes_on_change():
    link, controller = loading_controller()
    result = {}

    waiter = threading.Thread(
        target=lambda: result.update(
            snap=controller.wait_until(lambda s: s["status"] != STATUS_LOADING)
        )
    )
    waiter.start()
    time.sleep(0.05)
    link.receive(aggregator("nav_m5"))
    waiter.join(timeout=2)

    assert result["snap"]["status"] == STATUS_RETURNING
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_controller.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.clients.r2_controller'`）

- [ ] **Step 3: 実装する**

`app/clients/r2_controller.py`：

```python
"""Drive R2's drink-loading sequence the way the vendor's UI-DRP does.

What is sent to R2 and how R2's messages are read mirror UI-DRP
(~/Linux/DRP-src/dist). R2 itself has no notion of these statuses; they are
built here from our own commands and changes of ``under_mode``.
"""

import logging
import threading
import time

from .r2_link import STATE_CONNECTED, default_now

logger = logging.getLogger(__name__)

STATUS_COMPLETED = "completed"
STATUS_LOADING = "loading"
STATUS_RETURNING = "returning"
STATUS_FAILED = "failed"

FAILURE_START_NO_REPLY = "start_no_reply"
FAILURE_START_REJECTED = "start_rejected"
FAILURE_START_DISCONNECTED = "start_disconnected"
FAILURE_DISCONNECTED = "disconnected"
FAILURE_STOPPED = "stopped"
FAILURE_MANUAL = "manual"
START_FAILURES = (FAILURE_START_NO_REPLY, FAILURE_START_REJECTED, FAILURE_START_DISCONNECTED)

FAILURE_MESSAGES = {
    FAILURE_START_NO_REPLY: "R2から開始の返事がありませんでした",
    FAILURE_START_REJECTED: "R2が開始を受け付けませんでした (success:false)",
    FAILURE_START_DISCONNECTED: "開始の返事を待つあいだにR2との接続が切れました",
    FAILURE_DISCONNECTED: "動作中にR2との接続が切れました",
    FAILURE_STOPPED: "オペレーターがSTOPしました",
    FAILURE_MANUAL: "オペレーターがfailedにしました",
}

# UI-DRP waits 2s between the gamepad combo and play_navigation5.
NAV_WAIT_SECONDS = 2.0
_NO_BUTTONS = [0] * 16
_BACK_START_BUTTONS = [0] * 8 + [1, 1] + [0] * 6  # BK + ST
_AXIS = [0] * 6
COMBO_NAVIGATION = [0, 0, 1, 0, 0]
COMBO_STAND = [1, 0, 0, 0, 0]
COMBO_NONE = [0, 0, 0, 0, 0]
LEAVE_NAV_REPEAT = 4

_MARK_FROM = {
    STATUS_RETURNING: (STATUS_LOADING,),
    STATUS_COMPLETED: (STATUS_RETURNING,),
    STATUS_FAILED: (STATUS_LOADING, STATUS_RETURNING),
}


def gamepad_message(buttons, combo):
    return {
        "type": "gamepad",
        "data": {"button": list(buttons), "axis": list(_AXIS), "combo": list(combo)},
    }


def play_navigation5_message(value):
    return {"type": "play_navigation5", "data": {"value": value}}


def under_mode_number(value):
    """UI-DRP's ``value.split("_m")[1]``; None where JavaScript gives undefined."""
    parts = value.split("_m")
    return parts[1] if len(parts) > 1 else None


def _under_mode_value(data):
    try:
        value = data["under_mode"]["data"]["data"]
    except (KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


class R2Controller:
    def __init__(self, link, *, start_reply_timeout=15.0, sleep=time.sleep, now=default_now):
        self._link = link
        self._start_reply_timeout = start_reply_timeout
        self._sleep = sleep
        self._now = now
        self._cond = threading.Condition()
        self._listeners = []

        self._connection = link.state()[0]
        self._status = STATUS_COMPLETED
        self._status_at = None
        self._failure = None
        self._starting = False
        self._stopping = False
        self._abort_start = False
        self._awaiting_reply = False
        self._reply = None
        self._reply_sent_at = None
        self._under_mode = None
        self._under_mode_at = None
        self._last_reply = None
        self._last_reply_at = None
        self._last_reply_seconds = None

        link.on_message = self._on_message
        link.on_state_change = self._on_link_state

    # --- reading ---------------------------------------------------------

    def snapshot(self):
        with self._cond:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        connection, connection_at = self._link.state()
        return {
            "url": self._link.url,
            "connection": connection,
            "connection_at": connection_at,
            "status": self._status,
            "status_at": self._status_at,
            "failure": self._failure,
            "failure_message": FAILURE_MESSAGES.get(self._failure),
            "starting": self._starting,
            "under_mode": self._under_mode,
            "under_mode_at": self._under_mode_at,
            "last_reply": self._last_reply,
            "last_reply_at": self._last_reply_at,
            "last_reply_seconds": self._last_reply_seconds,
        }

    def wait_until(self, predicate):
        with self._cond:
            while True:
                snap = self._snapshot_locked()
                if predicate(snap):
                    return snap
                self._cond.wait()

    def add_listener(self, listener):
        self._listeners.append(listener)

    def _publish(self):
        snap = self.snapshot()
        for listener in list(self._listeners):
            try:
                listener(snap)
            except Exception:
                logger.exception("R2 listener failed")

    def _set_status_locked(self, status, failure=None):
        self._status = status
        self._failure = failure if status == STATUS_FAILED else None
        self._status_at = self._now()
        logger.info("R2 status -> %s%s", status, f" ({failure})" if failure else "")
        self._cond.notify_all()

    # --- what R2 sends ------------------------------------------------------

    def _on_link_state(self, state):
        with self._cond:
            self._connection = state
            if state != STATE_CONNECTED and self._status in (STATUS_LOADING, STATUS_RETURNING):
                self._set_status_locked(STATUS_FAILED, FAILURE_DISCONNECTED)
            self._cond.notify_all()
        self._publish()

    def _on_message(self, message):
        kind = message.get("type")
        if kind == "robot_aggregator":
            self._on_aggregator(message.get("data"))
        elif kind == "play_navigation5_rp":
            self._on_reply(message.get("data"))

    def _on_aggregator(self, data):
        under_mode = _under_mode_value(data)
        if not under_mode:
            return
        with self._cond:
            previous = self._under_mode
            if under_mode == previous:
                return
            self._under_mode = under_mode
            self._under_mode_at = self._now()
            logger.info("R2 under_mode: %s -> %s", previous, under_mode)
            number = under_mode_number(under_mode)
            previous_number = under_mode_number(previous) if previous else None
            if previous_number is None:
                previous_number = ""  # UI-DRP: ?? ""
            if number == "5" and previous_number != "5" and self._status == STATUS_LOADING:
                self._set_status_locked(STATUS_RETURNING)
            elif number == "1" and previous_number != "1" and self._status == STATUS_RETURNING:
                self._set_status_locked(STATUS_COMPLETED)
            self._cond.notify_all()
        self._publish()

    def _on_reply(self, data):
        with self._cond:
            self._last_reply = data
            self._last_reply_at = self._now()
            if self._awaiting_reply:
                self._last_reply_seconds = round(time.monotonic() - self._reply_sent_at, 3)
                self._reply = data if data is not None else {}
                self._awaiting_reply = False
            else:
                logger.info("R2 play_navigation5_rp outside a start: %s", data)
            self._cond.notify_all()
        self._publish()

    # --- starting -----------------------------------------------------------

    def start_load_drink(self):
        with self._cond:
            reason = self._start_refusal_locked()
            if reason:
                return reason
            self._starting = True
            self._abort_start = False
            self._cond.notify_all()
        self._publish()
        try:
            return self._run_start()
        finally:
            with self._cond:
                self._starting = False
                self._awaiting_reply = False
                self._cond.notify_all()
            self._publish()

    def _start_refusal_locked(self):
        if self._starting:
            return "開始の処理中です"
        if self._connection != STATE_CONNECTED:
            return "R2に接続していません"
        if self._status != STATUS_COMPLETED:
            return f"R2が待機中ではありません（status={self._status}）"
        return None

    def _run_start(self):
        if not self._link.send_json(gamepad_message(_NO_BUTTONS, COMBO_NAVIGATION)):
            return self._fail_start(FAILURE_START_DISCONNECTED)
        self._sleep(NAV_WAIT_SECONDS)
        with self._cond:
            if self._abort_start:
                return FAILURE_MESSAGES[FAILURE_STOPPED]
            self._reply = None
            self._awaiting_reply = True
            self._reply_sent_at = time.monotonic()
        if not self._link.send_json(play_navigation5_message(True)):
            return self._fail_start(FAILURE_START_DISCONNECTED)

        deadline = time.monotonic() + self._start_reply_timeout
        with self._cond:
            while (
                self._reply is None
                and not self._abort_start
                and self._connection == STATE_CONNECTED
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            reply = self._reply
            aborted = self._abort_start
            connected = self._connection == STATE_CONNECTED

        if aborted:
            return FAILURE_MESSAGES[FAILURE_STOPPED]
        if reply is None:
            return self._fail_start(
                FAILURE_START_NO_REPLY if connected else FAILURE_START_DISCONNECTED
            )
        if isinstance(reply, dict) and reply.get("success") is True:
            with self._cond:
                self._set_status_locked(STATUS_LOADING)
            self._publish()
            return None
        return self._fail_start(FAILURE_START_REJECTED)

    def _fail_start(self, failure):
        with self._cond:
            # A STOP while starting has already failed this cycle.
            if self._status == STATUS_COMPLETED:
                self._set_status_locked(STATUS_FAILED, failure)
            message = FAILURE_MESSAGES[self._failure or failure]
        self._publish()
        return message

    def resend_start(self):
        with self._cond:
            if self._status != STATUS_FAILED or self._failure not in START_FAILURES:
                return "開始の失敗で failed になっているときだけ再送できます"
            if under_mode_number(self._under_mode or "") != "1":
                return "under_mode が _m1（A にいる）のときだけ再送できます"
            if self._connection != STATE_CONNECTED:
                return "R2に接続していません"
            if self._starting:
                return "開始の処理中です"
            self._set_status_locked(STATUS_COMPLETED)
        self._publish()
        return self.start_load_drink()

    # --- operator actions ---------------------------------------------------

    def stop(self):
        with self._cond:
            if self._connection != STATE_CONNECTED:
                return "R2に接続していません"
            if self._stopping:
                return "STOP の処理中です"
            self._stopping = True
            self._abort_start = True
            self._set_status_locked(STATUS_FAILED, FAILURE_STOPPED)
        self._publish()
        try:
            for _ in range(LEAVE_NAV_REPEAT):
                if not self._link.send_json(gamepad_message(_BACK_START_BUTTONS, COMBO_STAND)):
                    return "STOP の送信中にR2との接続が切れました"
            if not self._link.send_json(gamepad_message(_NO_BUTTONS, COMBO_NONE)):
                return "STOP の送信中にR2との接続が切れました"
            self._sleep(NAV_WAIT_SECONDS)
            if not self._link.send_json(play_navigation5_message(False)):
                return "STOP の送信中にR2との接続が切れました"
            return None
        finally:
            with self._cond:
                self._stopping = False
                self._cond.notify_all()
            self._publish()

    def mark(self, status):
        allowed = _MARK_FROM.get(status)
        if allowed is None:
            return f"手動では {status} にできません"
        with self._cond:
            if self._status not in allowed:
                return f"{status} にできるのは status が {' / '.join(allowed)} のときだけです"
            self._set_status_locked(status, FAILURE_MANUAL if status == STATUS_FAILED else None)
        self._publish()
        return None

    def reset(self):
        with self._cond:
            if self._status != STATUS_FAILED:
                return "R2 を初期状態に戻せるのは failed のときだけです"
            self._set_status_locked(STATUS_COMPLETED)
        self._publish()
        return None

    def connect(self):
        self._link.connect()
        return None

    def disconnect(self):
        self._link.disconnect()
        return None
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_controller.py -q`
Expected: 全件 PASS

- [ ] **Step 5: コミットする**

```bash
git add app/clients/r2_controller.py tests/test_r2_controller.py
git commit -m "feat: drive R2's loading sequence the way UI-DRP does

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `/realtime` のモックと結合テスト

**Files:**
- Create: `mocks/r2_realtime_mock.py`
- Modify: `mocks/themis_video_mock.py`（`serve_mock` と `main`）
- Modify: `run_mocks.py`
- Create: `tests/ws_mock_server.py`（テスト用：モックを別スレッドで起動するヘルパー。`test_*.py` ではないので pytest は集めない）
- Test: `tests/test_r2_realtime_mock.py`、`tests/test_r2_integration.py`

**Interfaces:**
- Consumes（Task 1, 2）：`R2Link`、`R2Controller`、`STATUS_*`
- Produces:
  - `R2RealtimeMock(step_seconds=3.0, start_reply="success", aggregator_interval=0.5)`、`R2RealtimeMock.from_env()`、属性 `received: list[dict]`、`under_mode: str`、`async handle(websocket)`
  - `serve_mock(host="127.0.0.1", port=9002, config=None, realtime=None)`（`realtime` が渡されたら `/realtime` をそれで処理）

- [ ] **Step 1: 失敗するテストを書く**

`tests/ws_mock_server.py`（pytest は各テストファイルのディレクトリを `sys.path` に入れるので、テストから `from ws_mock_server import running_mock` で import できる）：

```python
"""Run the Themis WebSocket mock (video + /realtime) on a free port for tests."""

import asyncio
import socket
import threading
import time
from contextlib import contextmanager

import websocket

from mocks.themis_video_mock import MockThemisVideoConfig, serve_mock


@contextmanager
def running_mock(realtime):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stop = threading.Event()

    def run():
        async def main():
            task = asyncio.create_task(
                serve_mock(
                    port=port,
                    config=MockThemisVideoConfig(payload=b"frame", interval_seconds=0.05),
                    realtime=realtime,
                )
            )
            try:
                await asyncio.to_thread(stop.wait)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(main())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while True:
        try:
            websocket.create_connection(f"ws://127.0.0.1:{port}/zed2i", timeout=0.2).close()
            break
        except (OSError, websocket.WebSocketException):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=2)
```

`tests/test_r2_realtime_mock.py`：

```python
import json
import time

import msgpack
import websocket
from ws_mock_server import running_mock

from mocks.r2_realtime_mock import R2RealtimeMock


def recv_until(ws, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = ws.recv()
        if isinstance(frame, bytes):
            message = msgpack.unpackb(frame, raw=False)
            if predicate(message):
                return message
    raise AssertionError("expected message did not arrive")


def is_under_mode(value):
    return lambda m: m.get("type") == "robot_aggregator" and (
        m["data"]["under_mode"]["data"]["data"] == value
    )


def test_video_path_still_streams_frames():
    with running_mock(R2RealtimeMock(step_seconds=0.05, aggregator_interval=0.02)) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/zed2i", timeout=2)
        try:
            assert ws.recv() == b"frame"
        finally:
            ws.close()


def test_realtime_runs_the_sequence_after_play_navigation5():
    realtime = R2RealtimeMock(step_seconds=0.05, aggregator_interval=0.02)
    with running_mock(realtime) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            recv_until(ws, is_under_mode("mock_m1"))
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            reply = recv_until(ws, lambda m: m.get("type") == "play_navigation5_rp")
            assert reply["data"] == {"success": True}
            recv_until(ws, is_under_mode("mock_m5"))
            recv_until(ws, is_under_mode("mock_m1"))
        finally:
            ws.close()
    assert realtime.received[0] == {"type": "play_navigation5", "data": {"value": True}}


def test_realtime_can_reject_or_ignore_the_start():
    rejecting = R2RealtimeMock(step_seconds=0.05, start_reply="fail", aggregator_interval=0.02)
    with running_mock(rejecting) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            reply = recv_until(ws, lambda m: m.get("type") == "play_navigation5_rp")
            assert reply["data"] == {"success": False}
        finally:
            ws.close()

    silent = R2RealtimeMock(step_seconds=0.05, start_reply="none", aggregator_interval=0.02)
    with running_mock(silent) as port:
        ws = websocket.create_connection(f"ws://127.0.0.1:{port}/realtime", timeout=2)
        try:
            ws.send(json.dumps({"type": "play_navigation5", "data": {"value": True}}))
            ws.settimeout(0.3)
            seen = []
            try:
                while True:
                    frame = ws.recv()
                    seen.append(msgpack.unpackb(frame, raw=False)["type"])
            except websocket.WebSocketTimeoutException:
                pass
            assert "play_navigation5_rp" not in seen
        finally:
            ws.close()


def test_from_env(monkeypatch):
    monkeypatch.setenv("R2_MOCK_STEP_SECONDS", "0.5")
    monkeypatch.setenv("R2_MOCK_START_REPLY", "none")

    mock = R2RealtimeMock.from_env()

    assert (mock.step_seconds, mock.start_reply) == (0.5, "none")
```

`tests/test_r2_integration.py`：

```python
"""Real R2Link + R2Controller against the real /realtime mock over a socket."""

from ws_mock_server import running_mock

from app.clients.r2_controller import STATUS_COMPLETED, STATUS_LOADING, STATUS_RETURNING, R2Controller
from app.clients.r2_link import R2Link
from mocks.r2_realtime_mock import R2RealtimeMock


def test_controller_runs_a_full_cycle_against_the_mock():
    realtime = R2RealtimeMock(step_seconds=0.1, aggregator_interval=0.02)
    with running_mock(realtime) as port:
        link = R2Link(f"ws://127.0.0.1:{port}/realtime", reconnect_delay=0.05)
        controller = R2Controller(link, start_reply_timeout=2.0, sleep=lambda s: None)
        seen = []
        controller.add_listener(lambda snap: seen.append(snap["status"]))
        link.start()
        try:
            controller.wait_until(
                lambda s: s["connection"] == "connected" and s["under_mode"] == "mock_m1"
            )
            assert controller.start_load_drink() is None
            snap = controller.wait_until(lambda s: s["status"] == STATUS_COMPLETED)
        finally:
            link.close()

    assert snap["under_mode"] == "mock_m1"
    assert STATUS_LOADING in seen and STATUS_RETURNING in seen
    assert [m["type"] for m in realtime.received] == ["gamepad", "play_navigation5"]
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_realtime_mock.py tests/test_r2_integration.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'mocks.r2_realtime_mock'`）

- [ ] **Step 3: モックを実装する**

`mocks/r2_realtime_mock.py`：

```python
"""Mimic R2's gamepad-server ``/realtime`` for local development.

Only what UI-DRP relies on is reproduced: a play_navigation5 reply and a
robot_aggregator stream whose under_mode goes _m1 -> _m3 -> _m5 -> _m3 -> _m1.
"""

import asyncio
import json
import os

import msgpack

START_REPLIES = ("success", "fail", "none")
_SEQUENCE = ("mock_m3", "mock_m5", "mock_m3", "mock_m1")


class R2RealtimeMock:
    def __init__(self, step_seconds=3.0, start_reply="success", aggregator_interval=0.5):
        if start_reply not in START_REPLIES:
            raise ValueError(f"start_reply must be one of {START_REPLIES}")
        self.step_seconds = step_seconds
        self.start_reply = start_reply
        self.aggregator_interval = aggregator_interval
        self.received = []
        self.under_mode = "mock_m1"
        self._sequence = None

    @classmethod
    def from_env(cls):
        return cls(
            step_seconds=float(os.environ.get("R2_MOCK_STEP_SECONDS", "3")),
            start_reply=os.environ.get("R2_MOCK_START_REPLY", "success"),
        )

    async def handle(self, websocket):
        sender = asyncio.create_task(self._send_aggregator(websocket))
        try:
            async for raw in websocket:
                if not isinstance(raw, str):
                    continue
                message = json.loads(raw)
                self.received.append(message)
                if message.get("type") == "play_navigation5":
                    await self._on_play(websocket, bool(message["data"]["value"]))
        finally:
            sender.cancel()

    async def _on_play(self, websocket, value):
        if not value:
            if self._sequence is not None:
                self._sequence.cancel()
                self._sequence = None
            await self._send(websocket, "play_navigation5_rp", {"success": True})
            return
        if self.start_reply == "none":
            return
        success = self.start_reply == "success"
        await self._send(websocket, "play_navigation5_rp", {"success": success})
        if success:
            self._sequence = asyncio.create_task(self._run_sequence())

    async def _run_sequence(self):
        for under_mode in _SEQUENCE:
            await asyncio.sleep(self.step_seconds)
            self.under_mode = under_mode

    async def _send_aggregator(self, websocket):
        while True:
            await self._send(
                websocket,
                "robot_aggregator",
                {"under_mode": {"data": {"data": self.under_mode}}},
            )
            await asyncio.sleep(self.aggregator_interval)

    @staticmethod
    async def _send(websocket, kind, data):
        await websocket.send(msgpack.packb({"type": kind, "data": data}))
```

`mocks/themis_video_mock.py` の `serve_mock` を次のように変える（`handler` の前で `realtime` を受け取り、パスで振り分ける）：

```python
async def serve_mock(
    host: str = "127.0.0.1",
    port: int = 9002,
    config: MockThemisVideoConfig | None = None,
    realtime=None,
) -> None:
    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("websockets is required for the mock server") from exc

    active_config = config or MockThemisVideoConfig()
    payload = make_payload(active_config)

    async def handler(websocket):
        # Like the real gamepad-server, one port serves /realtime and video.
        if realtime is not None and websocket.path == "/realtime":
            try:
                await realtime.handle(websocket)
            except ConnectionClosed:
                pass
            return
        try:
            while True:
                await websocket.send(payload)
                await asyncio.sleep(active_config.interval_seconds)
        except ConnectionClosed:
            return

    async with websockets.serve(handler, host, port):
        await asyncio.Future()
```

同じファイルの `main()` で `realtime` を渡す（import をファイル先頭に足す：`from mocks.r2_realtime_mock import R2RealtimeMock`）：

```python
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9002)
    parser.add_argument("--interval", type=float, default=0.5)
    args = parser.parse_args()
    asyncio.run(
        serve_mock(
            args.host,
            args.port,
            MockThemisVideoConfig(interval_seconds=args.interval),
            realtime=R2RealtimeMock.from_env(),
        )
    )
```

ファイル先頭の docstring を `"""Local WebSocket server that mimics Themis' gamepad-server (video and /realtime)."""` に変える。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `.venv/bin/python -m pytest tests/test_r2_realtime_mock.py tests/test_r2_integration.py tests/test_themis_video_mock.py tests/test_visual_e2e.py -q`
Expected: 全件 PASS（映像のテストも壊れていないこと）

- [ ] **Step 5: `run_mocks.py` を書き換える**

この時点では `mocks/r2_mock.py` はまだ残っている（Task 4 で消す）。`run_mocks.py` 全体を次にする：

```python
import asyncio
import threading

from mocks.pf_mock import create_pf_mock_app
from mocks.r2_realtime_mock import R2RealtimeMock
from mocks.themis_video_mock import serve_mock


def main():
    pf_app = create_pf_mock_app()

    pf_thread = threading.Thread(
        target=lambda: pf_app.run(host="0.0.0.0", port=5002, threaded=True),
        daemon=True,
    )
    # R2 (/realtime) and Themis video (/zed2i) share :9002, like the real robot.
    themis_thread = threading.Thread(
        target=lambda: asyncio.run(
            serve_mock("127.0.0.1", 9002, realtime=R2RealtimeMock.from_env())
        ),
        daemon=True,
    )
    pf_thread.start()
    themis_thread.start()
    pf_thread.join()
    themis_thread.join()


if __name__ == "__main__":
    main()
```

Run: `timeout 3 .venv/bin/python run_mocks.py; echo exit=$?`
Expected: `exit=124`（3秒動き続けて timeout で止まる。例外が出ないこと）

- [ ] **Step 6: コミットする**

```bash
git add mocks/r2_realtime_mock.py mocks/themis_video_mock.py run_mocks.py tests/ws_mock_server.py tests/test_r2_realtime_mock.py tests/test_r2_integration.py
git commit -m "feat: mock R2's /realtime next to the Themis video mock

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ステートマシンを `R2Controller` に切り替え、HTTP の R2 を消す

**Files:**
- Modify: `app/state_machine.py`
- Modify: `app/__init__.py`
- Modify: `app/config.py`、`.env.example`
- Modify: `app/routes/checkin.py`（スキップの API を消す）
- Modify: `app/routes/ui.py`、`app/templates/debug.html`（接続先の行だけ）
- Modify: `app/static/app.js`（step 名）
- Delete: `app/clients/r2_client.py`、`mocks/r2_mock.py`、`tests/test_r2_client.py`、`tests/test_r2_mock.py`
- Modify: `tests/test_integration_mocks.py`（PF だけにする）
- Test: `tests/test_state_machine.py`、`tests/test_state_machine_runner.py`、`tests/test_app_factory.py`、`tests/test_config.py`、`tests/test_routes_checkin.py`、`tests/test_routes_debug.py`

**Interfaces:**
- Consumes（Task 1, 2）：`R2Link(url, *, reconnect_delay, connect_timeout)`、`R2Controller(link, *, start_reply_timeout)`、`wait_until`、`start_load_drink`、`STATUS_*`
- Produces:
  - `STEP_WAITING_R2_READY = "waiting_r2_ready"`, `STEP_STARTING_R2 = "starting_r2"`, `STEP_WAITING_R2_PLACED = "waiting_r2_placed"`
  - `StateMachine(r2_controller, pf_client, on_change, sleep=time.sleep, poll_interval=2.0, now=default_now, sequence_wait=1.0, monotonic=time.monotonic, entry_idle_seconds=60.0)`
  - `StateMachine.can_resume_after_start() -> bool`、`try_resume_after_start() -> bool`、`resume_after_start()`
  - `StateMachineRunner.can_resume_after_start() -> bool`、`request_resume_after_start() -> bool`
  - `create_app(r2_controller=None, pf_client=None, reservation_store=None, start_r2=True)`、`app.config["R2_CONTROLLER"]`、`app.config["R2_LINK"]`（注入されたときは `None`）
  - `config.R2_WS_URL`, `config.R2_START_REPLY_TIMEOUT_SECONDS`, `config.R2_WS_RECONNECT_DELAY_SECONDS`, `config.R2_WS_CONNECT_TIMEOUT_SECONDS`
  - スナップショットから `request_id`、`r2_status`、`r2_status_at` を外す

- [ ] **Step 1: ステートマシンのテストを書き直す（失敗するテスト）**

`tests/test_state_machine.py` の先頭から `def test_pf_and_r2_get_status_are_recorded_with_timestamps` の終わりまでを、次で置き換える（`# --- check-in entry tracking ---` 以降は残す）：

```python
import pytest

from app.state_machine import (
    StateMachine,
    PHASE_WAITING,
    PHASE_ACTIVE,
    PHASE_ERROR,
    STEP_AWAITING_CHECKIN,
    STEP_STARTING_R2,
    STEP_WAITING_R2_PLACED,
    STEP_WAITING_R2_READY,
)


class FakeR2:
    """Scripted R2Controller: each wait walks through ``states`` until one fits.

    A state is a status string (connected) or a dict overriding snapshot keys.
    """

    def __init__(self, states=("completed",), start_result=None, after_start=("loading", "returning")):
        self.states = list(states)
        self.start_result = start_result
        self.after_start = list(after_start)
        self.start_calls = 0
        self.seen = []

    def _snapshot(self):
        state = self.states[0]
        snap = {"connection": "connected", "starting": False, "failure": None,
                "failure_message": None}
        snap.update({"status": state} if isinstance(state, str) else state)
        return snap

    def wait_until(self, predicate):
        while True:
            snap = self._snapshot()
            self.seen.append(snap["status"])
            if predicate(snap):
                return snap
            if len(self.states) == 1:
                raise AssertionError(f"would wait forever on {snap}")
            self.states.pop(0)

    def start_load_drink(self):
        self.start_calls += 1
        if self.start_result is None:
            self.states = list(self.after_start)
        return self.start_result


class FakePFClient:
    def __init__(self, status_sequence, placed_result=True):
        self._status_sequence = list(status_sequence)
        self.placed_result = placed_result
        self.placed_calls = 0

    def get_guide_robot_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_drink_placed(self):
        self.placed_calls += 1
        return self.placed_result


def make_state_machine(r2, pf, changes, sleeps, now=None):
    kwargs = dict(
        r2_controller=r2,
        pf_client=pf,
        on_change=changes.append,
        sleep=sleeps.append,
        poll_interval=2.0,
    )
    if now is not None:
        kwargs["now"] = now
    return StateMachine(**kwargs)


def test_try_start_from_awaiting_checkin_succeeds_and_transitions():
    changes = []
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), changes, [])

    assert sm.try_start("Tanaka") is True
    snap = sm.snapshot()
    assert snap["phase"] == PHASE_WAITING
    assert snap["step"] == "polling_pf_ready"
    assert snap["guest_name"] == "Tanaka"
    assert changes[-1] == snap


def test_snapshot_no_longer_carries_http_r2_fields():
    snap = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], []).snapshot()

    for key in ("request_id", "r2_status", "r2_status_at"):
        assert key not in snap


def test_state_machine_preserves_positional_constructor_arguments():
    r2 = FakeR2()
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2, pf, [].append, [].append, 2.0, lambda: "NOW")

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert r2.start_calls == 1


def test_try_start_fails_when_not_awaiting_checkin():
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], [])
    assert sm.try_start("Tanaka") is True
    assert sm.try_start("Suzuki") is False


def test_full_cycle_returns_to_waiting_awaiting_checkin():
    changes = []
    sleeps = []
    r2 = FakeR2(states=["loading", "completed"], after_start=["loading", "returning"])
    pf = FakePFClient(status_sequence=["initializing", "ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, sleeps)

    assert sm.try_start("Tanaka") is True
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["error_message"] is None
    assert r2.start_calls == 1
    assert pf.placed_calls == 1
    assert sleeps == [1.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    steps = [c["step"] for c in changes]
    for step in (STEP_WAITING_R2_READY, STEP_STARTING_R2, STEP_WAITING_R2_PLACED):
        assert step in steps


def test_cycle_passes_through_active_phase():
    changes = []
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert PHASE_ACTIVE in [c["phase"] for c in changes]


def test_ready_wait_keeps_waiting_while_disconnected():
    r2 = FakeR2(states=[{"connection": "disconnected", "status": "completed"}, "completed"])
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert r2.start_calls == 1
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_pf_fatal_error_moves_to_error_phase():
    sm = make_state_machine(FakeR2(), FakePFClient(["unexpected"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert "AI管制PF" in final["error_message"]
    assert final["guest_name"] == "Tanaka"


def test_r2_failed_during_ready_wait_moves_to_error_phase():
    r2 = FakeR2(states=[{"status": "failed", "failure_message": "オペレーターがSTOPしました"}])
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_WAITING_R2_READY)
    assert "STOP" in final["error_message"]
    assert r2.start_calls == 0


def test_r2_start_failure_moves_to_error_at_starting_r2():
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    sm = make_state_machine(r2, FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_STARTING_R2)
    assert "返事がありません" in final["error_message"]


def test_r2_failed_while_waiting_for_placement_moves_to_error():
    r2 = FakeR2(after_start=["loading", {"status": "failed", "failure_message": "動作中にR2との接続が切れました"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert (final["phase"], final["step"]) == (PHASE_ERROR, STEP_WAITING_R2_PLACED)
    assert "接続が切れました" in final["error_message"]
    assert pf.placed_calls == 0


def test_placed_wait_accepts_completed_after_a_quick_return():
    # _m5 and _m1 can both land before the state machine wakes up.
    r2 = FakeR2(after_start=["completed"])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert pf.placed_calls == 1
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_pf_drink_placed_not_accepted_moves_to_error_immediately():
    pf = FakePFClient(status_sequence=["ready"], placed_result=False)
    sm = make_state_machine(FakeR2(), pf, [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR
    assert pf.placed_calls == 1


def test_try_reset_from_error_returns_to_awaiting_checkin():
    sm = make_state_machine(FakeR2(states=["failed"]), FakePFClient(["ready"]), [], [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()
    assert sm.snapshot()["phase"] == PHASE_ERROR

    assert sm.try_reset() is True
    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["error_message"] is None


def test_try_reset_fails_when_not_in_error():
    sm = make_state_machine(FakeR2(), FakePFClient(["ready"]), [], [])
    assert sm.try_reset() is False


def test_pf_status_is_recorded_with_timestamp():
    timestamps = iter([f"2026-09-13T09:00:{i:02d}Z" for i in range(20)])
    sm = make_state_machine(
        FakeR2(), FakePFClient(["initializing", "ready"]), [], [], now=lambda: next(timestamps)
    )

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["pf_status"] == "ready"
    assert final["pf_status_at"] is not None


def test_resume_after_start_continues_from_placement_wait():
    changes = []
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])
    sm.try_start("Tanaka")
    sm.run_started_cycle()
    assert sm.can_resume_after_start() is True

    assert sm.try_resume_after_start() is True
    assert sm.snapshot()["phase"] == PHASE_WAITING
    assert sm.snapshot()["error_message"] is None

    r2.states = ["loading", "returning"]  # the operator's resend succeeded
    sm.resume_after_start()

    assert r2.start_calls == 1
    assert pf.placed_calls == 1
    assert STEP_WAITING_R2_PLACED in [c["step"] for c in changes]
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


@pytest.mark.parametrize("states", [["completed"], ["failed"]])
def test_resume_after_start_rejected_unless_stopped_at_starting_r2(states):
    sm = make_state_machine(FakeR2(states=states), FakePFClient(["ready"]), [], [])
    if states == ["failed"]:
        sm.try_start("Tanaka")
        sm.run_started_cycle()  # error at waiting_r2_ready

    assert sm.can_resume_after_start() is False
    assert sm.try_resume_after_start() is False
```

同じファイルの `_entry_state_machine` を次に変える：

```python
def _entry_state_machine(changes=None, clock=None, idle=60.0):
    sm = StateMachine(
        r2_controller=FakeR2(),
        pf_client=FakePFClient(["ready"]),
        on_change=(changes if changes is not None else []).append,
        sleep=lambda s: None,
        now=lambda: "2026-09-29T00:00:00Z",
        monotonic=clock or FakeClock(),
        entry_idle_seconds=idle,
    )
    return sm
```

ファイル末尾の `test_skip_load_drink_is_rejected_outside_sending_load_drink`、`SkippingR2Client`、`test_skip_while_load_drink_retries_moves_on_without_another_post`、`test_skip_after_load_drink_failed_resumes_from_polling_r2_active`、`test_request_id_mismatch_still_fails_when_not_skipped` を削除する。

`tests/test_state_machine_runner.py` 全体を次にする：

```python
import threading
import time

from app.state_machine import StateMachine, StateMachineRunner, PHASE_WAITING, STEP_AWAITING_CHECKIN


class FakeR2:
    def __init__(self, status="completed", start_result=None):
        self.status = status
        self.start_result = start_result

    def wait_until(self, predicate):
        while True:
            snap = {"connection": "connected", "status": self.status, "starting": False,
                    "failure": None, "failure_message": None}
            if predicate(snap):
                return snap
            time.sleep(0.01)

    def start_load_drink(self):
        if self.start_result is None:
            self.status = "returning"
        return self.start_result


class FakePFClient:
    def __init__(self, status_sequence, placed_result=True):
        self._status_sequence = list(status_sequence)
        self.placed_result = placed_result

    def get_guide_robot_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_drink_placed(self):
        return self.placed_result


def start_runner_thread(runner):
    thread = threading.Thread(target=runner.run_forever, daemon=True)
    thread.start()
    return thread


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def make_machine(r2, pf=None):
    return StateMachine(
        r2_controller=r2,
        pf_client=pf or FakePFClient(["ready"]),
        on_change=lambda snap: None,
        sleep=lambda s: None,
    )


def test_request_checkin_runs_cycle_in_background_thread():
    sm = make_machine(FakeR2())
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_checkin_rejected_while_cycle_in_progress():
    sm = make_machine(FakeR2(status="loading"))
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True
    assert wait_until(lambda: sm.snapshot()["step"] != STEP_AWAITING_CHECKIN)

    assert runner.request_checkin("Suzuki") is False


def test_request_reset_is_synchronous_and_does_not_need_the_thread():
    sm = make_machine(FakeR2(status="failed"))
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    assert runner.request_reset() is True
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


class RaisingPFClient:
    def get_guide_robot_status(self):
        raise RuntimeError("boom: unexpected failure deep in the client")

    def post_drink_placed(self):
        return True


def test_unexpected_exception_in_cycle_does_not_wedge_the_thread():
    sm = make_machine(FakeR2(), RaisingPFClient())
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    # The background thread must still be alive and able to service further
    # requests (i.e. it wasn't killed by the unhandled exception).
    assert runner.request_reset() is True
    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_reset_rejected_when_not_in_error():
    runner = StateMachineRunner(make_machine(FakeR2()))
    assert runner.request_reset() is False


def test_request_resume_after_start_continues_a_failed_start_on_the_thread():
    r2 = FakeR2(start_result="R2から開始の返事がありませんでした")
    sm = make_machine(r2)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")
    assert runner.can_resume_after_start() is True

    r2.status = "returning"  # the operator's resend succeeded
    assert runner.request_resume_after_start() is True
    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_resume_after_start_rejected_when_idle():
    runner = StateMachineRunner(make_machine(FakeR2()))
    assert runner.can_resume_after_start() is False
    assert runner.request_resume_after_start() is False
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_state_machine.py tests/test_state_machine_runner.py -q`
Expected: FAIL（`ImportError: cannot import name 'STEP_STARTING_R2'`）

- [ ] **Step 3: ステートマシンを書き換える**

`app/state_machine.py` で次のとおり変える。

定数（`STEP_POLLING_R2_READY` から `STEP_POLLING_R2_ACTIVE` の3行と `SKIP_PENDING`/`SKIP_RESUME`、`default_request_id` を消して）：

```python
from .clients.r2_controller import STATUS_COMPLETED, STATUS_FAILED, STATUS_LOADING

STEP_AWAITING_CHECKIN = "awaiting_checkin"
STEP_POLLING_PF_READY = "polling_pf_ready"
STEP_WAITING_R2_READY = "waiting_r2_ready"
STEP_STARTING_R2 = "starting_r2"
STEP_WAITING_R2_PLACED = "waiting_r2_placed"
STEP_NOTIFYING_PF_PLACED = "notifying_pf_placed"
```

モジュールに述語を足す：

```python
def _r2_ready_or_failed(snap):
    if snap["status"] == STATUS_FAILED:
        return True
    return (
        snap["connection"] == "connected"
        and snap["status"] == STATUS_COMPLETED
        and not snap["starting"]
    )


def _r2_placed_or_failed(snap):
    # completed counts too: _m5 and _m1 can both land before we wake up.
    return snap["status"] != STATUS_LOADING


def _r2_failure_text(snap):
    return snap.get("failure_message") or snap.get("failure") or "不明"
```

`__init__` のシグネチャと本体（`request_id_factory`、`_request_id`、`_r2_status`、`_r2_status_at`、`_load_drink_skipped` を消す）：

```python
    def __init__(
        self,
        r2_controller,
        pf_client,
        on_change,
        sleep=time.sleep,
        poll_interval=2.0,
        now=default_now,
        sequence_wait=1.0,
        monotonic=time.monotonic,
        entry_idle_seconds=DEFAULT_ENTRY_IDLE_SECONDS,
    ):
        self._r2 = r2_controller
        self._pf = pf_client
        self._on_change = on_change
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._sequence_wait = sequence_wait
        self._now = now
        self._monotonic = monotonic
        self._entry_idle_seconds = entry_idle_seconds

        self._lock = threading.Lock()
        self._phase = PHASE_WAITING
        self._step = STEP_AWAITING_CHECKIN
        self._guest_name = None
        self._error_message = None
        self._pf_status = None
        self._pf_status_at = None
        self._entry_source = None
        self._entry_stage = None
        self._entry_at = None
        self._entry_touched = None
```

`_snapshot_locked` から `"request_id"`、`"r2_status"`、`"r2_status_at"` の3行を消す。`_record_r2_status` を消す。`try_start` の `self._request_id = None` と `self._load_drink_skipped = False` を消す。`_to_waiting_step0` の `request_id=None,` を消す。

`try_skip_load_drink` と `resume_after_load_drink` を消し、代わりに次を足す：

```python
    def can_resume_after_start(self):
        with self._lock:
            return self._phase == PHASE_ERROR and self._step == STEP_STARTING_R2

    def try_resume_after_start(self):
        """Clear a failed start once the operator's resend has started R2."""
        with self._lock:
            if not (self._phase == PHASE_ERROR and self._step == STEP_STARTING_R2):
                return False
            self._phase = PHASE_WAITING
            self._error_message = None
            self._on_change(self._snapshot_locked())
        return True

    def resume_after_start(self):
        self._run_after_start()
```

`run_started_cycle` 以降の R2 部分を次にする（`_poll_r2_ready`、`_send_load_drink`、`_poll_r2_active`、`_run_after_load_drink` を消す）：

```python
    def run_started_cycle(self):
        self._wait_before_step()
        if not self._poll_pf_ready():
            return
        self._update(step=STEP_WAITING_R2_READY)
        self._wait_before_step()
        if not self._wait_r2_ready():
            return
        self._update(step=STEP_STARTING_R2)
        self._wait_before_step()
        if not self._start_r2():
            return
        self._run_after_start()

    def _run_after_start(self):
        self._update(phase=PHASE_ACTIVE, step=STEP_WAITING_R2_PLACED)
        self._wait_before_step()
        if not self._wait_r2_placed():
            return
        self._update(step=STEP_NOTIFYING_PF_PLACED)
        self._wait_before_step()
        if not self._notify_pf_placed():
            return
        self._to_waiting_step0()

    def _wait_r2_ready(self):
        snap = self._r2.wait_until(_r2_ready_or_failed)
        if snap["status"] == STATUS_FAILED:
            self._fail(f"R2が failed です: {_r2_failure_text(snap)}")
            return False
        return True

    def _start_r2(self):
        reason = self._r2.start_load_drink()
        if reason:
            self._fail(f"R2の開始に失敗しました: {reason}")
            return False
        return True

    def _wait_r2_placed(self):
        snap = self._r2.wait_until(_r2_placed_or_failed)
        if snap["status"] == STATUS_FAILED:
            self._fail(f"R2の動作が止まりました: {_r2_failure_text(snap)}")
            return False
        return True
```

`StateMachineRunner` の `request_skip_load_drink` を消し、代わりに：

```python
    def can_resume_after_start(self):
        return self._state_machine.can_resume_after_start()

    def request_resume_after_start(self):
        resumed = self._state_machine.try_resume_after_start()
        if resumed:
            self._start_signal.put(self._state_machine.resume_after_start)
        return resumed
```

Run: `.venv/bin/python -m pytest tests/test_state_machine.py tests/test_state_machine_runner.py -q`
Expected: 全件 PASS

- [ ] **Step 4: 設定・アプリの組み立て・周辺のテストを書き直す（失敗するテスト）**

`tests/test_config.py` の `test_defaults_when_env_not_set` と `test_env_overrides` を次に変える（`test_dotenv_values_are_loaded` の `monkeypatch.delenv("R2_BASE_URL", raising=False)` の行は消す）：

```python
R2_ENV = (
    "R2_WS_URL",
    "R2_START_REPLY_TIMEOUT_SECONDS",
    "R2_WS_RECONNECT_DELAY_SECONDS",
    "R2_WS_CONNECT_TIMEOUT_SECONDS",
)


def test_defaults_when_env_not_set(monkeypatch, tmp_path):
    for name in R2_ENV + (
        "PF_BASE_URL",
        "PF_API_KEY",
        "PF_PROXY_URL",
        "POLL_INTERVAL_SECONDS",
        "HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_WS_URL == "ws://127.0.0.1:9002/realtime"
    assert config.R2_START_REPLY_TIMEOUT_SECONDS == 15.0
    assert config.R2_WS_RECONNECT_DELAY_SECONDS == 1.0
    assert config.R2_WS_CONNECT_TIMEOUT_SECONDS == 5.0
    assert config.PF_BASE_URL == "http://localhost:5002"
    assert config.PF_API_KEY == ""
    assert config.PF_PROXY_URL == ""
    assert config.POLL_INTERVAL_SECONDS == 2.0
    assert config.HTTP_TIMEOUT_SECONDS == 5.0
    for removed in ("R2_BASE_URL", "DRINK_TYPE", "TARGET_ROBOT_ID"):
        assert not hasattr(config, removed)


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("R2_WS_URL", "ws://10.17.4.171:9002/realtime")
    monkeypatch.setenv("R2_START_REPLY_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("R2_WS_RECONNECT_DELAY_SECONDS", "2")
    monkeypatch.setenv("R2_WS_CONNECT_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("PF_BASE_URL", "http://pf.example.com")
    monkeypatch.setenv("PF_API_KEY", "test-key")
    monkeypatch.setenv("PF_PROXY_URL", "http://115.69.226.50:8080")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "3")
    monkeypatch.chdir(tmp_path)

    from app import config
    importlib.reload(config)

    assert config.R2_WS_URL == "ws://10.17.4.171:9002/realtime"
    assert config.R2_START_REPLY_TIMEOUT_SECONDS == 20.0
    assert config.R2_WS_RECONNECT_DELAY_SECONDS == 2.0
    assert config.R2_WS_CONNECT_TIMEOUT_SECONDS == 3.0
    assert config.PF_BASE_URL == "http://pf.example.com"
    assert config.PF_API_KEY == "test-key"
    assert config.PF_PROXY_URL == "http://115.69.226.50:8080"
    assert config.POLL_INTERVAL_SECONDS == 1.5
    assert config.HTTP_TIMEOUT_SECONDS == 3.0
```

`tests/test_app_factory.py` の `FakeR2Client` を次で置き換え、ファイル内の `create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())` をすべて `create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())` に置き換える（`sed -i 's/create_app(r2_client=FakeR2Client()/create_app(r2_controller=FakeR2Controller()/' tests/test_app_factory.py`）：

```python
class FakeR2Controller:
    """An R2 that is always connected and loads the drink instantly."""

    def __init__(self):
        self.listeners = []

    def snapshot(self):
        return {"connection": "connected", "status": "completed", "starting": False,
                "failure": None, "failure_message": None}

    def wait_until(self, predicate):
        snap = self.snapshot()
        assert predicate(snap)
        return snap

    def start_load_drink(self):
        return None

    def add_listener(self, listener):
        self.listeners.append(listener)
```

同じファイルの末尾に足す：

```python
def test_default_app_builds_an_r2_link_without_starting_it_when_asked(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "R2_WS_URL", "ws://r2.test:9002/realtime")
    app = create_app(pf_client=FakePFClient(), start_r2=False)

    link = app.config["R2_LINK"]
    assert link.url == "ws://r2.test:9002/realtime"
    assert link.state()[0] == "stopped"
    assert app.config["R2_CONTROLLER"].snapshot()["status"] == "completed"
```

`tests/test_routes_checkin.py`：`FakeRunner` から `skip_result`、`skip_calls`、`request_skip_load_drink` を消し、`test_skip_load_drink_accepted` と `test_skip_load_drink_rejected_when_not_sending_load_drink` を削除し、次を足す：

```python
def test_skip_load_drink_endpoint_is_gone():
    client = make_client(FakeRunner())

    assert client.post("/api/debug/skip-load-drink").status_code == 404
```

`tests/test_routes_debug.py` の `test_debug_page_shows_connection_targets` を次に変える：

```python
def test_debug_page_shows_connection_targets():
    client = make_client()

    resp = client.get("/debug")

    assert resp.status_code == 200
    assert b'id="r2-ws-url"' in resp.data
    assert b'id="pf-base-url"' in resp.data
```

`tests/test_integration_mocks.py` を PF だけにする：先頭の docstring を `"""Integration test: binds the real PFClient to the real PF mock over actual HTTP."""` に変え、`R2Client` と `create_r2_mock_app` の import、fixture 内の `R2_MOCK_*` の `setenv` と `r2_server`、`"r2_url"` を消す。テスト関数を次にする：

```python
def test_real_pf_client_against_real_pf_mock(mock_servers):
    pf = PFClient(
        base_url=mock_servers["pf_url"], timeout=2.0, api_key="test-key"
    )

    # PF starts ready (no PF_MOCK_INITIALIZING_SECONDS set).
    assert pf.get_guide_robot_status() == "ready"
    assert pf.post_drink_placed() is True
```

- [ ] **Step 5: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_app_factory.py tests/test_routes_checkin.py tests/test_routes_debug.py tests/test_integration_mocks.py -q`
Expected: FAIL（`config.R2_WS_URL` がない、`create_app()` が `r2_controller` を受け取らない、など）

- [ ] **Step 6: 設定・組み立て・ルートを書き換え、古いものを消す**

`app/config.py`：`R2_BASE_URL`、`DRINK_TYPE`、`TARGET_ROBOT_ID` の行を消し、`PF_BASE_URL` の前に足す：

```python
R2_WS_URL = os.environ.get("R2_WS_URL", "ws://127.0.0.1:9002/realtime")
R2_START_REPLY_TIMEOUT_SECONDS = float(os.environ.get("R2_START_REPLY_TIMEOUT_SECONDS", "15"))
R2_WS_RECONNECT_DELAY_SECONDS = float(os.environ.get("R2_WS_RECONNECT_DELAY_SECONDS", "1"))
R2_WS_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("R2_WS_CONNECT_TIMEOUT_SECONDS", "5"))
```

`app/__init__.py`：import の `from .clients.r2_client import R2Client` を次の2行に替える：

```python
from .clients.r2_controller import R2Controller
from .clients.r2_link import R2Link
```

`create_app` の先頭部分を次にする：

```python
def create_app(r2_controller=None, pf_client=None, reservation_store=None, start_r2=True):
    app = Flask(__name__)

    r2_link = None
    if r2_controller is None:
        r2_link = R2Link(
            config.R2_WS_URL,
            reconnect_delay=config.R2_WS_RECONNECT_DELAY_SECONDS,
            connect_timeout=config.R2_WS_CONNECT_TIMEOUT_SECONDS,
        )
        r2_controller = R2Controller(
            r2_link, start_reply_timeout=config.R2_START_REPLY_TIMEOUT_SECONDS
        )
```

`StateMachine(` の呼び出しの `r2_client=r2_client,` を `r2_controller=r2_controller,` に替える。`app.config["STATE_MACHINE_RUNNER"] = runner` の次に足す：

```python
    app.config["R2_CONTROLLER"] = r2_controller
    app.config["R2_LINK"] = r2_link
```

`thread.start()` の次に足す：

```python
    if r2_link is not None and start_r2:
        r2_link.start()
```

`app/routes/checkin.py`：`skip_load_drink`（`/api/debug/skip-load-drink`）の関数を消す。

`app/routes/ui.py` の `debug()`：

```python
@ui_bp.route("/debug")
def debug():
    return render_template(
        "debug.html",
        r2_ws_url=config.R2_WS_URL,
        pf_base_url=config.PF_BASE_URL,
    )
```

`app/templates/debug.html` の接続先の R2 の行：

```html
      <dt>R2 (Humanoid)</dt><dd id="r2-ws-url">{{ r2_ws_url }}</dd>
```

`app/static/app.js` の `STEP_MESSAGES`（文言は変えない）：

```javascript
const STEP_MESSAGES = {
  polling_pf_ready: "AI管制PF(案内ロボット)の状態を確認しています",
  waiting_r2_ready: "ドリンク準備ロボットの状態を確認しています",
  starting_r2: "ドリンクをセットしています",
  waiting_r2_placed: "ドリンクを積み込み中です",
  notifying_pf_placed: "積み込み完了をAI管制PFに通知しています",
};
```

`.env.example`：先頭のブロックを次にする：

```
# Local mock servers (default). R2 is driven over the gamepad-server WebSocket;
# run_mocks.py serves /realtime on :9002. On site, point this at spark-60c9's
# forwarded port (see README "R2 (THEMIS) への接続").
R2_WS_URL=ws://127.0.0.1:9002/realtime
PF_BASE_URL=http://localhost:5002
```

`DRINK_TYPE=water` と `TARGET_ROBOT_ID=temi` の行を消し、`HTTP_TIMEOUT_SECONDS=5` の次に足す：

```
# Seconds to wait for R2's reply to play_navigation5
R2_START_REPLY_TIMEOUT_SECONDS=15
R2_WS_RECONNECT_DELAY_SECONDS=1
R2_WS_CONNECT_TIMEOUT_SECONDS=5
```

`# Mock server behavior` の `R2_MOCK_RETURNING_SECONDS=3`、`# Empty, or 422 / 500 / failed`、`R2_MOCK_FORCE_FAILURE=` の3行を次に替える：

```
# Seconds per under_mode step of the /realtime mock
R2_MOCK_STEP_SECONDS=3
# success / fail / none (reply to play_navigation5)
R2_MOCK_START_REPLY=success
```

古いものを消す：

```bash
git rm app/clients/r2_client.py mocks/r2_mock.py tests/test_r2_client.py tests/test_r2_mock.py
```

- [ ] **Step 7: 全テストが通ることを確かめる**

Run: `PYTEST`（Global Constraints のコマンド）と、別に `.venv/bin/python -m pytest tests/test_integration_mocks.py -q`
Expected: 全件 PASS。`grep -rn "r2_client\|R2_BASE_URL\|skip-load-drink\|polling_r2\|sending_load_drink" app mocks run.py run_mocks.py tests` が何も出さない（`app/static/debug.js` と `app/templates/debug.html` のシーケンス図・スキップボタンは Task 6 で直すので、そこだけ出てよい）。

- [ ] **Step 8: コミットする**

```bash
git add -A app mocks tests .env.example run_mocks.py
git commit -m "feat: run the R2 part of the state machine on R2Controller

Replace the HTTP R2 client and mock: the state machine now waits for
R2Controller's status, and a failed start resumes after the operator
resends it instead of skipping POST load-drink.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `/debug` 用の R2 API、SSE の `r2_state`、リローダー対策

**Files:**
- Create: `app/routes/r2_debug.py`
- Modify: `app/__init__.py`、`run.py`
- Test: `tests/test_routes_r2_debug.py`、`tests/test_app_factory.py`、`tests/test_run.py`（新規）

**Interfaces:**
- Consumes（Task 2, 4）：`R2Controller` の操作、`StateMachineRunner.can_resume_after_start()`、`request_resume_after_start()`、`app.config["R2_CONTROLLER"]`
- Produces：`GET /api/debug/r2`、`POST /api/debug/r2/{connect,disconnect,stop,resend,mark,reset}`（成功は 200＋スナップショット、断るときは 409＋`{"message"}`、`mark` の status なしは 422）。SSE の `{"type": "r2_state", ...snapshot}`。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_r2_debug.py`：

```python
import pytest
from flask import Flask

from app.routes.r2_debug import r2_debug_bp


class FakeController:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def snapshot(self):
        return {"status": "completed", "connection": "connected"}

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        return self.result

    def connect(self):
        return self._call("connect")

    def disconnect(self):
        return self._call("disconnect")

    def stop(self):
        return self._call("stop")

    def reset(self):
        return self._call("reset")

    def mark(self, status):
        return self._call("mark", status)

    def resend_start(self):
        return self._call("resend_start")


class FakeRunner:
    def __init__(self, can_resume=True):
        self.can_resume = can_resume
        self.resume_calls = 0

    def can_resume_after_start(self):
        return self.can_resume

    def request_resume_after_start(self):
        self.resume_calls += 1
        return True


def make_client(controller, runner=None):
    app = Flask(__name__)
    app.config["R2_CONTROLLER"] = controller
    app.config["STATE_MACHINE_RUNNER"] = runner or FakeRunner()
    app.register_blueprint(r2_debug_bp)
    return app.test_client()


def test_get_returns_snapshot():
    resp = make_client(FakeController()).get("/api/debug/r2")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "completed", "connection": "connected"}


@pytest.mark.parametrize("action", ["connect", "disconnect", "stop", "reset"])
def test_simple_actions(action):
    controller = FakeController()
    resp = make_client(controller).post(f"/api/debug/r2/{action}")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"
    assert controller.calls == [(action,)]


def test_refused_action_returns_409_with_reason():
    controller = FakeController(result="R2に接続していません")

    resp = make_client(controller).post("/api/debug/r2/stop")

    assert resp.status_code == 409
    assert resp.get_json() == {"message": "R2に接続していません"}


def test_mark_passes_status():
    controller = FakeController()

    resp = make_client(controller).post("/api/debug/r2/mark", json={"status": "returning"})

    assert resp.status_code == 200
    assert controller.calls == [("mark", "returning")]


def test_mark_requires_status():
    resp = make_client(FakeController()).post("/api/debug/r2/mark", json={})

    assert resp.status_code == 422


def test_resend_resumes_the_state_machine():
    controller = FakeController()
    runner = FakeRunner()

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 200
    assert controller.calls == [("resend_start",)]
    assert runner.resume_calls == 1


def test_resend_rejected_unless_state_machine_stopped_at_start():
    controller = FakeController()
    runner = FakeRunner(can_resume=False)

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 409
    assert controller.calls == []
    assert runner.resume_calls == 0


def test_failed_resend_does_not_resume():
    controller = FakeController(result="R2から開始の返事がありませんでした")
    runner = FakeRunner()

    resp = make_client(controller, runner).post("/api/debug/r2/resend")

    assert resp.status_code == 409
    assert runner.resume_calls == 0
```

`tests/test_app_factory.py` の末尾に足す：

```python
def test_r2_changes_are_published_as_typed_sse_events():
    controller = FakeR2Controller()
    app = create_app(r2_controller=controller, pf_client=FakePFClient())
    subscriber = app.config["EVENT_BROADCASTER"].subscribe()

    controller.listeners[0]({"status": "loading", "connection": "connected"})

    assert subscriber.get(timeout=1) == {
        "type": "r2_state",
        "status": "loading",
        "connection": "connected",
    }


def test_r2_debug_routes_are_registered():
    app = create_app(r2_controller=FakeR2Controller(), pf_client=FakePFClient())

    assert app.test_client().get("/api/debug/r2").status_code == 200
```

`tests/test_run.py`：

```python
import importlib
import sys


def test_run_module_does_not_start_r2_outside_reloader_child(monkeypatch):
    monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
    sys.modules.pop("run", None)

    run = importlib.import_module("run")

    assert run.app.config["R2_LINK"].state()[0] == "stopped"
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_routes_r2_debug.py tests/test_app_factory.py tests/test_run.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.routes.r2_debug'` など）

- [ ] **Step 3: 実装する**

`app/routes/r2_debug.py`：

```python
"""Operator controls for R2 on the debug page."""

from flask import Blueprint, current_app, jsonify, request

r2_debug_bp = Blueprint("r2_debug", __name__)


def _controller():
    return current_app.config["R2_CONTROLLER"]


def _respond(reason):
    if reason:
        return jsonify({"message": reason}), 409
    return jsonify(_controller().snapshot()), 200


@r2_debug_bp.route("/api/debug/r2", methods=["GET"])
def r2_state():
    return jsonify(_controller().snapshot())


@r2_debug_bp.route("/api/debug/r2/connect", methods=["POST"])
def r2_connect():
    return _respond(_controller().connect())


@r2_debug_bp.route("/api/debug/r2/disconnect", methods=["POST"])
def r2_disconnect():
    return _respond(_controller().disconnect())


@r2_debug_bp.route("/api/debug/r2/stop", methods=["POST"])
def r2_stop():
    return _respond(_controller().stop())


@r2_debug_bp.route("/api/debug/r2/reset", methods=["POST"])
def r2_reset():
    return _respond(_controller().reset())


@r2_debug_bp.route("/api/debug/r2/mark", methods=["POST"])
def r2_mark():
    status = (request.get_json(silent=True) or {}).get("status")
    if not status:
        return jsonify({"message": "status is required"}), 422
    return _respond(_controller().mark(status))


@r2_debug_bp.route("/api/debug/r2/resend", methods=["POST"])
def r2_resend():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    # Never move R2 unless a stopped cycle is there to pick it up.
    if not runner.can_resume_after_start():
        return jsonify(
            {"message": "ステートマシンが R2 の開始の失敗で止まっているときだけ再送できます"}
        ), 409
    reason = _controller().resend_start()
    if reason:
        return jsonify({"message": reason}), 409
    runner.request_resume_after_start()
    return jsonify(_controller().snapshot()), 200
```

`app/__init__.py`：import に `from .routes.r2_debug import r2_debug_bp` を足し、`app.register_blueprint(voice_turns_bp)` の次に `app.register_blueprint(r2_debug_bp)` を足す。`app.config["R2_LINK"] = r2_link` の次に足す：

```python
    r2_controller.add_listener(
        lambda snap: broadcaster.publish({"type": "r2_state", **snap})
    )
```

`run.py` 全体：

```python
import os

from app import create_app

# run() below uses debug=True, so the reloader's parent process imports this
# module too. Only the child that serves requests may connect to R2; two
# connections from one host would both act on R2's /realtime.
app = create_app(start_r2=os.environ.get("WERKZEUG_RUN_MAIN") == "true")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, threaded=True, debug=True)
```

- [ ] **Step 4: テストが通ることを確かめる**

Run: `PYTEST`
Expected: 全件 PASS

- [ ] **Step 5: コミットする**

```bash
git add app/routes/r2_debug.py app/__init__.py run.py tests/test_routes_r2_debug.py tests/test_app_factory.py tests/test_run.py
git commit -m "feat: add R2 operator API and stream R2 state to the debug page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `/debug` の R2 パネルとシーケンス図

画面はユーザーが実際に見てから調整する。ここでは spec の「/debug」の内容を最初の形として作る。

**Files:**
- Modify: `app/templates/debug.html`、`app/static/debug.js`、`app/static/debug.css`
- Test: `tests/test_routes_debug.py`

**Interfaces:**
- Consumes（Task 5）：`GET /api/debug/r2`、`POST /api/debug/r2/*`、SSE の `r2_state`、`/api/reset`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_debug.py` で：
- `test_debug_page_has_all_step_arrows` の id の一覧を `["arrow-polling_pf_ready", "arrow-waiting_r2_ready", "arrow-starting_r2", "arrow-waiting_r2_placed", "arrow-notifying_pf_placed"]` にする。
- `test_debug_page_has_get_status_panel` から `r2-status-value` と `r2-status-at` の2行を消し、`assert b'id="r2-status-value"' not in resp.data` を足す。
- `test_debug_js_handles_voice_turns_and_skips_other_typed_events` を次にする：

```python
def test_debug_js_handles_typed_events_before_rendering_snapshots():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert re.search(
        r"if \(payload\.type\) \{\s*if \(payload\.type === \"voice_turn\"\) \{\s*addVoiceTurn\(payload\);\s*\}\s*"
        r"if \(payload\.type === \"r2_state\"\) \{\s*renderR2\(payload\);\s*\}\s*return;\s*\}\s*render\(payload\);",
        source,
    )
```

- `test_debug_page_has_skip_load_drink_button` を削除し、次を足す：

```python
def test_debug_page_has_r2_panel():
    resp = make_client().get("/debug")

    for element_id in [
        "r2-panel",
        "r2-connection",
        "r2-connection-at",
        "r2-status",
        "r2-status-at",
        "r2-failure",
        "r2-under-mode",
        "r2-under-mode-at",
        "r2-last-reply",
        "r2-toggle-connection",
        "r2-stop",
        "r2-resend",
        "r2-mark-returning",
        "r2-mark-completed",
        "r2-mark-failed",
        "r2-reset",
        "r2-confirm",
        "r2-result",
        "r2-hint",
        "state-machine-reset",
    ]:
        assert f'id="{element_id}"'.encode() in resp.data
    assert b'id="skip-load-drink"' not in resp.data


def test_debug_js_drives_r2_api_and_confirms_risky_actions():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'fetch("/api/debug/r2")' in source
    for action in ["connect", "disconnect", "stop", "resend", "mark", "reset"]:
        assert f'"{action}"' in source
    assert "temi が出発します" in source
    assert "R2 が A にいることを確認しましたか" in source
    assert 'fetch("/api/reset", { method: "POST" })' in source
    # No browser dialogs: they block the page (and automation).
    for dialog in ["confirm(", "alert(", "prompt("]:
        assert dialog not in source
    assert "innerHTML" not in source


def test_debug_sequence_diagram_describes_the_websocket_exchange():
    text = make_client().get("/debug").data.decode()

    assert "play_navigation5" in text
    assert "under_mode" in text
    assert "GET load-drink/status" not in text
    assert "POST load-drink" not in text
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `.venv/bin/python -m pytest tests/test_routes_debug.py -q`
Expected: FAIL（`r2-panel` がない など）

- [ ] **Step 3: `debug.html` を書き換える**

`<div id="debug-error" hidden>` のブロックを次にする：

```html
    <div id="debug-error" hidden>
      <p id="debug-error-message"></p>
      <button type="button" id="state-machine-reset">ステートマシンをリセット</button>
    </div>
```

`<h2 class="section-label">手動操作</h2>` から `</div>`（`manual-controls` の終わり）までを次で置き換える：

```html
    <h2 class="section-label">R2</h2>
    <div id="r2-panel" class="r2-connection-disconnected">
      <div class="r2-row">
        <span id="r2-connection" class="r2-badge">-</span>
        <span class="r2-at">（<span id="r2-connection-at">-</span> から）</span>
        <button type="button" id="r2-toggle-connection">接続</button>
      </div>
      <dl class="r2-fields">
        <dt>status</dt><dd><span id="r2-status">-</span> <span class="r2-at"><span id="r2-status-at">-</span> に変化</span></dd>
        <dt>failed の理由</dt><dd id="r2-failure">-</dd>
        <dt>under_mode</dt><dd><span id="r2-under-mode">-</span> <span class="r2-at"><span id="r2-under-mode-at">-</span> に変化</span></dd>
        <dt>開始の返事</dt><dd id="r2-last-reply">-</dd>
      </dl>
      <div class="r2-buttons">
        <button type="button" id="r2-stop" class="r2-danger">STOP</button>
        <button type="button" id="r2-resend">開始を再送</button>
        <button type="button" id="r2-mark-returning">returning にする</button>
        <button type="button" id="r2-mark-completed">completed にする</button>
        <button type="button" id="r2-mark-failed">failed にする</button>
        <button type="button" id="r2-reset">R2 を初期状態に戻す</button>
      </div>
      <div id="r2-confirm" hidden>
        <p id="r2-confirm-message"></p>
        <button type="button" id="r2-confirm-yes">実行する</button>
        <button type="button" id="r2-confirm-no">やめる</button>
      </div>
      <p id="r2-hint"></p>
      <p id="r2-result"></p>
    </div>
```

「GETステータス最新取得」の R2 の行（`R2: GET load-drink/status` の `get-status-row` の div）を消す。

シーケンス図の3つの `<g>` を次で置き換える：

```html
        <g id="arrow-waiting_r2_ready" class="arrow">
          <line class="msg-request" x1="280" y1="220" x2="700" y2="220" marker-end="url(#arrowhead)"></line>
          <text x="490" y="212">WebSocket /realtime 接続を確認</text>
          <line class="msg-response" x1="700" y1="250" x2="280" y2="250" marker-end="url(#arrowhead)"></line>
          <text x="490" y="242">接続中 かつ status = completed</text>
        </g>

        <g id="arrow-starting_r2" class="arrow">
          <line class="msg-request" x1="280" y1="300" x2="700" y2="300" marker-end="url(#arrowhead)"></line>
          <text x="490" y="292">gamepad NAVIGATION → play_navigation5(true)</text>
          <line class="msg-response" x1="700" y1="330" x2="280" y2="330" marker-end="url(#arrowhead)"></line>
          <text x="490" y="322">play_navigation5_rp success</text>
        </g>

        <g id="arrow-waiting_r2_placed" class="arrow">
          <line class="msg-response" x1="700" y1="380" x2="280" y2="380" marker-end="url(#arrowhead)"></line>
          <text x="490" y="372">robot_aggregator（under_mode）</text>
          <line class="msg-response" x1="700" y1="410" x2="280" y2="410" marker-end="url(#arrowhead)"></line>
          <text x="490" y="402">under_mode _m5 → returning</text>
        </g>
```

- [ ] **Step 4: `debug.js` を書き換える**

`STEPS` と `ROW_BOUNDS` の R2 の3つを新しい名前にする：

```javascript
const STEPS = [
  "awaiting_checkin",
  "polling_pf_ready",
  "waiting_r2_ready",
  "starting_r2",
  "waiting_r2_placed",
  "notifying_pf_placed",
];

const ROW_BOUNDS = {
  awaiting_checkin: { y: 75, height: 30 },
  polling_pf_ready: { y: 125, height: 60 },
  waiting_r2_ready: { y: 205, height: 60 },
  starting_r2: { y: 285, height: 60 },
  waiting_r2_placed: { y: 365, height: 60 },
  notifying_pf_placed: { y: 445, height: 60 },
};
```

`const r2StatusValue = ...` と `const r2StatusAt = ...` の2行を消す。`skipLoadDrinkButton`、`skipLoadDrinkResult` とそのクリック処理（`skipLoadDrinkButton.addEventListener(...)` のブロック）を消す。`render()` から `skipLoadDrinkButton.disabled = ...` と `r2StatusValue...`、`r2StatusAt...` の行を消す。

`function render(snapshot) {` の前に次を足す：

```javascript
const CONNECTION_LABELS = {
  connected: "● 接続中",
  connecting: "● 接続試行中",
  disconnected: "● 未接続",
  stopped: "● 切断中（手動）",
};

const r2Panel = document.getElementById("r2-panel");
const r2Connection = document.getElementById("r2-connection");
const r2ConnectionAt = document.getElementById("r2-connection-at");
const r2ToggleConnection = document.getElementById("r2-toggle-connection");
const r2Status = document.getElementById("r2-status");
const r2StatusAt = document.getElementById("r2-status-at");
const r2Failure = document.getElementById("r2-failure");
const r2UnderMode = document.getElementById("r2-under-mode");
const r2UnderModeAt = document.getElementById("r2-under-mode-at");
const r2LastReply = document.getElementById("r2-last-reply");
const r2Confirm = document.getElementById("r2-confirm");
const r2ConfirmMessage = document.getElementById("r2-confirm-message");
const r2Result = document.getElementById("r2-result");
const r2Hint = document.getElementById("r2-hint");

// Each button: the API action, an optional body, an optional confirmation,
// and when it may be pressed (mirrors R2Controller; the server re-checks).
const R2_BUTTONS = {
  "r2-stop": {
    action: "stop",
    confirm: "R2 を止めます（その場で立ち止まり、status は failed になります）。",
    hint: "R2 に接続しているときだけ",
    enabled: (s) => s.connection === "connected",
  },
  "r2-resend": {
    action: "resend",
    hint: "開始の失敗で failed、かつ under_mode が _m1 のときだけ",
    enabled: (s) =>
      s.status === "failed" &&
      ["start_no_reply", "start_rejected", "start_disconnected"].includes(s.failure) &&
      typeof s.under_mode === "string" &&
      s.under_mode.split("_m")[1] === "1" &&
      s.connection === "connected",
  },
  "r2-mark-returning": {
    action: "mark",
    body: { status: "returning" },
    confirm: "置き終わったものとして AI管制PF に drink/placed を送り、temi が出発します。",
    hint: "status が loading のときだけ",
    enabled: (s) => s.status === "loading",
  },
  "r2-mark-completed": {
    action: "mark",
    body: { status: "completed" },
    hint: "status が returning のときだけ",
    enabled: (s) => s.status === "returning",
  },
  "r2-mark-failed": {
    action: "mark",
    body: { status: "failed" },
    hint: "status が loading / returning のときだけ",
    enabled: (s) => s.status === "loading" || s.status === "returning",
  },
  "r2-reset": {
    action: "reset",
    confirm: "R2 が A にいることを確認しましたか？ status を completed に戻します。",
    hint: "status が failed のときだけ",
    enabled: (s) => s.status === "failed",
  },
};

let r2Snapshot = null;
let pendingR2Action = null;

function postR2(action, body) {
  r2Result.textContent = "送信中…";
  fetch("/api/debug/r2/" + action, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  })
    .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data })))
    .then(({ ok, data }) => {
      r2Result.textContent = ok ? "完了" : data.message || "受け付けられませんでした";
      if (ok) {
        renderR2(data);
      }
    })
    .catch(() => {
      r2Result.textContent = "送信に失敗しました";
    });
}

Object.entries(R2_BUTTONS).forEach(([id, spec]) => {
  document.getElementById(id).addEventListener("click", () => {
    if (!spec.confirm) {
      postR2(spec.action, spec.body);
      return;
    }
    pendingR2Action = spec;
    r2ConfirmMessage.textContent = spec.confirm;
    r2Confirm.hidden = false;
  });
});

document.getElementById("r2-confirm-yes").addEventListener("click", () => {
  r2Confirm.hidden = true;
  if (pendingR2Action) {
    postR2(pendingR2Action.action, pendingR2Action.body);
    pendingR2Action = null;
  }
});

document.getElementById("r2-confirm-no").addEventListener("click", () => {
  r2Confirm.hidden = true;
  pendingR2Action = null;
});

r2ToggleConnection.addEventListener("click", () => {
  const live = r2Snapshot && ["connected", "connecting", "disconnected"].includes(r2Snapshot.connection);
  postR2(live ? "disconnect" : "connect");
});

document.getElementById("state-machine-reset").addEventListener("click", () => {
  fetch("/api/reset", { method: "POST" }).catch(() => {});
});

function formatReply(snapshot) {
  if (!snapshot.last_reply) {
    return "-";
  }
  const seconds =
    typeof snapshot.last_reply_seconds === "number"
      ? `（受信まで ${snapshot.last_reply_seconds.toFixed(1)} 秒）`
      : "";
  return `${JSON.stringify(snapshot.last_reply)} ${toSecondsTime(snapshot.last_reply_at)}${seconds}`;
}

function renderR2(snapshot) {
  r2Snapshot = snapshot;
  r2Panel.className = "r2-connection-" + snapshot.connection;
  r2Connection.textContent = CONNECTION_LABELS[snapshot.connection] || snapshot.connection;
  r2ConnectionAt.textContent = toSecondsTime(snapshot.connection_at);
  r2ToggleConnection.textContent = snapshot.connection === "stopped" ? "接続" : "切断";
  r2Status.textContent = snapshot.starting ? `${snapshot.status}（開始中）` : snapshot.status;
  r2StatusAt.textContent = toSecondsTime(snapshot.status_at);
  r2Failure.textContent = snapshot.failure
    ? `${snapshot.failure_message}（${snapshot.failure}）`
    : "-";
  r2UnderMode.textContent = snapshot.under_mode || "-";
  r2UnderModeAt.textContent = toSecondsTime(snapshot.under_mode_at);
  r2LastReply.textContent = formatReply(snapshot);
  Object.entries(R2_BUTTONS).forEach(([id, spec]) => {
    const button = document.getElementById(id);
    button.disabled = snapshot.starting || !spec.enabled(snapshot);
    button.title = button.disabled ? spec.hint : "";
  });
  r2Hint.textContent = Object.entries(R2_BUTTONS)
    .filter(([id]) => document.getElementById(id).disabled)
    .map(([id, spec]) => `${document.getElementById(id).textContent}: ${spec.hint}`)
    .join(" / ");
}

fetch("/api/debug/r2")
  .then((resp) => resp.json())
  .then(renderR2)
  .catch(() => {});
```

`eventSource.onmessage` の種類付きイベントの分岐を次にする：

```javascript
  if (payload.type) {
    if (payload.type === "voice_turn") {
      addVoiceTurn(payload);
    }
    if (payload.type === "r2_state") {
      renderR2(payload);
    }
    return;
  }
```

- [ ] **Step 5: `debug.css` を書き換える**

`#manual-controls` から `.manual-hint` までの4つのルールを次で置き換える：

```css
#r2-panel {
  border: 2px solid #ccc;
  border-radius: 4px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

#r2-panel.r2-connection-connected {
  border-color: #1e8e3e;
}

#r2-panel.r2-connection-disconnected,
#r2-panel.r2-connection-stopped {
  border-color: #b00020;
}

#r2-panel.r2-connection-connecting {
  border-color: #f29900;
}

.r2-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.r2-badge {
  font-weight: bold;
}

.r2-connection-connected .r2-badge {
  color: #1e8e3e;
}

.r2-connection-disconnected .r2-badge,
.r2-connection-stopped .r2-badge {
  color: #b00020;
}

.r2-connection-connecting .r2-badge {
  color: #f29900;
}

.r2-at {
  font-size: 0.8rem;
  color: #666;
}

.r2-fields {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
  margin: 0.75rem 0;
}

.r2-fields dt {
  font-weight: bold;
  font-size: 0.8rem;
  color: #666;
}

.r2-fields dd {
  margin: 0;
  font-family: monospace;
}

.r2-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.r2-buttons button {
  font-size: 0.9rem;
  padding: 0.35rem 0.9rem;
}

.r2-danger {
  color: #fff;
  background: #b00020;
  border: 1px solid #b00020;
}

.r2-danger:disabled {
  background: #ccc;
  border-color: #ccc;
}

#r2-confirm {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: #fff4e5;
  border: 1px solid #f29900;
  border-radius: 4px;
}

#r2-hint {
  margin: 0.5rem 0 0;
  font-size: 0.75rem;
  color: #999;
}

#r2-result {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: #666;
}
```

- [ ] **Step 6: テストが通ることを確かめる**

Run: `PYTEST`
Expected: 全件 PASS。`grep -rn "skip-load-drink\|polling_r2\|sending_load_drink\|r2-status-value" app` が何も出さない。

- [ ] **Step 7: 画面を目で確かめる**

ターミナル1：`.venv/bin/python run_mocks.py`、ターミナル2：`.venv/bin/python run.py`。ブラウザで `http://localhost:5100/debug` を開き、R2 パネルが「● 接続中」（緑の枠）、`under_mode` が `mock_m1` になること、[切断] で「● 切断中（手動）」（赤の枠）になり [接続] で戻ることを確かめる。

- [ ] **Step 8: コミットする**

```bash
git add app/templates/debug.html app/static/debug.js app/static/debug.css tests/test_routes_debug.py
git commit -m "feat: show and operate R2 from the debug page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: README と手動確認手順

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/manual-e2e-check.md`

- [ ] **Step 1: README の「Run (mock mode)」を直す**

コードブロックを次にする：

```
python run_mocks.py   # starts the PF mock on :5002 and the Themis WebSocket mock on :9002
                      # (R2 /realtime and video /zed2i share the port, like the real robot)
python run.py          # starts this app on :5100
```

- [ ] **Step 2: 「Environment variables」の表を直す**

`R2_BASE_URL`、`DRINK_TYPE`、`TARGET_ROBOT_ID`、`R2_MOCK_RETURNING_SECONDS`、`R2_MOCK_FORCE_FAILURE` の行を消し、次の行を足す：

```
| `R2_WS_URL` | `ws://127.0.0.1:9002/realtime` | R2's gamepad-server `/realtime` (on site: spark-60c9's forwarded port) |
| `R2_START_REPLY_TIMEOUT_SECONDS` | `15` | Seconds to wait for R2's reply to `play_navigation5` before failing |
| `R2_WS_RECONNECT_DELAY_SECONDS` | `1` | Seconds before reconnecting to R2 |
| `R2_WS_CONNECT_TIMEOUT_SECONDS` | `5` | Timeout of the WebSocket handshake with R2 |
| `R2_MOCK_STEP_SECONDS` | `3` | (mock only) seconds per `under_mode` step of the `/realtime` mock |
| `R2_MOCK_START_REPLY` | `success` | (mock only) `success`, `fail`, or `none` as the reply to `play_navigation5` |
```

- [ ] **Step 3: 映像モックの起動手順を直す**

「Themis WebSocket image client」の節の、3行のコードブロックの `.venv/bin/python -m mocks.themis_video_mock` の行を消し、その前の文を「For local end-to-end testing, run the existing Flask app, `run_mocks.py` (which serves the Themis WebSocket mock on :9002), and the VLM mock in separate terminals.」に変える。

- [ ] **Step 4: R2 の節を足す**

「展示PCで音声IFだけ動かす（サーバーと分離）」の節の後（`## Test` の前）に足す：

````markdown
## R2 (THEMIS) への接続

R2 は、ロボットの gamepad-server（`ws://192.168.0.11:9002/realtime`）に WebSocket で
つないで、このアプリ（Flask）が直接操作する。送るものと受け取ったものの解釈は、
ロボットのベンダーの操作パネル UI-DRP と同じ（詳細は
`docs/superpowers/specs/2026-10-03-r2-websocket-design.md`）。UI-DRP は使わない。
UI-DRP と同時に R2 につながないこと。

R2 には、ロボットの AP「THEMIS_5G」につながっている展示PC（spark-60c9）からしか
届かない。spark-60c9 で 9002 番を転送し、サーバー（spark-3a50）からは
`R2_WS_URL=ws://10.17.4.171:9002/realtime` でつなぐ。ロボット側の設定は変えない。

**spark-60c9 での設定**（sudo が必要。`<有線IF>` は 10.17.4.171 を持つインターフェース名）：

```
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A PREROUTING -i <有線IF> -s 10.17.2.171 -p tcp --dport 9002 \
  -j DNAT --to-destination 192.168.0.11:9002
sudo iptables -t nat -A POSTROUTING -o wlP9s9 -d 192.168.0.11 -p tcp --dport 9002 -j MASQUERADE
sudo iptables -A FORWARD -s 10.17.2.171 -d 192.168.0.11 -p tcp --dport 9002 -j ACCEPT
sudo iptables -A FORWARD -s 192.168.0.11 -d 10.17.2.171 -m state --state ESTABLISHED,RELATED -j ACCEPT
```

- ufw が有効なので、ufw の FORWARD ポリシーで止まらないか確かめる。
- 再起動後も残すには、`net.ipv4.ip_forward=1` を `/etc/sysctl.d/` に書き、iptables の
  ルールを `iptables-persistent`（`netfilter-persistent save`）で保存する。
- ロボットの電源が切れると Wi-Fi が Robotbank に切り替わる。THEMIS_5G を優先して
  自動でつなぎ直すよう NetworkManager の優先度を設定する。
- 映像（`THEMIS_WS_URL`）も同じ 9002 番なので、`ws://10.17.4.171:9002/zed2i` で届く。
- `/realtime` には認証がなく、ロボットの停止や関節の操作も受け付ける。転送する相手を
  spark-3a50 だけに絞っておくこと。

**確認**：spark-3a50 で `.venv/bin/python -c "import websocket; websocket.create_connection('ws://10.17.4.171:9002/realtime', timeout=5).close(); print('ok')"`

**運用上の注意**

- R2 の status（`completed` / `loading` / `returning` / `failed`）はこのアプリの中に
  しかない。**R2 の動作中に Flask を再起動しない**（再起動すると `completed` に戻る）。
- `/debug` の R2 パネルで、接続状態、status、`under_mode`、開始の返事を確認できる。
  - STOP：R2 をその場で止めて `failed` にする。R2 を手で A に戻してから
    「R2 を初期状態に戻す」→「ステートマシンをリセット」。
  - 開始の返事が来なかったとき：R2 が A にいる（`under_mode` が `_m1`）なら
    「開始を再送」で続きから進める。
````

- [ ] **Step 5: 「Switching to the real systems」を直す**

「point `R2_BASE_URL` and `PF_BASE_URL` at their real URLs」を「point `R2_WS_URL` (see "R2 (THEMIS) への接続") and `PF_BASE_URL` at their real URLs」に変える。

- [ ] **Step 6: `manual-e2e-check.md` を直す**

冒頭の手順1を `ターミナル1: R2_MOCK_STEP_SECONDS=3 python run_mocks.py（PFモックが:5002、Themis WebSocketモック（R2 /realtime と映像）が:9002で起動）` に変える。手順4の `PF_MOCK_ACCEPTED=false R2_MOCK_LOADING_SECONDS=3 R2_MOCK_RETURNING_SECONDS=3 python run_mocks.py` を `PF_MOCK_ACCEPTED=false R2_MOCK_STEP_SECONDS=3 python run_mocks.py` に、「（R2モックも同じプロセスで一緒に起動し直す）」を「（Themis WebSocketモックも同じプロセスで一緒に起動し直す）」に変える。最初の節の最後に足す：

```markdown
6. R2 の異常系（ブラウザで `http://localhost:5100/debug` を開いておく）:
   - `R2_MOCK_START_REPLY=none python run_mocks.py` で起動し直してチェックインする。
     15秒後に `phase: "error"`、`step: "starting_r2"` になり、R2 パネルの failed の理由が
     `start_no_reply` になることを確認する。`under_mode` が `mock_m1` のまま
     「開始を再送」が押せることを確認する（モックは返事をしないので、再送もまた
     `start_no_reply` になる）。
   - `python run_mocks.py`（既定）で起動し直し、R2 パネルの「R2 を初期状態に戻す」→
     「ステートマシンをリセット」で戻す。チェックインし、`waiting_r2_placed` の間に
     「STOP」→「実行する」を押す。`phase: "error"`、failed の理由 `stopped` になることを
     確認し、「R2 を初期状態に戻す」→「ステートマシンをリセット」で戻ることを確認する。
   - R2 パネルの「切断」で「切断中（手動）」になり、自動でつなぎ直さないこと、
     「接続」で戻ることを確認する。
```

- [ ] **Step 7: コミットする**

```bash
git add README.md docs/superpowers/plans/manual-e2e-check.md
git commit -m "docs: describe driving R2 over WebSocket and the exhibit PC forwarding

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## 実機で確かめること（実装の後、ユーザーと）

spec の「実機で確かめること」のとおり：DNAT と ufw、開始の返事までの秒数、`under_mode` の値の一覧、STOP の後の様子と A に戻す方法（ベンダーに確認）、UI-DRP と同時につないだときの動き。
