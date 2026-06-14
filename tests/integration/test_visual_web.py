"""A1/V1 real-browser test: visual-regression baseline capture + diff.

Gated behind --playwright (and needs Pillow / the [visual] extra). Exercises
the full lifecycle on the sample app: first run captures a baseline and passes,
an unchanged page still passes, a deliberate visual change fails and produces a
highlighted diff image (the V1 acceptance criterion), and --update re-captures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_visual_baseline_capture_and_regression(bubblegum_page, sample_app, tmp_path):
    pytest.importorskip("PIL", reason="visual regression needs Pillow ([visual] extra)")

    s = bubblegum_page
    await s.goto(f"{sample_app}/login.html")
    bdir = str(tmp_path / "baselines")

    # 1. First run captures the baseline and passes.
    r1 = await s.verify("login page matches baseline", assertion_type="visual", baseline_dir=bdir)
    assert r1.status == "passed"
    assert r1.target.metadata["visual"]["baseline_action"] == "created"
    assert Path(bdir, "login_page.png").exists()

    # 2. Unchanged page → passes (within tolerance).
    r2 = await s.verify("login page matches baseline", assertion_type="visual", baseline_dir=bdir)
    assert r2.status == "passed"

    # 3. Deliberate visual change → fails and writes a highlighted diff image.
    await s.page.evaluate("document.body.style.background = 'magenta'")
    r3 = await s.verify(
        "login page matches baseline", assertion_type="visual",
        baseline_dir=bdir, tolerance=0.0,
    )
    assert r3.status == "failed"
    assert r3.error.error_type == "VisualRegressionError"
    diff_image = Path(r3.target.metadata["visual"]["diff_image"])
    assert diff_image.exists()
    assert any(a.path.endswith("login_page.diff.png") for a in r3.artifacts)

    # 4. Updating the baseline re-captures the changed page → passes again.
    r4 = await s.verify(
        "login page matches baseline", assertion_type="visual",
        baseline_dir=bdir, update_baseline=True,
    )
    assert r4.status == "passed"
    assert r4.target.metadata["visual"]["baseline_action"] == "updated"
