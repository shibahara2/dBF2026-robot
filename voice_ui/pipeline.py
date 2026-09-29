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
