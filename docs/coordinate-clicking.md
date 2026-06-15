# Coordinate-based vision clicking (X3)

Some UIs have no element to resolve: a `<canvas>` game board, an image map, a
chart, a custom-drawn control. Bubblegum's deterministic resolvers (a11y tree,
DOM, Appium hierarchy) and even the visual-ref **hydrator** — which normally
maps a vision/OCR hit back to a real element by its text/role — find nothing to
click. All the model gives you is a **bounding box**.

X3 turns that box into an action: when hydration can't map a vision/OCR target
to an element, Bubblegum clicks the **center of the bounding box** directly —
`page.mouse.click(x, y)` on web, a coordinate `tap` on mobile.

## Opt-in

A blind coordinate click is riskier than an element click (no visibility /
enabled / hit-testing guarantees), so it is **off by default**. Enable it in
`bubblegum.yaml`:

```yaml
grounding:
  enable_vision: true              # produce vision candidates
  coordinate_click_fallback: true  # X3: click bbox-center when nothing maps
```

## How it fits the pipeline

1. Grounding resolves a target. For a canvas, the only resolver that can match
   is vision/OCR, producing a synthetic `vision://…` / `ocr://…` ref with a
   `bbox` in its metadata.
2. The `VisualRefHydrator` first tries a **deterministic** mapping (text / role /
   content-desc / resource-id → a real element ref). This still wins when it
   can — a coordinate click is the *last* resort, never a shortcut past an
   element.
3. If no element mapping exists **and** `coordinate_click_fallback` is on **and**
   the action is a click/tap **and** the bbox is usable, the target is hydrated
   with an explicit **`point` field** (the bbox center). Its `ref` stays a
   human-readable `point://x,y` label for traces/reports.
4. The adapter sees a non-`None` `target.point` and clicks/taps that coordinate
   directly — no locator resolution.

## Scope & guarantees

- **Click / tap only.** Typing and selecting need a real, focusable element, so
  coordinate fallback never applies to them.
- **Fail-closed parsing.** Malformed or negative coordinates, and degenerate
  zero-area boxes, yield no point — the step fails cleanly rather than clicking
  `(0, 0)`.
- **Traceable.** A coordinate step stamps `coordinate_click=True`,
  `coordinate_point=[x, y]`, and `hydration_strategy="coordinate"` onto the
  target metadata, so reports show the step used the fallback rather than an
  element. The deterministic reason it fell back to coordinates is recorded too.

## Internals

- Structured click point: `ResolvedTarget.point` (`[x, y]`, screen pixels) —
  the field adapters dispatch on. Pure geometry + validation in
  `bubblegum/core/coordinates.py` (`bbox_center`, `normalize_point`,
  `coordinate_ref` for the readable label).
- Fallback decision: `VisualRefHydrator._coordinate_fallback`
  (`bubblegum/core/grounding/hydrator.py`) sets `point` (+ a `point://x,y` ref).
- Execution: `_execute_coordinate_action` in the Playwright and Appium adapters
  (`page.mouse.click` / `driver.tap`).
