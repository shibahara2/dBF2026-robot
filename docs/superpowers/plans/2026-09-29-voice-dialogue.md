# 音声対話（フロント雑談） Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `voice_ui` で、チェックインの意図は今の開始動作につなぎ、それ以外のフロント宛ての質問・雑談には LLM の返事を読み上げ、宛てでない会話には黙る。会話はデバッグ画面で見られる。

**Architecture:** 対話は `voice_ui` の中で完結する。`DialogueLLMClient`（OpenAI互換、JSON schema 強制）を `DialogueAgent`（プロンプト・履歴・判定）が使い、`run_turn_once`（パイプライン）が「エコーガード → 確信度 → キーワード即開始 → LLM 判定」の順に振り分ける。`VoicevoxSpeaker` は合成と再生を別スレッドにして文単位で先読み合成し、再生中を `is_busy()` で知らせる。会話ログは `POST /api/voice/turns` でアプリに送り、アプリは直近20件を保持して SSE の typed event で配信する。

**Tech Stack:** Python 3.12, Flask 3.0.3, requests, pytest + responses, バニラJS

**Spec:** `docs/superpowers/specs/2026-09-29-voice-dialogue-design.md`

## Global Constraints

- 新しい依存パッケージは追加しない。
- テストは `.venv/bin/python -m pytest` で実行する（プロジェクト直下）。
- LLM 出力の schema は `{"intent": "checkin"|"chat"|"ignore", "reply": string}`、`required` は両方、`additionalProperties: false`。
- LLM 呼び出しは `temperature=0.3`、`max_tokens=200`。
- 時間切れ・HTTPエラー・不正出力は `ignore` 扱い（例外を外に出さない）。
- 会話履歴: `DIALOGUE_HISTORY_TURNS`（既定6）往復、`DIALOGUE_IDLE_RESET_SECONDS`（既定60）で消去、`checkin` で消去、`ignore` は履歴に入れない。
- `BUSY_MESSAGE` は `ただいま他のお客様をご案内しています。少々お待ちください`（一字一句このまま）。
- 事前合成の対象は `VOICE_START_GUIDANCE` と `BUSY_MESSAGE`。
- `ECHO_GUARD_SECONDS` 既定 `0.5`。再生中または最後の再生終了から0.5秒以内に確定した発話は `self_echo` として破棄する。
- `outcome` は `rejected_low_confidence` / `self_echo` / `keyword_start` / `checkin` / `chat` / `ignore` / `no_keyword` のいずれか。
- アプリの会話ログは直近20件、`GET /api/voice/turns` は新しい順。
- 環境変数と既定値は仕様の「設定」表のとおり（`DIALOGUE_LLM_URL` 既定 `http://10.43.10.179:8000/v1`、`DIALOGUE_LLM_MODEL` 既定 `qwen3.6-35b-a3b`、`DIALOGUE_LLM_TIMEOUT_SECONDS` 既定 `8`）。
- コミットメッセージの末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` を付ける。

## Review Focus

- LLM が `intent=chat` で `reply` を空文字で返す → 何も読み上げず、履歴も汚さない（`ignore` 扱い）。→ Task 2
- 返事が句点で終わらない、または「！」「?」で区切られる → 文が欠けずに全部読み上げられる。→ Task 3
- 読み上げ直後（0.5秒以内）にマイクが拾った残響 → LLM に回らない。0.5秒を過ぎた来場者の発話は通る。→ Task 3, Task 5
- 60秒以上あけて次の人が話す → 前の人の会話が履歴に残らない。→ Task 2
- LLM がチェックインと判断したがサイクル中（409） → `BUSY_MESSAGE` を読み上げる。キーワード経由も同じ。→ Task 5

---

## File Structure

| ファイル | 役割 | Task |
|---|---|---|
| `data/hotel_info.md`（新規） | 架空ホテルの情報 | 1 |
| `voice_ui/config.py` | 対話関連の設定 | 1 |
| `voice_ui/llm_client.py`（新規） | OpenAI互換 LLM 呼び出しと出力の検証 | 1 |
| `voice_ui/dialogue.py`（新規） | プロンプト、履歴、判定 | 2 |
| `voice_ui/tts.py`, `voice_ui/step_messages.py` | 文区切り、合成/再生の分離、`is_busy()`、`BUSY_MESSAGE` | 3 |
| `app/voice_turns.py`（新規）, `app/routes/voice_turns.py`（新規）, `app/__init__.py` | 会話ログの保持・API・SSE | 4 |
| `voice_ui/turn_reporter.py`（新規）, `voice_ui/pipeline.py`, `voice_ui/main.py` | 振り分けと配線 | 5 |
| `app/templates/debug.html`, `app/static/debug.js`, `app/static/debug.css` | 音声対話ログ欄 | 6 |
| `tools/dialogue_eval.py`（新規）, `tests/fixtures/dialogue/cases.json`（新規） | 判定精度の評価 | 7 |
| `README.md` | ドキュメント | 8 |

---

### Task 1: ホテル情報、設定、LLM クライアント

**Files:**
- Create: `data/hotel_info.md`, `voice_ui/llm_client.py`, `tests/test_voice_ui_llm_client.py`
- Modify: `voice_ui/config.py`, `tests/test_voice_ui_config.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `voice_ui.llm_client.INTENTS = ("checkin", "chat", "ignore")`
  - `voice_ui.llm_client.DIALOGUE_SCHEMA`（Global Constraints の schema）
  - `voice_ui.llm_client.DialogueLLMError(RuntimeError)`
  - `voice_ui.llm_client.DialogueLLMClient(base_url: str, model: str, *, api_key: str | None = None, timeout: float = 8.0, session=None)`、`.decide(messages: list[dict]) -> dict`（`{"intent": str, "reply": str}`、失敗時 `DialogueLLMError`）
  - `voice_ui.config`: `DIALOGUE_ENABLED: bool`, `DIALOGUE_LLM_URL: str`, `DIALOGUE_LLM_MODEL: str`, `DIALOGUE_LLM_API_KEY: str | None`, `DIALOGUE_LLM_TIMEOUT_SECONDS: float`, `DIALOGUE_HISTORY_TURNS: int`, `DIALOGUE_IDLE_RESET_SECONDS: float`, `HOTEL_INFO_FILE: str`, `ECHO_GUARD_SECONDS: float`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_llm_client.py`:

```python
import json

import pytest
import requests
import responses

from voice_ui.llm_client import (
    DIALOGUE_SCHEMA,
    DialogueLLMClient,
    DialogueLLMError,
)

URL = "http://llm.test/v1"
MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "こんにちは"}]


def _reply(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@responses.activate
def test_decide_sends_schema_and_returns_decision():
    responses.add(
        responses.POST,
        f"{URL}/chat/completions",
        json=_reply('{"intent": "chat", "reply": "いらっしゃいませ。"}'),
    )
    client = DialogueLLMClient(URL, "qwen3.6-35b-a3b", api_key="k", timeout=3.0)

    assert client.decide(MESSAGES) == {"intent": "chat", "reply": "いらっしゃいませ。"}

    request = responses.calls[0].request
    body = json.loads(request.body)
    assert request.headers["Authorization"] == "Bearer k"
    assert body["model"] == "qwen3.6-35b-a3b"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 200
    assert body["response_format"]["json_schema"]["schema"] == DIALOGUE_SCHEMA


def test_schema_restricts_intent_and_requires_reply():
    assert DIALOGUE_SCHEMA["properties"]["intent"]["enum"] == ["checkin", "chat", "ignore"]
    assert DIALOGUE_SCHEMA["required"] == ["intent", "reply"]
    assert DIALOGUE_SCHEMA["additionalProperties"] is False


@responses.activate
@pytest.mark.parametrize(
    "content",
    [
        "はい",
        '{"intent": "maybe", "reply": ""}',
        '{"intent": "chat"}',
        '{"intent": "chat", "reply": 3}',
    ],
)
def test_decide_rejects_invalid_output(content):
    responses.add(responses.POST, f"{URL}/chat/completions", json=_reply(content))

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)


@responses.activate
def test_decide_wraps_http_error():
    responses.add(responses.POST, f"{URL}/chat/completions", status=503)

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)


@responses.activate
def test_decide_wraps_timeout():
    responses.add(
        responses.POST, f"{URL}/chat/completions", body=requests.exceptions.Timeout()
    )

    with pytest.raises(DialogueLLMError):
        DialogueLLMClient(URL, "m").decide(MESSAGES)
