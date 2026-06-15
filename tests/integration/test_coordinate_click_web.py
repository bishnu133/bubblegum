"""X3 real-browser test: coordinate-based clicking on a canvas.

Gated behind --playwright. A `<canvas>` has no DOM children, so a vision/OCR
target over it can only be actioned by clicking its bounding-box center. This
test proves the genuinely browser-dependent half of X3 — that a `point://x,y`
ResolvedTarget produces a real mouse click at that pixel in Chromium — by
wiring a canvas click listener that records where it was clicked. The
hydrator's bbox→point fallback is covered exhaustively in the unit tests.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.coordinates import coordinate_ref
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]

# A canvas plus a click listener that records the click coordinates (relative to
# the canvas) into #log — no DOM target exists inside the canvas to resolve.
_CANVAS_HTML = """
<!doctype html><html><body style="margin:0">
<canvas id="board" width="300" height="200"
        style="position:absolute;left:0;top:0;background:#eee"></canvas>
<div id="log">none</div>
<script>
  const c = document.getElementById('board');
  c.addEventListener('click', (e) => {
    const r = c.getBoundingClientRect();
    document.getElementById('log').textContent =
      Math.round(e.clientX - r.left) + ',' + Math.round(e.clientY - r.top);
  });
</script>
</body></html>
"""


async def test_coordinate_target_clicks_canvas(bubblegum_page):
    s = bubblegum_page
    await s.goto("data:text/html," + quote(_CANVAS_HTML))

    adapter = PlaywrightAdapter(s.page)
    target = ResolvedTarget(
        ref=coordinate_ref(120, 80),
        point=[120, 80],
        confidence=0.8,
        resolver_name="vision_model",
        metadata={"bbox": [100, 60, 140, 100]},
    )
    plan = ActionPlan(action_type="click", target_hint="player", options=ExecutionOptions())

    result = await adapter.execute(plan, target)

    assert result.success, result.error
    assert result.element_ref == "point://120,80"
    assert target.metadata["coordinate_click"] is True
    # The canvas listener recorded a click at (≈120, ≈80).
    logged = await s.page.locator("#log").inner_text()
    assert logged == "120,80"
