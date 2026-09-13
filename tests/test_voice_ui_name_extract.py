from voice_ui.name_extract import extract_name


def test_plain_name_passthrough():
    assert extract_name("田中太郎") == "田中太郎"


def test_strips_trailing_desu():
    assert extract_name("田中太郎です") == "田中太郎"


def test_strips_leading_namae_wa():
    assert extract_name("名前は田中太郎") == "田中太郎"


def test_strips_leading_and_trailing_together():
    assert extract_name("名前は田中太郎です") == "田中太郎"


def test_strips_to_moushimasu():
    assert extract_name("田中太郎と申します") == "田中太郎"


def test_strips_surrounding_whitespace():
    assert extract_name("  田中太郎です  ") == "田中太郎"
