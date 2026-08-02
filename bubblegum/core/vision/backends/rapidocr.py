"""Offline, on-device OCR grounding backend (RapidOCR).

Turns a screenshot into on-screen text candidates **entirely on the machine
running the test** — no network, no hosted model, no per-call cost. This is the
grounding path for screens the Appium hierarchy cannot describe: Flutter and
other canvas-drawn UIs, games, custom-rendered widgets, and DRM-masked views,
where the only reliable signal about "what's on screen" is the pixels.

Because inference is in-process, screenshots never leave the box — so it is the
privacy-clean default for enterprise apps and the low-latency default on a device
farm (only the screenshot travels back over the wire; OCR runs on the runner).

The provider implements the same ``VisionProvider.detect_targets`` contract as
the hosted backends, returning ``VisionCandidate`` objects (``text``/``label`` +
axis-aligned ``bbox`` + ``confidence``). Those flow through the existing
``VisionModelResolver`` and the visual-ref hydrator, which map a matched bbox to
a tap coordinate — so no resolver, adapter, or hydrator change is needed.

RapidOCR (``rapidocr-onnxruntime``) is an optional dependency. When it is not
installed the provider stays fail-safe and returns ``[]`` so the deterministic
tiers still run; install it with ``pip install "bubblegum-ai[localvision]"``.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from bubblegum.core.vision.engine import VisionCandidate

logger = logging.getLogger(__name__)


class RapidOCRVisionProvider:
    """VisionProvider backed by RapidOCR (ONNXRuntime) running locally.

    Args:
        engine: An optional pre-built OCR engine (any callable returning either
            a RapidOCR-style ``(result, elapse)`` tuple or a bare ``result``
            list). Injectable so the conversion logic is unit-testable without
            the heavy model download.
        create_engine: When True (default) and no ``engine`` is injected, the
            RapidOCR engine is built lazily on first use and cached.
        min_confidence: Text boxes below this OCR score are dropped.
        max_candidates: Hard cap on returned candidates (defensive; busy screens
            can OCR into hundreds of tiny fragments).
    """

    provider_name = "rapidocr"

    def __init__(
        self,
        *,
        engine: Any | None = None,
        create_engine: bool = True,
        min_confidence: float = 0.3,
        max_candidates: int = 200,
    ) -> None:
        if isinstance(min_confidence, bool) or not isinstance(min_confidence, (int, float)):
            raise ValueError("RapidOCRVisionProvider min_confidence must be a number in [0, 1].")
        self._engine = engine
        self._create_engine = bool(create_engine)
        self._min_confidence = max(0.0, min(float(min_confidence), 1.0))
        self._max_candidates = max(1, int(max_candidates))

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    def _ensure_engine(self) -> Any | None:
        """Return the OCR engine, building it lazily. Never raises."""
        if self._engine is not None:
            return self._engine
        if not self._create_engine:
            return None
        engine_cls = None
        for module_name in ("rapidocr_onnxruntime", "rapidocr"):
            try:
                module = __import__(module_name, fromlist=["RapidOCR"])
                engine_cls = getattr(module, "RapidOCR", None)
                if engine_cls is not None:
                    break
            except Exception:  # noqa: BLE001 — optional dep: stay dormant if absent
                continue
        if engine_cls is None:
            logger.debug(
                "RapidOCR is not installed; local vision tier dormant. "
                "Install with: pip install \"bubblegum-ai[localvision]\""
            )
            return None
        try:
            self._engine = engine_cls()
        except Exception as exc:  # noqa: BLE001 — model init failure must not crash a run
            logger.debug("RapidOCR engine init failed; local vision tier dormant: %s", exc)
            return None
        return self._engine

    # ------------------------------------------------------------------
    # VisionProvider contract
    # ------------------------------------------------------------------

    def detect_targets(
        self,
        image_bytes: bytes,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> list[VisionCandidate]:
        del instruction, context  # OCR returns all on-screen text; the resolver matches.
        if not image_bytes:
            return []
        engine = self._ensure_engine()
        if engine is None:
            return []
        image = _to_ocr_input(image_bytes)
        try:
            raw = engine(image)
        except Exception as exc:  # noqa: BLE001 — a bad frame must not fail the step
            logger.debug("RapidOCR inference failed; returning no candidates: %s", exc)
            return []
        result = raw[0] if isinstance(raw, tuple) and raw else raw
        return candidates_from_rapidocr_result(
            result, min_confidence=self._min_confidence, max_candidates=self._max_candidates
        )


def _to_ocr_input(image_bytes: bytes) -> Any:
    """Decode PNG/JPEG bytes to an ndarray for the engine.

    Falls back to handing the raw bytes to the engine when Pillow/NumPy are
    unavailable or decoding fails (recent RapidOCR builds accept bytes directly,
    and injected test engines ignore the input entirely).
    """
    try:
        import numpy as np  # noqa: WPS433 — optional, comes with rapidocr
        from PIL import Image  # noqa: WPS433

        with Image.open(io.BytesIO(image_bytes)) as img:
            return np.array(img.convert("RGB"))
    except Exception:  # noqa: BLE001
        return image_bytes


def candidates_from_rapidocr_result(
    result: Any, *, min_confidence: float, max_candidates: int
) -> list[VisionCandidate]:
    """Convert a RapidOCR result list into ``VisionCandidate`` objects.

    RapidOCR yields ``[box, text, score]`` per detected line, where ``box`` is a
    four-point polygon ``[[x,y], ...]``. We reduce each polygon to an
    axis-aligned ``[x1, y1, x2, y2]`` bbox (what the hydrator taps the centre of)
    and keep ``text`` as both ``text`` and ``label``. Pure and side-effect free
    so it is unit-testable without an engine.
    """
    if not result:
        return []
    out: list[VisionCandidate] = []
    for item in result:
        parsed = _parse_line(item)
        if parsed is None:
            continue
        text, bbox, score = parsed
        if score < min_confidence:
            continue
        out.append(
            VisionCandidate(label=text, bbox=bbox, confidence=score, role=None, text=text)
        )
        if len(out) >= max_candidates:
            break
    return out


def _parse_line(item: Any) -> tuple[str, list[int], float] | None:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return None
    box, text = item[0], item[1]
    score = item[2] if len(item) > 2 else 1.0
    if not isinstance(text, str) or not text.strip():
        return None
    bbox = _bbox_from_polygon(box)
    if bbox is None:
        return None
    try:
        score_val = float(score)
    except (TypeError, ValueError):
        score_val = 1.0
    return text.strip(), bbox, max(0.0, min(score_val, 1.0))


def _bbox_from_polygon(box: Any) -> list[int] | None:
    """Reduce a 4-point polygon (or an [x1,y1,x2,y2] box) to an int bbox."""
    if not isinstance(box, (list, tuple)) or not box:
        return None
    # Already an axis-aligned [x1, y1, x2, y2].
    if len(box) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box):
        x1, y1, x2, y2 = (float(v) for v in box)
        return [int(min(x1, x2)), int(min(y1, y2)), int(max(x1, x2)), int(max(y1, y2))]
    xs: list[float] = []
    ys: list[float] = []
    for point in box:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        px, py = point[0], point[1]
        if isinstance(px, bool) or isinstance(py, bool) or not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
            return None
        xs.append(float(px))
        ys.append(float(py))
    if not xs or not ys:
        return None
    return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
