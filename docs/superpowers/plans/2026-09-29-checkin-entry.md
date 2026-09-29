# チェックイン入口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** チェックインをキオスクの「チェックイン開始 → 予約選択 → チェックイン完了」の1本に統一し、画像・発話は「チェックイン開始」だけを叩ける入口にして、入口と段階をデバッグ画面にライブ表示する。

**Architecture:** 入口と段階は `app/state_machine.py` のsnapshot (`entry_source` / `entry_stage` / `entry_at`) に記録し、既存のSSE (`/api/events`) でデバッグ画面へ流す。画像と発話の開始は共通のハンドラ（`/api/visual/start`, `/api/voice/start`）で受け、キオスクはサーバーから見えない操作を `/api/entry` で報告する。`voice_ui` は開始キーワードを検知して `/api/voice/start` を呼ぶだけになり、入力の案内はSSEを受けて読み上げる。

**Tech Stack:** Python 3.12, Flask 3.0.3, requests, pytest + responses, バニラJS/CSS（ビルドなし）

**Spec:** `docs/superpowers/specs/2026-09-29-checkin-entry-design.md`

## Global Constraints

- 新しい依存パッケージは追加しない。
- テストは `.venv/bin/python -m pytest` で実行する（プロジェクト直下）。
- 入口の値: `entry_source` は `screen` / `visual` / `voice` / `null`、`entry_stage` は `start` / `select` / `checkin` / `null`、`entry_at` は `YYYY-MM-DDTHH:MM:SSZ`（既存の `now()`）/ `null`。
- `ENTRY_IDLE_SECONDS` の既定値は `60`。
- 画像・発話の開始の連打抑制は既存の `VisualStartGate` と `VISUAL_START_COOLDOWN_SECONDS` を入口ごとに使う。
- 開始キーワードの環境変数は `VOICE_START_KEYWORDS`（カンマ区切り、既定 `チェックイン`）。
- 発話開始後の読み上げ文言は `画面にお名前、予約番号、または電話番号を入力してください`（一字一句このまま）。
- デバッグ画面の強調色は既存のシーケンス図と同じ `#1a73e8`。
- キオスクの報告は失敗しても画面の動作を止めない（`.catch(() => {})`）。
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

- 画面で予約を選んでいる最中にVLMが「話しかけている」と判定しても、キオスクが検索画面へ飛ばない（409）。→ Task 2
- 開始したまま放置された記録があっても、`ENTRY_IDLE_SECONDS` 経過後は画像・発話で再び開始できる。→ Task 1
- 画像・発話で開始してから予約選択まで60秒以上かかっても、入口は `screen` に変わらず元の入口のまま。→ Task 1
- Whisperの書き起こしが「チェック イン」「チェックイン。」「ﾁｪｯｸｲﾝ」のように揺れても開始できる。→ Task 7
- 画像パイプラインがサイクル中や操作中に `/api/visual/start` から409を受け続けても、処理エラーに数えず、毎フレーム叩き続けない。→ Task 6

---

## File Structure

| ファイル | 役割 | Task |
|---|---|---|
| `app/state_machine.py` | 入口の記録（規則はすべてここ） | 1 |
| `app/config.py`, `app/__init__.py`, `.env.example` | `ENTRY_IDLE_SECONDS` の配線、Blueprint登録 | 2, 3 |
| `app/routes/external_start.py`（新規、`visual.py` を置き換え） | `/api/visual/start`, `/api/voice/start` | 2 |
| `app/routes/entry.py`（新規） | キオスク用 `/api/entry`（POST/DELETE） | 3 |
| `app/routes/checkin.py` | 名前だけのチェックインを廃止 | 3 |
| `app/static/app.js` | キオスクの報告 | 4 |
| `app/templates/debug.html`, `app/static/debug.js`, `app/static/debug.css` | 入口欄 | 5 |
| `themis_video/pipeline.py` | 409/429を想定内として扱う | 6 |
| `voice_ui/start_keyword.py`（新規）, `voice_ui/start_client.py`（新規）, `voice_ui/pipeline.py`, `voice_ui/main.py`, `voice_ui/config.py` | 開始キーワード → `/api/voice/start` | 7 |
| `voice_ui/checkin_client.py`, `voice_ui/name_extract.py` | 削除 | 7 |
| `voice_ui/progress_announcer.py`, `voice_ui/step_messages.py` | 案内の読み上げ、`type` 付きイベントの無視 | 8 |
| `tests/test_visual_e2e.py` | 配信順の変更に追従 | 2 |
| `README.md` | ドキュメント | 9 |

---

### Task 1: 状態機械に入口の記録を追加

**Files:**
- Modify: `app/state_machine.py`
- Test: `tests/test_state_machine.py`

**Interfaces:**
- Consumes: なし
- Produces（`app/state_machine.py`）:
  - 定数 `ENTRY_SCREEN = "screen"`, `ENTRY_VISUAL = "visual"`, `ENTRY_VOICE = "voice"`, `EXTERNAL_ENTRY_SOURCES = (ENTRY_VISUAL, ENTRY_VOICE)`, `ENTRY_STAGE_START = "start"`, `ENTRY_STAGE_SELECT = "select"`, `ENTRY_STAGE_CHECKIN = "checkin"`, `KIOSK_ENTRY_STAGES = (ENTRY_STAGE_START, ENTRY_STAGE_SELECT)`, `DEFAULT_ENTRY_IDLE_SECONDS = 60.0`
  - `StateMachine.__init__(..., sequence_wait=1.0, monotonic=time.monotonic, entry_idle_seconds=DEFAULT_ENTRY_IDLE_SECONDS)`
  - `StateMachine.external_start_available() -> bool`
  - `StateMachine.start_external_entry(source: str) -> bool`（`source` が `EXTERNAL_ENTRY_SOURCES` 以外なら `ValueError`）
  - `StateMachine.record_kiosk_stage(stage: str) -> bool`（`stage` が `KIOSK_ENTRY_STAGES` 以外なら `ValueError`）
  - `StateMachine.clear_entry() -> bool`
  - `StateMachine.try_start(guest_name)` は受け付け時に `(進行中の入口 or screen, checkin)` を記録する（シグネチャは変えない）
  - snapshotに `entry_source`, `entry_stage`, `entry_at` を追加

- [ ] **Step 1: 作業ツリーに残っている試作実装を退避する**

前段の試作（段階名 `start/search/checkin`、発話の `speech/transcribed` 報告）は本仕様で置き換えるので、stashに退避してからHEAD（仕様書のコミット）の状態で始める。`docs/*.pdf` は利用者のファイルなので対象に含めない。

```bash
git stash push -u -m "superseded check-in entry prototype" -- \
  app/__init__.py app/routes/checkin.py app/routes/visual.py app/state_machine.py \
  app/static/app.js app/static/debug.css app/static/debug.js app/templates/debug.html \
  app/routes/entry.py \
  tests/test_routes_checkin.py tests/test_routes_debug.py tests/test_routes_visual.py \
  tests/test_state_machine.py tests/test_visual_e2e.py tests/test_routes_entry.py \
  tests/test_voice_ui_checkin_client.py tests/test_voice_ui_pipeline.py \
  voice_ui/checkin_client.py voice_ui/pipeline.py
git status --short
```

Expected: `?? docs/R2_Demo_Specification-v1.pdf` と `?? docs/state_machine.pdf` だけが残る。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_state_machine.py` の末尾に追加する。

```python
# --- check-in entry tracking -------------------------------------------------


class FakeClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


