from __future__ import annotations

SIGNAL_TEXT_MATCH = "text_match"
SIGNAL_ROLE_MATCH = "role_match"
SIGNAL_VISIBILITY = "visibility"
SIGNAL_UNIQUENESS = "uniqueness"
SIGNAL_PROXIMITY = "proximity"
SIGNAL_MEMORY = "memory"
SIGNAL_MEMORY_HISTORY = "memory_history"


def clamp_signal(value: float) -> float:
    """Clamp any signal to the closed interval [0.0, 1.0]."""
    return min(max(float(value), 0.0), 1.0)


def make_signals(
    text_match: float = 0.0,
    role_match: float = 0.0,
    visibility: float = 0.0,
    uniqueness: float = 0.0,
    proximity: float = 0.0,
    memory: float = 0.0,
    memory_history: float | None = None,
) -> dict[str, float]:
    """
    Build normalized ranking signals.

    Emits both `memory` and `memory_history` for compatibility.
    If memory_history is omitted, it mirrors memory.
    """
    memory_val = clamp_signal(memory)
    memory_hist_val = memory_val if memory_history is None else clamp_signal(memory_history)
    return {
        SIGNAL_TEXT_MATCH: clamp_signal(text_match),
        SIGNAL_ROLE_MATCH: clamp_signal(role_match),
        SIGNAL_VISIBILITY: clamp_signal(visibility),
        SIGNAL_UNIQUENESS: clamp_signal(uniqueness),
        SIGNAL_PROXIMITY: clamp_signal(proximity),
        SIGNAL_MEMORY: memory_val,
        SIGNAL_MEMORY_HISTORY: memory_hist_val,
    }