```

`tests/test_voice_ui_config.py`:
- `test_defaults_when_env_not_set` の `monkeypatch.delenv` の並びに、次の各変数の `monkeypatch.delenv(<name>, raising=False)` を追加する: `DIALOGUE_ENABLED`, `DIALOGUE_LLM_URL`, `DIALOGUE_LLM_MODEL`, `DIALOGUE_LLM_API_KEY`, `DIALOGUE_LLM_TIMEOUT_SECONDS`, `DIALOGUE_HISTORY_TURNS`, `DIALOGUE_IDLE_RESET_SECONDS`, `HOTEL_INFO_FILE`, `ECHO_GUARD_SECONDS`。
- 同テストの末尾に追加する:

```python
    assert config.DIALOGUE_ENABLED is True
    assert config.DIALOGUE_LLM_URL == "http://10.43.10.179:8000/v1"
    assert config.DIALOGUE_LLM_MODEL == "qwen3.6-35b-a3b"
    assert config.DIALOGUE_LLM_API_KEY is None
    assert config.DIALOGUE_LLM_TIMEOUT_SECONDS == 8.0
    assert config.DIALOGUE_HISTORY_TURNS == 6
    assert config.DIALOGUE_IDLE_RESET_SECONDS == 60.0
    assert config.HOTEL_INFO_FILE.endswith("data/hotel_info.md")
    assert config.ECHO_GUARD_SECONDS == 0.5
```

- ファイル末尾に追加する:

```python
def test_dialogue_env_overrides(monkeypatch):
    monkeypatch.setenv("DIALOGUE_ENABLED", "0")
    monkeypatch.setenv("DIALOGUE_LLM_URL", "http://llm.example/v1")
    monkeypatch.setenv("DIALOGUE_LLM_MODEL", "other")
    monkeypatch.setenv("DIALOGUE_LLM_API_KEY", "secret")
    monkeypatch.setenv("DIALOGUE_LLM_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("DIALOGUE_HISTORY_TURNS", "2")
    monkeypatch.setenv("DIALOGUE_IDLE_RESET_SECONDS", "30")
    monkeypatch.setenv("HOTEL_INFO_FILE", "/tmp/hotel.md")
    monkeypatch.setenv("ECHO_GUARD_SECONDS", "0.8")

    from voice_ui import config
    importlib.reload(config)

    assert config.DIALOGUE_ENABLED is False
    assert config.DIALOGUE_LLM_URL == "http://llm.example/v1"
    assert config.DIALOGUE_LLM_MODEL == "other"
    assert config.DIALOGUE_LLM_API_KEY == "secret"
    assert config.DIALOGUE_LLM_TIMEOUT_SECONDS == 3.0
    assert config.DIALOGUE_HISTORY_TURNS == 2
    assert config.DIALOGUE_IDLE_RESET_SECONDS == 30.0
    assert config.HOTEL_INFO_FILE == "/tmp/hotel.md"
    assert config.ECHO_GUARD_SECONDS == 0.8
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_llm_client.py tests/test_voice_ui_config.py -q`
Expected: FAIL（`No module named 'voice_ui.llm_client'`、`AttributeError: ... 'DIALOGUE_ENABLED'`）

- [ ] **Step 3: 実装する**

`voice_ui/llm_client.py`:

```python
"""OpenAI-compatible chat client that returns a front-desk turn decision."""

import json

import requests

INTENTS = ("checkin", "chat", "ignore")

DIALOGUE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "reply": {"type": "string"},
    },
    "required": ["intent", "reply"],
    "additionalProperties": False,
}


class DialogueLLMError(RuntimeError):
    """Raised when the LLM cannot produce a valid turn decision."""


class DialogueLLMClient:
    def __init__(self, base_url, model, *, api_key=None, timeout=8.0, session=None):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._session = session or requests.Session()
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def decide(self, messages):
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 200,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "front_desk_turn",
                    "schema": DIALOGUE_SCHEMA,
                    "strict": True,
                },
            },
        }
        try:
            response = self._session.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            decision = json.loads(content)
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            raise DialogueLLMError(f"dialogue LLM failed: {exc}") from exc

        intent = decision.get("intent") if isinstance(decision, dict) else None
        reply = decision.get("reply") if isinstance(decision, dict) else None
        if intent not in INTENTS or not isinstance(reply, str):
            raise DialogueLLMError(f"unexpected dialogue output: {content!r}")
        return {"intent": intent, "reply": reply}
```

`voice_ui/config.py` の先頭 `import os` の後に `_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` を追加し、末尾に追加する:

```python
DIALOGUE_ENABLED = os.environ.get("DIALOGUE_ENABLED", "1") == "1"
DIALOGUE_LLM_URL = os.environ.get("DIALOGUE_LLM_URL", "http://10.43.10.179:8000/v1")
DIALOGUE_LLM_MODEL = os.environ.get("DIALOGUE_LLM_MODEL", "qwen3.6-35b-a3b")
DIALOGUE_LLM_API_KEY = os.environ.get("DIALOGUE_LLM_API_KEY") or None
DIALOGUE_LLM_TIMEOUT_SECONDS = float(os.environ.get("DIALOGUE_LLM_TIMEOUT_SECONDS", "8"))
DIALOGUE_HISTORY_TURNS = int(os.environ.get("DIALOGUE_HISTORY_TURNS", "6"))
DIALOGUE_IDLE_RESET_SECONDS = float(os.environ.get("DIALOGUE_IDLE_RESET_SECONDS", "60"))
HOTEL_INFO_FILE = os.environ.get(
    "HOTEL_INFO_FILE", os.path.join(_PROJECT_ROOT, "data", "hotel_info.md")
)
ECHO_GUARD_SECONDS = float(os.environ.get("ECHO_GUARD_SECONDS", "0.5"))
```

`data/hotel_info.md`:

```markdown
# ホテル・サクラテラス東京（デモ用の架空ホテル）

## 基本情報
- チェックイン: 15時から
- チェックアウト: 11時まで
- フロント: 24時間営業
- 客室数: 120室（全室禁煙）

## 朝食
- 時間: 6時30分から10時まで（最終入場9時30分）
- 場所: 1階レストラン「さくら」
- 形式: 和洋ビュッフェ
- 朝食付きプランでないお客様は、当日フロントでお申し込みいただけます（料金はスタッフにお尋ねください）

## 館内設備
- Wi-Fi: 館内全域で無料。ネットワーク名とパスワードはお部屋のカードに記載
- 大浴場: 2階。15時から翌1時、6時から10時まで
- コインランドリー: 3階。24時間利用可能
- 自動販売機: 各階のエレベーター前
- ジムはありません

## サービス
- 荷物預かり: チェックイン前・チェックアウト後も当日中はフロントでお預かりします
- タクシー: フロントでお呼びします
- 貸し出し品: 充電器、加湿器、ズボンプレッサー（数に限りがあります）

## 周辺案内
- 最寄り駅: 桜町駅 徒歩5分
- コンビニ: ホテルを出て右へ徒歩1分
- 周辺の飲食店: フロントで地図をお渡しします

## お願い
- 館内は全面禁煙です
- ペットの同伴はご遠慮いただいております
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_llm_client.py tests/test_voice_ui_config.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add data/hotel_info.md voice_ui/llm_client.py voice_ui/config.py \
  tests/test_voice_ui_llm_client.py tests/test_voice_ui_config.py
git commit -m "feat: add hotel info, dialogue settings and LLM client for voice dialogue

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 対話エージェント（プロンプト・履歴・判定）

**Files:**
- Create: `voice_ui/dialogue.py`, `tests/test_voice_ui_dialogue.py`

**Interfaces:**
- Consumes: `DialogueLLMClient.decide(messages) -> dict`, `DialogueLLMError`（Task 1）
- Produces:
  - `voice_ui.dialogue.Decision(intent: str, reply: str)`（frozen dataclass）
  - `voice_ui.dialogue.build_system_prompt(hotel_info: str) -> str`
  - `voice_ui.dialogue.DialogueAgent(llm, hotel_info: str, *, history_turns: int = 6, idle_reset_seconds: float = 60.0, clock=time.monotonic)`、`.respond(text: str) -> Decision`（`reply` は `chat` のときだけ非空）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_dialogue.py`:

```python
from voice_ui.dialogue import Decision, DialogueAgent, build_system_prompt
from voice_ui.llm_client import DialogueLLMError

HOTEL = "# テストホテル\n- 朝食: 7時から"


class FakeLLM:
    def __init__(self, *results):
        self._results = list(results)
        self.calls = []

    def decide(self, messages):
        self.calls.append(messages)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def chat(reply):
    return {"intent": "chat", "reply": reply}


