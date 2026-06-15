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
   to a `point://x,y` ref (the bbox center).
4. The adapter recognizes `point://` and clicks/taps the raw coordinate.

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

- Pure geometry + ref encoding: `bubblegum/core/coordinates.py`
  (`bbox_center`, `coordinate_ref`, `parse_coordinate_ref`, `is_coordinate_ref`).
- Fallback decision: `VisualRefHydrator._coordinate_fallback`
  (`bubblegum/core/grounding/hydrator.py`).
- Execution: `_execute_coordinate_action` in the Playwright and Appium adapters.
