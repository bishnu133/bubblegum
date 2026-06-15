"""Unit tests for visual-regression logic (V1).

Browser-free. The pure pixel math (compare/evaluate/highlight/name) runs with
no dependencies; the end-to-end sdk.verify(assertion_type="visual") flow runs
against a fake adapter, faking PNG decode so Pillow is not required.
"""

from __future__ import annotations

import pytest

from bubblegum.core import sdk
from bubblegum.core import visual as v
from bubblegum.core.config import VisualConfig


# ---------------------------------------------------------------------------
# baseline_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction,expected",
    [
        ("header matches baseline", "header"),
        ("Verify the header matches baseline", "header"),
        ("checkout page looks the same", "checkout_page"),
        ("matches baseline", "baseline"),  # nothing left → fallback
        ("Nav Bar", "nav_bar"),
    ],
)
def test_baseline_name_derivation(instruction, expected):
    assert v.baseline_name(instruction) == expected


def test_baseline_name_prefers_explicit_and_falls_back_to_signature():
    assert v.baseline_name("anything", expected_value="My Region") == "my_region"
    assert v.baseline_name("matches baseline", screen_signature="ABC123") == "abc123"


# ---------------------------------------------------------------------------
# compare_rgba / evaluate_diff / highlight
# ---------------------------------------------------------------------------


def _solid(width, height, rgba):
    return bytes(rgba) * (width * height)


def test_compare_identical_is_zero_diff():
    img = _solid(2, 2, (10, 20, 30, 255))
    diff, total, mask = v.compare_rgba(img, img, 2, 2)
    assert (diff, total) == (0, 4)
    assert mask == bytes(4)


def test_compare_counts_changed_pixels():
    base = _solid(2, 1, (0, 0, 0, 255))
    actual = bytearray(base)
    actual[0:4] = bytes((255, 255, 255, 255))  # change pixel 0
    diff, total, mask = v.compare_rgba(base, bytes(actual), 2, 1)
    assert (diff, total) == (1, 2)
    assert mask == bytes([1, 0])


def test_channel_threshold_absorbs_small_deltas():
    base = _solid(1, 1, (100, 100, 100, 255))
    actual = _solid(1, 1, (108, 100, 100, 255))  # +8 on red
    assert v.compare_rgba(base, actual, 1, 1, channel_threshold=10)[0] == 0
    assert v.compare_rgba(base, actual, 1, 1, channel_threshold=5)[0] == 1


def test_compare_rejects_wrong_size():
    with pytest.raises(ValueError):
        v.compare_rgba(b"\x00" * 4, b"\x00" * 8, 1, 1)


def test_evaluate_diff_tolerance_boundary():
    # 1 of 100 pixels = 0.01 ratio
    assert v.evaluate_diff(1, 100, 0.01) == (True, 0.01)
    assert v.evaluate_diff(2, 100, 0.01)[0] is False


def test_highlight_paints_changed_red_and_dims_rest():
    actual = bytes((0, 0, 0, 255)) + bytes((0, 0, 0, 255))
    mask = bytes([1, 0])
    out = v.highlight_diff_rgba(actual, mask, 2, 1)
    assert out[0:4] == bytes((255, 0, 0, 255))   # changed → red
    assert out[4:7] == bytes((170, 170, 170))     # unchanged black dimmed toward white


# ---------------------------------------------------------------------------
# VisualConfig validation
# ---------------------------------------------------------------------------


def test_visual_config_defaults_and_validation():
    cfg = VisualConfig()
    assert cfg.baseline_dir == ".bubblegum/baselines"
    assert cfg.tolerance == 0.001
    with pytest.raises(ValueError):
        VisualConfig(tolerance=1.5)
    with pytest.raises(ValueError):
        VisualConfig(channel_threshold=300)


# ---------------------------------------------------------------------------
# sdk.verify(assertion_type="visual") — against a fake adapter
# ---------------------------------------------------------------------------


class FakeVisualAdapter:
    def __init__(self, png=b"PNG-A"):
        self.png = png

    async def screenshot_bytes(self, *, full_page=False):
        return self.png