def _agent(llm, clock=None, turns=6):
    return DialogueAgent(
        llm, HOTEL, history_turns=turns, idle_reset_seconds=60.0, clock=clock or FakeClock()
    )


def test_system_prompt_contains_hotel_info_and_rules():
    prompt = build_system_prompt(HOTEL)

    assert HOTEL in prompt
    for word in ["checkin", "chat", "ignore", "スタッフにお尋ねください", "迷ったら ignore"]:
        assert word in prompt


def test_chat_returns_reply_and_sends_system_then_user():
    llm = FakeLLM(chat("7時からです。"))

    assert _agent(llm).respond("朝ごはんは何時？") == Decision("chat", "7時からです。")
    messages = llm.calls[0]
    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "朝ごはんは何時？"}


def test_chat_history_is_sent_on_next_turn():
    llm = FakeLLM(chat("7時からです。"), chat("1階です。"))
    agent = _agent(llm)

    agent.respond("朝ごはんは何時？")
    agent.respond("場所は？")

    assert llm.calls[1][1:] == [
        {"role": "user", "content": "朝ごはんは何時？"},
        {"role": "assistant", "content": "7時からです。"},
        {"role": "user", "content": "場所は？"},
    ]


def test_history_keeps_only_last_turns():
    llm = FakeLLM(chat("a"), chat("b"), chat("c"), chat("d"))
    agent = _agent(llm, turns=2)

    for text in ["1", "2", "3", "4"]:
        agent.respond(text)

    sent = llm.calls[3][1:]
    assert sent == [
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "4"},
    ]


def test_ignore_is_not_kept_in_history_and_has_no_reply():
    llm = FakeLLM({"intent": "ignore", "reply": "何か"}, chat("はい。"))
    agent = _agent(llm)

    assert agent.respond("それでさあ") == Decision("ignore", "")
    agent.respond("こんにちは")

    assert llm.calls[1][1:] == [{"role": "user", "content": "こんにちは"}]


def test_chat_with_empty_reply_is_treated_as_ignore():
    llm = FakeLLM(chat("  "), chat("はい。"))
    agent = _agent(llm)

    assert agent.respond("えっと") == Decision("ignore", "")
    agent.respond("こんにちは")

    assert llm.calls[1][1:] == [{"role": "user", "content": "こんにちは"}]


def test_checkin_clears_history_and_has_no_reply():
    llm = FakeLLM(chat("こんにちは。"), {"intent": "checkin", "reply": "どうぞ"}, chat("はい。"))
    agent = _agent(llm)

    agent.respond("こんにちは")
    assert agent.respond("部屋に入りたい") == Decision("checkin", "")
    agent.respond("ありがとう")

    assert llm.calls[2][1:] == [{"role": "user", "content": "ありがとう"}]


def test_history_is_cleared_after_idle_seconds():
    clock = FakeClock()
    llm = FakeLLM(chat("こんにちは。"), chat("はい。"), chat("どうぞ。"))
    agent = _agent(llm, clock=clock)

    agent.respond("こんにちは")
    clock.value = 10.0
    agent.respond("朝食は？")
    assert len(llm.calls[1]) == 4  # system + previous turn + new user

    clock.value = 70.0  # 60 seconds after the last utterance
    agent.respond("Wi-Fiは？")
    assert llm.calls[2][1:] == [{"role": "user", "content": "Wi-Fiは？"}]


def test_llm_error_is_treated_as_ignore():
    llm = FakeLLM(DialogueLLMError("timeout"))

    assert _agent(llm).respond("こんにちは") == Decision("ignore", "")
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_dialogue.py -q`
Expected: FAIL（`No module named 'voice_ui.dialogue'`）

- [ ] **Step 3: 実装する**

`voice_ui/dialogue.py`:

```python
"""Front-desk dialogue: decides checkin / chat / ignore for one utterance."""

import logging
import time
from dataclasses import dataclass

from .llm_client import DialogueLLMError

logger = logging.getLogger(__name__)

_PROMPT = """あなたは以下のホテル情報に書かれたホテルのフロントにいる案内ロボットです。
来場者の発話を1つ受け取り、次のどれかに判定して JSON で答えてください。
- checkin: チェックインの手続きを求めている（チェックインしたい、予約して来た、部屋に入りたい など）
- chat: あなた（フロント）に向けた質問・挨拶・雑談
- ignore: あなた宛てではない周囲の会話、独り言、意味をなさない断片。迷ったら ignore
chat のときだけ reply に返事を書いてください。返事は丁寧な日本語で1〜2文、合計80文字程度までにし、読み上げるので記号・箇条書き・絵文字は使わないでください。
ホテルに関する事実はホテル情報に書かれている範囲だけで答え、書かれていなければ「スタッフにお尋ねください」と答えてください。天気や挨拶などの一般的な雑談には自由に答えてかまいません。
checkin と ignore のときは reply を空にしてください。

# ホテル情報
"""


@dataclass(frozen=True)
class Decision:
    intent: str
    reply: str


def build_system_prompt(hotel_info):
    return _PROMPT + hotel_info


class DialogueAgent:
    def __init__(
        self,
        llm,
        hotel_info,
        *,
        history_turns=6,
        idle_reset_seconds=60.0,
        clock=time.monotonic,
    ):
        self._llm = llm
        self._system = {"role": "system", "content": build_system_prompt(hotel_info)}
        self._history_turns = history_turns
        self._idle_reset_seconds = idle_reset_seconds
        self._clock = clock
        self._history = []
        self._last_at = None

    def respond(self, text):
        now = self._clock()
        if self._last_at is not None and now - self._last_at >= self._idle_reset_seconds:
            # A new visitor should not inherit the previous conversation.
            self._history.clear()
        self._last_at = now

        user = {"role": "user", "content": text}
        try:
            result = self._llm.decide([self._system, *self._history, user])
        except DialogueLLMError:
            logger.warning("対話LLMの判定に失敗したため無視します: text=%r", text, exc_info=True)
            return Decision("ignore", "")

        intent = result["intent"]
        reply = result["reply"].strip()
        if intent == "checkin":
            self._history.clear()
            return Decision("checkin", "")
        if intent == "chat" and reply:
            self._history += [user, {"role": "assistant", "content": reply}]
            del self._history[: -2 * self._history_turns]
            return Decision("chat", reply)
        return Decision("ignore", "")
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_dialogue.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add voice_ui/dialogue.py tests/test_voice_ui_dialogue.py
git commit -m "feat: add front-desk dialogue agent with history and idle reset

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: スピーカー（文区切り、合成と再生の分離、`is_busy()`、`BUSY_MESSAGE`）

**Files:**
- Modify: `voice_ui/tts.py`, `voice_ui/step_messages.py`, `tests/test_voice_ui_tts.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `voice_ui.step_messages.BUSY_MESSAGE`、`PRELOAD_TEXTS == [VOICE_START_GUIDANCE, BUSY_MESSAGE]`
  - `voice_ui.tts.split_sentences(text: str) -> list[str]`
  - `voice_ui.tts.VoicevoxSpeaker(base_url, output_sink, speaker_id=29, speed_scale=1.0, synthesize=synthesize_speech, echo_guard_seconds=0.5, clock=time.monotonic)`
    - `.speak(text)`（文に区切って合成キューへ）、`.preload(texts)`、`.start()`、`.stop()`
    - `.is_busy() -> bool`（再生中、または最後の再生終了から `echo_guard_seconds` 未満）
    - テスト用の1ステップ実行: `._synth_once(timeout=0.0) -> bool`、`._play_once(timeout=0.0) -> bool`（処理したら True）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_tts.py` の `# --- VoicevoxSpeaker ---` 以降（`_FakeSink` から末尾まで）を次に置き換える。先頭の import 行 `from voice_ui.step_messages import PRELOAD_TEXTS, VOICE_START_GUIDANCE` は `from voice_ui.step_messages import BUSY_MESSAGE, PRELOAD_TEXTS, VOICE_START_GUIDANCE` に、`from voice_ui.tts import VoicevoxSpeaker, synthesize_speech` は `from voice_ui.tts import VoicevoxSpeaker, split_sentences, synthesize_speech` にする。

