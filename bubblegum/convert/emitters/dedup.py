"""
bubblegum/convert/emitters/dedup.py
===================================
Optional sub-flow deduplication for the smart-tests emitter.

Extracts a run of **identical, consecutive** rendered step-blocks that appears in
3+ scenarios into a shared helper function, replacing each occurrence with a
call. Matching on the *already-rendered* lines is what keeps this safe alongside
data extraction: a data-bearing step renders as ``${scenarioAData.x}`` in one
scenario and ``${scenarioBData.x}`` in another — different text — so such steps
are never wrongly merged.

Off by default (``output.dedup_subflows``). Conservative thresholds mirror the
spec: a run must be **≥ 3 blocks** and appear in **≥ 3 scenarios**, and must
contain at least two executable (``await``) blocks so we don't hoist bare
comments.
"""

from __future__ import annotations

MIN_RUN = 3        # minimum consecutive blocks in a shared run
MIN_SCENARIOS = 3  # minimum distinct scenarios a run must appear in
_MAX_RUN = 12      # upper bound on run length we search for


def _key(blocks: list[tuple[str, ...]], start: int, length: int) -> tuple:
    return tuple(blocks[start:start + length])


def _executable(block: tuple[str, ...]) -> bool:
    return any("await " in line for line in block)


def dedup_scenarios(
    scenario_blocks: list[list[tuple[str, ...]]],
) -> tuple[list[tuple[str, list[str]]], list[list[tuple[str, ...]]]]:
    """Find shared runs across scenarios.

    Args:
        scenario_blocks: per scenario, an ordered list of blocks; each block is a
            tuple of already-rendered (indented) source lines for one step.

    Returns:
        (shared, rewritten) where ``shared`` is a list of
        ``(fn_name, body_lines)`` and ``rewritten`` is the per-scenario block
        list with each shared run collapsed to a single call block.
    """
    # Count, for each candidate run (by its block-tuple key), how many distinct
    # scenarios contain it. Longest runs first so we prefer maximal extraction.
    counts: dict[tuple, int] = {}
    for length in range(min(_MAX_RUN, max((len(b) for b in scenario_blocks), default=0)), MIN_RUN - 1, -1):
        for blocks in scenario_blocks:
            seen_here: set[tuple] = set()
            for start in range(0, len(blocks) - length + 1):
                key = _key(blocks, start, length)
                if key in seen_here:
                    continue
                seen_here.add(key)
                counts[key] = counts.get(key, 0) + 1

    # Choose runs: longest first, then most shared. Skip keys with too few
    # executable blocks or below the scenario threshold.
    candidates = [
        k for k, c in counts.items()
        if c >= MIN_SCENARIOS and sum(1 for b in k if _executable(b)) >= 2
    ]
    candidates.sort(key=lambda k: (len(k), counts[k]), reverse=True)

    shared: list[tuple[str, list[str]]] = []
    chosen: list[tuple[tuple, str]] = []
    claimed_keys: set[tuple] = set()
    for key in candidates:
        # Skip a run that is wholly contained in an already-chosen (longer) run.
        if any(_is_subrun(key, ck) for ck, _ in chosen):
            continue
        fn = f"sharedFlow{len(shared) + 1}"
        body = [line for block in key for line in block]
        shared.append((fn, body))
        chosen.append((key, fn))
        claimed_keys.add(key)

    if not chosen:
        return [], scenario_blocks

    call_block_for = {key: (f"  await {fn}(engine, page);",) for key, fn in chosen}
    rewritten: list[list[tuple[str, ...]]] = []
    for blocks in scenario_blocks:
        rewritten.append(_rewrite(blocks, chosen, call_block_for))
    return shared, rewritten


def _is_subrun(inner: tuple, outer: tuple) -> bool:
    if len(inner) >= len(outer):
        return False
    return any(outer[i:i + len(inner)] == inner for i in range(len(outer) - len(inner) + 1))


def _rewrite(blocks, chosen, call_block_for):
    """Replace each chosen run in ``blocks`` with its single call block."""
    out: list[tuple[str, ...]] = []
    i = 0
    n = len(blocks)
    # Longest chosen runs first so a maximal run wins at a given position.
    ordered = sorted(chosen, key=lambda ck: len(ck[0]), reverse=True)
    while i < n:
        matched = False
        for key, _ in ordered:
            L = len(key)
            if i + L <= n and tuple(blocks[i:i + L]) == key:
                out.append(call_block_for[key])
                i += L
                matched = True
                break
        if not matched:
            out.append(blocks[i])
            i += 1
    return out
