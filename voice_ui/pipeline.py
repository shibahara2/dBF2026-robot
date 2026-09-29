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