```python
class _FakeSink:
    def __init__(self, on_write=None):
        self.writes = []
        self._on_write = on_write

    def write(self, waveform, sample_rate, channels):
        if self._on_write:
            self._on_write()
        self.writes.append((waveform, sample_rate, channels))


class _FakeSynth:
    def __init__(self, fail_on=()):
        self.calls = []
        self._fail_on = set(fail_on)

    def __call__(self, text, base_url, speaker_id, speed_scale):
        self.calls.append((text, speaker_id))
        if text in self._fail_on:
            raise RuntimeError("synthesis failed")
        return f"wave:{text}", 24000, 1


class _FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def _speaker(synth, sink=None, clock=None):
    return VoicevoxSpeaker(
        base_url="http://voicevox.test",
        output_sink=sink or _FakeSink(),
        synthesize=synth,
        echo_guard_seconds=0.5,
        clock=clock or _FakeClock(),
    )


def _drain(speaker):
    while speaker._synth_once() or speaker._play_once():
        pass


@pytest.mark.parametrize(
    "text, expected",
    [
        ("朝食は7時からです。場所は1階です。", ["朝食は7時からです。", "場所は1階です。"]),
        ("ようこそ！何かお手伝いしますか？", ["ようこそ！", "何かお手伝いしますか？"]),
        ("Wi-Fiは無料です!パスワードはカードにあります?", ["Wi-Fiは無料です!", "パスワードはカードにあります?"]),
        ("句点のない文", ["句点のない文"]),
        ("  ", []),
    ],
)
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected


def test_default_speaker_is_29_like_dimos():
    synth = _FakeSynth()
    speaker = _speaker(synth)

    speaker.speak("こんにちは")
    _drain(speaker)

    assert synth.calls == [("こんにちは", 29)]


def test_speak_plays_every_sentence_in_order():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.speak("一文目です。二文目です。三文目")
    _drain(speaker)

    assert [w[0] for w in sink.writes] == ["wave:一文目です。", "wave:二文目です。", "wave:三文目"]


def test_next_sentence_is_synthesized_before_current_one_finishes_playing():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)
    speaker.speak("一文目です。二文目です。")

    speaker._synth_once()
    speaker._synth_once()

    assert [c[0] for c in synth.calls] == ["一文目です。", "二文目です。"]
    assert sink.writes == []


def test_preloaded_text_is_played_without_synthesizing_again():
    synth = _FakeSynth()
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["案内です。"])
    speaker.speak("案内です。")
    _drain(speaker)

    assert synth.calls == [("案内です。", 29)]
    assert sink.writes == [("wave:案内です。", 24000, 1)]


def test_failed_sentence_is_skipped_and_next_one_plays():
    synth = _FakeSynth(fail_on={"失敗する文。"})
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.speak("失敗する文。成功する文。")
    _drain(speaker)

    assert sink.writes == [("wave:成功する文。", 24000, 1)]


def test_preload_failure_is_skipped_and_retried_on_demand():
    synth = _FakeSynth(fail_on={"失敗する文"})
    sink = _FakeSink()
    speaker = _speaker(synth, sink)

    speaker.preload(["失敗する文", "成功する文"])
    speaker.speak("成功する文")
    _drain(speaker)

    assert synth.calls == [("失敗する文", 29), ("成功する文", 29)]
    assert sink.writes == [("wave:成功する文", 24000, 1)]


def test_is_busy_while_playing_and_during_echo_guard():
    clock = _FakeClock()
    busy_during_write = []
    speaker = None

    def on_write():
        busy_during_write.append(speaker.is_busy())
        clock.value += 2.0  # playback takes 2 seconds

    sink = _FakeSink(on_write=on_write)
    speaker = _speaker(_FakeSynth(), sink, clock)

    assert speaker.is_busy() is False
    speaker.speak("こんにちは。")
    speaker._synth_once()
    speaker._play_once()

    assert busy_during_write == [True]
    clock.value += 0.49
    assert speaker.is_busy() is True
    clock.value += 0.02
    assert speaker.is_busy() is False


def test_preload_texts_are_the_fixed_phrases_voice_ui_speaks():
    assert PRELOAD_TEXTS == [VOICE_START_GUIDANCE, BUSY_MESSAGE]
    assert BUSY_MESSAGE == "ただいま他のお客様をご案内しています。少々お待ちください"
```

ファイル先頭の import に `import pytest` を追加する。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_tts.py -q`
Expected: FAIL（`cannot import name 'BUSY_MESSAGE'`）

- [ ] **Step 3: 実装する**

`voice_ui/step_messages.py` を次にする。

```python
VOICE_START_GUIDANCE = "画面にお名前、予約番号、または電話番号を入力してください"
BUSY_MESSAGE = "ただいま他のお客様をご案内しています。少々お待ちください"

# Every fixed phrase voice_ui can speak; synthesized once at startup so the
# kiosk never waits on VOICEVOX for them.
PRELOAD_TEXTS = [VOICE_START_GUIDANCE, BUSY_MESSAGE]
```

`voice_ui/tts.py` の `import` 群に `import queue` と `import re` を追加し、`class VoicevoxSpeaker` を丸ごと次に置き換える（`synthesize_speech` と `_probe_voicevox` はそのまま）。`_probe_voicevox` の直前に `split_sentences` を置く。

```python
_SENTENCE_END = re.compile(r"(?<=[。！？!?])")


def split_sentences(text):
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]
```

```python
class VoicevoxSpeaker:
    """Speaks text sentence by sentence; synthesis runs ahead of playback."""

    def __init__(
        self,
        base_url,
        output_sink,
        speaker_id=_DEFAULT_SPEAKER_ID,
        speed_scale=1.0,
        synthesize=synthesize_speech,
        echo_guard_seconds=0.5,
        clock=time.monotonic,
    ):
        self._base_url = base_url
        self._output_sink = output_sink
        self._speaker_id = speaker_id
        self._speed_scale = speed_scale
        self._synthesize = synthesize
        self._echo_guard_seconds = echo_guard_seconds
        self._clock = clock
        self._cache = {}
        self._texts = queue.Queue()
        self._audio = queue.Queue()
        self._lock = threading.Lock()
        self._playing = False
        self._last_played_at = None
        self._running = True
        self._threads = [
            threading.Thread(target=self._loop, args=(self._synth_once,), daemon=True),
            threading.Thread(target=self._loop, args=(self._play_once,), daemon=True),
        ]

    def start(self):
        _probe_voicevox(self._base_url)
        for thread in self._threads:
            thread.start()

    def preload(self, texts):
        """Synthesize fixed phrases up front; failures fall back to on-demand."""
        for text in texts:
            try:
                self._cache[text] = self._synthesize(
                    text, self._base_url, self._speaker_id, self._speed_scale
                )
            except Exception:  # noqa: BLE001 - a missing phrase is synthesized later
                logger.warning("音声の事前合成に失敗しました。text=%r", text, exc_info=True)
        logger.info("音声を事前合成しました: %d/%d件", len(self._cache), len(texts))

    def speak(self, text):
        for sentence in split_sentences(text):
            self._texts.put(sentence)

    def is_busy(self):
        """True while playing and for a short tail, so the mic ignores our own voice."""
        with self._lock:
            if self._playing:
                return True
            if self._last_played_at is None:
                return False
            return self._clock() - self._last_played_at < self._echo_guard_seconds

    def stop(self):
        self._running = False
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2.0)

    def _loop(self, step):
        while self._running:
            step(timeout=0.05)

    def _synth_once(self, timeout=0.0):
        try:
            text = self._texts.get(timeout=timeout) if timeout else self._texts.get_nowait()
        except queue.Empty:
            return False
        try:
            audio = self._cache.get(text) or self._synthesize(
                text, self._base_url, self._speaker_id, self._speed_scale
            )
        except Exception:  # noqa: BLE001 - keep speaking the remaining sentences
            logger.warning("音声合成に失敗しました。text=%r", text, exc_info=True)
            return True
        self._audio.put(audio)
        return True

    def _play_once(self, timeout=0.0):
        try:
            audio = self._audio.get(timeout=timeout) if timeout else self._audio.get_nowait()
        except queue.Empty:
            return False
        with self._lock:
            self._playing = True
        try:
            self._output_sink.write(*audio)
        except Exception:  # noqa: BLE001 - keep the playback loop alive
            logger.warning("音声の再生に失敗しました。", exc_info=True)
        finally:
            with self._lock:
                self._playing = False
                self._last_played_at = self._clock()
        return True
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_tts.py tests/test_voice_ui_main.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add voice_ui/tts.py voice_ui/step_messages.py tests/test_voice_ui_tts.py
git commit -m "feat: speak sentence by sentence with look-ahead synthesis and echo guard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: アプリの会話ログ（`/api/voice/turns`）

**Files:**
- Create: `app/voice_turns.py`, `app/routes/voice_turns.py`, `tests/test_routes_voice_turns.py`
- Modify: `app/__init__.py`, `tests/test_app_factory.py`

