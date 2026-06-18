"""
bubblegum/core/table.py
=======================
Table assertions — verify that a data table has expected columns, and that a
value appears under a given column (optionally only in the row matched by another
column's value, e.g. a key sourced from a database).

Two entry styles, both routed through ``verify``:

  Structured ("other way" — deterministic):
      bg.verify("participant row", assertion_type="table",
                row_match={"PPHID": pphid}, cell={"Account Status": "Active"})
      bg.verify("columns", assertion_type="table",
                columns=["PPHID", "Account Status", "Profile Status"])

  Natural language ("AI way"):
      bg.verify("the table has columns PPHID, Account Status and Profile Status")
      bg.verify('in the row where Name is "Bishnu Test Account", '
                'Account Status is "Active"')
      bg.verify('the Account Status column shows "Active"')

A *matcher* is a plain dict with any of:
  - ``columns``:   [str, ...]         columns whose headers must be present
  - ``row_match``: {column: value}    locate the row(s) where these cells match
  - ``cell``:      {column: value}    assert these column cells in the row(s)

Matching is whitespace-normalised and case-insensitive; a cell matches when the
expected value equals the cell text or is contained in it (tolerates badges /
icons rendered alongside the value, e.g. a status pill "✓ Active").
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Normalisation / matching helpers
# ---------------------------------------------------------------------------

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _key(s: Any) -> str:
    return _norm(s).casefold()


def _value_matches(actual: Any, expected: Any) -> bool:
    a, e = _key(actual), _key(expected)
    if not e:
        return not a
    return a == e or e in a


def _find_header(column: str, headers: list[str]) -> str | None:
    """Return the header from ``headers`` that names ``column`` (or None).

    Tries normalised-equality first, then containment either way so
    "Account Status" still resolves a header rendered as "Account Status ▲".
    """
    ck = _key(column)
    for h in headers:
        if _key(h) == ck:
            return h
    for h in headers:
        hk = _key(h)
        if ck and (ck in hk or hk in ck):
            return h
    return None


# ---------------------------------------------------------------------------
# Matcher construction
# ---------------------------------------------------------------------------

def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_strip_quotes(str(v)) for v in value if str(v).strip()]
    return _split_list(str(value))


def _split_list(text: str) -> list[str]:
    # Split on commas and the conjunctions "and" / "&".
    parts = re.split(r"\s*,\s*|\s+and\s+|\s*&\s*", text.strip())
    out = []
    for p in parts:
        p = _strip_quotes(p)
        # Drop a leading article left over from "the X, Y columns".
        p = re.sub(r"^(?:the|a|an)\s+", "", p, flags=re.IGNORECASE).strip()
        if p:
            out.append(p)
    return out


def _strip_quotes(s: str) -> str:
    # Drop trailing sentence punctuation, then any surrounding quote characters
    # (handles unbalanced leftovers like 'Active"' from a regex capture).
    s = s.strip().rstrip(".!?").strip()
    return s.strip("\"'`").strip()


def build_table_matcher(instruction: str, kwargs: dict[str, Any]) -> dict | None:
    """Build a matcher from structured kwargs / expected_value, else parse NL."""
    columns = kwargs.get("columns")
    row_match = kwargs.get("row_match") or kwargs.get("row")
    cell = kwargs.get("cell")

    ev = kwargs.get("expected_value")
    if isinstance(ev, dict):
        columns = columns if columns is not None else ev.get("columns")
        row_match = row_match or ev.get("row_match") or ev.get("row")
        cell = cell or ev.get("cell")

    matcher: dict[str, Any] = {}
    if columns:
        matcher["columns"] = _as_list(columns)
    if row_match:
        matcher["row_match"] = {str(k): _strip_quotes(str(v)) for k, v in dict(row_match).items()}
    if cell:
        matcher["cell"] = {str(k): _strip_quotes(str(v)) for k, v in dict(cell).items()}

    if matcher:
        return matcher
    return parse_table_spec(instruction)


# ---------------------------------------------------------------------------
# Natural-language parsing (rule-based)
# ---------------------------------------------------------------------------

def parse_table_spec(instruction: str) -> dict | None:
    """Parse a table assertion from natural language. Returns None if no match.

    Recognised shapes (case-insensitive):
      - "... row where|with|for <col> is|= <val>, <col2> is|=|shows <val2>"
      - "<col> column shows|has|contains|is <val>"
      - "<val> (appears|is shown|displayed) under the <col> column"
      - "... columns <A>, <B> and <C>"   (requires a has/show/with/present cue)
    """
    text = (instruction or "").strip()
    low = text.casefold()
    if not any(w in low for w in ("column", "row", "table", "grid")):
        return None

    # 1) Row-keyed cell: "row where Name is "X", Account Status is "Active""
    m = re.search(
        r"\brow\s+(?:where|with|for)\s+(.+?)\s+(?:is|=|equals?)\s+(.+?)\s*[,;]\s*"
        r"(?:the\s+)?(.+?)\s+(?:is|=|equals?|shows?|should\s+be|displays?)\s+(.+?)\s*$",
        text, re.IGNORECASE,
    )
    if m:
        kc, kv, col, val = (_strip_quotes(g) for g in m.groups())
        col = re.sub(r"\s+column$", "", col, flags=re.IGNORECASE).strip()
        if kc and col:
            return {"row_match": {kc: kv}, "cell": {col: val}}

    # 2) "<col> column shows|has|contains|is <val>"
    m = re.search(
        r"\b(?:the\s+)?(.+?)\s+column\s+(?:shows?|has|contains?|displays?|is|=|equals?)\s+(.+?)\s*$",
        text, re.IGNORECASE,
    )
    if m and not re.search(r"\bcolumns\b", m.group(1) + " column", re.IGNORECASE):
        col, val = _strip_quotes(m.group(1)), _strip_quotes(m.group(2))
        if col and val:
            return {"cell": {col: val}}

    # 3) "<val> (appears|is shown|displayed) under the <col> column"
    m = re.search(
        r"\b(.+?)\s+(?:appears?|is\s+shown|is\s+displayed|displayed|shown)\s+under\s+"
        r"(?:the\s+)?(.+?)\s+column\b",
        text, re.IGNORECASE,
    )
    if m:
        val, col = _strip_quotes(m.group(1)), _strip_quotes(m.group(2))
        if col and val:
            return {"cell": {col: val}}

    # 4) Columns present: "... columns A, B and C" with a presence cue.
    m = re.search(r"\bcolumns?\b\s+(.+?)\s*$", text, re.IGNORECASE)
    if m and re.search(
        r"\b(has|have|shows?|contains?|with|including|are|is|present|displayed|visible)\b|:",
        low,
    ):
        cols = _split_list(m.group(1))
        if cols:
            return {"columns": cols}

    return None


# ---------------------------------------------------------------------------
# Evaluation against extracted tables
# ---------------------------------------------------------------------------

def evaluate_table(matcher: dict, tables: list[dict]) -> tuple[bool, str]:
    """Evaluate ``matcher`` against extracted ``tables``.

    Each table is ``{"headers": [str], "rows": [{header: cell_text}], ...}``.
    Returns ``(passed, human_readable_detail)``.
    """
    columns = matcher.get("columns") or []
    row_match = matcher.get("row_match") or {}
    cell = matcher.get("cell") or {}

    if not (columns or row_match or cell):
        return False, "empty table assertion (need columns / row_match / cell)"
    if not tables:
        return False, "no tables found on the page"

    needed_cols = list(columns) + list(row_match) + list(cell)

    # Pick the table that has every required column header.
    chosen: dict | None = None
    best_missing: list[str] | None = None
    for t in tables:
        headers = t.get("headers", [])
        missing = [c for c in needed_cols if _find_header(c, headers) is None]
        if not missing:
            chosen = t
            break
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing

    if chosen is None:
        seen = [t.get("headers", []) for t in tables]
        return False, (
            f"no table has the required column(s); missing {best_missing}. "
            f"Tables seen with headers: {seen}"
        )

    # Columns-only assertion.
    if columns and not row_match and not cell:
        return True, f"all columns present: {columns}"

    headers = chosen["headers"]
    rows = chosen.get("rows", [])

    def cell_value(row: dict, col: str) -> str:
        h = _find_header(col, headers)
        return row.get(h, "") if h is not None else ""

    # Candidate rows by row_match.
    candidates = [
        row for row in rows
        if all(_value_matches(cell_value(row, c), v) for c, v in row_match.items())
    ]
    if row_match and not candidates:
        return False, (
            f"no row where { {k: v for k, v in row_match.items()} } "
            f"(scanned {len(rows)} row(s))"
        )

    search_rows = candidates if row_match else rows
    for row in search_rows:
        if all(_value_matches(cell_value(row, c), v) for c, v in cell.items()):
            shown = {**row_match, **{c: cell_value(row, c) for c in cell}}
            return True, f"matched row {shown}"

    # Build an actionable failure message.
    if row_match:
        actual = [{c: cell_value(r, c) for c in cell} for r in candidates]
        return False, (
            f"row {dict(row_match)} found, but cell(s) {dict(cell)} did not match; "
            f"actual {actual}"
        )
    seen_values = {c: [cell_value(r, c) for r in rows] for c in cell}
    return False, f"no row has cell(s) {dict(cell)}; values seen per column: {seen_values}"


def describe_table_matcher(matcher: dict) -> str:
    bits = []
    if matcher.get("columns"):
        bits.append("columns=" + ", ".join(matcher["columns"]))
    if matcher.get("row_match"):
        bits.append("row " + ", ".join(f"{k}={v!r}" for k, v in matcher["row_match"].items()))
    if matcher.get("cell"):
        bits.append("cell " + ", ".join(f"{k}={v!r}" for k, v in matcher["cell"].items()))
    return "; ".join(bits) or "table assertion"


# ---------------------------------------------------------------------------
# Table / link ACTIONS — click an element in a cell, or click a link by text
# ---------------------------------------------------------------------------

_ORDINALS = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10, "last": -1,
}

# Trailing nouns that describe the cell target rather than the column name.
_CELL_NOUN = r"(?:value|element|link|cell|button|item|text)"
# Noise words that can precede "row" (e.g. "first result row", "data row").
_ROW_NOISE = r"(?:result|results|data|table|search)\s+"


def _parse_row_spec(text: str):
    """Parse a row selector → ("index", n) (1-based; -1 = last) or ("match", {col: val})."""
    s = _norm(text).casefold()
    if not s:
        return None
    if s in _ORDINALS:
        return ("index", _ORDINALS[s])
    m = re.match(r"^(?:row\s*)?(\d+)(?:st|nd|rd|th)?$", s)
    if m:
        return ("index", int(m.group(1)))
    m = re.search(r"where\s+(.+?)\s+(?:is|=|equals?)\s+(.+)$", text, re.IGNORECASE)
    if m:
        return ("match", {_strip_quotes(m.group(1)): _strip_quotes(m.group(2))})
    return None


def _cell_spec(column: str, row_text: str) -> dict | None:
    column = re.sub(rf"\s+{_CELL_NOUN}$", "", _strip_quotes(column), flags=re.IGNORECASE).strip()
    rs = _parse_row_spec(row_text)
    if not column or rs is None:
        return None
    spec: dict[str, Any] = {"kind": "cell", "column": column}
    if rs[0] == "index":
        spec["row_index"] = rs[1]
    else:
        spec["row_match"] = rs[1]
    return spec


def parse_table_action(instruction: str, kwargs: dict[str, Any] | None = None) -> dict | None:
    """Parse a click-in-table or click-link action. Returns None if not matched.

    Returns one of:
      {"kind": "link", "text": str, "exact": bool}
      {"kind": "cell", "column": str, "row_index": int}       # 1-based; -1 = last
      {"kind": "cell", "column": str, "row_match": {col: val}}
    """
    kwargs = kwargs or {}

    # --- Structured kwargs win -------------------------------------------------
    if kwargs.get("link_text"):
        return {"kind": "link", "text": str(kwargs["link_text"]), "exact": bool(kwargs.get("exact", False))}
    col = kwargs.get("column")
    if col is not None and any(k in kwargs for k in ("row", "row_index", "row_match")):
        spec: dict[str, Any] = {"kind": "cell", "column": str(col)}
        if kwargs.get("row_match"):
            spec["row_match"] = dict(kwargs["row_match"])
        elif kwargs.get("row_index") is not None:
            spec["row_index"] = int(kwargs["row_index"])
        else:
            row = kwargs.get("row")
            if isinstance(row, int):
                spec["row_index"] = row
            else:
                rs = _parse_row_spec(str(row))
                if rs is None:
                    return None
                spec["row_index" if rs[0] == "index" else "row_match"] = rs[1]
        return spec

    text = (instruction or "").strip()
    low = text.casefold()

    # --- Cell actions (require both a column and a row in the phrase) ----------
    if "column" in low or "row" in low:
        # "in the row where KEY is VAL[,] click [the] COL [value]"
        m = re.search(
            rf"\brow\s+(?:where|with|for)\s+(?P<rk>.+?)\s+(?:is|=|equals?)\s+(?P<rv>.+?)\s*[,;]\s*"
            rf"(?:click|tap|press|select)\s+(?:on\s+)?(?:the\s+)?(?P<col>.+?)(?:\s+{_CELL_NOUN})?\s*$",
            text, re.IGNORECASE,
        )
        if m:
            col = re.sub(rf"\s+{_CELL_NOUN}$", "", _strip_quotes(m.group("col")), flags=re.IGNORECASE).strip()
            if col:
                return {"kind": "cell", "column": col,
                        "row_match": {_strip_quotes(m.group("rk")): _strip_quotes(m.group("rv"))}}

        patterns = (
            # "under [the] COL column[,] click [on] [the] ROW row [value]"
            rf"under\s+(?:the\s+)?(?P<col>.+?)\s+column\b[\s,]*"
            rf"(?:click|tap|press|select)?\s*(?:on\s+)?(?:the\s+)?(?P<row>.+?)\s+(?:{_ROW_NOISE})?row\b",
            # "click [the] COL (value|link|cell) in|of|for [the] ROW row"
            rf"(?:click|tap|press|select)\s+(?:on\s+)?(?:the\s+)?(?P<col>.+?)\s+{_CELL_NOUN}\s+"
            rf"(?:in|of|for|from)\s+(?:the\s+)?(?P<row>.+?)\s+(?:{_ROW_NOISE})?row\b",
            # "in [the] ROW row[,] click [the] COL [value]"
            rf"in\s+(?:the\s+)?(?P<row>.+?)\s+(?:{_ROW_NOISE})?row\b[\s,]*"
            rf"(?:click|tap|press|select)\s+(?:on\s+)?(?:the\s+)?(?P<col>.+?)(?:\s+{_CELL_NOUN})?\s*$",
            # "click [on] [the] ROW row['s] COL [value]"
            rf"(?:click|tap|press|select)\s+(?:on\s+)?(?:the\s+)?(?P<row>.+?)\s+(?:{_ROW_NOISE})?row(?:'s|s)?\s+"
            rf"(?P<col>.+?)(?:\s+{_CELL_NOUN})?\s*$",
        )
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                spec = _cell_spec(m.group("col"), m.group("row"))
                if spec:
                    return spec

    # --- Link by text ----------------------------------------------------------
    # "click [on] [the] link [with text|labelled|that says|named|:] <text>"
    m = re.search(
        r"(?:click|tap|press|open|follow)\s+(?:on\s+)?(?:the\s+)?link\b"
        r"(?:\s+(?:with\s+(?:the\s+)?text|with\s+the\s+text|labell?ed|that\s+says|named|titled|text|:))?"
        r"\s*[:\-]?\s*(?P<text>.+?)\s*$",
        text, re.IGNORECASE,
    )
    if m:
        link_text = _strip_quotes(m.group("text"))
        if link_text:
            return {"kind": "link", "text": link_text, "exact": False}

    return None
