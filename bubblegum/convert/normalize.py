"""
bubblegum/convert/normalize.py
==============================
Turn RawScenario rows into classified CanonicalStep / Scenario / Feature IR.

Deterministic-first: every step is run through Bubblegum's existing rule-based
``decompose`` grammar (the same one the SDK uses at runtime). The AI fallback is
optional, off by default, and only consulted for steps the grammar cannot
confidently split — mirroring Bubblegum's fallback-first posture.

Classification (StepKind) is the honest part of the scaffold:
  * AUTO       — clean action/assertion, emit a real Bubblegum call.
  * NEEDS_DATA — precondition / test data a human must wire (emit + TODO).
  * BACKEND    — non-UI backend behaviour (emit skipped stub).
  * MANUAL     — couldn't interpret; emit a TODO for a human.
"""

from __future__ import annotations

import re

from bubblegum.convert.gherkin import clean_text, parse_gherkin
from bubblegum.convert.models import (
    CanonicalStep,
    Feature,
    RawScenario,
    Scenario,
    StepKind,
)
from bubblegum.convert.profile import ConvertProfile
from bubblegum.core.parser.instruction import decompose

# Actions decompose() can produce that map to a real UI interaction.
_ACTIONABLE = {
    "click", "tap", "type", "select", "upload", "check", "uncheck",
    "set", "hover", "scroll", "verify", "extract",
    "long_press", "double_tap", "pinch", "zoom", "drag",
}

# A "Given" that describes data / preconditions rather than a navigable action.
_DATA_HINT_RE = re.compile(
    r"\b(has|have|having|with|contains?|configured|there\s+(?:is|are|exists?)|"
    r"set\s+to|equals?|between|at\s+least|more\s+than|fewer\s+than|less\s+than)\b"
    r"|\d",
    re.IGNORECASE,
)

# A "Given" that is plain navigation we can drive with a click/goto.
_NAV_HINT_RE = re.compile(
    r"\b(open|navigate|go\s+to|view|viewing|on\s+the\b|land(?:s|ed)?\s+on)\b",
    re.IGNORECASE,
)

# A "Given" that is a login / authentication precondition — maps to a fixture,
# not a UI action, so it is NEEDS_DATA rather than AUTO.
_LOGIN_HINT_RE = re.compile(
    r"\b(logged\s+in|log\s+in|sign\s+in|signed\s+in|authenticated|"
    r"as\s+an?\s+.+\s+user|with\s+.+\s+role)\b",
    re.IGNORECASE,
)

# Vague assertion phrasing that has no concrete, checkable target. Checked
# against the *original* step text (before subject/modal stripping) so signals
# like "will be able to" survive.
_VAGUE_RE = re.compile(
    r"\b(will\s+be\s+able\s+to|able\s+to|as\s+expected|correctly|appropriately|"
    r"existing\s+behaviou?r|follow\s+existing|depend(?:s|ing)?\s+on|regardless|"
    r"based\s+on|where\s+applicable|if\s+applicable|etc\.?|and\s+so\s+on|"
    r"e\.g\.)\b",
    re.IGNORECASE,
)

# A single assertion, not a compound one. Real "Then" lines that pack several
# checks (with "if", inline "e.g.", or many clauses) can't map to one verify.
_COMPOUND_RE = re.compile(r"\bif\b|,\s*(?:and|followed by)\b|\band\b.*\band\b", re.IGNORECASE)

# Verbs that mark a step as a genuine UI action (used to gate When → AUTO so a
# state precondition like "there is 1 row" isn't mistaken for a click).
_ACTION_VERBS = {
    "click", "tap", "press", "type", "enter", "fill", "input", "select",
    "choose", "pick", "open", "navigate", "go", "follow", "upload", "attach",
    "check", "uncheck", "tick", "untick", "toggle", "set", "hover", "scroll",
    "expand", "collapse", "drag", "swipe", "double", "long", "zoom", "pinch",
    "submit", "search", "clear", "close", "switch",
}


def _starts_with_action_verb(instruction: str) -> bool:
    m = re.match(r"^\s*([a-zA-Z]+)", instruction or "")
    return bool(m) and m.group(1).lower() in _ACTION_VERBS

_SECTION = {"given": "given", "when": "when", "then": "then"}