**Interfaces:**
- Consumes: `EVENT_BROADCASTER.publish(event)`（既存）
- Produces:
  - `app.voice_turns.VOICE_TURN_OUTCOMES`（Global Constraints の7種）
  - `app.voice_turns.VoiceTurnLog(max_turns=20, now=default_now)`、`.add(turn: dict) -> dict`（`at` を付けた記録を返す）、`.recent() -> list[dict]`（新しい順）
  - `POST /api/voice/turns` → 202（SSE に `{"type": "voice_turn", **record}`）/ 422 `{"message": ...}`
  - `GET /api/voice/turns` → 200 `{"turns": [...]}`（新しい順）
  - `app.config["VOICE_TURN_LOG"]`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_voice_turns.py`:

```python
import pytest
from flask import Flask

from app.routes.voice_turns import voice_turns_bp
from app.voice_turns import VoiceTurnLog


class FakeBroadcaster:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


def make_client(max_turns=20):
    app = Flask(__name__)
    app.config["EVENT_BROADCASTER"] = FakeBroadcaster()
    app.config["VOICE_TURN_LOG"] = VoiceTurnLog(
        max_turns=max_turns, now=lambda: "2026-09-29T00:00:00Z"
    )
    app.register_blueprint(voice_turns_bp)
    return app.test_client(), app


def turn(**overrides):
    body = {
        "text": "朝ごはんは何時ですか",
        "no_speech_prob": 0.12,
        "avg_logprob": -0.31,
        "outcome": "chat",
        "reply": "6時半からです。",
        "stt_ms": 840,
        "llm_ms": 1100,
    }
    body.update(overrides)
    return body


def test_post_turn_stores_and_publishes_typed_event():
    client, app = make_client()

    resp = client.post("/api/voice/turns", json=turn())

    assert resp.status_code == 202
    expected = {**turn(), "at": "2026-09-29T00:00:00Z"}
    assert app.config["EVENT_BROADCASTER"].events == [{"type": "voice_turn", **expected}]
    assert client.get("/api/voice/turns").get_json() == {"turns": [expected]}


def test_optional_fields_default_to_null_and_empty_reply():
    client, _app = make_client()

    client.post(
        "/api/voice/turns",
        json={"text": "ノイズ", "outcome": "rejected_low_confidence"},
    )

    stored = client.get("/api/voice/turns").get_json()["turns"][0]
    assert stored["reply"] == ""
    assert stored["llm_ms"] is None
    assert stored["no_speech_prob"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        turn(outcome="unknown"),
        turn(text=3),
        turn(reply=5),
        turn(stt_ms="fast"),
        turn(no_speech_prob="high"),
    ],
)
def test_post_turn_rejects_invalid_body(body):
    client, app = make_client()

    resp = client.post("/api/voice/turns", json=body)

    assert resp.status_code == 422
    assert app.config["EVENT_BROADCASTER"].events == []


def test_get_returns_newest_first_and_keeps_limit():
    client, _app = make_client(max_turns=3)

    for i in range(5):
        client.post("/api/voice/turns", json=turn(text=f"発話{i}"))

    texts = [t["text"] for t in client.get("/api/voice/turns").get_json()["turns"]]
    assert texts == ["発話4", "発話3", "発話2"]
```

`tests/test_app_factory.py` の末尾に追加する:

```python
def test_voice_turns_are_wired_into_app_factory():
    app = create_app(r2_client=FakeR2Client(), pf_client=FakePFClient())
    client = app.test_client()

    assert client.post(
        "/api/voice/turns", json={"text": "こんにちは", "outcome": "chat", "reply": "こんにちは。"}
    ).status_code == 202
    assert client.get("/api/voice/turns").get_json()["turns"][0]["text"] == "こんにちは"
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_voice_turns.py tests/test_app_factory.py -q`
Expected: FAIL（`No module named 'app.routes.voice_turns'`）

- [ ] **Step 3: 実装する**

`app/voice_turns.py`:

```python
"""In-memory log of recent voice turns for the debug page."""

import threading
from collections import deque

from .state_machine import default_now

VOICE_TURN_OUTCOMES = (
    "rejected_low_confidence",
    "self_echo",
    "keyword_start",
    "checkin",
    "chat",
    "ignore",
    "no_keyword",
)


class VoiceTurnLog:
    def __init__(self, max_turns=20, now=default_now):
        self._turns = deque(maxlen=max_turns)
        self._now = now
        self._lock = threading.Lock()

    def add(self, turn):
        record = {**turn, "at": self._now()}
        with self._lock:
            self._turns.append(record)
        return record

    def recent(self):
        with self._lock:
            return list(reversed(self._turns))
```

`app/routes/voice_turns.py`:

```python
from flask import Blueprint, current_app, jsonify, request

from ..voice_turns import VOICE_TURN_OUTCOMES

voice_turns_bp = Blueprint("voice_turns", __name__)

_NUMBER_FIELDS = ("no_speech_prob", "avg_logprob", "stt_ms", "llm_ms")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@voice_turns_bp.route("/api/voice/turns", methods=["POST"])
def add_turn():
    body = request.get_json(silent=True) or {}
    text = body.get("text")
    outcome = body.get("outcome")
    reply = body.get("reply", "")
    if not isinstance(text, str) or outcome not in VOICE_TURN_OUTCOMES:
        return jsonify({"message": "text and a known outcome are required"}), 422
    if reply is None:
        reply = ""
    if not isinstance(reply, str):
        return jsonify({"message": "reply must be a string"}), 422
    turn = {"text": text, "outcome": outcome, "reply": reply}
    for field in _NUMBER_FIELDS:
        value = body.get(field)
        if value is not None and not _is_number(value):
            return jsonify({"message": f"{field} must be a number"}), 422
        turn[field] = value

    record = current_app.config["VOICE_TURN_LOG"].add(turn)
    current_app.config["EVENT_BROADCASTER"].publish({"type": "voice_turn", **record})
    return jsonify({"message": "turn recorded"}), 202


@voice_turns_bp.route("/api/voice/turns", methods=["GET"])
def list_turns():
    return jsonify({"turns": current_app.config["VOICE_TURN_LOG"].recent()}), 200
```

`app/__init__.py`:
- `from .routes.voice_turns import voice_turns_bp` と `from .voice_turns import VoiceTurnLog` を import に追加する。
- `app.config["RESERVATION_STORE"] = reservation_store` の直後に `app.config["VOICE_TURN_LOG"] = VoiceTurnLog()` を追加する。
- `app.register_blueprint(external_start_bp)` の直後に `app.register_blueprint(voice_turns_bp)` を追加する。

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_voice_turns.py tests/test_app_factory.py -q`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add app/voice_turns.py app/routes/voice_turns.py app/__init__.py \
  tests/test_routes_voice_turns.py tests/test_app_factory.py
git commit -m "feat: keep recent voice turns and stream them to the debug page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: パイプラインの振り分けと配線

**Files:**
- Create: `voice_ui/turn_reporter.py`, `tests/test_voice_ui_turn_reporter.py`
- Modify: `voice_ui/pipeline.py`, `voice_ui/main.py`, `tests/test_voice_ui_pipeline.py`（全面書き換え）

**Interfaces:**
- Consumes: `DialogueAgent.respond(text) -> Decision`（Task 2）、`VoicevoxSpeaker.speak/is_busy`・`BUSY_MESSAGE`（Task 3）、`POST /api/voice/turns`（Task 4）、既存の `VoiceStartClient.start() -> str`、`contains_start_keyword`、`is_confident`
- Produces:
  - `voice_ui.turn_reporter.TurnReporter(base_url: str, timeout: float = 2.0)`、`.report(turn: dict) -> bool`（例外を出さない）
  - `voice_ui.pipeline.run_turn_once(mic_source, vad_segmenter, transcriber, start_client, speaker, turn_reporter, start_keywords, dialogue_agent, no_speech_prob_max, avg_logprob_min, read_timeout=1.0, clock=time.perf_counter) -> str`（`no_utterance` または Global Constraints の outcome のいずれか）。`dialogue_agent` が `None` なら雑談なし。
  - `voice_ui.main.run_checkin_loop(mic_source, vad_segmenter, transcriber, start_client, speaker, turn_reporter, dialogue_agent, no_utterance_exit_threshold=...)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_voice_ui_turn_reporter.py`:

