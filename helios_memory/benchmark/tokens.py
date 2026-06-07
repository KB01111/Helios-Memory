"""Token helpers for benchmark length math (NIAH-compatible when tiktoken is installed)."""

from __future__ import annotations

_ENCODING_NAME = "cl100k_base"


def _load_encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding(_ENCODING_NAME)
    except ImportError:
        return None


_ENCODING = _load_encoding()


def encoding_name() -> str:
    return _ENCODING_NAME if _ENCODING is not None else "char_estimate"


def encode(text: str) -> list[int]:
    if _ENCODING is not None:
        return _ENCODING.encode(text)
    # ~4 chars per token fallback when tiktoken is unavailable.
    return list(range(max(1, len(text) // 4)))


def decode(tokens: list[int]) -> str:
    if _ENCODING is not None:
        return _ENCODING.decode(tokens)
    return "x" * max(1, len(tokens) * 4)


def count(text: str) -> int:
    if _ENCODING is not None:
        return len(_ENCODING.encode(text))
    return max(1, len(text) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if _ENCODING is not None:
        tokens = _ENCODING.encode(text)
        return _ENCODING.decode(tokens[:max_tokens])
    return text[: max_tokens * 4]