def _entry_state_machine(changes=None, clock=None, idle=60.0):
    r2 = FakeR2Client(
        [
            {"outcome": "completed", "request_id": "none"},
            {"outcome": "completed", "request_id": "RID"},
        ]
    )
    sm = StateMachine(
        r2_client=r2,
        pf_client=FakePFClient(["ready"]),
        on_change=(changes if changes is not None else []).append,
        sleep=lambda s: None,
        request_id_factory=lambda: "RID",
        now=lambda: "2026-09-29T00:00:00Z",
        monotonic=clock or FakeClock(),
        entry_idle_seconds=idle,
    )
    return sm


def _entry(sm):
    snap = sm.snapshot()
    return snap["entry_source"], snap["entry_stage"], snap["entry_at"]


def test_snapshot_starts_without_entry():
    assert _entry(_entry_state_machine()) == (None, None, None)


def test_external_start_records_start_stage_and_publishes():
    changes = []
    sm = _entry_state_machine(changes)

    assert sm.start_external_entry("visual") is True

    assert _entry(sm) == ("visual", "start", "2026-09-29T00:00:00Z")
    assert changes[-1] == sm.snapshot()


def test_external_start_rejects_screen_source():
    sm = _entry_state_machine()

    try:
        sm.start_external_entry("screen")
    except ValueError:
        return
    raise AssertionError("screen is not an external source")


def test_external_start_rejected_while_entry_in_progress():
    sm = _entry_state_machine()
    sm.record_kiosk_stage("select")

    assert sm.external_start_available() is False
    assert sm.start_external_entry("voice") is False
    assert _entry(sm)[:2] == ("screen", "select")


def test_external_start_accepted_after_entry_idle_seconds():
    clock = FakeClock(1000.0)
    sm = _entry_state_machine(clock=clock, idle=60.0)
    sm.record_kiosk_stage("start")

    clock.value = 1059.9
    assert sm.start_external_entry("visual") is False
    clock.value = 1060.0
    assert sm.start_external_entry("visual") is True
    assert _entry(sm)[:2] == ("visual", "start")


def test_external_start_rejected_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.external_start_available() is False
    assert sm.start_external_entry("visual") is False


def test_kiosk_stage_without_entry_is_screen():
    sm = _entry_state_machine()

    assert sm.record_kiosk_stage("start") is True

    assert _entry(sm)[:2] == ("screen", "start")


def test_kiosk_stage_keeps_external_source_even_after_idle_seconds():
    clock = FakeClock(1000.0)
    sm = _entry_state_machine(clock=clock, idle=60.0)
    sm.start_external_entry("voice")

    clock.value = 1500.0
    sm.record_kiosk_stage("select")

    assert _entry(sm)[:2] == ("voice", "select")


def test_back_to_search_returns_select_to_start_keeping_source():
    sm = _entry_state_machine()
    sm.start_external_entry("visual")
    sm.record_kiosk_stage("select")

    sm.record_kiosk_stage("start")

    assert _entry(sm)[:2] == ("visual", "start")


def test_kiosk_stage_rejects_unknown_stage():
    sm = _entry_state_machine()

    for stage in ["checkin", "search", None]:
        try:
            sm.record_kiosk_stage(stage)
        except ValueError:
            continue
        raise AssertionError(f"{stage!r} should be rejected")


def test_kiosk_stage_ignored_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.record_kiosk_stage("start") is False
    assert _entry(sm)[:2] == ("screen", "checkin")


def test_try_start_records_checkin_with_inherited_source():
    sm = _entry_state_machine()
    sm.start_external_entry("visual")
    sm.record_kiosk_stage("select")

    sm.try_start("田中太郎")

    assert _entry(sm)[:2] == ("visual", "checkin")


def test_try_start_without_entry_records_screen_checkin():
    sm = _entry_state_machine()

    sm.try_start("田中太郎")

    assert _entry(sm)[:2] == ("screen", "checkin")


def test_clear_entry_forgets_any_source():
    changes = []
    sm = _entry_state_machine(changes)
    sm.start_external_entry("voice")

    assert sm.clear_entry() is True

    assert _entry(sm) == (None, None, None)
    assert changes[-1] == sm.snapshot()


def test_clear_entry_without_entry_returns_false():
    assert _entry_state_machine().clear_entry() is False


def test_clear_entry_ignored_while_cycle_in_progress():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    assert sm.clear_entry() is False
    assert _entry(sm)[:2] == ("screen", "checkin")


def test_entry_cleared_when_cycle_returns_to_awaiting_checkin():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")

    sm.run_started_cycle()

    assert sm.snapshot()["step"] == STEP_AWAITING_CHECKIN
    assert _entry(sm) == (None, None, None)


def test_entry_cleared_on_reset_from_error():
    sm = _entry_state_machine()
    sm.try_start("田中太郎")
    sm.fail_unexpected("boom")

    assert sm.try_reset() is True
    assert _entry(sm) == (None, None, None)
```

- [ ] **Step 3: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_state_machine.py -q`
Expected: FAIL（`TypeError: StateMachine.__init__() got an unexpected keyword argument 'monotonic'` など）

- [ ] **Step 4: 実装する**

`app/state_machine.py` の `STEP_NOTIFYING_PF_PLACED = ...` の直後に定数を追加する。

```python
# How a check-in was initiated and how far it got (see
# docs/superpowers/specs/2026-09-29-checkin-entry-design.md).
ENTRY_SCREEN = "screen"
ENTRY_VISUAL = "visual"
ENTRY_VOICE = "voice"
EXTERNAL_ENTRY_SOURCES = (ENTRY_VISUAL, ENTRY_VOICE)

ENTRY_STAGE_START = "start"
ENTRY_STAGE_SELECT = "select"
ENTRY_STAGE_CHECKIN = "checkin"
KIOSK_ENTRY_STAGES = (ENTRY_STAGE_START, ENTRY_STAGE_SELECT)

DEFAULT_ENTRY_IDLE_SECONDS = 60.0
```

`StateMachine.__init__` の引数末尾に2つ追加し、状態を初期化する。

```python
        now=default_now,
        sequence_wait=1.0,
        monotonic=time.monotonic,
        entry_idle_seconds=DEFAULT_ENTRY_IDLE_SECONDS,
    ):
```

```python
        self._monotonic = monotonic
        self._entry_idle_seconds = entry_idle_seconds
```

（上の2行は `self._now = now` の直後に置く。）

```python
        self._entry_source = None
        self._entry_stage = None
        self._entry_at = None
        self._entry_touched = None
```

（上の4行は `self._r2_status_at = None` の直後に置く。）

`_snapshot_locked` の辞書の末尾に追加する。

```python
            "entry_source": self._entry_source,
            "entry_stage": self._entry_stage,
            "entry_at": self._entry_at,
```

`try_start` を次に置き換え、その直前に入口の記録用メソッドを追加する。

