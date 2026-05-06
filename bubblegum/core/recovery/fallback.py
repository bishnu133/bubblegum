from __future__ import annotations


def used_explicit_selector(*, resolver_name: str, failed_selector: str | None, ref: str) -> bool:
    return resolver_name == "explicit_selector" and failed_selector is not None and ref == failed_selector


def remove_explicit_selector(context: dict) -> None:
    context.pop("explicit_selector", None)
