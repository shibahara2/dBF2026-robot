import logging

from .name_extract import extract_name
from .stt import is_confident

logger = logging.getLogger(__name__)


def run_checkin_once(
    mic_source,
    vad_segmenter,
    transcriber,
    checkin_client,
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

    name = extract_name(text)
    logger.info("抽出された名前でチェックインを実行します: name=%r", name)
    checkin_result = checkin_client.checkin(name)
    logger.info("checkin_clientの結果: %s (name=%r)", checkin_result, name)
    return "checked_in"