```python
import json

import requests
import responses

from voice_ui.turn_reporter import TurnReporter

URL = "http://flask.test/api/voice/turns"


@responses.activate
def test_report_posts_turn():
    responses.add(responses.POST, URL, status=202, json={})

    assert TurnReporter("http://flask.test").report({"text": "こんにちは", "outcome": "chat"}) is True
    assert json.loads(responses.calls[0].request.body) == {"text": "こんにちは", "outcome": "chat"}


@responses.activate
def test_report_returns_false_on_rejection():
    responses.add(responses.POST, URL, status=422, json={})

    assert TurnReporter("http://flask.test").report({"text": "", "outcome": "chat"}) is False


@responses.activate
def test_report_swallows_connection_errors():
    responses.add(responses.POST, URL, body=requests.exceptions.ConnectionError())

    assert TurnReporter("http://flask.test").report({"text": "", "outcome": "chat"}) is False
```

`tests/test_voice_ui_pipeline.py` を次の内容で全面的に置き換える。

```python
import logging

from voice_ui.dialogue import Decision
from voice_ui.pipeline import run_turn_once
from voice_ui.step_messages import BUSY_MESSAGE

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


class _FakeSpeaker:
    def __init__(self, busy=False):
        self.spoken = []
        self._busy = busy

    def speak(self, text):
        self.spoken.append(text)

    def is_busy(self):
        return self._busy


class _FakeReporter:
    def __init__(self):
        self.turns = []

    def report(self, turn):
        self.turns.append(turn)
        return True


class _FakeAgent:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def respond(self, text):
        self.calls.append(text)
        return self.decision


class _Env:
    def __init__(self, transcription, decision=Decision("ignore", ""), start_result="accepted",
                 busy=False, dialogue=True, chunks=(object(),), utterance_after=1):
        self.mic = _FakeMicSource(list(chunks))
        self.vad = _FakeVadSegmenter(utterance_after)
        self.transcriber = _FakeTranscriber(transcription)
        self.start_client = _FakeStartClient(start_result)
        self.speaker = _FakeSpeaker(busy)
        self.reporter = _FakeReporter()
        self.agent = _FakeAgent(decision) if dialogue else None

    def run(self):
        return run_turn_once(
            self.mic, self.vad, self.transcriber, self.start_client, self.speaker,
            self.reporter, KEYWORDS, self.agent,
            no_speech_prob_max=0.6, avg_logprob_min=-1.0,
        )


def test_keyword_starts_without_asking_llm():
    env = _Env(("チェックインお願いします", 0.1, -0.2), decision=Decision("chat", "x"))

    assert env.run() == "keyword_start"
    assert env.start_client.calls == 1
    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "keyword_start"
    assert env.reporter.turns[0]["llm_ms"] is None


def test_llm_checkin_requests_start():
    env = _Env(("部屋に入りたいんですけど", 0.1, -0.2), decision=Decision("checkin", ""))

    assert env.run() == "checkin"
    assert env.start_client.calls == 1
    assert env.speaker.spoken == []


def test_chat_reply_is_spoken_and_reported():
    env = _Env(("朝ごはんは何時ですか", 0.1, -0.2), decision=Decision("chat", "6時半からです。"))

    assert env.run() == "chat"
    assert env.speaker.spoken == ["6時半からです。"]
    assert env.start_client.calls == 0
    turn = env.reporter.turns[0]
    assert turn["text"] == "朝ごはんは何時ですか"
    assert turn["reply"] == "6時半からです。"
    assert turn["no_speech_prob"] == 0.1
    assert turn["avg_logprob"] == -0.2
    assert isinstance(turn["stt_ms"], int)
    assert isinstance(turn["llm_ms"], int)


def test_ignore_says_nothing():
    env = _Env(("それでさあ", 0.1, -0.2), decision=Decision("ignore", ""))

    assert env.run() == "ignore"
    assert env.speaker.spoken == []
    assert env.start_client.calls == 0


def test_busy_message_when_start_is_not_available():
    keyword = _Env(("チェックイン", 0.1, -0.2), start_result="not_available")
    llm = _Env(("部屋に入りたい", 0.1, -0.2), decision=Decision("checkin", ""), start_result="not_available")

    keyword.run()
    llm.run()

    assert keyword.speaker.spoken == [BUSY_MESSAGE]
    assert llm.speaker.spoken == [BUSY_MESSAGE]


def test_rate_limited_start_says_nothing():
    env = _Env(("チェックイン", 0.1, -0.2), start_result="rate_limited")

    env.run()

    assert env.speaker.spoken == []


def test_utterance_while_speaker_busy_is_discarded_as_self_echo():
    env = _Env(("チェックインお願いします", 0.1, -0.2), decision=Decision("chat", "x"), busy=True)

    assert env.run() == "self_echo"
    assert env.start_client.calls == 0
    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "self_echo"


def test_low_confidence_is_rejected_and_reported(caplog):
    env = _Env(("ノイズ", 0.9, -5.0), decision=Decision("chat", "x"))

    with caplog.at_level(logging.INFO, logger="voice_ui.pipeline"):
        assert env.run() == "rejected_low_confidence"

    assert env.agent.calls == []
    assert env.reporter.turns[0]["outcome"] == "rejected_low_confidence"
    assert "ノイズ" in caplog.text and "0.9" in caplog.text and "-5.0" in caplog.text


def test_without_dialogue_non_keyword_is_ignored_as_no_keyword():
    env = _Env(("こんにちは", 0.1, -0.2), dialogue=False)

    assert env.run() == "no_keyword"
    assert env.speaker.spoken == []
    assert env.reporter.turns[0]["outcome"] == "no_keyword"


def test_no_chunk_returns_no_utterance_without_report():
    env = _Env(("unused", 0.0, 0.0), chunks=())

    assert env.run() == "no_utterance"
    assert env.reporter.turns == []


def test_multiple_chunks_are_fed_until_utterance_completes():
    env = _Env(("チェックイン", 0.1, -0.2), chunks=(object(), object(), object()), utterance_after=3)

    assert env.run() == "keyword_start"
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_voice_ui_turn_reporter.py tests/test_voice_ui_pipeline.py -q`
Expected: FAIL（`No module named 'voice_ui.turn_reporter'`、`cannot import name 'run_turn_once'`）

- [ ] **Step 3: 実装する**

`voice_ui/turn_reporter.py`:

```python
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
```

`voice_ui/pipeline.py` を次の内容に置き換える。

```python
import logging
import time

from .start_keyword import contains_start_keyword
from .step_messages import BUSY_MESSAGE
from .stt import is_confident

logger = logging.getLogger(__name__)


def _elapsed_ms(clock, started):
    return round((clock() - started) * 1000)


def _request_start(start_client, speaker, text):
    result = start_client.start()
    logger.info("チェックイン開始を依頼しました: result=%s text=%r", result, text)
    if result == "not_available":
        speaker.speak(BUSY_MESSAGE)


def run_turn_once(
    mic_source,
    vad_segmenter,
    transcriber,
    start_client,
    speaker,
    turn_reporter,
    start_keywords,
    dialogue_agent,
    no_speech_prob_max,
    avg_logprob_min,
    read_timeout=1.0,
    clock=time.perf_counter,
):
    utterance = None
    while utterance is None:
        chunk = mic_source.read_chunk(timeout=read_timeout)
        if chunk is None:
            return "no_utterance"
        utterance = vad_segmenter.feed(chunk)

    # Decide before transcribing: the speaker state is what it was when the
    # utterance ended, not after Whisper's delay.
    self_echo = speaker.is_busy()

    started = clock()
    text, no_speech_prob, avg_logprob = transcriber.transcribe(utterance)
    turn = {
        "text": text,
        "no_speech_prob": no_speech_prob,
        "avg_logprob": avg_logprob,
        "reply": "",
        "stt_ms": _elapsed_ms(clock, started),
        "llm_ms": None,
    }

    def finish(outcome):
        turn["outcome"] = outcome
        turn_reporter.report(turn)
        return outcome

    if self_echo:
        logger.info("読み上げと重なった発話を無視しました: text=%r", text)
        return finish("self_echo")

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
        return finish("rejected_low_confidence")

    if contains_start_keyword(text, start_keywords):
        _request_start(start_client, speaker, text)
        return finish("keyword_start")

    if dialogue_agent is None:
        logger.info("開始キーワードを含まない発話を無視しました: text=%r", text)
        return finish("no_keyword")

    started = clock()
    decision = dialogue_agent.respond(text)
    turn["llm_ms"] = _elapsed_ms(clock, started)
    logger.info("対話の判定: intent=%s text=%r reply=%r", decision.intent, text, decision.reply)
    if decision.intent == "checkin":
        _request_start(start_client, speaker, text)
    elif decision.intent == "chat":
        turn["reply"] = decision.reply
        speaker.speak(decision.reply)
    return finish(decision.intent)
```

