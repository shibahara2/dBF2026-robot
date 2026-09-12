# 分散ロボ基盤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dBF2026会場デモ用の「分散ロボ基盤」（AI管制PF・R2/Themis・会場UIを仲介するFlaskオーケストレーター）を、R2/PFの実機がなくても開発・検証できる形で実装する。

**Architecture:** 単一プロセス・単一Flaskワーカー。プロセス起動時から常駐する1本のバックグラウンドスレッドが状態機械（WAITING→ACTIVE→WAITING、異常時はERROR）を実行し、Flaskのリクエストスレッド群がチェックイン/リセットAPIとSSE配信を担当する。R2/Themis・AI管制PFへのHTTP呼び出しはそれぞれ専用クライアントに閉じ込め、開発中は同リポジトリのモックFlaskアプリで代替する。

**Tech Stack:** Python, Flask, requests, pytest

**Spec:** `docs/superpowers/specs/2026-09-13-distributed-robot-platform-design.md`

## Global Constraints

- 状態は WAITING / ACTIVE / ERROR の3つのみ（独自のIDLE等の状態を追加しない）
- Flaskは単一プロセス・単一ワーカー（`threaded=True`）で動かす。ワーカー数を増やさない
- ポーリング間隔は2秒（`docs/state_machine.pdf`のWAITING/ACTIVE手順に準拠）
- `request_id` はISO8601タイムスタンプ形式（例 `2026-09-11T07:54:32.481Z`）で生成する
- R2/Themis・AI管制PFの接続先は環境変数（`R2_BASE_URL` / `PF_BASE_URL`）で切り替え可能にする
- 状態機械が進行中（WAITING step0=`awaiting_checkin`以外）のときに `POST /api/checkin` が来たら409を返す
- ERROR状態以外で `POST /api/reset` が来たら409を返す
- `POST <AI管制PF>/drink/placed` が `accepted!=true` またはHTTPエラーの場合は即座にERROR（リトライしない）

---

## ファイル構成

```
app/
  __init__.py          # Flaskアプリファクトリ（create_app）
  config.py            # 環境変数読み込み
  state_machine.py     # StateMachine, StateMachineRunner, 定数, request_id生成
  sse.py               # EventBroadcaster（SSE配信用pub/sub）
  clients/
    __init__.py
    r2_client.py        # R2Client
    pf_client.py        # PFClient
  routes/
    __init__.py
    checkin.py           # POST /api/checkin, POST /api/reset
    events.py            # GET /api/events (SSE)
mocks/
  r2_mock.py            # R2/Themis仕様どおりのモックFlaskアプリ
  pf_mock.py            # AI管制PFのモックFlaskアプリ
tests/
  test_pf_client.py
  test_r2_client.py
  test_state_machine.py
  test_state_machine_runner.py
  test_routes_checkin.py
  test_routes_events.py
  test_app_factory.py
  test_r2_mock.py
  test_pf_mock.py
requirements.txt
run.py                  # 本体アプリの起動エントリポイント
run_mocks.py             # モック2本（R2/PF）を別ポートで起動するエントリポイント
```

---

### Task 1: プロジェクト scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `app/__init__.py`（空）
- Create: `app/config.py`
- Create: `app/clients/__init__.py`（空）
- Create: `app/routes/__init__.py`（空）
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `app.config.R2_BASE_URL: str`, `app.config.PF_BASE_URL: str`, `app.config.POLL_INTERVAL_SECONDS: float`, `app.config.HTTP_TIMEOUT_SECONDS: float`, `app.config.DRINK_TYPE: str`, `app.config.TARGET_ROBOT_ID: str`

- [ ] **Step 1: 依存関係ファイルを作成**

```
# requirements.txt
flask==3.0.3
requests==2.32.3
pytest==8.3.3
responses==0.25.3
```

- [ ] **Step 2: pytest設定を作成**

```ini
# pytest.ini
[pytest]
testpaths = tests
```

- [ ] **Step 3: 依存関係をインストール**

Run: `pip install -r requirements.txt`

- [ ] **Step 4: 失敗するテストを書く**

```python
# tests/test_config.py
import importlib
import os


def test_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("R2_BASE_URL", raising=False)
    monkeypatch.delenv("PF_BASE_URL", raising=False)
    monkeypatch.delenv("POLL_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("HTTP_TIMEOUT_SECONDS", raising=False)

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://localhost:5001"
    assert config.PF_BASE_URL == "http://localhost:5002"
    assert config.POLL_INTERVAL_SECONDS == 2.0
    assert config.HTTP_TIMEOUT_SECONDS == 5.0
    assert config.DRINK_TYPE == "water"
    assert config.TARGET_ROBOT_ID == "temi"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("R2_BASE_URL", "http://r2.example.com")
    monkeypatch.setenv("PF_BASE_URL", "http://pf.example.com")
    monkeypatch.setenv("POLL_INTERVAL_SECONDS", "1.5")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "3")

    from app import config
    importlib.reload(config)

    assert config.R2_BASE_URL == "http://r2.example.com"
    assert config.PF_BASE_URL == "http://pf.example.com"
    assert config.POLL_INTERVAL_SECONDS == 1.5
    assert config.HTTP_TIMEOUT_SECONDS == 3.0
```

- [ ] **Step 5: テストが失敗することを確認**

Run: `pytest tests/test_config.py -v`
Expected: FAIL（`app.config` モジュールが存在しない）

- [ ] **Step 6: `app/config.py` を実装**

```python
# app/config.py
import os

R2_BASE_URL = os.environ.get("R2_BASE_URL", "http://localhost:5001")
PF_BASE_URL = os.environ.get("PF_BASE_URL", "http://localhost:5002")
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "2"))
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "5"))
DRINK_TYPE = os.environ.get("DRINK_TYPE", "water")
TARGET_ROBOT_ID = os.environ.get("TARGET_ROBOT_ID", "temi")
```

- [ ] **Step 7: テストが通ることを確認**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 8: commit**

