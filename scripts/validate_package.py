#!/usr/bin/env python3
"""Offline-safe package metadata validation for Bubblegum release checks."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from importlib import metadata
from pathlib import Path
from typing import Iterable

EXPECTED_NAME = "bubblegum-ai"
REQUIRED_METADATA_FIELDS = (
    "Summary",
    "License",
    "Author",
    "Requires-Python",
)
REQUIRED_URL_LABELS = ("Homepage", "Repository", "Issues")


def _print_header(title: str) -> None:
    print(f"\n[{title}]")


def _validate_metadata(dist_name: str, strict: bool = False) -> bool:
    _print_header("installed metadata")
    try:
        md = metadata.metadata(dist_name)
    except metadata.PackageNotFoundError:
        print(f"distribution not installed: {dist_name}")
        print("hint: run editable install first (pip install -e .) to validate installed metadata")
        if strict:
            print("strict mode: FAIL (installed distribution metadata is required)")
            return False
        return True

    ok = True
    print(f"Name: {md.get('Name')}")
    print(f"Version: {md.get('Version')}")

    for field in REQUIRED_METADATA_FIELDS:
        value = md.get(field)
        status = "OK" if value else "MISSING"
        print(f"{field}: {status}{f' -> {value}' if value else ''}")
        ok = ok and bool(value)

    project_urls: Iterable[str] = md.get_all("Project-URL", [])
    normalized = {u.split(",", 1)[0].strip() for u in project_urls if "," in u}
    for label in REQUIRED_URL_LABELS:
        present = label in normalized
        print(f"Project-URL[{label}]: {'OK' if present else 'MISSING'}")
        ok = ok and present

    return ok


def _validate_import() -> bool:
    _print_header("import smoke")
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        import bubblegum  # noqa: F401
    except Exception as exc:
        print(f"import bubblegum: FAILED ({exc})")
        return False

    import bubblegum

    version = getattr(bubblegum, "__version__", None)
    print(f"bubblegum.__version__: {version}")
    return bool(version)


def _check_license_file() -> bool:
    _print_header("license file")
    license_path = Path(__file__).resolve().parents[1] / "LICENSE"
    exists = license_path.exists()
    print(f"LICENSE exists: {exists}")
    return exists


def _build_check(strict: bool = False) -> bool:
    _print_header("build module check" if strict else "optional build check")
    has_build = importlib.util.find_spec("build") is not None
    if has_build:
        print("build module detected. run: python -m build")
        return True

    if strict:
        print("build module not installed. strict mode requires it: pip install build")
        return False

    print("build module not installed. optional release check skipped.")
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Bubblegum package metadata and release-readiness checks.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict release-mode validation (installed metadata and build module required).",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Alias for --strict.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strict = bool(args.strict or args.release)

    ok = True
    ok = _validate_import() and ok
    ok = _check_license_file() and ok
    ok = _validate_metadata(EXPECTED_NAME, strict=strict) and ok
    ok = _build_check(strict=strict) and ok

    _print_header("result")
    if ok:
        print("package validation passed")
        return 0

    print("package validation found issues")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
