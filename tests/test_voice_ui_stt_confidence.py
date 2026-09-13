from voice_ui.stt import is_confident


def test_confident_when_both_within_bounds():
    assert is_confident(no_speech_prob=0.1, avg_logprob=-0.2, no_speech_prob_max=0.6, avg_logprob_min=-1.0)


def test_rejected_when_no_speech_prob_too_high():
    assert not is_confident(no_speech_prob=0.9, avg_logprob=-0.2, no_speech_prob_max=0.6, avg_logprob_min=-1.0)


def test_rejected_when_avg_logprob_too_low():
    assert not is_confident(no_speech_prob=0.1, avg_logprob=-5.0, no_speech_prob_max=0.6, avg_logprob_min=-1.0)


def test_boundary_values_are_accepted():
    assert is_confident(no_speech_prob=0.6, avg_logprob=-1.0, no_speech_prob_max=0.6, avg_logprob_min=-1.0)
