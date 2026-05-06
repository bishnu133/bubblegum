from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject() -> dict:
    pyproject = ROOT / "pyproject.toml"
    with pyproject.open("rb") as f:
        return tomllib.load(f)


def test_project_identity_unchanged() -> None:
    data = _load_pyproject()
    project = data["project"]

    assert project["name"] == "bubblegum-ai"
    assert project["version"] == "0.0.2a0"


def test_required_release_metadata_present() -> None:
    data = _load_pyproject()
    project = data["project"]

    assert project.get("description")
    assert project.get("readme") == "README.md"
    assert project.get("license") == "MIT"
    assert project.get("authors")
    assert project.get("classifiers")
    assert project.get("urls")

    urls = project["urls"]
    assert "Homepage" in urls
    assert "Repository" in urls
    assert "Issues" in urls


def test_license_file_exists() -> None:
    assert (ROOT / "LICENSE").exists()