`voice_ui/main.py`:
- import を変更・追加する（アルファベット順を保つ）:
  - `from pathlib import Path`（標準ライブラリの import に追加）
  - `from .dialogue import DialogueAgent`
  - `from .llm_client import DialogueLLMClient`
  - `from .pipeline import run_start_once` → `from .pipeline import run_turn_once`
  - `from .turn_reporter import TurnReporter`
- `run_checkin_loop` を次に置き換える。

```python
def run_checkin_loop(
    mic_source,
    vad_segmenter,
    transcriber,
    start_client,
    speaker,
    turn_reporter,
    dialogue_agent,
    no_utterance_exit_threshold=NO_UTTERANCE_EXIT_THRESHOLD,
):
    def _outcomes():
        while True:
            yield run_turn_once(
                mic_source,
                vad_segmenter,
                transcriber,
                start_client,
                speaker,
                turn_reporter,
                config.VOICE_START_KEYWORDS,
                dialogue_agent,
                no_speech_prob_max=config.STT_NO_SPEECH_PROB_MAX,
                avg_logprob_min=config.STT_AVG_LOGPROB_MIN,
            )

    _run_checkin_loop_body(_outcomes(), no_utterance_exit_threshold)
```

- `main()` に対話エージェントの生成を加える（`start_client = ...` の直後）:

```python
    turn_reporter = TurnReporter(base_url=config.FLASK_BASE_URL)
    dialogue_agent = None
    if config.DIALOGUE_ENABLED:
        hotel_info = Path(config.HOTEL_INFO_FILE).read_text(encoding="utf-8")
        dialogue_agent = DialogueAgent(
            DialogueLLMClient(
                config.DIALOGUE_LLM_URL,
                config.DIALOGUE_LLM_MODEL,
                api_key=config.DIALOGUE_LLM_API_KEY,
                timeout=config.DIALOGUE_LLM_TIMEOUT_SECONDS,
            ),
            hotel_info,
            history_turns=config.DIALOGUE_HISTORY_TURNS,
            idle_reset_seconds=config.DIALOGUE_IDLE_RESET_SECONDS,
        )
```

- `VoicevoxSpeaker(base_url=config.VOICEVOX_URL, output_sink=speaker_sink)` を `VoicevoxSpeaker(base_url=config.VOICEVOX_URL, output_sink=speaker_sink, echo_guard_seconds=config.ECHO_GUARD_SECONDS)` にする。
- 最後の `run_checkin_loop(mic_source, vad_segmenter, transcriber, start_client)` を `run_checkin_loop(mic_source, vad_segmenter, transcriber, start_client, speaker, turn_reporter, dialogue_agent)` にする。

確認: `grep -n "run_start_once" -r voice_ui tests` が何も出さないこと。

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/ -q -k voice_ui && .venv/bin/python -c "import voice_ui.main"`
Expected: PASS、import エラーなし

- [ ] **Step 5: コミットする**

```bash
git add voice_ui/turn_reporter.py voice_ui/pipeline.py voice_ui/main.py \
  tests/test_voice_ui_turn_reporter.py tests/test_voice_ui_pipeline.py
git commit -m "feat: route utterances to keyword start, LLM checkin, chat or ignore

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: デバッグ画面の「音声対話ログ」欄

**Files:**
- Modify: `app/templates/debug.html`, `app/static/debug.js`, `app/static/debug.css`, `tests/test_routes_debug.py`

**Interfaces:**
- Consumes: `GET /api/voice/turns`、SSE `{"type": "voice_turn", ...}`（Task 4）
- Produces: 要素ID `voice-turn-panel`, `voice-turn-rows`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_debug.py`:
- 既存の `test_debug_js_ignores_typed_events` を次に置き換える（typed event はまず `voice_turn` を処理し、その後 render せずに戻る形に変わるため）。

```python
def test_debug_js_handles_voice_turns_and_skips_other_typed_events():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert re.search(
        r"if \(payload\.type\) \{\s*if \(payload\.type === \"voice_turn\"\) \{\s*addVoiceTurn\(payload\);\s*\}\s*return;\s*\}\s*render\(payload\);",
        source,
    )
```

- 末尾に追加する:

```python
def test_debug_page_has_voice_turn_panel():
    resp = make_client().get("/debug")

    assert b'id="voice-turn-panel"' in resp.data
    assert b'id="voice-turn-rows"' in resp.data
    for label in ["時刻", "書き起こし", "判定", "返事", "STT(ms)", "LLM(ms)"]:
        assert label in resp.data.decode()


def test_debug_js_loads_recent_voice_turns_and_escapes_text():
    source = (Path(__file__).parents[1] / "app" / "static" / "debug.js").read_text()

    assert 'fetch("/api/voice/turns")' in source
    assert "const MAX_VOICE_TURNS = 20;" in source
    # Transcripts come from a microphone; never inject them as HTML.
    assert "innerHTML" not in source
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_debug.py -q`
Expected: FAIL

- [ ] **Step 3: 実装する**

`app/templates/debug.html` の `<h2 class="section-label">シーケンス図（実行中ステップをハイライト）</h2>` の直前に挿入する。

```html
    <h2 class="section-label">音声対話ログ（新しい順・最大20件）</h2>
    <div id="voice-turn-panel">
      <table>
        <thead>
          <tr>
            <th>時刻</th><th>書き起こし</th><th>判定</th><th>返事</th>
            <th>no_speech</th><th>logprob</th><th>STT(ms)</th><th>LLM(ms)</th>
          </tr>
        </thead>
        <tbody id="voice-turn-rows"></tbody>
      </table>
    </div>

```

`app/static/debug.js`:
- `const entryStages = ...` の行の直後に追加する。

```js
const MAX_VOICE_TURNS = 20;
const voiceTurnRows = document.getElementById("voice-turn-rows");

function formatNumber(value, digits) {
  return typeof value === "number" ? value.toFixed(digits) : "-";
}

function voiceTurnRow(turn) {
  const row = document.createElement("tr");
  row.className = "voice-turn outcome-" + turn.outcome;
  [
    toSecondsTime(turn.at),
    turn.text,
    turn.outcome,
    turn.reply || "",
    formatNumber(turn.no_speech_prob, 2),
    formatNumber(turn.avg_logprob, 2),
    turn.stt_ms ?? "-",
    turn.llm_ms ?? "-",
  ].forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = String(value);
    row.append(cell);
  });
  return row;
}

function addVoiceTurn(turn) {
  voiceTurnRows.prepend(voiceTurnRow(turn));
  while (voiceTurnRows.children.length > MAX_VOICE_TURNS) {
    voiceTurnRows.lastElementChild.remove();
  }
}

fetch("/api/voice/turns")
  .then((resp) => resp.json())
  .then((data) => {
    voiceTurnRows.replaceChildren(...(data.turns || []).map(voiceTurnRow));
  })
  .catch(() => {});
```

- `eventSource.onmessage` の typed event 処理を次に置き換える。

```js
  if (payload.type) {
    if (payload.type === "voice_turn") {
      addVoiceTurn(payload);
    }
    return;
  }
  render(payload);
```

（既存の `// Typed events (e.g. ui_action) are not state snapshots.` コメントは `if (payload.type) {` の直前に残す。）

`app/static/debug.css` の末尾に追加する。

```css
#voice-turn-panel {
  border: 1px solid #ccc;
  border-radius: 4px;
  margin-bottom: 1rem;
  overflow-x: auto;
}

#voice-turn-panel table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

#voice-turn-panel th,
#voice-turn-panel td {
  border-bottom: 1px solid #eee;
  padding: 0.25rem 0.5rem;
  text-align: left;
  vertical-align: top;
}

.voice-turn.outcome-chat td:nth-child(3),
.voice-turn.outcome-checkin td:nth-child(3),
.voice-turn.outcome-keyword_start td:nth-child(3) {
  color: #1a73e8;
  font-weight: bold;
}

.voice-turn.outcome-ignore,
.voice-turn.outcome-self_echo,
.voice-turn.outcome-rejected_low_confidence,
.voice-turn.outcome-no_keyword {
  color: #999;
}
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_routes_debug.py -q && node --check app/static/debug.js`
Expected: PASS、構文エラーなし

- [ ] **Step 5: コミットする**