```python
    def _awaiting_checkin_locked(self):
        return self._phase == PHASE_WAITING and self._step == STEP_AWAITING_CHECKIN

    def _entry_in_progress_locked(self):
        return self._entry_stage in KIOSK_ENTRY_STAGES

    def _kiosk_source_locked(self):
        if self._entry_in_progress_locked():
            return self._entry_source
        return ENTRY_SCREEN

    def _set_entry_locked(self, source, stage):
        self._entry_source = source
        self._entry_stage = stage
        self._entry_at = self._now()
        self._entry_touched = self._monotonic()

    def _external_start_available_locked(self):
        if not self._awaiting_checkin_locked():
            return False
        if not self._entry_in_progress_locked():
            return True
        # An abandoned kiosk must not block visual/voice starts forever.
        return self._monotonic() - self._entry_touched >= self._entry_idle_seconds

    def external_start_available(self):
        with self._lock:
            return self._external_start_available_locked()

    def start_external_entry(self, source):
        """Record a visual/voice start unless someone is using the kiosk."""
        if source not in EXTERNAL_ENTRY_SOURCES:
            raise ValueError(f"unknown external entry source: {source!r}")
        with self._lock:
            if not self._external_start_available_locked():
                return False
            self._set_entry_locked(source, ENTRY_STAGE_START)
            self._on_change(self._snapshot_locked())
        return True

    def record_kiosk_stage(self, stage):
        """Record a kiosk stage, keeping the source of an entry in progress."""
        if stage not in KIOSK_ENTRY_STAGES:
            raise ValueError(f"unknown kiosk entry stage: {stage!r}")
        with self._lock:
            if not self._awaiting_checkin_locked():
                return False
            self._set_entry_locked(self._kiosk_source_locked(), stage)
            self._on_change(self._snapshot_locked())
        return True

    def clear_entry(self):
        """Forget the entry when the kiosk goes back to its start screen."""
        with self._lock:
            if not (self._awaiting_checkin_locked() and self._entry_source is not None):
                return False
            self._entry_source = None
            self._entry_stage = None
            self._entry_at = None
            self._entry_touched = None
            self._on_change(self._snapshot_locked())
        return True

    def try_start(self, guest_name):
        with self._lock:
            if not self._awaiting_checkin_locked():
                return False
            source = self._kiosk_source_locked()
            self._phase = PHASE_WAITING
            self._step = STEP_POLLING_PF_READY
            self._guest_name = guest_name
            self._request_id = None
            self._error_message = None
            self._set_entry_locked(source, ENTRY_STAGE_CHECKIN)
            snap = self._snapshot_locked()
            self._on_change(snap)
        return True
```

`_to_waiting_step0` の `_update(...)` に入口のクリアを加える。

```python
    def _to_waiting_step0(self):
        self._update(
            phase=PHASE_WAITING,
            step=STEP_AWAITING_CHECKIN,
            guest_name=None,
            request_id=None,
            error_message=None,
            entry_source=None,
            entry_stage=None,
            entry_at=None,
            entry_touched=None,
        )
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_state_machine.py tests/test_state_machine_runner.py -q`
Expected: PASS

- [ ] **Step 6: コミットする**

```bash
git add app/state_machine.py tests/test_state_machine.py
git commit -m "feat: record check-in entry source and stage in state machine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 画像・発話の開始API（`/api/visual/start`, `/api/voice/start`）

**Files:**
- Create: `app/routes/external_start.py`
- Delete: `app/routes/visual.py`
- Modify: `app/__init__.py`, `app/config.py`, `.env.example`
- Delete: `tests/test_routes_visual.py`
- Create: `tests/test_routes_external_start.py`
- Modify: `tests/test_app_factory.py`, `tests/test_visual_e2e.py`

**Interfaces:**
- Consumes: `StateMachine.external_start_available()`, `StateMachine.start_external_entry(source)`, `ENTRY_VISUAL`, `ENTRY_VOICE`（Task 1）
- Produces:
  - `POST /api/visual/start`, `POST /api/voice/start`: 202 `{"message": "start action accepted"}` / 409 `{"message": "check-in start is not available"}` / 429 `{"message": "start is rate limited"}`
  - 202のとき `EVENT_BROADCASTER` に `{"type": "ui_action", "action": "start_checkin"}` を配信（入口記録のsnapshotの後）
  - `app.config["EXTERNAL_START_GATES"]`: `{source: VisualStartGate}`
  - `app/config.py` の `ENTRY_IDLE_SECONDS`（float、既定60）

- [ ] **Step 1: 失敗するテストを書く**

`git rm -q tests/test_routes_visual.py` で旧テストを削除し、`tests/test_routes_external_start.py` を作る。

```python
import pytest
from flask import Flask

from app.routes.external_start import external_start_bp


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class FakeStateMachine:
    def __init__(self, available=True, start_result=True):
        self.available = available
        self.start_result = start_result
        self.started = []

    def external_start_available(self):
        return self.available

    def start_external_entry(self, source):
        self.started.append(source)
        return self.start_result


def make_client(state_machine=None):
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["STATE_MACHINE"] = state_machine or FakeStateMachine()
    app.config["VISUAL_START_COOLDOWN_SECONDS"] = 5.0
    app.register_blueprint(external_start_bp)
    return app.test_client(), app


@pytest.mark.parametrize(
    "path, source", [("/api/visual/start", "visual"), ("/api/voice/start", "voice")]
)
def test_start_records_entry_and_opens_search(path, source):
    client, app = make_client()

    response = client.post(path, json={})

    assert response.status_code == 202
    assert response.get_json() == {"message": "start action accepted"}
    assert app.config["STATE_MACHINE"].started == [source]
    assert app.config["EVENT_BROADCASTER"].events == [
        {"type": "ui_action", "action": "start_checkin"}
    ]


@pytest.mark.parametrize("path", ["/api/visual/start", "/api/voice/start"])
def test_start_rejected_when_not_available(path):
    # Cycle in progress, or someone is using the kiosk.
    state_machine = FakeStateMachine(available=False)
    client, app = make_client(state_machine)

    response = client.post(path, json={})

    assert response.status_code == 409
    assert state_machine.started == []
    assert app.config["EVENT_BROADCASTER"].events == []


def test_start_rejected_when_entry_recording_loses_race():
    state_machine = FakeStateMachine(available=True, start_result=False)
    client, app = make_client(state_machine)

    response = client.post("/api/voice/start", json={})

    assert response.status_code == 409
    assert app.config["EVENT_BROADCASTER"].events == []


def test_start_is_rate_limited_per_source():
    client, app = make_client()

    visual_first = client.post("/api/visual/start", json={})
    visual_second = client.post("/api/visual/start", json={})
    voice_first = client.post("/api/voice/start", json={})

    assert visual_first.status_code == 202
    assert visual_second.status_code == 429
    assert voice_first.status_code == 202
    assert app.config["STATE_MACHINE"].started == ["visual", "voice"]
```

`tests/test_app_factory.py` の末尾に、実物の状態機械を通す結合テストを追加する。

```python
def test_voice_start_blocked_while_kiosk_user_is_selecting():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    assert client.post("/api/visual/start", json={}).status_code == 202
    state_machine.record_kiosk_stage("select")

    assert client.post("/api/voice/start", json={}).status_code == 409
    snap = state_machine.snapshot()
    assert (snap["entry_source"], snap["entry_stage"]) == ("visual", "select")


