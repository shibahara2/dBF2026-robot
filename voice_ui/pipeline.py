from .name_extract import extract_name
from .stt import is_confident


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
        return "rejected_low_confidence"

    name = extract_name(text)
    checkin_client.checkin(name)
    return "checked_in"
