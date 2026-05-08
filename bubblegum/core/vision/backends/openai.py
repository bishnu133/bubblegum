from __future__ import annotations

import base64
import json
from typing import Any

from bubblegum.core.vision.engine import VisionCandidate, normalize_vision_candidates


class OpenAIVisionProvider:
    """Optional VisionProvider-compatible backend using an OpenAI-style client.

    The provider supports either:
    - an injected client exposing `responses.create(...)`, or
    - lazy construction of an OpenAI client when `create_client=True`.

    Provider failures are fail-safe and return an empty list.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str = "gpt-4.1-mini",
        timeout: float = 10.0,
        create_client: bool = False,
    ) -> None:
        model = model.strip()
        if not model:
            raise ValueError("OpenAIVisionProvider model must be a non-empty string.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or float(timeout) <= 0:
            raise ValueError("OpenAIVisionProvider timeout must be a positive number.")
        if client is None and not create_client:
            raise ValueError(
                "OpenAIVisionProvider requires an injected client or create_client=True. "
                "Install and configure the OpenAI SDK, or inject a compatible client."
            )
        self._client = client
        self._model = model
        self._timeout = float(timeout)

    def _extract_response_text(self, response: Any) -> str | None:
        if isinstance(response, str):
            text = response.strip()
            return text or None

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            text = output_text.strip()
            return text or None

        output = getattr(response, "output", None)
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") in {"output_text", "text"} and isinstance(block.get("text"), str):
                        text = block["text"].strip()
                        if text:
                            return text
        return None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - import path tested via error behavior
            raise RuntimeError(
                "OpenAI SDK is not installed. Install optional dependency (e.g. `openai`) "
                "or inject a preconfigured client into OpenAIVisionProvider."
            ) from exc
        self._client = OpenAI(timeout=self._timeout)
        return self._client

    def detect_targets(
        self,
        image_bytes: bytes,
        instruction: str,
        context: dict[str, Any] | None = None,
    ) -> list[VisionCandidate] | list[dict[str, Any]]:
        if not image_bytes:
            return []

        try:
            client = self._ensure_client()
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            prompt = (
                "Return JSON only with shape {\"candidates\": [...]} where each candidate has "
                "label (string), bbox ([x1,y1,x2,y2] or null), confidence (0..1), optional role, optional text. "
                f"Instruction: {instruction.strip()}"
            )
            if context:
                prompt = f"{prompt}\nContext: {json.dumps(context, sort_keys=True)}"

            response = client.responses.create(
                model=self._model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                        ],
                    }
                ],
                response_format={"type": "json_object"},
            )
            text = self._extract_response_text(response)
            if not text:
                return []
            parsed = json.loads(text)
            raw_candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
            return normalize_vision_candidates(raw_candidates)
        except Exception:
            return []