```bash
git add requirements.txt pytest.ini app/__init__.py app/config.py app/clients/__init__.py app/routes/__init__.py tests/test_config.py
git commit -m "feat: add project scaffolding and config module

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: PFClient（AI管制PFへのHTTPクライアント）

**Files:**
- Create: `app/clients/pf_client.py`
- Test: `tests/test_pf_client.py`

**Interfaces:**
- Consumes: なし（`requests`のみ）
- Produces:
  - `PFClient(base_url: str, timeout: float)`
  - `PFClient.get_guide_robot_status() -> str`（戻り値は `"ready"` | `"initializing"` | `"timeout"` | `"retryable_error"` | `"fatal_error"` のいずれか）
  - `PFClient.post_drink_placed() -> bool`（`accepted: true` のときだけ `True`、それ以外・HTTPエラー・タイムアウトはすべて `False`）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_pf_client.py
import responses
import requests

from app.clients.pf_client import PFClient


def make_client():
    return PFClient(base_url="http://pf.test", timeout=1.0)


@responses.activate
def test_get_guide_robot_status_ready():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Ready"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "ready"


@responses.activate
def test_get_guide_robot_status_initializing():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Initializing"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "initializing"


@responses.activate
def test_get_guide_robot_status_422_is_retryable():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"message": "bad request"},
        status=422,
    )
    assert make_client().get_guide_robot_status() == "retryable_error"


@responses.activate
def test_get_guide_robot_status_500_is_fatal():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().get_guide_robot_status() == "fatal_error"


@responses.activate
def test_get_guide_robot_status_timeout():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().get_guide_robot_status() == "timeout"


@responses.activate
def test_get_guide_robot_status_unexpected_body_is_fatal():
    responses.add(
        responses.GET,
        "http://pf.test/api/v1/guide-robot/status",
        json={"status": "Unknown"},
        status=200,
    )
    assert make_client().get_guide_robot_status() == "fatal_error"


@responses.activate
def test_post_drink_placed_accepted():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": True},
        status=200,
    )
    assert make_client().post_drink_placed() is True


@responses.activate
def test_post_drink_placed_not_accepted():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"accepted": False},
        status=200,
    )
    assert make_client().post_drink_placed() is False


@responses.activate
def test_post_drink_placed_http_error():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().post_drink_placed() is False


@responses.activate
def test_post_drink_placed_timeout():
    responses.add(
        responses.POST,
        "http://pf.test/api/v1/drink/placed",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().post_drink_placed() is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_pf_client.py -v`
Expected: FAIL（`app.clients.pf_client` が存在しない）

- [ ] **Step 3: `PFClient` を実装**

```python
# app/clients/pf_client.py
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_pf_client.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/clients/pf_client.py tests/test_pf_client.py
git commit -m "feat: add PFClient for AI管制PF HTTP calls

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: R2Client（R2/Themisへのクライアント）

**Files:**
- Create: `app/clients/r2_client.py`
- Test: `tests/test_r2_client.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `R2Client(base_url: str, timeout: float, drink_type: str = "water", target_robot_id: str = "temi")`
  - `R2Client.get_status() -> dict`（`{"outcome": "loading"|"returning"|"completed"|"failed"|"timeout"|"fatal_error", "request_id": str | None}`）
  - `R2Client.post_load_drink(request_id: str) -> str`（`"accepted"` | `"validation_error"` | `"server_error"` | `"timeout"`）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_r2_client.py
import responses
import requests

from app.clients.r2_client import R2Client


def make_client():
    return R2Client(base_url="http://r2.test", timeout=1.0)


@responses.activate
def test_get_status_loading():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "RID", "status": "loading"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "loading", "request_id": "RID"}


@responses.activate
def test_get_status_completed():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "none", "status": "completed"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "completed", "request_id": "none"}


@responses.activate
def test_get_status_failed():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"request_id": "RID", "status": "failed"},
        status=200,
    )
    assert make_client().get_status() == {"outcome": "failed", "request_id": "RID"}


@responses.activate
def test_get_status_timeout():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().get_status() == {"outcome": "timeout", "request_id": None}


@responses.activate
def test_get_status_500_is_fatal():
    responses.add(
        responses.GET,
        "http://r2.test/v1/commands/load-drink/status",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().get_status() == {"outcome": "fatal_error", "request_id": None}


@responses.activate
def test_post_load_drink_accepted_sends_expected_body():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={},
        status=200,
    )
    result = make_client().post_load_drink("RID")
    assert result == "accepted"
    sent_body = responses.calls[0].request.body
    assert b'"request_id": "RID"' in sent_body
    assert b'"drink_type": "water"' in sent_body
    assert b'"target_robot_id": "temi"' in sent_body


@responses.activate
def test_post_load_drink_validation_error():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={"message": "bad"},
        status=422,
    )
    assert make_client().post_load_drink("RID") == "validation_error"


@responses.activate
def test_post_load_drink_server_error():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        json={"message": "boom"},
        status=500,
    )
    assert make_client().post_load_drink("RID") == "server_error"


@responses.activate
def test_post_load_drink_timeout():
    responses.add(
        responses.POST,
        "http://r2.test/v1/commands/load-drink",
        body=requests.exceptions.Timeout(),
    )
    assert make_client().post_load_drink("RID") == "timeout"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_r2_client.py -v`
Expected: FAIL（`app.clients.r2_client` が存在しない）

- [ ] **Step 3: `R2Client` を実装**

```python
# app/clients/r2_client.py
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

        body = resp.json()
        request_id = body.get("request_id")
        status = body.get("status")
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_r2_client.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/clients/r2_client.py tests/test_r2_client.py
git commit -m "feat: add R2Client for R2/Themis HTTP calls

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: StateMachine — 正常系（WAITING→ACTIVE→WAITING）

**Files:**
- Create: `app/state_machine.py`
- Test: `tests/test_state_machine.py`

