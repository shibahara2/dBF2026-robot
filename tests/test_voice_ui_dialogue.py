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


def test_reset_forgets_the_conversation():
    llm = FakeLLM(chat("こんにちは。"), chat("はい。"))
    agent = _agent(llm)

    agent.respond("こんにちは")
    agent.reset()
    agent.respond("朝食は？")

    assert llm.calls[1][1:] == [{"role": "user", "content": "朝食は？"}]


def test_background_chatter_does_not_keep_old_history_alive():
    clock = FakeClock()
    llm = FakeLLM(chat("こんにちは。"), {"intent": "ignore", "reply": ""}, chat("はい。"))
    agent = _agent(llm, clock=clock)

    agent.respond("こんにちは")
    clock.value = 50.0
    agent.respond("それでさあ")
    clock.value = 70.0  # 70 s after the last chat, only 20 s after the chatter
    agent.respond("朝食は？")

    assert llm.calls[2][1:] == [{"role": "user", "content": "朝食は？"}]