def _fake_pillow(monkeypatch, decode_map):
    """Make visual_image use a fake codec: bytes → (rgba, w, h) from decode_map.

    decode_map maps a screenshot-bytes token → (rgba_bytes, w, h). save_png is
    stubbed to just write the raw bytes so artifacts land on disk.
    """
    from bubblegum.core import visual_image as vimg

    monkeypatch.setattr(vimg, "pillow_available", lambda: True)
    monkeypatch.setattr(vimg, "load_png_rgba", lambda data: decode_map[data])

    def fake_save(rgba, w, h, path):
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"diff")
        return p

    monkeypatch.setattr(vimg, "save_png", fake_save)


@pytest.mark.asyncio
async def test_visual_first_run_creates_baseline(monkeypatch, tmp_path):
    adapter = FakeVisualAdapter(png=b"shot")
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    _fake_pillow(monkeypatch, {b"shot": (b"\x00" * 4, 1, 1)})

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path),
    )
    assert result.status == "passed"
    assert (tmp_path / "header.png").read_bytes() == b"shot"
    assert result.target.metadata["visual"]["baseline_action"] == "created"


@pytest.mark.asyncio
async def test_visual_matching_baseline_passes(monkeypatch, tmp_path):
    (tmp_path / "header.png").write_bytes(b"baseline")
    adapter = FakeVisualAdapter(png=b"actual")
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    # Both decode to the same 1x1 black pixel → no diff.
    _fake_pillow(monkeypatch, {b"baseline": (b"\x00" * 4, 1, 1), b"actual": (b"\x00" * 4, 1, 1)})

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path),
    )
    assert result.status == "passed"
    assert result.target.metadata["visual"]["diff_pixels"] == 0


@pytest.mark.asyncio
async def test_visual_change_fails_and_writes_diff(monkeypatch, tmp_path):
    (tmp_path / "header.png").write_bytes(b"baseline")
    adapter = FakeVisualAdapter(png=b"actual")
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    # baseline black, actual white → 1/1 pixel differs.
    _fake_pillow(monkeypatch, {
        b"baseline": (bytes((0, 0, 0, 255)), 1, 1),
        b"actual": (bytes((255, 255, 255, 255)), 1, 1),
    })

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path), tolerance=0.0,
    )
    assert result.status == "failed"
    assert result.error.error_type == "VisualRegressionError"
    assert (tmp_path / "header.diff.png").exists()
    assert (tmp_path / "header.actual.png").read_bytes() == b"actual"
    assert any(a.path.endswith("header.diff.png") for a in result.artifacts)


@pytest.mark.asyncio
async def test_visual_size_mismatch_fails(monkeypatch, tmp_path):
    (tmp_path / "header.png").write_bytes(b"baseline")
    adapter = FakeVisualAdapter(png=b"actual")
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    _fake_pillow(monkeypatch, {
        b"baseline": (b"\x00" * 4, 1, 1),
        b"actual": (b"\x00" * 16, 2, 2),
    })

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path),
    )
    assert result.status == "failed"
    assert "size changed" in result.error.message


@pytest.mark.asyncio
async def test_visual_update_baseline_overwrites(monkeypatch, tmp_path):
    (tmp_path / "header.png").write_bytes(b"old")
    adapter = FakeVisualAdapter(png=b"new")
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    _fake_pillow(monkeypatch, {b"new": (b"\x00" * 4, 1, 1)})

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path), update_baseline=True,
    )
    assert result.status == "passed"
    assert (tmp_path / "header.png").read_bytes() == b"new"
    assert result.target.metadata["visual"]["baseline_action"] == "updated"


@pytest.mark.asyncio
async def test_visual_missing_pillow_fails_clearly(monkeypatch, tmp_path):
    adapter = FakeVisualAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    from bubblegum.core import visual_image as vimg
    monkeypatch.setattr(vimg, "pillow_available", lambda: False)

    result = await sdk.verify(
        "header matches baseline", channel="web", page=object(),
        assertion_type="visual", baseline_dir=str(tmp_path),
    )
    assert result.status == "failed"
    assert result.error.error_type == "VisualDependencyError"


@pytest.mark.asyncio
async def test_visual_mobile_channel_unsupported(monkeypatch):
    class _Drv:
        pass
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FakeVisualAdapter())

    result = await sdk.verify(
        "header matches baseline", channel="mobile", driver=_Drv(),
        assertion_type="visual",
    )
    assert result.status == "failed"
    assert result.error.error_type == "UnsupportedChannelError"