```bash
git add app/templates/debug.html app/static/debug.js app/static/debug.css tests/test_routes_debug.py
git commit -m "feat: show voice dialogue log on debug page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 判定精度の評価スクリプト

**Files:**
- Create: `tests/fixtures/dialogue/cases.json`, `tools/dialogue_eval.py`, `tests/test_dialogue_eval.py`

**Interfaces:**
- Consumes: `DialogueLLMClient`（Task 1）、`DialogueAgent`（Task 2）、`voice_ui.config`
- Produces:
  - `tools.dialogue_eval.FIXTURE_FILE`、`load_cases(path) -> list[dict]`（各 `{"text": str, "intent": str}`）
  - `tools.dialogue_eval.main(argv=None) -> int`（`--cases`、`--llm-url`、`--model`、`--hotel-info`、`--min-accuracy`）

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_dialogue_eval.py`:

```python
import json

import responses

from tools.dialogue_eval import FIXTURE_FILE, load_cases, main

LLM = "http://llm.test/v1"


def _write_cases(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {"text": "チェックインしたい", "intent": "checkin"},
                {"text": "朝食は何時？", "intent": "chat"},
                {"text": "それでさあ", "intent": "ignore"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _reply_with(*intents):
    answers = iter(intents)

    def callback(_request):
        intent = next(answers)
        content = json.dumps({"intent": intent, "reply": "はい。" if intent == "chat" else ""})
        return 200, {}, json.dumps({"choices": [{"message": {"content": content}}]})

    return callback


def test_repository_cases_cover_all_intents():
    intents = {case["intent"] for case in load_cases(FIXTURE_FILE)}

    assert intents == {"checkin", "chat", "ignore"}
    assert len(load_cases(FIXTURE_FILE)) >= 12


@responses.activate
def test_all_correct_exits_zero(tmp_path, capsys):
    responses.add_callback(
        responses.POST, f"{LLM}/chat/completions", callback=_reply_with("checkin", "chat", "ignore")
    )

    code = main(["--cases", str(_write_cases(tmp_path)), "--llm-url", LLM])

    assert code == 0
    assert "accuracy 3/3 (100.0%)" in capsys.readouterr().out


@responses.activate
def test_mismatch_is_reported_and_fails_min_accuracy(tmp_path, capsys):
    responses.add_callback(
        responses.POST, f"{LLM}/chat/completions", callback=_reply_with("checkin", "ignore", "chat")
    )

    code = main(
        ["--cases", str(_write_cases(tmp_path)), "--llm-url", LLM, "--min-accuracy", "0.9"]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "NG" in out and "朝食は何時？" in out
    assert "accuracy 1/3 (33.3%)" in out
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest tests/test_dialogue_eval.py -q`
Expected: FAIL（`No module named 'tools.dialogue_eval'`）

- [ ] **Step 3: 実装する**

`tests/fixtures/dialogue/cases.json`:

```json
[
  {"text": "チェックインお願いします", "intent": "checkin"},
  {"text": "予約してるんですけど", "intent": "checkin"},
  {"text": "今日泊まる田中です", "intent": "checkin"},
  {"text": "部屋に入りたいんですが", "intent": "checkin"},
  {"text": "朝ごはんは何時からですか", "intent": "chat"},
  {"text": "Wi-Fiのパスワードってどこにありますか", "intent": "chat"},
  {"text": "チェックアウトは何時までですか", "intent": "chat"},
  {"text": "近くにコンビニありますか", "intent": "chat"},
  {"text": "大浴場は何時まで入れますか", "intent": "chat"},
  {"text": "こんにちは", "intent": "chat"},
  {"text": "今日は暑いですね", "intent": "chat"},
  {"text": "ロボットさん、お名前は", "intent": "chat"},
  {"text": "それでさあ、昨日の会議どうだった", "intent": "ignore"},
  {"text": "ちょっと待ってて、トイレ行ってくる", "intent": "ignore"},
  {"text": "えーと", "intent": "ignore"},
  {"text": "明日の新幹線何時だっけ", "intent": "ignore"}
]
```

`tools/dialogue_eval.py`:

```python
"""Evaluate the front-desk dialogue intent against labeled utterances.

Each case is judged with a fresh agent (no history), so cases are independent.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from voice_ui import config
from voice_ui.dialogue import DialogueAgent
from voice_ui.llm_client import DialogueLLMClient

FIXTURE_FILE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "dialogue" / "cases.json"


def load_cases(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=FIXTURE_FILE)
    parser.add_argument("--llm-url", default=config.DIALOGUE_LLM_URL)
    parser.add_argument("--model", default=config.DIALOGUE_LLM_MODEL)
    parser.add_argument("--hotel-info", type=Path, default=Path(config.HOTEL_INFO_FILE))
    parser.add_argument("--min-accuracy", type=float, default=0.0)
    args = parser.parse_args(argv)

    hotel_info = args.hotel_info.read_text(encoding="utf-8")
    llm = DialogueLLMClient(args.llm_url, args.model, timeout=config.DIALOGUE_LLM_TIMEOUT_SECONDS)
    cases = load_cases(args.cases)
    correct = 0
    confusion = Counter()
    latencies = []
    for case in cases:
        agent = DialogueAgent(llm, hotel_info)
        started = time.monotonic()
        decision = agent.respond(case["text"])
        latencies.append((time.monotonic() - started) * 1000)
        ok = decision.intent == case["intent"]
        correct += ok
        confusion[(case["intent"], decision.intent)] += 1
        reply = f"\treply={decision.reply}" if decision.reply else ""
        print(f"{'OK' if ok else 'NG'}\t{case['text']}\texpected={case['intent']}\tactual={decision.intent}{reply}")

    accuracy = correct / len(cases)
    mistakes = ", ".join(f"{e}->{a}:{n}" for (e, a), n in sorted(confusion.items()) if e != a)
    print(
        f"accuracy {correct}/{len(cases)} ({accuracy:.1%})\t"
        f"mistakes={mistakes or '-'}\tavg_latency={sum(latencies) / len(latencies):.0f}ms"
    )
    return 1 if accuracy < args.min_accuracy else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest tests/test_dialogue_eval.py -q`
Expected: PASS

- [ ] **Step 5: 実際の pod で評価する（手動）**

Run: `.venv/bin/python -m tools.dialogue_eval`
Expected: 16件の OK/NG と正答率が表示される。結果（正答率、間違い、平均レイテンシ）を ledger に記録する。正答率が低くてもこのタスクは完了とし、プロンプトの調整は利用者と相談する。

- [ ] **Step 6: コミットする**

```bash
git add tests/fixtures/dialogue/cases.json tools/dialogue_eval.py tests/test_dialogue_eval.py
git commit -m "feat: add dialogue intent evaluation tool and labeled cases

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: ドキュメントと全体確認

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1〜7 のすべて
- Produces: なし

- [ ] **Step 1: README を更新する**

`README.md` の「音声IF (voice_ui) の起動 (GPU環境のみ)」節の、`docs/superpowers/specs/2026-09-13-voice-ui-design.md`を参照。` の行の直後に追加する。

```markdown

### 音声対話（フロント雑談）

「チェックイン」を含む発話はすぐにキオスクを検索画面にする。それ以外の
発話は LLM（既定は Qwen3.6 pod、`DIALOGUE_LLM_URL`）が判定し、
チェックインの意図なら同じく検索画面へ、フロントへの質問・雑談なら
返事を読み上げ、宛てでない会話には黙る。ホテルの事実は
`data/hotel_info.md`（デモ用の架空ホテル）に基づいて答える。
`DIALOGUE_ENABLED=0` でキーワードだけの動作に戻る。会話は `/debug` の
「音声対話ログ」で確認できる。判定精度は `python -m tools.dialogue_eval`
で評価できる。

雑談の返事はその場で合成するため、VOICEVOX（CPU版）は性能コアに固定して
起動することを推奨する（GB10 の例）:

```
docker run -d --name voicevox -p 127.0.0.1:50021:50021 --cpuset-cpus=5-9,15-19 \
  voicevox/voicevox_engine:cpu-ubuntu22.04-latest \
  gosu user /opt/voicevox_engine/run --host 0.0.0.0 --cpu_num_threads 10
```

固定しないと1文の合成が2〜9秒ぶれることを計測で確認している。
```

- [ ] **Step 2: 全テストを実行する**

Run: `.venv/bin/python -m pytest -q`
Expected: すべて PASS

- [ ] **Step 3: 実機で確認する**

VOICEVOX、R2/PF モック、アプリ、voice_ui を起動し、利用者にマイクで「朝ごはんは何時ですか」「こんにちは」「予約してるんですけど」と、ロボット宛てでない会話を話してもらう。`/debug` の「音声対話ログ」で判定・返事・処理時間を確認し、ledger に記録する。確認後、起動したプロセスを止める。

- [ ] **Step 4: コミットする**

```bash
git add README.md
git commit -m "docs: describe voice dialogue and VOICEVOX core pinning

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
