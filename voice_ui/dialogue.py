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
        self._last_chat_at = None

    def reset(self):
        self._history.clear()
        self._last_chat_at = None

    def respond(self, text):
        now = self._clock()
        # A new visitor should not inherit the previous conversation. Measured
        # from the last chat so background chatter cannot keep it alive.
        if self._last_chat_at is not None and now - self._last_chat_at >= self._idle_reset_seconds:
            self.reset()

        user = {"role": "user", "content": text}
        try:
            result = self._llm.decide([self._system, *self._history, user])
        except DialogueLLMError:
            logger.warning("対話LLMの判定に失敗したため無視します: text=%r", text, exc_info=True)
            return Decision("ignore", "")

        intent = result["intent"]
        reply = result["reply"].strip()
        if intent == "checkin":
            self.reset()
            return Decision("checkin", "")
        if intent == "chat" and reply:
            self._last_chat_at = now
            self._history += [user, {"role": "assistant", "content": reply}]
            del self._history[: -2 * self._history_turns]
            return Decision("chat", reply)
        return Decision("ignore", "")
