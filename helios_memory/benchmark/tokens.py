"""Token helpers for benchmark length math (NIAH-compatible when tiktoken is installed)."""

from __future__ import annotations

_ENCODING_NAME = "cl100k_base"


def _load_encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding(_ENCODING_NAME)
    except Exception:
        return None


_ENCODING = _load_encoding()


def encoding_name() -> str:
    return _ENCODING_NAME if _ENCODING is not None else "char_estimate"


def encode(text: str) -> list[int]:
    if _ENCODING is not None:
        return _ENCODING.encode(text)
    # Fallback: encode text as UTF-8 bytes for reversibility.
    return list(text.encode("utf-8"))


def decode(tokens: list[int]) -> str:
    if _ENCODING is not None:
        return _ENCODING.decode(tokens)
    # Fallback: decode bytes back to original string.
    return bytes(tokens).decode("utf-8", errors="replace")


    # Fallback: return byte length.
    return len(text.encode("utf-8")) // 4 or len(text.encode("utf-8"))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if _ENCODING is not None:
        tokens = _ENCODING.encode(text)
        return _ENCODING.decode(tokens[:max_tokens])
    return text[: max_tokens * 4]
