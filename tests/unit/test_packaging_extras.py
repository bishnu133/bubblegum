from __future__ import annotations

from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 test env fallback
    import tomli as tomllib


def test_optional_dependency_groups_and_members() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    optional = data["project"]["optional-dependencies"]

    for group in ("web", "mobile", "test", "dev", "all"):
        assert group in optional

    assert "playwright" in optional["web"]
    assert "Appium-Python-Client" in optional["mobile"]

    assert "pytest-asyncio" in optional["test"]
    assert "pytest-asyncio" in optional["dev"]
    assert "pytest-asyncio" in optional["all"]
