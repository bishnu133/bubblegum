"""Unit tests for X3 coordinate primitives (bubblegum.core.coordinates)."""

from __future__ import annotations

import pytest

from bubblegum.core.coordinates import (
    COORDINATE_CLICK_ACTIONS,
    bbox_center,
    coordinate_ref,
    coordinate_ref_from_bbox,
    is_coordinate_ref,
    parse_coordinate_ref,
)


def test_is_coordinate_ref():
    assert is_coordinate_ref("point://10,20")
    assert not is_coordinate_ref("vision://target/0")
    assert not is_coordinate_ref("role=button[name=\"Login\"]")
    assert not is_coordinate_ref(None)
    assert not is_coordinate_ref(123)


def test_coordinate_ref_roundtrip():
    ref = coordinate_ref(60, 45)
    assert ref == "point://60,45"
    assert parse_coordinate_ref(ref) == (60, 45)


def test_coordinate_ref_coerces_floats():
    assert coordinate_ref(60.7, 45.2) == "point://60,45"


def test_parse_rejects_non_coordinate():
    assert parse_coordinate_ref("vision://target/0") is None
    assert parse_coordinate_ref("point://10") is None
    assert parse_coordinate_ref("point://10,20,30") is None
    assert parse_coordinate_ref("point://a,b") is None


def test_parse_rejects_negative():
    assert parse_coordinate_ref("point://-1,5") is None
    assert parse_coordinate_ref("point://5,-1") is None


def test_parse_tolerates_whitespace():
    assert parse_coordinate_ref("point://10, 20") == (10, 20)


def test_bbox_center_basic():
    # [x1, y1, x2, y2] → center
    assert bbox_center([10, 20, 110, 70]) == (60, 45)


def test_bbox_center_handles_unordered_corners():
    assert bbox_center([110, 70, 10, 20]) == (60, 45)


def test_bbox_center_rejects_malformed():
    assert bbox_center(None) is None
    assert bbox_center([1, 2, 3]) is None
    assert bbox_center([1, 2, 3, "x"]) is None
    assert bbox_center([1, 2, 3, True]) is None


def test_bbox_center_rejects_negative():
    assert bbox_center([-1, 0, 10, 10]) is None


def test_bbox_center_rejects_zero_area():
    assert bbox_center([10, 20, 10, 70]) is None  # zero width
    assert bbox_center([10, 20, 110, 20]) is None  # zero height


def test_coordinate_ref_from_bbox():
    assert coordinate_ref_from_bbox([10, 20, 110, 70]) == "point://60,45"
    assert coordinate_ref_from_bbox([1, 2, 3]) is None


def test_click_actions_set():
    assert COORDINATE_CLICK_ACTIONS == frozenset({"click", "tap"})
