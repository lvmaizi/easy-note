import re

# Token estimation calibrated for mixed Chinese/English text.
# Conservative: over-estimates ~20% to provide safety margin.
_CHINESE_PATTERN = re.compile(r'[一-鿿㐀-䶿豈-﫿]')
_WORD_PATTERN = re.compile(r'[a-zA-Z0-9]+')


def count_tokens(text: str) -> int:
    """Estimate token count for mixed Chinese/English text."""
    chinese_chars = len(_CHINESE_PATTERN.findall(text))
    english_words = len(_WORD_PATTERN.findall(text))
    # Remaining: punctuation, whitespace, newlines, non-letter symbols
    matched_len = sum(len(w) for w in _WORD_PATTERN.findall(text))
    remaining = len(text) - chinese_chars - matched_len

    # Chinese chars ~1.5 tokens, English words ~1.3 tokens, rest ~1.0 token
    return int(chinese_chars * 1.5 + english_words * 1.3 + remaining * 1.0)