import re

_LEADING_PATTERNS = [r"^名前は", r"^わたしは", r"^私は"]
_TRAILING_PATTERNS = [r"と申します$", r"です$"]


def extract_name(text: str) -> str:
    name = text.strip()
    for pattern in _LEADING_PATTERNS:
        name = re.sub(pattern, "", name)
    for pattern in _TRAILING_PATTERNS:
        name = re.sub(pattern, "", name)
    return name.strip()
