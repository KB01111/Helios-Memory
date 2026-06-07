"""Haystack generation and needle insertion (NIAH single-depth methodology)."""

from __future__ import annotations

from helios_memory.benchmark.tokens import count, decode, encode, truncate_to_tokens
from helios_memory.benchmark.types import HaystackBuild, NeedlePlacement, NeedleSpec

MAX_PERIOD_SNAP = 100

DEFAULT_HAYSTACK_UNIT = (
    "This is filler prose about distributed systems, observability, and software design. "
)


def _snap_to_period(context_tokens: list[int], insertion_point: int) -> int:
    if insertion_point <= 0:
        return 0
    period_tokens = set(encode("."))
    lower_bound = max(0, insertion_point - MAX_PERIOD_SNAP)
    candidate = insertion_point
    while candidate > lower_bound:
        if context_tokens[candidate - 1] in period_tokens:
            return candidate
        candidate -= 1
    return insertion_point


def build_repeating_haystack(
    min_tokens: int,
    unit: str = DEFAULT_HAYSTACK_UNIT,
    separator: str = "\n\n",
) -> str:
    """Repeat filler text until `min_tokens`, then truncate to exact length."""
    if not unit.strip():
        raise ValueError("Haystack unit text must be non-empty")
    block = unit + separator
    block_tokens = count(block)
    if block_tokens == 0:
        raise ValueError("Haystack unit encodes to zero tokens")
    repeats = (min_tokens // block_tokens) + 1
    haystack = block * repeats
    return truncate_to_tokens(haystack, min_tokens)


def insert_needle_at_depth(
    haystack_text: str,
    needle_text: str,
    depth_percent: float,
    *,
    snap_to_periods: bool = True,
) -> tuple[str, NeedlePlacement]:
    """Insert one needle at `depth_percent` of the haystack token stream."""
    if not 0.0 <= depth_percent <= 100.0:
        raise ValueError(f"depth_percent must be in [0, 100]; got {depth_percent}")

    context_tokens = encode(haystack_text)
    needle_tokens = encode(needle_text)
    pre_len = len(context_tokens)

    if depth_percent == 100.0:
        insertion_point = pre_len
    elif depth_percent == 0.0:
        insertion_point = 0
    else:
        insertion_point = int(pre_len * (depth_percent / 100.0))
        if snap_to_periods:
            insertion_point = _snap_to_period(context_tokens, insertion_point)

    actual_depth = (insertion_point / pre_len * 100.0) if pre_len > 0 else 0.0
    new_tokens = (
        context_tokens[:insertion_point] + needle_tokens + context_tokens[insertion_point:]
    )
    placement = NeedlePlacement(
        text=needle_text,
        insertion_token_index=insertion_point,
        actual_depth_percent=actual_depth,
    )
    return decode(new_tokens), placement


def build_haystack_with_needle(
    context_length: int,
    depth_percent: float,
    needle: NeedleSpec | None = None,
    *,
    haystack_unit: str = DEFAULT_HAYSTACK_UNIT,
    snap_to_periods: bool = True,
) -> HaystackBuild:
    """Build a haystack at `context_length` tokens and embed the needle at depth."""
    spec = needle or NeedleSpec()
    base = build_repeating_haystack(context_length, unit=haystack_unit)
    text, placement = insert_needle_at_depth(
        base,
        spec.needle_text,
        depth_percent,
        snap_to_periods=snap_to_periods,
    )
    return HaystackBuild(
        text=text,
        token_count=count(text),
        target_token_count=context_length,
        depth_percent=depth_percent,
        placement=placement,
        needle=spec,
    )