def test_entry_idle_seconds_comes_from_config(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ENTRY_IDLE_SECONDS", 0.0)
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()
    app.config["STATE_MACHINE"].record_kiosk_stage("start")

    # With no idle window, an abandoned kiosk entry never blocks a start.
    assert client.post("/api/voice/start", json={}).status_code == 202
```

`tests/test_visual_e2e.py` は、`/api/visual/start` が画面遷移の指示より先に入口記録のsnapshotを配信するようになるので、配信順の確認を置き換える。

```python
        assert subscriber.get(timeout=10) == {
            "type": "ui_action",
            "action": "start_checkin",
        }
```

を次にする。

```python
        entry_snapshot = subscriber.get(timeout=10)
        assert entry_snapshot["entry_source"] == "visual"
        assert entry_snapshot["entry_stage"] == "start"
        assert subscriber.get(timeout=10) == {
            "type": "ui_action",
            "action": "start_checkin",
        }
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_external_start.py tests/test_app_factory.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'app.routes.external_start'`）

- [ ] **Step 3: 実装する**

`app/routes/external_start.py` を作る。

```python
from flask import Blueprint, current_app, jsonify

from ..state_machine import ENTRY_VISUAL, ENTRY_VOICE
from ..visual_trigger import VisualStartGate


external_start_bp = Blueprint("external_start", __name__)


@external_start_bp.route("/api/visual/start", methods=["POST"])
def visual_start():
    return _external_start(ENTRY_VISUAL)


@external_start_bp.route("/api/voice/start", methods=["POST"])
def voice_start():
    return _external_start(ENTRY_VOICE)


def _external_start(source):
    """Open the kiosk search screen for a visual/voice start.

    Both entries only stand in for the kiosk's start button, so they share
    this handler and differ only in the recorded source.
    """
    state_machine = current_app.config["STATE_MACHINE"]
    if not state_machine.external_start_available():
        return jsonify({"message": "check-in start is not available"}), 409

    gates = current_app.config.setdefault("EXTERNAL_START_GATES", {})
    gate = gates.setdefault(source, VisualStartGate())
    cooldown = current_app.config.get("VISUAL_START_COOLDOWN_SECONDS", 5.0)
    if not gate.accept(cooldown):
        return jsonify({"message": "start is rate limited"}), 429

    if not state_machine.start_external_entry(source):
        return jsonify({"message": "check-in start is not available"}), 409

    current_app.config["EVENT_BROADCASTER"].publish(
        {"type": "ui_action", "action": "start_checkin"}
    )
    return jsonify({"message": "start action accepted"}), 202
```

`app/routes/visual.py` を削除する: `git rm -q app/routes/visual.py`

`app/config.py` の `VISUAL_START_COOLDOWN_SECONDS` の定義の直後に追加する。

```python
ENTRY_IDLE_SECONDS = float(os.environ.get("ENTRY_IDLE_SECONDS", "60"))
```

`app/__init__.py`:
- `from .routes.visual import visual_bp` を `from .routes.external_start import external_start_bp` に置き換える。
- `app.register_blueprint(visual_bp)` を `app.register_blueprint(external_start_bp)` に置き換える。
- `StateMachine(...)` の呼び出しに `entry_idle_seconds=config.ENTRY_IDLE_SECONDS,` を追加する。

`.env.example` の `VISUAL_TRIGGER_URL=...` の行の直後に追加する。

```
# Seconds after which an abandoned kiosk entry no longer blocks visual/voice starts
ENTRY_IDLE_SECONDS=60
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_external_start.py tests/test_app_factory.py tests/test_visual_e2e.py -q`
Expected: PASS（`test_app_factory.py` の既存の名前チェックインのテストもまだPASSする。Task 3で予約IDに置き換える）

- [ ] **Step 5: コミットする**

```bash
git add app/routes/external_start.py app/__init__.py app/config.py .env.example \
  tests/test_routes_external_start.py tests/test_app_factory.py tests/test_visual_e2e.py
git commit -m "feat: share visual/voice start handler and block starts during kiosk use

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: キオスク用 `/api/entry` と、予約IDを必須にした `/api/checkin`

**Files:**
- Create: `app/routes/entry.py`
- Modify: `app/routes/checkin.py`, `app/__init__.py`
- Create: `tests/test_routes_entry.py`
- Modify: `tests/test_routes_checkin.py`, `tests/test_app_factory.py`

**Interfaces:**
- Consumes: `StateMachine.record_kiosk_stage(stage)`, `StateMachine.clear_entry()`, `KIOSK_ENTRY_STAGES`（Task 1）
- Produces:
  - `POST /api/entry {"stage": "start" | "select"}`: 202 `{"message": "entry recorded"}` / 409 `{"message": "a cycle is already in progress"}` / 422 `{"message": "stage must be start or select"}`
  - `DELETE /api/entry`: 200 `{"cleared": bool}`
  - `POST /api/checkin`: `reservation_id` がなければ 422 `{"message": "reservation_id is required"}`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_entry.py` を作る。

```python
import pytest
from flask import Flask

from app.routes.entry import entry_bp


class FakeStateMachine:
    def __init__(self, record_result=True, clear_result=True):
        self.record_result = record_result
        self.clear_result = clear_result
        self.stages = []
        self.clear_calls = 0

    def record_kiosk_stage(self, stage):
        self.stages.append(stage)
        return self.record_result

    def clear_entry(self):
        self.clear_calls += 1
        return self.clear_result


def make_client(state_machine):
    app = Flask(__name__)
    app.config["STATE_MACHINE"] = state_machine
    app.register_blueprint(entry_bp)
    return app.test_client()


@pytest.mark.parametrize("stage", ["start", "select"])
def test_entry_records_kiosk_stage(stage):
    state_machine = FakeStateMachine()

    resp = make_client(state_machine).post("/api/entry", json={"stage": stage})

    assert resp.status_code == 202
    assert state_machine.stages == [stage]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"stage": "checkin"},
        {"stage": "search"},
        {"stage": None},
        # The kiosk never names the source; the server decides it.
        {"source": "voice", "stage": "speech"},
    ],
)
def test_entry_rejects_unknown_stage(body):
    state_machine = FakeStateMachine()

    resp = make_client(state_machine).post("/api/entry", json=body)

    assert resp.status_code == 422
    assert state_machine.stages == []


def test_entry_returns_409_while_cycle_in_progress():
    resp = make_client(FakeStateMachine(record_result=False)).post(
        "/api/entry", json={"stage": "start"}
    )

    assert resp.status_code == 409


@pytest.mark.parametrize("cleared", [True, False])
def test_delete_entry_reports_whether_it_cleared(cleared):
    state_machine = FakeStateMachine(clear_result=cleared)

    resp = make_client(state_machine).delete("/api/entry")

    assert resp.status_code == 200
    assert resp.get_json() == {"cleared": cleared}
    assert state_machine.clear_calls == 1
```

`tests/test_routes_checkin.py` から名前だけのチェックインのテスト3つ（`test_checkin_accepted`, `test_checkin_rejected_when_cycle_in_progress`, `test_checkin_requires_name`）を削除し、代わりに追加する。

```python
@pytest.mark.parametrize("body", [{}, {"name": "田中太郎"}])
def test_checkin_requires_reservation_id(body):
    runner = FakeRunner()
    client = make_client(runner)

    resp = client.post("/api/checkin", json=body)

    assert resp.status_code == 422
    assert resp.get_json() == {"message": "reservation_id is required"}
    assert runner.checkin_calls == []
```

（ファイル先頭に `import pytest` を追加する。）

`tests/test_app_factory.py` の名前チェックインを予約IDに置き換える。
- `test_checkin_then_events_reflect_state_machine_progress`: `json={"name": "Tanaka"}` → `json={"reservation_id": "RSV-0001"}`、`assert payload["guest_name"] in ("Tanaka", None)` → `assert payload["guest_name"] in ("田中太郎", None)`
- `test_second_checkin_is_rejected_immediately_after_first`: 1回目を `json={"reservation_id": "RSV-0001"}`、2回目を `json={"reservation_id": "RSV-0003"}` にする。

さらに、キオスクの流れを実物の状態機械で通す結合テストを追加する。

```python
def test_kiosk_flow_records_entry_through_checkin():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()
    state_machine = app.config["STATE_MACHINE"]

    def entry():
        snap = state_machine.snapshot()
        return snap["entry_source"], snap["entry_stage"]

    assert client.post("/api/entry", json={"stage": "start"}).status_code == 202
    assert entry() == ("screen", "start")
    assert client.post("/api/entry", json={"stage": "select"}).status_code == 202
    assert entry() == ("screen", "select")
    assert client.post("/api/checkin", json={"reservation_id": "RSV-0001"}).status_code == 200
    assert entry()[1] == "checkin"
    assert wait_until(lambda: entry() == (None, None), timeout=8.0)