# Gherkin steps are written in first/third person ("I click…", "they enter…",
# "the user sees…"). Bubblegum's grammar expects the verb to lead, so we strip a
# leading subject + optional modal before parsing and before emitting the
# runtime instruction. The readable first-person text is kept for the .feature.
_SUBJECT_RE = re.compile(
    r"^\s*(?:i|we|you|they|it|he|she|"
    r"the\s+user|a\s+user|an?\s+\w+\s+user|user|the\s+system|system)\s+"
    r"(?:will\s+|would\s+|should\s+|shall\s+|can\s+|could\s+|must\s+|"
    r"then\s+|also\s+|now\s+)*",
    re.IGNORECASE,
)


def _strip_subject(text: str) -> str:
    """Drop a leading subject/modal so the verb leads, for cleaner parsing.

    "I enter \"x\" into Username" -> "enter \"x\" into Username"
    "they will see the Dashboard" -> "see the Dashboard"
    Returns the original text if stripping would empty it.
    """
    stripped = _SUBJECT_RE.sub("", text, count=1).strip()
    return stripped or text


def _resolve_sections(steps) -> list:
    """Resolve And/But to the section (given/when/then) of the prior primary."""
    resolved = []
    current = "given"
    for s in steps:
        if s.keyword in _SECTION:
            current = _SECTION[s.keyword]
            resolved.append((s.keyword, s.text))
        elif s.keyword in ("and", "but"):
            resolved.append((current, s.text))
        else:  # keyword-less (imperative column) — infer by position later
            resolved.append((current, s.text))
    return resolved


def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
    """Replace a whole-step phrase via the team glossary (case-insensitive)."""
    if not glossary:
        return text
    key = text.strip().casefold()
    for phrase, canonical in glossary.items():
        if phrase.strip().casefold() == key:
            return canonical
    return text


def _classify(
    section: str,
    display_text: str,
    instruction: str,
    parsed,
    is_backend: bool,
) -> tuple[StepKind, str | None]:
    """Decide the StepKind + a TODO reason for one step.

    ``display_text`` is the original step text (used for vagueness/compound
    signals); ``instruction`` is the subject-stripped form used for the action.
    """
    if is_backend:
        return StepKind.BACKEND, "Backend/data behaviour — not a UI interaction."

    vague = bool(_VAGUE_RE.search(display_text))

    if section == "given":
        # Login / persona precondition → map to an auth fixture (not a UI act).
        if _LOGIN_HINT_RE.search(display_text):
            return StepKind.NEEDS_DATA, "Login/persona precondition — map to an auth fixture."
        # Plain navigation → drivable. Pure state/data → needs seeding.
        if _NAV_HINT_RE.search(display_text) and not _DATA_HINT_RE.search(display_text):
            return StepKind.AUTO, None
        if _DATA_HINT_RE.search(display_text):
            return StepKind.NEEDS_DATA, "Precondition / test data must be set up."
        # Persona-style "Given a <role> user" → precondition.
        return StepKind.NEEDS_DATA, "Precondition — map persona/setup to a fixture."

    if section == "then":
        if vague or parsed.target_phrase is None:
            return StepKind.MANUAL, "Abstract assertion — supply a concrete element/expectation."
        if _COMPOUND_RE.search(display_text):
            return StepKind.MANUAL, "Compound assertion — split into one check per Then."
        return StepKind.AUTO, None

    # when / imperative action: require a genuine action verb so a state
    # precondition ("there is 1 row") isn't mistaken for a UI action.
    if not _starts_with_action_verb(instruction):
        if _DATA_HINT_RE.search(display_text):
            return StepKind.NEEDS_DATA, "Reads like a precondition/state — set up test data."
        return StepKind.MANUAL, "No clear UI action — rephrase to a concrete action."
    if parsed.action_type in _ACTIONABLE and parsed.target_phrase:
        return StepKind.AUTO, None
    return StepKind.MANUAL, "Could not resolve a concrete action/target."


def _slugify(name: str) -> str:
    """Filesystem/identifier-safe slug from a feature/scenario name."""
    s = re.sub(r"\[[^\]]*\]", " ", name)          # drop [F][H365]-style tags
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or "feature"


def _feature_tags(name: str) -> list[str]:
    """Extract bracket tags like [F][H365] → @f @h365."""
    tags = re.findall(r"\[([^\]]+)\]", name)
    return ["@" + re.sub(r"[^a-zA-Z0-9]+", "_", t).strip("_").lower() for t in tags if t.strip()]


