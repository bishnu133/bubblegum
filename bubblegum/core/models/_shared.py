"""
bubblegum/core/models/_shared.py
================================
Shared provider plumbing (Task #7).

Single source of truth for helpers that were duplicated across the text and
vision provider stacks (Anthropic/OpenAI text providers + vision backends). Both
stacks import from here instead of copy-pasting, so a fix lands in one place.
"""

from __future__ import annotations


def strip_code_fence(raw: str) -> str:
    """Remove a leading/trailing markdown code fence some models wrap JSON in.

    ```json\n{...}\n```  ->  {...}
    Idempotent and safe on unfenced text.
    """
    if not raw:
        return raw
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    inner = lines[1:] if len(lines) > 1 else lines   # drop opening ```lang
    if inner and inner[-1].strip() == "```":
        inner = inner[:-1]                            # drop closing ```
    return "\n".join(inner).strip()