def test_back_to_start_clears_visual_entry():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    client.post("/api/visual/start", json={})
    resp = client.delete("/api/entry")

    assert resp.get_json() == {"cleared": True}
    assert app.config["STATE_MACHINE"].snapshot()["entry_source"] is None
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_entry.py tests/test_routes_checkin.py tests/test_app_factory.py -q`
Expected: FAIL（`No module named 'app.routes.entry'`）

- [ ] **Step 3: 実装する**

`app/routes/entry.py` を作る。

```python
from flask import Blueprint, current_app, jsonify, request

from ..state_machine import KIOSK_ENTRY_STAGES

entry_bp = Blueprint("entry", __name__)


@entry_bp.route("/api/entry", methods=["POST"])
def report_entry():
    """Kiosk reports of steps the server cannot observe (debug view only)."""
    stage = (request.get_json(silent=True) or {}).get("stage")
    if stage not in KIOSK_ENTRY_STAGES:
        return jsonify({"message": "stage must be start or select"}), 422

    state_machine = current_app.config["STATE_MACHINE"]
    if not state_machine.record_kiosk_stage(stage):
        return jsonify({"message": "a cycle is already in progress"}), 409
    return jsonify({"message": "entry recorded"}), 202


@entry_bp.route("/api/entry", methods=["DELETE"])
def clear_entry():
    state_machine = current_app.config["STATE_MACHINE"]
    return jsonify({"cleared": state_machine.clear_entry()}), 200
```

`app/__init__.py` に `from .routes.entry import entry_bp` を追加し、`app.register_blueprint(checkin_bp)` の直後に `app.register_blueprint(entry_bp)` を追加する。

`app/routes/checkin.py` の `checkin()` を次に置き換え、`_checkin_by_reservation` はそのまま残す。

```python
@checkin_bp.route("/api/checkin", methods=["POST"])
def checkin():
    runner = current_app.config["STATE_MACHINE_RUNNER"]
    body = request.get_json(silent=True) or {}
    reservation_id = body.get("reservation_id")
    if not reservation_id:
        return jsonify({"message": "reservation_id is required"}), 422
    return _checkin_by_reservation(runner, reservation_id)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_entry.py tests/test_routes_checkin.py tests/test_app_factory.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add app/routes/entry.py app/routes/checkin.py app/__init__.py \
  tests/test_routes_entry.py tests/test_routes_checkin.py tests/test_app_factory.py
git commit -m "feat: add kiosk entry reports and require reservation_id for check-in

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: キオスクからの報告

**Files:**
- Modify: `app/static/app.js`
- Create: `tests/test_kiosk_entry_js.py`

**Interfaces:**
- Consumes: `POST /api/entry {"stage": ...}`, `DELETE /api/entry`（Task 3）
- Produces: なし（ブラウザ側のみ）

- [ ] **Step 1: 失敗するテストを書く**

このリポジトリのJSはソースを読むテストで確認している（`tests/test_routes_debug.py` の `test_debug_clock_formats_times_in_tokyo_timezone` と同じ方式）。`tests/test_kiosk_entry_js.py` を作る。

```python
import re
from pathlib import Path

APP_JS = (Path(__file__).parents[1] / "app" / "static" / "app.js").read_text()


def _function_body(name):
    match = re.search(rf"function {name}\([^)]*\) {{(.*?)\n}}", APP_JS, re.S)
    assert match, f"function {name} not found"
    return match.group(1)


def test_report_helpers_ignore_failures():
    assert 'fetch("/api/entry", {' in _function_body("reportEntry")
    assert ".catch(() => {})" in _function_body("reportEntry")
    assert 'fetch("/api/entry", { method: "DELETE" }).catch(() => {})' in _function_body(
        "clearEntry"
    )


def test_report_body_sends_only_stage():
    assert "JSON.stringify({ stage: stage })" in _function_body("reportEntry")


def test_start_button_reports_start():
    assert re.search(
        r'startButton\.addEventListener\("click", \(\) => \{\s*showStage\("search"\);\s*reportEntry\("start"\);',
        APP_JS,
    )


def test_selecting_reservation_reports_select():
    assert 'reportEntry("select");' in _function_body("selectReservation")


def test_back_buttons_report_or_clear():
    assert re.search(r"resetFlow\(\);\s*clearEntry\(\);", APP_JS)
    assert re.search(
        r'showStage\(button\.dataset\.target\);\s*reportEntry\("start"\);', APP_JS
    )
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_kiosk_entry_js.py -q`
Expected: FAIL（`function reportEntry not found`）

- [ ] **Step 3: 実装する**

`app/static/app.js` の `function resetFlow() {` の直前に追加する。

```js
// Entry reports only feed the debug view, so failures are ignored.
function reportEntry(stage) {
  fetch("/api/entry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage: stage }),
  }).catch(() => {});
}

function clearEntry() {
  fetch("/api/entry", { method: "DELETE" }).catch(() => {});
}
```

`selectReservation` を次にする。

```js
function selectReservation(reservation) {
  selectedReservation = reservation;
  renderDetail(reservation);
  showStage("confirm");
  reportEntry("select");
}
```

`startButton.addEventListener("click", () => showStage("search"));` を次に置き換える。

```js
startButton.addEventListener("click", () => {
  showStage("search");
  reportEntry("start");
});
```

`.back-button` のハンドラを次に置き換える。

```js
document.querySelectorAll(".back-button").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.target === "start") {
      resetFlow();
      clearEntry();
    } else {
      showStage(button.dataset.target);
      reportEntry("start");
    }
  });
});
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_kiosk_entry_js.py tests/test_routes_ui.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add app/static/app.js tests/test_kiosk_entry_js.py
git commit -m "feat: report kiosk start, selection and back navigation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: デバッグ画面の「チェックイン入口」欄

**Files:**
- Modify: `app/templates/debug.html`, `app/static/debug.js`, `app/static/debug.css`
- Test: `tests/test_routes_debug.py`

**Interfaces:**
- Consumes: snapshotの `entry_source`, `entry_stage`, `entry_at`（Task 1）
- Produces: 要素ID `entry-panel`, `entry-at`, `entry-start-screen`, `entry-start-visual`, `entry-start-voice`, `entry-stage-select`, `entry-stage-checkin`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_debug.py` の末尾に追加する。

```python
def test_debug_page_has_entry_panel():
    resp = make_client().get("/debug")

    for element_id in [
        "entry-panel",
        "entry-at",
        "entry-start-screen",
        "entry-start-visual",
        "entry-start-voice",
        "entry-stage-select",
        "entry-stage-checkin",
    ]:
        assert f'id="{element_id}"'.encode() in resp.data
    text = resp.data.decode()
    for label in ["開始ボタン", "VLM検知", "発話検知", "予約選択", "チェックイン完了"]:
        assert label in text


def test_debug_js_renders_entry_fields():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'const ENTRY_ORDER = ["start", "select", "checkin"];' in source
    for field in ["entry_source", "entry_stage", "entry_at"]:
        assert f"snapshot.{field}" in source
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_debug.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`app/templates/debug.html` の `<h2 class="section-label">シーケンス図（実行中ステップをハイライト）</h2>` の直前に挿入する。

```html
    <h2 class="section-label">チェックイン入口（最終更新: <span id="entry-at">-</span>）</h2>
    <div id="entry-panel">
      <div class="entry-column">
        <div class="entry-column-title">チェックイン開始</div>
        <div class="entry-box entry-start" id="entry-start-screen" data-source="screen">画面操作：開始ボタン</div>
        <div class="entry-box entry-start" id="entry-start-visual" data-source="visual">画像：VLM検知</div>
        <div class="entry-box entry-start" id="entry-start-voice" data-source="voice">発話：発話検知</div>
      </div>
      <div class="entry-arrow">→</div>
      <div class="entry-column">
        <div class="entry-column-title">&nbsp;</div>
        <div class="entry-box entry-stage" id="entry-stage-select" data-stage="select">予約選択</div>
      </div>
      <div class="entry-arrow">→</div>
      <div class="entry-column">
        <div class="entry-column-title">&nbsp;</div>
        <div class="entry-box entry-stage" id="entry-stage-checkin" data-stage="checkin">チェックイン完了</div>
      </div>
    </div>