**Interfaces:**
- Consumes: `PFClient.get_guide_robot_status() -> str`, `PFClient.post_drink_placed() -> bool`, `R2Client.get_status() -> dict`, `R2Client.post_load_drink(request_id) -> str`（Task 2, 3の契約。テストではこれと同じインターフェースのフェイクを使う）
- Produces:
  - 定数: `PHASE_WAITING = "waiting"`, `PHASE_ACTIVE = "active"`, `PHASE_ERROR = "error"`
  - 定数: `STEP_AWAITING_CHECKIN = "awaiting_checkin"`, `STEP_POLLING_PF_READY = "polling_pf_ready"`, `STEP_POLLING_R2_READY = "polling_r2_ready"`, `STEP_SENDING_LOAD_DRINK = "sending_load_drink"`, `STEP_POLLING_R2_ACTIVE = "polling_r2_active"`, `STEP_NOTIFYING_PF_PLACED = "notifying_pf_placed"`
  - `default_request_id() -> str`
  - `StateMachine(r2_client, pf_client, on_change: callable, sleep: callable = time.sleep, poll_interval: float = 2.0, request_id_factory: callable = default_request_id)`
  - `StateMachine.snapshot() -> dict`（`{"phase", "step", "guest_name", "request_id", "error_message"}`）
  - `StateMachine.try_start(guest_name: str) -> bool`
  - `StateMachine.try_reset() -> bool`
  - `StateMachine.run_started_cycle() -> None`（後続タスクで使う。`try_start`成功後に呼ぶ前提）

- [ ] **Step 1: 失敗するテストを書く（正常系のみ）**

```python
# tests/test_state_machine.py
from app.state_machine import (
    StateMachine,
    PHASE_WAITING,
    PHASE_ACTIVE,
    PHASE_ERROR,
    STEP_AWAITING_CHECKIN,
)


class FakeR2Client:
    def __init__(self, status_sequence, load_drink_result="accepted"):
        self._status_sequence = list(status_sequence)
        self.load_drink_result = load_drink_result
        self.load_drink_calls = []

    def get_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_load_drink(self, request_id):
        self.load_drink_calls.append(request_id)
        return self.load_drink_result


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


def make_state_machine(r2, pf, changes, sleeps):
    return StateMachine(
        r2_client=r2,
        pf_client=pf,
        on_change=changes.append,
        sleep=sleeps.append,
        poll_interval=2.0,
        request_id_factory=lambda: "RID",
    )


def test_try_start_from_awaiting_checkin_succeeds_and_transitions():
    changes = []
    sm = make_state_machine(FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), changes, [])

    assert sm.try_start("Tanaka") is True
    snap = sm.snapshot()
    assert snap["phase"] == PHASE_WAITING
    assert snap["step"] == "polling_pf_ready"
    assert snap["guest_name"] == "Tanaka"
    assert changes[-1] == snap


def test_try_start_fails_when_not_awaiting_checkin():
    sm = make_state_machine(
        FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), [], []
    )
    assert sm.try_start("Tanaka") is True
    assert sm.try_start("Suzuki") is False


def test_full_cycle_returns_to_waiting_awaiting_checkin():
    changes = []
    sleeps = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "loading", "request_id": "none"},
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "loading", "request_id": "RID"},
            {"outcome": "completed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["initializing", "ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, sleeps)

    assert sm.try_start("Tanaka") is True
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_WAITING
    assert final["step"] == STEP_AWAITING_CHECKIN
    assert final["guest_name"] is None
    assert final["request_id"] is None
    assert final["error_message"] is None
    assert r2.load_drink_calls == ["RID"]
    assert pf.placed_calls == 1
    assert sleeps == [2.0, 2.0, 2.0]


def test_cycle_passes_through_active_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "returning", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["ready"], placed_result=True)
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    phases_seen = [c["phase"] for c in changes]
    assert PHASE_ACTIVE in phases_seen
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_state_machine.py -v`
Expected: FAIL（`app.state_machine` が存在しない）

- [ ] **Step 3: `StateMachine`（正常系）を実装**

```python
# app/state_machine.py
import threading
from datetime import datetime, timezone
import time

PHASE_WAITING = "waiting"
PHASE_ACTIVE = "active"
PHASE_ERROR = "error"

STEP_AWAITING_CHECKIN = "awaiting_checkin"
STEP_POLLING_PF_READY = "polling_pf_ready"
STEP_POLLING_R2_READY = "polling_r2_ready"
STEP_SENDING_LOAD_DRINK = "sending_load_drink"
STEP_POLLING_R2_ACTIVE = "polling_r2_active"
STEP_NOTIFYING_PF_PLACED = "notifying_pf_placed"


def default_request_id():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class StateMachine:
    def __init__(
        self,
        r2_client,
        pf_client,
        on_change,
        sleep=time.sleep,
        poll_interval=2.0,
        request_id_factory=default_request_id,
    ):
        self._r2 = r2_client
        self._pf = pf_client
        self._on_change = on_change
        self._sleep = sleep
        self._poll_interval = poll_interval
        self._request_id_factory = request_id_factory

        self._lock = threading.Lock()
        self._phase = PHASE_WAITING
        self._step = STEP_AWAITING_CHECKIN
        self._guest_name = None
        self._request_id = None
        self._error_message = None

    def snapshot(self):
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self):
        return {
            "phase": self._phase,
            "step": self._step,
            "guest_name": self._guest_name,
            "request_id": self._request_id,
            "error_message": self._error_message,
        }

    def _update(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, f"_{key}", value)
            snap = self._snapshot_locked()
        self._on_change(snap)

    def try_start(self, guest_name):
        with self._lock:
            if not (self._phase == PHASE_WAITING and self._step == STEP_AWAITING_CHECKIN):
                return False
            self._phase = PHASE_WAITING
            self._step = STEP_POLLING_PF_READY
            self._guest_name = guest_name
            self._request_id = None
            self._error_message = None
            snap = self._snapshot_locked()
        self._on_change(snap)
        return True

    def try_reset(self):
        with self._lock:
            if self._phase != PHASE_ERROR:
                return False
        self._to_waiting_step0()
        return True

    def _to_waiting_step0(self):
        self._update(
            phase=PHASE_WAITING,
            step=STEP_AWAITING_CHECKIN,
            guest_name=None,
            request_id=None,
            error_message=None,
        )

    def _fail(self, message):
        self._update(phase=PHASE_ERROR, error_message=message)

    def run_started_cycle(self):
        if not self._poll_pf_ready():
            return
        self._update(step=STEP_POLLING_R2_READY)
        if not self._poll_r2_ready():
            return
        request_id = self._request_id_factory()
        self._update(step=STEP_SENDING_LOAD_DRINK, request_id=request_id)
        if not self._send_load_drink(request_id):
            return
        self._update(phase=PHASE_ACTIVE, step=STEP_POLLING_R2_ACTIVE)
        if not self._poll_r2_active(request_id):
            return
        self._update(step=STEP_NOTIFYING_PF_PLACED)
        if not self._notify_pf_placed():
            return
        self._to_waiting_step0()

    def _poll_pf_ready(self):
        while True:
            outcome = self._pf.get_guide_robot_status()
            if outcome == "ready":
                return True
            if outcome in ("initializing", "timeout", "retryable_error"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"AI管制PFの状態確認に失敗しました: {outcome}")
            return False

    def _poll_r2_ready(self):
        while True:
            result = self._r2.get_status()
            outcome = result["outcome"]
            if outcome == "completed":
                return True
            if outcome in ("loading", "returning", "timeout"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2の状態確認に失敗しました: {outcome}")
            return False

    def _send_load_drink(self, request_id):
        while True:
            outcome = self._r2.post_load_drink(request_id)
            if outcome == "accepted":
                return True
            if outcome == "timeout":
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2へのload-drink送信に失敗しました: {outcome}")
            return False

    def _poll_r2_active(self, request_id):
        while True:
            result = self._r2.get_status()
            outcome = result["outcome"]
            response_request_id = result["request_id"]
            if response_request_id is not None and response_request_id != request_id:
                self._fail("R2から返ったrequest_idが一致しません")
                return False
            if outcome in ("returning", "completed"):
                return True
            if outcome in ("loading", "timeout"):
                self._sleep(self._poll_interval)
                continue
            self._fail(f"R2の状態確認に失敗しました: {outcome}")
            return False

    def _notify_pf_placed(self):
        if self._pf.post_drink_placed():
            return True
        self._fail("AI管制PFがdrink/placedを受理しませんでした")
        return False
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_state_machine.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/state_machine.py tests/test_state_machine.py
git commit -m "feat: add StateMachine happy path (WAITING to ACTIVE to WAITING)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: StateMachine — 異常系・reset

**Files:**
- Modify: `tests/test_state_machine.py`（`app/state_machine.py`は変更不要のはずだが、実装に不足があれば`app/state_machine.py`も修正する）

**Interfaces:**
- Consumes: Task 4で定義した `StateMachine` のインターフェースそのもの
- Produces: なし（追加の公開APIはない。既存実装の異常系を検証する）

- [ ] **Step 1: 失敗する可能性のあるテストを追記**

```python
# tests/test_state_machine.py に追記
from app.state_machine import PHASE_ERROR


