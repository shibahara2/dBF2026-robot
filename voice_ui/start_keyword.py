import unicodedata


def _normalize(text: str) -> str:
    # NFKC folds half-width kana, and dropping whitespace plus substring
    # matching absorbs Whisper's spacing and trailing punctuation.
    return "".join(unicodedata.normalize("NFKC", text).split()).casefold()


def contains_start_keyword(text: str, keywords: list[str]) -> bool:
    normalized = _normalize(text)
    for keyword in keywords:
        key = _normalize(keyword)
        if key and key in normalized:
            return True
    return False