```

`app/static/debug.js` の `const currentTime = ...` の直後に追加する。

```js
const ENTRY_ORDER = ["start", "select", "checkin"];
const entryAt = document.getElementById("entry-at");
const entryStarts = document.querySelectorAll(".entry-start");
const entryStages = document.querySelectorAll(".entry-stage");

function renderEntry(snapshot) {
  entryAt.textContent = toSecondsTime(snapshot.entry_at);
  // -1 when no entry is recorded, so nothing is highlighted.
  const reached = ENTRY_ORDER.indexOf(snapshot.entry_stage);
  entryStarts.forEach((el) => {
    const isSource = el.dataset.source === snapshot.entry_source;
    el.classList.toggle("active", isSource && reached === 0);
    el.classList.toggle("done", isSource && reached > 0);
  });
  entryStages.forEach((el) => {
    const index = ENTRY_ORDER.indexOf(el.dataset.stage);
    el.classList.toggle("active", index === reached);
    el.classList.toggle("done", index < reached);
  });
}
```

`function render(snapshot) {` の直後の1行目に `renderEntry(snapshot);` を追加する。

`app/static/debug.css` の末尾に追加する。

```css
#entry-panel {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  flex-wrap: wrap;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.entry-column {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.entry-column-title {
  font-size: 0.8rem;
  font-weight: bold;
  color: #666;
}

.entry-box {
  border: 1px solid #ddd;
  border-radius: 999px;
  padding: 0.2rem 0.75rem;
  font-size: 0.85rem;
  color: #999;
  white-space: nowrap;
}

.entry-box.done {
  border-color: #1a73e8;
  color: #1a73e8;
}

.entry-box.active {
  background: #1a73e8;
  border-color: #1a73e8;
  color: #fff;
  font-weight: bold;
}

.entry-arrow {
  color: #bbb;
  padding-bottom: 0.2rem;
}
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_debug.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add app/templates/debug.html app/static/debug.js app/static/debug.css tests/test_routes_debug.py
git commit -m "feat: show check-in entry and stage on debug page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 画像パイプラインで409/429を想定内の応答にする

**Files:**
- Modify: `themis_video/pipeline.py`
- Test: `tests/test_visual_pipeline.py`

**Interfaces:**
- Consumes: `/api/visual/start` の409/429（Task 2）
- Produces: `VisualConversationPipeline.process(image_bytes) -> bool` は409/429で例外を出さず `False` を返し、クールダウン（`cooldown_seconds`）が明けるまで再送しない。再送できる状態（armed）は維持する。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_visual_pipeline.py` の末尾に追加する。

```python
class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


@pytest.mark.parametrize("status", [409, 429])
@responses.activate
def test_not_accepted_start_is_not_an_error_and_waits_for_cooldown(status, caplog):
    responses.add(
        responses.POST, "http://app/api/visual/start", json={"message": "busy"}, status=status
    )
    clock = FakeClock()
    pipeline = VisualConversationPipeline(
        FakeVLM([True] * 4),
        "http://app/api/visual/start",
        window_size=1,
        yes_threshold=1,
        cooldown_seconds=5,
        clock=clock,
    )

    with caplog.at_level(logging.INFO, logger="themis_video.pipeline"):
        assert pipeline.process(b"f1") is False
    assert len(responses.calls) == 1
    assert str(status) in caplog.text

    clock.value = 4.9
    assert pipeline.process(b"f2") is False
    assert len(responses.calls) == 1

    clock.value = 5.0
    assert pipeline.process(b"f3") is False
    assert len(responses.calls) == 2


@responses.activate
def test_server_error_still_raises():
    responses.add(responses.POST, "http://app/api/visual/start", status=500)
    pipeline = VisualConversationPipeline(
        FakeVLM([True]), "http://app/api/visual/start", window_size=1, yes_threshold=1
    )

    with pytest.raises(VisualTriggerError):
        pipeline.process(b"f1")
```

ファイル先頭のimportに `import logging`, `import pytest` と `from themis_video.pipeline import VisualTriggerError` を追加する。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_visual_pipeline.py -q`
Expected: FAIL（`VisualTriggerError: visual start trigger failed`）

- [ ] **Step 3: 実装する**

`themis_video/pipeline.py` の先頭に `import logging` を追加し、`import requests` の後に `logger = logging.getLogger(__name__)` と `_NOT_ACCEPTED = (409, 429)` を置く。`process` の送信部分を次に置き換える。

```python
        try:
            response = self.session.post(self.trigger_url, json={}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise VisualTriggerError("visual start trigger failed") from exc
        if response.status_code in _NOT_ACCEPTED:
            # Expected while a cycle runs or someone is using the kiosk: stay
            # armed but wait out the cooldown instead of posting every frame.
            logger.info("visual start not accepted: HTTP %d", response.status_code)
            self._last_triggered = now
            return False
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise VisualTriggerError("visual start trigger failed") from exc
        self._last_triggered = now
        self._armed = False
        return True
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_visual_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add themis_video/pipeline.py tests/test_visual_pipeline.py
git commit -m "fix: treat 409/429 from visual start as expected in pipeline

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `voice_ui` を開始キーワード → `/api/voice/start` にする

**Files:**
- Create: `voice_ui/start_keyword.py`, `voice_ui/start_client.py`
- Modify: `voice_ui/pipeline.py`, `voice_ui/main.py`, `voice_ui/config.py`
- Delete: `voice_ui/checkin_client.py`, `voice_ui/name_extract.py`, `tests/test_voice_ui_checkin_client.py`, `tests/test_voice_ui_name_extract.py`
- Create: `tests/test_voice_ui_start_keyword.py`, `tests/test_voice_ui_start_client.py`
- Modify: `tests/test_voice_ui_pipeline.py`（全面書き換え）, `tests/test_voice_ui_config.py`

**Interfaces:**
- Consumes: `POST /api/voice/start`（Task 2）
- Produces:
  - `voice_ui.start_keyword.contains_start_keyword(text: str, keywords: list[str]) -> bool`
  - `voice_ui.start_client.VoiceStartClient(base_url: str, timeout: float = 5.0)`、`.start() -> str`（`accepted` / `not_available` / `rate_limited` / `timeout` / `connection_error` / `server_error`）
  - `voice_ui.pipeline.run_start_once(mic_source, vad_segmenter, transcriber, start_client, start_keywords, no_speech_prob_max, avg_logprob_min, read_timeout=1.0) -> str`（`no_utterance` / `rejected_low_confidence` / `no_keyword` / `start_requested`）
  - `voice_ui.config.VOICE_START_KEYWORDS: list[str]`
  - `voice_ui.main.run_checkin_loop(mic_source, vad_segmenter, transcriber, start_client, no_utterance_exit_threshold=...)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_start_keyword.py`:

```python
import pytest

from voice_ui.start_keyword import contains_start_keyword


