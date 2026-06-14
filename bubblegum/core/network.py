"""Network-assertion matching (W4).

Pure, browser-free helpers for ``verify(..., assertion_type="network",
expected_value="POST /api/login 200")``. The web adapter records responses and
calls into this module to decide whether an expected backend call occurred.

A matcher has three optional parts — method, URL pattern, status — parsed from a
compact spec like ``"POST /api/login 200"``. Any omitted part matches anything,
so ``"/api/login"`` matches that URL with any method/status and ``"500"`` matches
any request that returned 500.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Any

_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
# Pull a spec out of a longer NL instruction, e.g. 'login posts POST /api/login 200'.
_SPEC_RE = re.compile(r"\b([A-Z]+\s+)?(/\S+|https?://\S+)(\s+\d{3})?")


def parse_network_matcher(expected: str | None) -> dict[str, Any] | None:
    """Parse a spec like 'POST /api/login 200' into {method, url, status}.

    Returns None when nothing usable is present (so the caller can fail with a
    clear "provide expected_value" message). At least a URL or a status is
    required for a meaningful matcher.
    """
    if not expected or not str(expected).strip():
        return None

    tokens = str(expected).split()
    method: str | None = None
    status: int | None = None
    url_parts: list[str] = []

    for tok in tokens:
        upper = tok.upper()
        if method is None and upper in _HTTP_METHODS:
            method = upper
            continue
        if status is None and tok.isdigit() and len(tok) == 3:
            status = int(tok)
            continue
        url_parts.append(tok)

    url = " ".join(url_parts).strip() or None
    if url is None and status is None:
        # Only a bare method (e.g. "POST") is not specific enough to assert on.
        return None
    return {"method": method, "url": url, "status": status}


def extract_network_spec(instruction: str | None) -> str | None:
    """Best-effort extraction of a network spec embedded in an NL instruction."""
    if not instruction:
        return None
    match = _SPEC_RE.search(instruction)
    if not match:
        return None
    return " ".join(part.strip() for part in match.groups() if part).strip() or None


def _url_matches(url: str, pattern: str) -> bool:
    if any(ch in pattern for ch in "*?["):
        # Glob against the whole URL or just the path tail.
        return fnmatch(url, pattern) or fnmatch(url, f"*{pattern}")
    return pattern in url


def response_matches(record: dict[str, Any], matcher: dict[str, Any]) -> bool:
    """True when a recorded response {method,url,status} satisfies the matcher."""
    if matcher.get("method") and str(record.get("method", "")).upper() != matcher["method"]:
        return False
    if matcher.get("status") is not None and int(record.get("status", -1)) != int(matcher["status"]):
        return False
    pattern = matcher.get("url")
    if pattern and not _url_matches(str(record.get("url", "")), pattern):
        return False
    return True


def find_matching_response(records: list[dict[str, Any]], matcher: dict[str, Any]) -> dict[str, Any] | None:
    """Return the most recent recorded response matching the matcher, else None."""
    for record in reversed(records):
        if response_matches(record, matcher):
            return record
    return None


def describe_matcher(matcher: dict[str, Any]) -> str:
    parts = []
    if matcher.get("method"):
        parts.append(str(matcher["method"]))
    if matcher.get("url"):
        parts.append(str(matcher["url"]))
    if matcher.get("status") is not None:
        parts.append(str(matcher["status"]))
    return " ".join(parts) or "<any>"


def describe_record(record: dict[str, Any]) -> str:
    return f"{record.get('method', '?')} {record.get('url', '?')} {record.get('status', '?')}"