# Generic bracket tags that don't distinguish one feature from another.
_GENERIC_TAGS = {"f", "e", "feature", "epic"}

# Slugs reserved for scaffolded shared flows so a generated feature flow never
# overwrites them (e.g. a Feature literally named "Login" must not clobber the
# scaffolded flows/login.flow.ts that exports loginFlow).
_RESERVED_SLUGS = {"login"}


def _unique_slug(name: str, used: set[str]) -> str:
    """A filesystem-safe slug guaranteed unique within ``used``.

    Two features whose names differ only by a bracket tag — e.g.
    ``[F][BAP] Streaks`` vs ``[F][Backend] Streaks`` — would otherwise slugify
    identically and overwrite each other. On collision we append the
    distinguishing (non-generic) bracket tag, then a numeric suffix as a last
    resort. ``used`` is mutated with the chosen slug.
    """
    base = _slugify(name)
    if base not in used:
        used.add(base)
        return base

    # Prefer a meaningful disambiguator from the feature's own bracket tags.
    for raw_tag in re.findall(r"\[([^\]]+)\]", name):
        tag = re.sub(r"[^a-zA-Z0-9]+", "_", raw_tag).strip("_").lower()
        if tag and tag not in _GENERIC_TAGS:
            candidate = f"{base}_{tag}"
            if candidate not in used:
                used.add(candidate)
                return candidate

    n = 2
    while f"{base}_{n}" in used:
        n += 1
    slug = f"{base}_{n}"
    used.add(slug)
    return slug


def normalize_scenario(
    raw: RawScenario,
    profile: ConvertProfile | None = None,
    ai_hook=None,
) -> Scenario:
    """Normalize one RawScenario row into a classified Scenario."""
    profile = profile or ConvertProfile()
    is_backend = _is_backend(raw, profile)

    gherkin = parse_gherkin(raw.steps_text)
    sectioned = _resolve_sections(gherkin)

    steps: list[CanonicalStep] = []
    for section, text in sectioned:
        text = _apply_glossary(clean_text(text), profile.glossary)
        instruction = _strip_subject(text)
        parsed = decompose(instruction)

        # Optional AI fallback for steps the grammar can't split confidently.
        if ai_hook is not None and not parsed.confident:
            improved = ai_hook(instruction, section)
            if improved is not None:
                parsed = improved

        kind, todo = _classify(section, text, instruction, parsed, is_backend)
        steps.append(
            CanonicalStep(
                keyword=section,
                text=text,
                instruction=instruction,
                action_type=parsed.action_type,
                target=parsed.target_phrase,
                value=parsed.input_value,
                kind=kind,
                confident=parsed.confident,
                todo=todo,
            )
        )

    tags = []
    if raw.jira:
        tags.append("@" + re.sub(r"[^a-zA-Z0-9]+", "_", raw.jira).strip("_").lower())
    if is_backend:
        tags.append("@backend")

    return Scenario(
        title=raw.title or f"Scenario row {raw.row}",
        steps=steps,
        persona=raw.persona,
        jira=raw.jira,
        feature=raw.feature,
        source_row=raw.row,
        tags=tags,
    )


def _is_backend(raw: RawScenario, profile: ConvertProfile) -> bool:
    haystack = f"{raw.feature} {raw.title}".casefold()
    return any(m.strip().casefold() in haystack for m in profile.input.backend_markers if m.strip())


def build_features(
    scenarios: list[RawScenario],
    profile: ConvertProfile | None = None,
    ai_hook=None,
) -> list[Feature]:
    """Group RawScenarios by Feature/Epic and normalize each into IR."""
    profile = profile or ConvertProfile()
    grouped: dict[str, Feature] = {}
    order: list[str] = []
    used_slugs: set[str] = set(_RESERVED_SLUGS)

    for raw in scenarios:
        name = raw.feature or "Ungrouped"
        if name not in grouped:
            grouped[name] = Feature(
                name=name,
                slug=_unique_slug(name, used_slugs),
                tags=_feature_tags(name),
                is_backend=_is_backend(raw, profile),
            )
            order.append(name)
        scenario = normalize_scenario(raw, profile, ai_hook=ai_hook)
        grouped[name].scenarios.append(scenario)
        if not scenario.is_backend:
            grouped[name].is_backend = grouped[name].is_backend and False

    return [grouped[n] for n in order]