@pytest.mark.parametrize(
    "text",
    [
        "チェックイン",
        "チェックインお願いします",
        "チェックイン。",
        "チェック イン",
        "ﾁｪｯｸｲﾝ",
        "すみません、チェックインしたいです",
    ],
)
def test_matches_whisper_variants(text):
    assert contains_start_keyword(text, ["チェックイン"]) is True


@pytest.mark.parametrize("text", ["", "こんにちは", "チェックアウト", "田中太郎です"])
def test_ignores_other_utterances(text):
    assert contains_start_keyword(text, ["チェックイン"]) is False


def test_any_configured_keyword_matches():
    assert contains_start_keyword("Check in please", ["チェックイン", "check in"]) is True


def test_blank_keywords_never_match():
    assert contains_start_keyword("こんにちは", ["", " "]) is False
```

`tests/test_voice_ui_start_client.py`:

```python
import pytest
import requests
import responses

from voice_ui.start_client import VoiceStartClient

URL = "http://flask.test/api/voice/start"


def make_client():
    return VoiceStartClient(base_url="http://flask.test", timeout=1.0)


@responses.activate
@pytest.mark.parametrize(
    "status, expected",
    [
        (202, "accepted"),
        (409, "not_available"),
        (429, "rate_limited"),
        (500, "server_error"),
    ],
)
def test_start_classifies_status(status, expected):
    responses.add(responses.POST, URL, json={}, status=status)

    assert make_client().start() == expected
    assert responses.calls[0].request.body == b"{}"


@responses.activate
def test_start_timeout():
    responses.add(responses.POST, URL, body=requests.exceptions.Timeout())

    assert make_client().start() == "timeout"


@responses.activate
def test_start_connection_error():
    responses.add(responses.POST, URL, body=requests.exceptions.ConnectionError())

    assert make_client().start() == "connection_error"
```

`tests/test_voice_ui_pipeline.py` を次の内容で全面的に置き換える。

```python
import logging

from voice_ui.pipeline import run_start_once

KEYWORDS = ["チェックイン"]


class _FakeMicSource:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def read_chunk(self, timeout=None):
        if not self._chunks:
            return None
        return self._chunks.pop(0)


class _FakeVadSegmenter:
    def __init__(self, utterance_after):
        self._utterance_after = utterance_after
        self._count = 0

    def feed(self, chunk):
        self._count += 1
        if self._count >= self._utterance_after:
            return "UTTERANCE"
        return None


class _FakeTranscriber:
    def __init__(self, result):
        self._result = result

    def transcribe(self, utterance):
        return self._result


class _FakeStartClient:
    def __init__(self, result="accepted"):
        self.calls = 0
        self._result = result

    def start(self):
        self.calls += 1
        return self._result


def _run(transcription, start_client, chunks=(object(),), utterance_after=1):
    return run_start_once(
        _FakeMicSource(list(chunks)),
        _FakeVadSegmenter(utterance_after=utterance_after),
        _FakeTranscriber(transcription),
        start_client,
        KEYWORDS,
        no_speech_prob_max=0.6,
        avg_logprob_min=-1.0,
    )


def test_keyword_utterance_requests_start():
    start_client = _FakeStartClient()

    assert _run(("チェックインお願いします", 0.1, -0.2), start_client) == "start_requested"
    assert start_client.calls == 1


def test_utterance_without_keyword_is_ignored(caplog):
    start_client = _FakeStartClient()

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = _run(("田中太郎です", 0.1, -0.2), start_client)

    assert outcome == "no_keyword"
    assert start_client.calls == 0
    assert "田中太郎です" in caplog.text


def test_start_result_is_logged_even_when_not_accepted(caplog):
    start_client = _FakeStartClient(result="not_available")

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        outcome = _run(("チェックイン", 0.1, -0.2), start_client)

    assert outcome == "start_requested"
    assert "not_available" in caplog.text


def test_low_confidence_transcription_is_rejected_without_start():
    start_client = _FakeStartClient()

    assert _run(("チェックイン", 0.9, -5.0), start_client) == "rejected_low_confidence"
    assert start_client.calls == 0


def test_low_confidence_rejection_logs_text_and_confidence_scores(caplog):
    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        _run(("ノイズ", 0.9, -5.0), _FakeStartClient())

    assert "ノイズ" in caplog.text
    assert "0.9" in caplog.text
    assert "-5.0" in caplog.text


def test_no_chunk_available_returns_without_start():
    start_client = _FakeStartClient()

    assert _run(("unused", 0.0, 0.0), start_client, chunks=()) == "no_utterance"
    assert start_client.calls == 0


def test_multiple_chunks_are_fed_until_utterance_completes():
    start_client = _FakeStartClient()

    outcome = _run(
        ("チェックイン", 0.1, -0.2),
        start_client,
        chunks=(object(), object(), object()),
        utterance_after=3,
    )

    assert outcome == "start_requested"
    assert start_client.calls == 1
```

`tests/test_voice_ui_config.py`:
- 両テストの `monkeypatch` の並びに `VOICE_START_KEYWORDS` を足す（defaultsでは `monkeypatch.delenv("VOICE_START_KEYWORDS", raising=False)`、overridesでは `monkeypatch.setenv("VOICE_START_KEYWORDS", "チェックイン, check in ,")`）。
- defaultsに `assert config.VOICE_START_KEYWORDS == ["チェックイン"]`、overridesに `assert config.VOICE_START_KEYWORDS == ["チェックイン", "check in"]` を足す。

旧テストを削除する。

```bash
git rm -q tests/test_voice_ui_checkin_client.py tests/test_voice_ui_name_extract.py
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_start_keyword.py tests/test_voice_ui_start_client.py tests/test_voice_ui_pipeline.py tests/test_voice_ui_config.py -q`
Expected: FAIL（`No module named 'voice_ui.start_keyword'` など）

- [ ] **Step 3: 実装する**

`voice_ui/start_keyword.py`:

```python
import unicodedata


def _normalize(text: str) -> str:
    # NFKC folds half-width kana, and dropping whitespace plus substring
    # matching absorbs Whisper's spacing and trailing punctuation.
    return "".join(unicodedata.normalize("NFKC", text).split()).casefold()


def contains_start_keyword(text: str, keywords: list[str]) -> bool:
    normalized = _normalize(text)
    for keyword in keywords:
        key = _normalize(keyword)
        if key and key in normalized:
            return True
    return False
```

`voice_ui/start_client.py`:

```python
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
```

`voice_ui/pipeline.py` を次の内容に置き換える。

```python
import logging

from .start_keyword import contains_start_keyword
from .stt import is_confident

logger = logging.getLogger(__name__)


def run_start_once(
    mic_source,
    vad_segmenter,
    transcriber,
    start_client,
    start_keywords,
    no_speech_prob_max,
    avg_logprob_min,
    read_timeout=1.0,
):
    utterance = None
    while utterance is None:
        chunk = mic_source.read_chunk(timeout=read_timeout)
        if chunk is None:
            return "no_utterance"
        utterance = vad_segmenter.feed(chunk)

    text, no_speech_prob, avg_logprob = transcriber.transcribe(utterance)
    if not is_confident(no_speech_prob, avg_logprob, no_speech_prob_max, avg_logprob_min):
        logger.warning(
            "低信頼度のため却下しました: text=%r no_speech_prob=%.3f avg_logprob=%.3f "
            "(no_speech_prob_max=%.3f avg_logprob_min=%.3f)",
            text,
            no_speech_prob,
            avg_logprob,
            no_speech_prob_max,
            avg_logprob_min,
        )
        return "rejected_low_confidence"

    if not contains_start_keyword(text, start_keywords):
        logger.info("開始キーワードを含まない発話を無視しました: text=%r", text)
        return "no_keyword"

    result = start_client.start()
    logger.info("チェックイン開始を依頼しました: result=%s text=%r", result, text)
    return "start_requested"
