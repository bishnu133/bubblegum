from __future__ import annotations

from importlib import metadata

from scripts import validate_package


def test_validate_metadata_default_mode_tolerates_missing_distribution(monkeypatch):
    def _raise(_: str):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(validate_package.metadata, "metadata", _raise)
    assert validate_package._validate_metadata("bubblegum-ai", strict=False) is True


def test_validate_metadata_strict_mode_fails_when_distribution_missing(monkeypatch):
    def _raise(_: str):
        raise metadata.PackageNotFoundError

    monkeypatch.setattr(validate_package.metadata, "metadata", _raise)
    assert validate_package._validate_metadata("bubblegum-ai", strict=True) is False


def test_build_check_default_tolerates_missing_build_module(monkeypatch):
    monkeypatch.setattr(validate_package.importlib.util, "find_spec", lambda _: None)
    assert validate_package._build_check(strict=False) is True


def test_build_check_strict_fails_when_build_module_missing(monkeypatch):
    monkeypatch.setattr(validate_package.importlib.util, "find_spec", lambda _: None)
    assert validate_package._build_check(strict=True) is False