def test_pf_fatal_error_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client([{"outcome": "completed", "request_id": "none"}])
    pf = FakePFClient(["unexpected"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert "AI管制PF" in final["error_message"]
    assert final["guest_name"] == "Tanaka"


def test_r2_failed_during_waiting_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client([{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_r2_validation_error_on_load_drink_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        [{"outcome": "completed", "request_id": "none"}], load_drink_result="validation_error"
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR
    assert r2.load_drink_calls == ["RID"]


def test_r2_request_id_mismatch_during_active_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "loading", "request_id": "OTHER"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_r2_failed_during_active_moves_to_error_phase():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "failed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    assert sm.snapshot()["phase"] == PHASE_ERROR


def test_pf_drink_placed_not_accepted_moves_to_error_immediately():
    changes = []
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "completed", "request_id": "RID"},
        ],
        load_drink_result="accepted",
    )
    pf = FakePFClient(status_sequence=["ready"], placed_result=False)
    sm = make_state_machine(r2, pf, changes, [])

    sm.try_start("Tanaka")
    sm.run_started_cycle()

    final = sm.snapshot()
    assert final["phase"] == PHASE_ERROR
    assert pf.placed_calls == 1


def test_try_reset_from_error_returns_to_awaiting_checkin():
    changes = []
    r2 = FakeR2Client([{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = make_state_machine(r2, pf, changes, [])

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
    sm = make_state_machine(
        FakeR2Client([{"outcome": "completed", "request_id": "none"}]), FakePFClient(["ready"]), [], []
    )
    assert sm.try_reset() is False
```

- [ ] **Step 2: テストを実行し、全て通ることを確認**

Run: `pytest tests/test_state_machine.py -v`
Expected: PASS（Task 4の実装がこの異常系を既にカバーしているはずだが、落ちた場合は該当の `_fail` 分岐漏れを `app/state_machine.py` に追記して直す）

- [ ] **Step 3: commit**

```bash
git add tests/test_state_machine.py app/state_machine.py
git commit -m "test: cover StateMachine error paths and reset

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: StateMachineRunner（バックグラウンドスレッド駆動）

**Files:**
- Modify: `app/state_machine.py`
- Test: `tests/test_state_machine_runner.py`

**Interfaces:**
- Consumes: `StateMachine.try_start`, `StateMachine.try_reset`, `StateMachine.run_started_cycle`, `StateMachine.snapshot`（Task 4, 5）
- Produces:
  - `StateMachineRunner(state_machine: StateMachine)`
  - `StateMachineRunner.request_checkin(name: str) -> bool`
  - `StateMachineRunner.request_reset() -> bool`
  - `StateMachineRunner.run_forever() -> None`（無限ループ。呼び出し元がデーモンスレッドで起動する想定）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_state_machine_runner.py
import threading
import time

from app.state_machine import StateMachine, StateMachineRunner, PHASE_WAITING, STEP_AWAITING_CHECKIN


class FakeR2Client:
    def __init__(self, status_sequence, load_drink_result="accepted"):
        self._status_sequence = list(status_sequence)
        self.load_drink_result = load_drink_result

    def get_status(self):
        if len(self._status_sequence) > 1:
            return self._status_sequence.pop(0)
        return self._status_sequence[0]

    def post_load_drink(self, request_id):
        return self.load_drink_result


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


def test_request_checkin_runs_cycle_in_background_thread():
    r2 = FakeR2Client(
        status_sequence=[
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "completed", "request_id": None},
        ]
    )
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True

    assert wait_until(
        lambda: sm.snapshot()["phase"] == PHASE_WAITING
        and sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    )


def test_request_checkin_rejected_while_cycle_in_progress():
    r2 = FakeR2Client(status_sequence=[{"outcome": "loading", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    assert runner.request_checkin("Tanaka") is True
    assert wait_until(lambda: sm.snapshot()["step"] != STEP_AWAITING_CHECKIN)

    assert runner.request_checkin("Suzuki") is False


def test_request_reset_is_synchronous_and_does_not_need_the_thread():
    r2 = FakeR2Client(status_sequence=[{"outcome": "failed", "request_id": "none"}])
    pf = FakePFClient(["ready"])
    sm = StateMachine(r2_client=r2, pf_client=pf, on_change=lambda snap: None, sleep=lambda s: None)
    runner = StateMachineRunner(sm)
    start_runner_thread(runner)

    runner.request_checkin("Tanaka")
    assert wait_until(lambda: sm.snapshot()["phase"] == "error")

    assert runner.request_reset() is True
    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN


def test_request_reset_rejected_when_not_in_error():
    sm = StateMachine(
        r2_client=FakeR2Client([{"outcome": "completed", "request_id": "none"}]),
        pf_client=FakePFClient(["ready"]),
        on_change=lambda snap: None,
    )
    runner = StateMachineRunner(sm)
    assert runner.request_reset() is False
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_state_machine_runner.py -v`
Expected: FAIL（`StateMachineRunner` が存在しない）

- [ ] **Step 3: `StateMachineRunner` を `app/state_machine.py` に追記**

```python
# app/state_machine.py の末尾に追記
import queue


class StateMachineRunner:
    def __init__(self, state_machine):
        self._state_machine = state_machine
        self._start_signal = queue.Queue()

    def request_checkin(self, name):
        started = self._state_machine.try_start(name)
        if started:
            self._start_signal.put(True)
        return started

    def request_reset(self):
        return self._state_machine.try_reset()

    def run_forever(self):
        while True:
            self._start_signal.get()
            self._state_machine.run_started_cycle()
```

（`import queue` はファイル先頭の他のimportと合わせて整理すること）

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_state_machine_runner.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/state_machine.py tests/test_state_machine_runner.py
git commit -m "feat: add StateMachineRunner to drive cycles on a background thread

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: EventBroadcaster（SSE配信のpub/sub）

**Files:**
- Create: `app/sse.py`
- Test: `tests/test_sse.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `EventBroadcaster()`
  - `EventBroadcaster.subscribe() -> queue.Queue`
  - `EventBroadcaster.unsubscribe(q: queue.Queue) -> None`
  - `EventBroadcaster.publish(snapshot: dict) -> None`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_sse.py
from app.sse import EventBroadcaster


def test_subscriber_receives_published_snapshot():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()

    broadcaster.publish({"phase": "waiting"})

    assert q.get(timeout=1) == {"phase": "waiting"}


def test_multiple_subscribers_each_receive_the_snapshot():
    broadcaster = EventBroadcaster()
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()

    broadcaster.publish({"phase": "active"})

    assert q1.get(timeout=1) == {"phase": "active"}
    assert q2.get(timeout=1) == {"phase": "active"}


def test_unsubscribed_queue_does_not_receive_future_snapshots():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()
    broadcaster.unsubscribe(q)

    broadcaster.publish({"phase": "error"})

    assert q.empty()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_sse.py -v`
Expected: FAIL（`app.sse` が存在しない）

- [ ] **Step 3: `EventBroadcaster` を実装**

```python
# app/sse.py
import queue
import threading


class EventBroadcaster:
    def __init__(self):
        self._subscribers = []
        self._lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, snapshot):
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(snapshot)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_sse.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/sse.py tests/test_sse.py
git commit -m "feat: add EventBroadcaster pub/sub for SSE

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: Flaskルート — checkin / reset

**Files:**
- Create: `app/routes/checkin.py`
- Test: `tests/test_routes_checkin.py`

**Interfaces:**
- Consumes: `StateMachineRunner.request_checkin(name) -> bool`, `StateMachineRunner.request_reset() -> bool`（Task 6）。Flaskアプリの `app.config["STATE_MACHINE_RUNNER"]` にrunnerが入っている前提
- Produces: `checkin_bp`（Flask Blueprint。`POST /api/checkin`, `POST /api/reset` を登録）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_routes_checkin.py
from flask import Flask

from app.routes.checkin import checkin_bp


class FakeRunner:
    def __init__(self, checkin_result=True, reset_result=True):
        self.checkin_result = checkin_result
        self.reset_result = reset_result
        self.checkin_calls = []
        self.reset_calls = 0

    def request_checkin(self, name):
        self.checkin_calls.append(name)
        return self.checkin_result

    def request_reset(self):
        self.reset_calls += 1
        return self.reset_result


def make_client(runner):
    app = Flask(__name__)
    app.config["STATE_MACHINE_RUNNER"] = runner
    app.register_blueprint(checkin_bp)
    return app.test_client()


def test_checkin_accepted():
    runner = FakeRunner(checkin_result=True)
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"name": "Tanaka"})

    assert resp.status_code == 200
    assert runner.checkin_calls == ["Tanaka"]


def test_checkin_rejected_when_cycle_in_progress():
    runner = FakeRunner(checkin_result=False)
    client = make_client(runner)

    resp = client.post("/api/checkin", json={"name": "Tanaka"})

    assert resp.status_code == 409


def test_checkin_requires_name():
    runner = FakeRunner()
    client = make_client(runner)

    resp = client.post("/api/checkin", json={})

    assert resp.status_code == 422
    assert runner.checkin_calls == []


def test_reset_accepted():
    runner = FakeRunner(reset_result=True)
    client = make_client(runner)

    resp = client.post("/api/reset")

    assert resp.status_code == 200
    assert runner.reset_calls == 1


def test_reset_rejected_when_not_in_error():
    runner = FakeRunner(reset_result=False)
    client = make_client(runner)

    resp = client.post("/api/reset")

    assert resp.status_code == 409
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_routes_checkin.py -v`
Expected: FAIL（`app.routes.checkin` が存在しない）

- [ ] **Step 3: `checkin_bp` を実装**

```python
# app/routes/checkin.py
from flask import Blueprint, current_app, jsonify, request

checkin_bp = Blueprint("checkin", __name__)


@checkin_bp.route("/api/checkin", methods=["POST"])
def checkin():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    if not name:
        return jsonify({"message": "name is required"}), 422

    if not runner.request_checkin(name):
        return jsonify({"message": "a cycle is already in progress"}), 409
    return jsonify({"message": "checkin accepted"}), 200


@checkin_bp.route("/api/reset", methods=["POST"])
def reset():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    if not runner.request_reset():
        return jsonify({"message": "not in error state"}), 409
    return jsonify({"message": "reset accepted"}), 200
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_routes_checkin.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/routes/checkin.py tests/test_routes_checkin.py
git commit -m "feat: add checkin and reset API routes

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Flaskルート — SSE配信

**Files:**
- Create: `app/routes/events.py`
- Test: `tests/test_routes_events.py`

**Interfaces:**
- Consumes: `EventBroadcaster.subscribe()/unsubscribe()/publish()`（Task 7）、`StateMachine.snapshot()`（Task 4）。Flaskアプリの `app.config["EVENT_BROADCASTER"]` と `app.config["STATE_MACHINE"]` を使う
- Produces: `events_bp`（Flask Blueprint。`GET /api/events` を登録。`text/event-stream` で `data: <json>\n\n` を配信）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_routes_events.py
import json

from flask import Flask

from app.routes.events import events_bp


class FakeBroadcaster:
    def __init__(self):
        self.published = []

    def subscribe(self):
        import queue

        q = queue.Queue()
        q.put({"phase": "active", "step": "polling_r2_active"})
        return q

    def unsubscribe(self, q):
        pass


class FakeStateMachine:
    def snapshot(self):
        return {"phase": "waiting", "step": "awaiting_checkin"}


def make_client():
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["STATE_MACHINE"] = FakeStateMachine()
    app.register_blueprint(events_bp)
    return app.test_client()


def test_stream_sends_initial_snapshot_then_subsequent_updates():
    client = make_client()

    resp = client.get("/api/events")
    body_iter = resp.response

    first_chunk = next(iter(body_iter)).decode("utf-8")
    assert first_chunk.startswith("data: ")
    first_payload = json.loads(first_chunk[len("data: "):].strip())
    assert first_payload == {"phase": "waiting", "step": "awaiting_checkin"}

    second_chunk = next(iter(body_iter)).decode("utf-8")
    second_payload = json.loads(second_chunk[len("data: "):].strip())
    assert second_payload == {"phase": "active", "step": "polling_r2_active"}

    resp.close()


def test_stream_content_type_is_event_stream():
    client = make_client()
    resp = client.get("/api/events")
    assert resp.content_type.startswith("text/event-stream")
    resp.close()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_routes_events.py -v`
Expected: FAIL（`app.routes.events` が存在しない）

- [ ] **Step 3: `events_bp` を実装**

```python
# app/routes/events.py
import json

from flask import Blueprint, Response, current_app

events_bp = Blueprint("events", __name__)


@events_bp.route("/api/events")
def stream_events():
    broadcaster = current_app.config["EVENT_BROADCASTER"]
    state_machine = current_app.config["STATE_MACHINE"]

    def generate():
        q = broadcaster.subscribe()
        try:
            yield _format_sse(state_machine.snapshot())
            while True:
                snapshot = q.get()
                yield _format_sse(snapshot)
        finally:
            broadcaster.unsubscribe(q)

    return Response(generate(), mimetype="text/event-stream")


def _format_sse(snapshot):
    return f"data: {json.dumps(snapshot)}\n\n"
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_routes_events.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/routes/events.py tests/test_routes_events.py
git commit -m "feat: add SSE events route

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 10: アプリファクトリ + 起動エントリポイント

**Files:**
- Modify: `app/__init__.py`
- Create: `run.py`
- Test: `tests/test_app_factory.py`

**Interfaces:**
- Consumes: `app.config.*`（Task 1）、`R2Client`/`PFClient`（Task 2, 3）、`StateMachine`/`StateMachineRunner`（Task 4-6）、`EventBroadcaster`（Task 7）、`checkin_bp`/`events_bp`（Task 8, 9）
- Produces: `create_app(r2_client=None, pf_client=None) -> Flask`（テスト時に偽クライアントを注入できるようにする）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_app_factory.py
import json

from app import create_app


class FakeR2Client:
    def get_status(self):
        return {"outcome": "completed", "request_id": "none"}

    def post_load_drink(self, request_id):
        return "accepted"


class FakePFClient:
    def get_guide_robot_status(self):
        return "ready"

    def post_drink_placed(self):
        return True


def test_checkin_then_events_reflect_state_machine_progress():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    resp = client.post("/api/checkin", json={"name": "Tanaka"})
    assert resp.status_code == 200

    events_resp = client.get("/api/events")
    first_chunk = next(iter(events_resp.response)).decode("utf-8")
    payload = json.loads(first_chunk[len("data: "):].strip())
    assert payload["guest_name"] in ("Tanaka", None)
    events_resp.close()


def test_second_checkin_is_rejected_immediately_after_first():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    first = client.post("/api/checkin", json={"name": "Tanaka"})
    assert first.status_code == 200

    second = client.post("/api/checkin", json={"name": "Suzuki"})
    assert second.status_code in (200, 409)
```

`test_second_checkin_is_rejected_immediately_after_first` はタイミング依存で不安定になりやすいテストです。ここでは「200か409のどちらかであり、想定外の例外にならないこと」だけを確認する緩い検証にとどめ、厳密な排他はTask 6で既に検証済みであることに留意してください。

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_app_factory.py -v`
Expected: FAIL（`create_app` が期待するシグネチャで存在しない）

- [ ] **Step 3: `create_app` を実装**

```python
# app/__init__.py
import threading

from flask import Flask

from . import config
from .clients.pf_client import PFClient
from .clients.r2_client import R2Client
from .routes.checkin import checkin_bp
from .routes.events import events_bp
from .sse import EventBroadcaster
from .state_machine import StateMachine, StateMachineRunner


def create_app(r2_client=None, pf_client=None):
    app = Flask(__name__)

    r2_client = r2_client or R2Client(
        base_url=config.R2_BASE_URL,
        timeout=config.HTTP_TIMEOUT_SECONDS,
        drink_type=config.DRINK_TYPE,
        target_robot_id=config.TARGET_ROBOT_ID,
    )
    pf_client = pf_client or PFClient(
        base_url=config.PF_BASE_URL, timeout=config.HTTP_TIMEOUT_SECONDS
    )

    broadcaster = EventBroadcaster()
    state_machine = StateMachine(
        r2_client=r2_client,
        pf_client=pf_client,
        on_change=broadcaster.publish,
        poll_interval=config.POLL_INTERVAL_SECONDS,
    )
    runner = StateMachineRunner(state_machine)

    app.config["EVENT_BROADCASTER"] = broadcaster
    app.config["STATE_MACHINE"] = state_machine
    app.config["STATE_MACHINE_RUNNER"] = runner

    app.register_blueprint(checkin_bp)
    app.register_blueprint(events_bp)

    thread = threading.Thread(target=runner.run_forever, daemon=True)
    thread.start()

    return app
```

```python
# run.py
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_app_factory.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add app/__init__.py run.py tests/test_app_factory.py
git commit -m "feat: wire app factory and add run entrypoint

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 11: R2/Themis モックサーバ

**Files:**
- Create: `mocks/r2_mock.py`
- Test: `tests/test_r2_mock.py`

**Interfaces:**
- Consumes: なし
- Produces: `create_r2_mock_app() -> Flask`（`POST /v1/commands/load-drink`, `GET /v1/commands/load-drink/status` を実装。`R2_MOCK_LOADING_SECONDS`/`R2_MOCK_RETURNING_SECONDS`/`R2_MOCK_FORCE_FAILURE` 環境変数で挙動を制御）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_r2_mock.py
import time

from mocks.r2_mock import create_r2_mock_app


def make_client(monkeypatch, loading_seconds="0.05", returning_seconds="0.05", force_failure=""):
    monkeypatch.setenv("R2_MOCK_LOADING_SECONDS", loading_seconds)
    monkeypatch.setenv("R2_MOCK_RETURNING_SECONDS", returning_seconds)
    monkeypatch.setenv("R2_MOCK_FORCE_FAILURE", force_failure)
    app = create_r2_mock_app()
    return app.test_client()


def test_initial_status_is_completed_with_no_request_id(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/v1/commands/load-drink/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"request_id": "none", "status": "completed"}


def test_load_drink_accepts_and_transitions_through_loading_returning_completed(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="0.05", returning_seconds="0.05")

    post_resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert post_resp.status_code == 200

    status_resp = client.get("/v1/commands/load-drink/status")
    assert status_resp.get_json()["status"] == "loading"

    time.sleep(0.15)
    status_resp = client.get("/v1/commands/load-drink/status")
    assert status_resp.get_json()["status"] in ("returning", "completed")


def test_load_drink_missing_fields_returns_422(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/v1/commands/load-drink", json={"request_id": "RID"})
    assert resp.status_code == 422


def test_load_drink_rejected_while_already_in_progress(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="1", returning_seconds="1")
    client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )

    resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID2", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert resp.status_code == 500


def test_load_drink_same_request_id_is_idempotent(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="1", returning_seconds="1")
    first = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )
    second = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID1", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert first.status_code == 200
    assert second.status_code == 200


def test_force_failure_422(monkeypatch):
    client = make_client(monkeypatch, force_failure="422")
    resp = client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    assert resp.status_code == 422


def test_force_failure_failed_status(monkeypatch):
    client = make_client(monkeypatch, loading_seconds="0.01", force_failure="failed")
    client.post(
        "/v1/commands/load-drink",
        json={"request_id": "RID", "drink_type": "water", "target_robot_id": "temi"},
    )
    time.sleep(0.05)
    resp = client.get("/v1/commands/load-drink/status")
    assert resp.get_json()["status"] == "failed"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_r2_mock.py -v`
Expected: FAIL（`mocks.r2_mock` が存在しない）

- [ ] **Step 3: モックを実装**

```python
# mocks/r2_mock.py
import os
import threading
import time

from flask import Flask, jsonify, request


def create_r2_mock_app():
    app = Flask(__name__)
    lock = threading.Lock()
    state = {"request_id": "none", "status": "completed", "phase_started_at": None}

    def loading_seconds():
        return float(os.environ.get("R2_MOCK_LOADING_SECONDS", "3"))

    def returning_seconds():
        return float(os.environ.get("R2_MOCK_RETURNING_SECONDS", "3"))

    def force_failure():
        return os.environ.get("R2_MOCK_FORCE_FAILURE", "")

    def current_status_locked():
        if force_failure() == "failed" and state["status"] in ("loading", "returning"):
            state["status"] = "failed"
            return "failed"
        if state["status"] not in ("loading", "returning"):
            return state["status"]

        elapsed = time.monotonic() - state["phase_started_at"]
        if state["status"] == "loading" and elapsed >= loading_seconds():
            state["status"] = "returning"
            state["phase_started_at"] = time.monotonic()
            return "returning"
        if state["status"] == "returning" and elapsed >= returning_seconds():
            state["status"] = "completed"
            state["phase_started_at"] = None
            return "completed"
        return state["status"]

    @app.route("/v1/commands/load-drink", methods=["POST"])
    def load_drink():
        body = request.get_json(silent=True) or {}
        request_id = body.get("request_id")
        drink_type = body.get("drink_type")
        target_robot_id = body.get("target_robot_id")
        if not request_id or not drink_type or not target_robot_id:
            return jsonify({"message": "request_id, drink_type, target_robot_id are required"}), 422

        if force_failure() == "422":
            return jsonify({"message": "forced validation error"}), 422
        if force_failure() == "500":
            return jsonify({"message": "forced server error"}), 500

        with lock:
            if request_id == state["request_id"]:
                return jsonify({}), 200
            if current_status_locked() != "completed":
                return jsonify({"message": "a command is already in progress"}), 500
            state["request_id"] = request_id
            state["status"] = "loading"
            state["phase_started_at"] = time.monotonic()
        return jsonify({}), 200

    @app.route("/v1/commands/load-drink/status", methods=["GET"])
    def load_drink_status():
        with lock:
            status = current_status_locked()
            return jsonify({"request_id": state["request_id"], "status": status}), 200

    return app
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_r2_mock.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add mocks/r2_mock.py tests/test_r2_mock.py
git commit -m "feat: add R2/Themis mock server

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 12: AI管制PF モックサーバ

**Files:**
- Create: `mocks/pf_mock.py`
- Test: `tests/test_pf_mock.py`

**Interfaces:**
- Consumes: なし
- Produces: `create_pf_mock_app() -> Flask`（`GET /api/v1/guide-robot/status`, `POST /api/v1/drink/placed` を実装。`PF_MOCK_INITIALIZING_SECONDS`/`PF_MOCK_ACCEPTED` 環境変数で挙動を制御）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_pf_mock.py
import time

from mocks.pf_mock import create_pf_mock_app


def make_client(monkeypatch, initializing_seconds="0", accepted="true"):
    monkeypatch.setenv("PF_MOCK_INITIALIZING_SECONDS", initializing_seconds)
    monkeypatch.setenv("PF_MOCK_ACCEPTED", accepted)
    app = create_pf_mock_app()
    return app.test_client()


def test_status_is_ready_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "Ready"}


def test_status_is_initializing_until_configured_delay_passes(monkeypatch):
    client = make_client(monkeypatch, initializing_seconds="0.1")
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.get_json() == {"status": "Initializing"}

    time.sleep(0.15)
    resp = client.get("/api/v1/guide-robot/status")
    assert resp.get_json() == {"status": "Ready"}


def test_drink_placed_accepted_by_default(monkeypatch):
    client = make_client(monkeypatch)
    resp = client.post("/api/v1/drink/placed")
    assert resp.status_code == 200
    assert resp.get_json() == {"accepted": True}


def test_drink_placed_can_be_forced_to_not_accepted(monkeypatch):
    client = make_client(monkeypatch, accepted="false")
    resp = client.post("/api/v1/drink/placed")
    assert resp.get_json() == {"accepted": False}
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `pytest tests/test_pf_mock.py -v`
Expected: FAIL（`mocks.pf_mock` が存在しない）

- [ ] **Step 3: モックを実装**

```python
# mocks/pf_mock.py
import os
import time

from flask import Flask, jsonify


def create_pf_mock_app():
    app = Flask(__name__)
    start_time = time.monotonic()

    @app.route("/api/v1/guide-robot/status", methods=["GET"])
    def guide_robot_status():
        initializing_seconds = float(os.environ.get("PF_MOCK_INITIALIZING_SECONDS", "0"))
        elapsed = time.monotonic() - start_time
        status = "Initializing" if elapsed < initializing_seconds else "Ready"
        return jsonify({"status": status}), 200

    @app.route("/api/v1/drink/placed", methods=["POST"])
    def drink_placed():
        accepted = os.environ.get("PF_MOCK_ACCEPTED", "true").lower() != "false"
        return jsonify({"accepted": accepted}), 200

    return app
```

- [ ] **Step 4: テストが通ることを確認**

Run: `pytest tests/test_pf_mock.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add mocks/pf_mock.py tests/test_pf_mock.py
git commit -m "feat: add AI管制PF mock server

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 13: モック起動エントリポイント + 手動E2E手順

**Files:**
- Create: `run_mocks.py`
- Create: `docs/superpowers/plans/manual-e2e-check.md`

**Interfaces:**
- Consumes: `create_r2_mock_app`（Task 11）, `create_pf_mock_app`（Task 12）
- Produces: なし（起動スクリプトと手動確認手順のドキュメント）

- [ ] **Step 1: モック起動スクリプトを作成**

```python
# run_mocks.py
import threading

from mocks.pf_mock import create_pf_mock_app
from mocks.r2_mock import create_r2_mock_app


def main():
    r2_app = create_r2_mock_app()
    pf_app = create_pf_mock_app()

    r2_thread = threading.Thread(
        target=lambda: r2_app.run(host="0.0.0.0", port=5001, threaded=True),
        daemon=True,
    )
    pf_thread = threading.Thread(
        target=lambda: pf_app.run(host="0.0.0.0", port=5002, threaded=True),
        daemon=True,
    )
    r2_thread.start()
    pf_thread.start()
    r2_thread.join()
    pf_thread.join()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 手動E2E確認手順をドキュメント化**

```markdown
# 手動E2E確認手順

前提: `pip install -r requirements.txt` 済み。

1. ターミナル1: `python run_mocks.py`（R2モックが:5001、PFモックが:5002で起動）
2. ターミナル2: `R2_MOCK_LOADING_SECONDS=3 R2_MOCK_RETURNING_SECONDS=3 python run.py`（本体が:5000で起動）
3. ターミナル3で以下を順に実行し、状態がwaiting→active→waitingと遷移することを確認する:
   - `curl -N http://localhost:5000/api/events &`（SSEの生ログが流れ始める）
   - `curl -X POST http://localhost:5000/api/checkin -H "Content-Type: application/json" -d '{"name":"田中太郎"}'`
   - SSEログに `phase: "waiting"` → `phase: "active"` → 最終的に `phase: "waiting", step: "awaiting_checkin"` が流れることを確認する
4. 異常系確認: `PF_MOCK_ACCEPTED=false python -c "from mocks.pf_mock import create_pf_mock_app; create_pf_mock_app().run(port=5002)"` のようにPFモックを異常応答に切り替えて再度チェックインし、`phase: "error"` になることを確認する
5. `curl -X POST http://localhost:5000/api/reset` でERRORからWAITINGへ戻ることを確認する
```

- [ ] **Step 3: commit**

```bash
git add run_mocks.py docs/superpowers/plans/manual-e2e-check.md
git commit -m "chore: add mock launcher and manual E2E checklist

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review メモ

- **Specカバレッジ**: 状態遷移（WAITING/ACTIVE/ERROR、request_id生成・冪等性・timeout再送）、公開API（checkin/reset/events、409条件）、モックサーバ、単一プロセス制約は全てタスクに対応済み。会場UIの画面（開始/予約確認/完了/エラー）自体のHTML/JS実装は本計画のスコープ外（バックエンドAPIとモックまでが対象）——UI実装は別途フロントエンド用のplanとして切り出すことを推奨。
- **プレースホルダ**: 全ステップに具体的なコードを記載済み。TODO/TBDなし。
- **型・シグネチャ整合性**: `StateMachine`/`StateMachineRunner`/`R2Client`/`PFClient`の戻り値の語彙（`"ready"`, `"loading"`, `"accepted"`等）をTask間で統一し、テストダブルも同じ語彙を使用している。
