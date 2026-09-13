def is_confident(
    no_speech_prob: float,
    avg_logprob: float,
    no_speech_prob_max: float,
    avg_logprob_min: float,
) -> bool:
    return no_speech_prob <= no_speech_prob_max and avg_logprob >= avg_logprob_min