```

`voice_ui/config.py` の末尾に追加する。

```python
VOICE_START_KEYWORDS = [
    keyword.strip()
    for keyword in os.environ.get("VOICE_START_KEYWORDS", "チェックイン").split(",")
    if keyword.strip()
]
```

`voice_ui/main.py`:
- `from .checkin_client import CheckinClient` → `from .start_client import VoiceStartClient`
- `from .pipeline import run_checkin_once` → `from .pipeline import run_start_once`
- `run_checkin_loop` の引数 `checkin_client` を `start_client` に改名し、中身を次にする。

```python
    def _outcomes():
        while True:
            yield run_start_once(
                mic_source,
                vad_segmenter,
                transcriber,
                start_client,
                config.VOICE_START_KEYWORDS,
                no_speech_prob_max=config.STT_NO_SPEECH_PROB_MAX,
                avg_logprob_min=config.STT_AVG_LOGPROB_MIN,
            )
```

- `main()` の `checkin_client = CheckinClient(base_url=config.FLASK_BASE_URL)` を `start_client = VoiceStartClient(base_url=config.FLASK_BASE_URL)` にし、最後の `run_checkin_loop(..., checkin_client)` を `run_checkin_loop(mic_source, vad_segmenter, transcriber, start_client)` にする。

旧モジュールを削除する。

```bash
git rm -q voice_ui/checkin_client.py voice_ui/name_extract.py
grep -rn "checkin_client\|name_extract\|CheckinClient\|run_checkin_once" voice_ui tests
```

Expected: `grep` は何も出さない。

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/ -q -k voice_ui`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add voice_ui tests/test_voice_ui_start_keyword.py tests/test_voice_ui_start_client.py \
  tests/test_voice_ui_pipeline.py tests/test_voice_ui_config.py
git commit -m "feat: start kiosk check-in by voice keyword instead of name check-in

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 発話開始の案内を読み上げ、`type` 付きイベントを無視する

**Files:**
- Modify: `voice_ui/progress_announcer.py`, `voice_ui/step_messages.py`
- Test: `tests/test_voice_ui_progress_announcer.py`

**Interfaces:**
- Consumes: snapshotの `entry_source`, `entry_stage`（Task 1）、`ui_action` イベント（Task 2）
- Produces: `voice_ui.step_messages.VOICE_START_GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_progress_announcer.py` の末尾に追加する。

```python
GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"


def _waiting(entry_source=None, entry_stage=None):
    return {
        "phase": "waiting",
        "step": "awaiting_checkin",
        "entry_source": entry_source,
        "entry_stage": entry_stage,
    }


def test_speaks_guidance_when_voice_start_is_recorded():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(_waiting())
    announcer.handle_snapshot(_waiting("voice", "start"))
    announcer.handle_snapshot(_waiting("voice", "start"))

    assert spoken == [GUIDANCE]


def test_no_guidance_for_other_entries():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot(_waiting("visual", "start"))
    announcer.handle_snapshot(_waiting("screen", "start"))
    announcer.handle_snapshot(_waiting("voice", "select"))

    assert spoken == []


def test_ui_action_events_do_not_reset_step_memory():
    spoken = []
    announcer = ProgressAnnouncer(speak=spoken.append)

    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})
    announcer.handle_snapshot({"type": "ui_action", "action": "start_checkin"})
    announcer.handle_snapshot({"phase": "waiting", "step": "polling_pf_ready"})

    assert spoken == ["AI管制PF(案内ロボット)の状態を確認しています"]
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_progress_announcer.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`voice_ui/step_messages.py` の末尾に追加する。

```python
VOICE_START_GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"
```

`voice_ui/progress_announcer.py` を次にする。

```python
from .step_messages import STEP_MESSAGES, VOICE_START_GUIDANCE

_VOICE_START = ("voice", "start")


class ProgressAnnouncer:
    def __init__(self, speak):
        self._speak = speak
        self._last_step = None
        self._last_phase = None
        self._last_entry = None

    def handle_snapshot(self, snapshot):
        # Typed events (e.g. ui_action) are not state snapshots.
        if "type" in snapshot:
            return

        entry = (snapshot.get("entry_source"), snapshot.get("entry_stage"))
        if entry == _VOICE_START and self._last_entry != _VOICE_START:
            self._speak(VOICE_START_GUIDANCE)
        self._last_entry = entry

        phase = snapshot.get("phase")
        step = snapshot.get("step")

        if phase == "error":
            if self._last_phase != "error":
                self._speak(snapshot.get("error_message") or "エラーが発生しました")
            self._last_phase = phase
            self._last_step = step
            return

        if step != self._last_step:
            message = STEP_MESSAGES.get(step)
            if message:
                self._speak(message)

        self._last_phase = phase
        self._last_step = step
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_progress_announcer.py tests/test_voice_ui_main.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add voice_ui/progress_announcer.py voice_ui/step_messages.py tests/test_voice_ui_progress_announcer.py
git commit -m "feat: speak input guidance after voice start and ignore typed SSE events

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: ドキュメントと全体確認

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1〜8のすべて
- Produces: なし

- [ ] **Step 1: READMEを更新する**

`README.md` の「Themis WebSocket image client」節で `POST /api/visual/start` を説明している段落の直後に、次を追加する。

```markdown
### Check-in entries

Check-in always follows the kiosk sequence: start → reservation select →
check-in. The kiosk's start button, the VLM (`POST /api/visual/start`) and
voice (`POST /api/voice/start`) only differ in how "start" is detected; all of
them open the kiosk search screen, and the guest searches, selects and confirms
on screen. `POST /api/checkin` requires `reservation_id`.

Visual and voice starts return 409 while a cycle runs or while someone is using
the kiosk (an entry at start/select). An entry idle for `ENTRY_IDLE_SECONDS`
(default 60) no longer blocks them.

`voice_ui` calls `/api/voice/start` when a confident utterance contains one of
`VOICE_START_KEYWORDS` (comma separated, default `チェックイン`), then reads out
the on-screen input guidance.

`/debug` shows the current entry and stage live.
```

- [ ] **Step 2: 全テストを実行する**

Run: `.venv/bin/python -m pytest -q`
Expected: すべてPASS

- [ ] **Step 3: 実際に起動して確認する**

```bash
.venv/bin/python run_mocks.py &
.venv/bin/python run.py &
sleep 5
curl -s -X POST localhost:5100/api/voice/start -H 'Content-Type: application/json' -d '{}'
curl -s -X POST localhost:5100/api/entry -H 'Content-Type: application/json' -d '{"stage":"select"}'
curl -s -X POST localhost:5100/api/visual/start -H 'Content-Type: application/json' -d '{}'
curl -s -X DELETE localhost:5100/api/entry
```

Expected: 1つ目202、2つ目202（入口は `voice/select`）、3つ目409（操作中）、4つ目 `{"cleared": true}`。ブラウザで `http://localhost:5100/debug` を開き、キオスク（`http://localhost:5100/`、開き直すこと）で「開始 → 検索 → 予約選択 → 確定」と操作して、入口欄が「画面操作：開始ボタン → 予約選択 → チェックイン完了」の順に強調され、サイクル終了で消えることを確認する。確認後、起動したプロセスを止める。

- [ ] **Step 4: コミットする**

```bash
git add README.md
git commit -m "docs: describe check-in entries

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
