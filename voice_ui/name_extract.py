import re

_LEADING_PATTERNS = [r"^名前は", r"^わたしは", r"^私は"]
_TRAILING_PATTERNS = [r"と申します$", r"です$"]
_TRAILING_PUNCT = re.compile(r"[。、．，！？!?・\s]+$")


def extract_name(text: str) -> str:
    name = text.strip()
    name = _TRAILING_PUNCT.sub("", name)
    for pattern in _LEADING_PATTERNS:
        name = re.sub(pattern, "", name)
    name = _TRAILING_PUNCT.sub("", name)
    for pattern in _TRAILING_PATTERNS:
        name = re.sub(pattern, "", name)
    name = _TRAILING_PUNCT.sub("", name)
    return name.strip()
