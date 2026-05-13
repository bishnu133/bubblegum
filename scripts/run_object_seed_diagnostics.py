#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bubblegum.core.elements import ElementGraph, NormalizedElement, build_graph_query_diagnostics
from bubblegum.core.parser.instruction import parse_relational_intent


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return data["cases"]
    raise ValueError(f"Unsupported seed format: {path}")


def _load_sidecar(path: Path) -> dict[str, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        out = {}
        for row in data["cases"]:
            cid = row.get("case_id")
            els = row.get("elements")
            if isinstance(cid, str) and isinstance(els, list):
                out[cid] = els
        return out
    raise ValueError(f"Unsupported synthetic-elements format: {path}")


def _to_normalized_elements(raw_elements: list[dict[str, Any]], fallback_channel: str) -> list[NormalizedElement]:
    elements: list[NormalizedElement] = []
    for e in raw_elements:
        payload = {
            "id": e["id"],
            "channel": e.get("channel", fallback_channel),
            "platform": e.get("platform", "web" if fallback_channel == "web" else "android"),
            "source_kind": e.get("source_kind", "seed_synthetic"),
            "source_ref": e.get("source_ref"),
            "role": e.get("role"),
            "tag": e.get("tag"),
            "widget_type": e.get("widget_type"),
            "text": e.get("text"),
            "label": e.get("label"),
            "accessibility_name": e.get("name") or e.get("accessibility_name"),
            "content_desc": e.get("content_desc"),
            "resource_id": e.get("resource_id"),
            "test_id": e.get("test_id"),
            "visible": bool(e.get("visible", True)),
            "enabled": bool(e.get("enabled", True)),
            "selected": bool(e.get("selected", False)),
            "parent_id": e.get("parent_id"),
            "children_ids": list(e.get("children_ids", [])),
            "attributes": dict(e.get("attributes", {})),
            "metadata": dict(e.get("metadata", {})),
        }
        elements.append(NormalizedElement(**payload))
    return elements


def _expected_status_ok(case: dict[str, Any], diagnostics: dict[str, Any]) -> bool:
    failure_mode = case.get("expected_failure_mode")
    status = str(diagnostics.get("status") or "")
    if failure_mode is None:
        return status in {"ok", "no_relation", "no_match", "no_scope", "no_anchor", "ambiguous"}
    mapping = {
        "ambiguous_candidate": {"ambiguous", "no_match", "no_relation"},
        "unsupported_surface": {"no_match", "no_scope", "unsupported", "no_relation"},
        "no_candidate": {"no_match", "no_anchor", "no_scope"},
    }
    return status in mapping.get(str(failure_mode), {"no_match", "ambiguous", "no_scope", "no_anchor", "unsupported", "no_relation"})


def run_diagnostics(cases_path: Path, sidecar_path: Path, *, strict: bool = False) -> dict[str, Any]:
    cases = _load_cases(cases_path)
    sidecar = _load_sidecar(sidecar_path)

    parsed_relation_counts: Counter[str] = Counter()
    diag_status_counts: Counter[str] = Counter()
    diag_relation_counts: Counter[str] = Counter()

    rows = []
    skipped_missing = 0
    parse_none_count = 0
    parsed_count = 0
    ambiguity_count = 0
    rel_match = 0
    rel_mismatch = 0
    status_match = 0
    status_mismatch = 0
    unsupported_or_deferred = 0

    for case in cases:
        case_id = case["case_id"]
        instruction = case["instruction"]
        action_type = case.get("action_type")
        expected_relation = case.get("expected_relation") or None
        expected_relation_type = expected_relation.get("type") if isinstance(expected_relation, dict) else "none"

        raw_elements = sidecar.get(case_id)
        if raw_elements is None:
            if strict:
                raise ValueError(f"Missing synthetic metadata for case_id={case_id}")
            skipped_missing += 1
            rows.append({"case_id": case_id, "instruction": instruction, "result_status": "skipped_missing_metadata"})
            continue

        relational_intent = parse_relational_intent(instruction, action_type=action_type)
        if relational_intent is None:
            parse_none_count += 1
        else:
            parsed_count += 1
            parsed_relation_counts[str(relational_intent.get("relation_type") or "none")] += 1

        graph = ElementGraph(_to_normalized_elements(raw_elements, case.get("channel", "web")))
        diagnostics = build_graph_query_diagnostics(graph, relational_intent, action_type=action_type)

        d_status = str(diagnostics.get("status") or "")
        d_relation = str(diagnostics.get("relation_type") or "none")
        d_amb = bool(diagnostics.get("ambiguity", {}).get("is_ambiguous", False) if isinstance(diagnostics.get("ambiguity"), dict) else diagnostics.get("ambiguity", False))
        d_matched_count = len(diagnostics.get("matched_ids") or [])
        reasons = [str(x) for x in (diagnostics.get("reasons") or [])]

        diag_status_counts[d_status] += 1
        diag_relation_counts[d_relation] += 1
        if d_amb:
            ambiguity_count += 1

        if d_relation == (expected_relation_type or "none"):
            rel_match += 1
        else:
            rel_mismatch += 1

        status_ok = _expected_status_ok(case, diagnostics)
        if status_ok:
            status_match += 1
        else:
            status_mismatch += 1

        if "deferred" in case.get("tags", []) or case.get("expected_failure_mode") == "unsupported_surface":
            unsupported_or_deferred += 1

        rows.append(
            {
                "case_id": case_id,
                "instruction": instruction,
                "expected_relation_type": expected_relation_type,
                "parsed_relation_type": (relational_intent or {}).get("relation_type", "none"),
                "diagnostics_status": d_status,
                "diagnostics_relation_type": d_relation,
                "ambiguity": d_amb,
                "matched_id_count": d_matched_count,
                "reasons": reasons,
                "result_status": "ok" if status_ok else "mismatch",
            }
        )

    summary = {
        "total_cases": len(cases),
        "evaluated_cases": len(cases) - skipped_missing,
        "skipped_missing_metadata": skipped_missing,
        "parsed_count": parsed_count,
        "parse_none_count": parse_none_count,
        "parsed_relation_type_counts": dict(sorted(parsed_relation_counts.items())),
        "diagnostics_status_counts": dict(sorted(diag_status_counts.items())),
        "diagnostics_relation_type_counts": dict(sorted(diag_relation_counts.items())),
        "ambiguity_count": ambiguity_count,
        "relation_type_match_count": rel_match,
        "relation_type_mismatch_count": rel_mismatch,
        "expected_status_match_count": status_match,
        "expected_status_mismatch_count": status_mismatch,
        "unsupported_or_deferred_count": unsupported_or_deferred,
    }
    return {"summary": summary, "cases": rows}


def _print_summary(summary: dict[str, Any]) -> None:
    print("[object seed diagnostics summary]")
    for k in [
        "total_cases",
        "evaluated_cases",
        "skipped_missing_metadata",
        "parsed_count",
        "parse_none_count",
        "ambiguity_count",
        "relation_type_match_count",
        "relation_type_mismatch_count",
        "expected_status_match_count",
        "expected_status_mismatch_count",
        "unsupported_or_deferred_count",
    ]:
        print(f"{k}: {summary[k]}")
    for key in ["parsed_relation_type_counts", "diagnostics_status_counts", "diagnostics_relation_type_counts"]:
        print(f"{key}:")
        for kk, vv in summary[key].items():
            print(f"  - {kk}: {vv}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Object seed graph-query diagnostics runner (metadata-only, opt-in).")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--synthetic-elements", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    out = run_diagnostics(Path(args.cases), Path(args.synthetic_elements), strict=args.strict)
    _print_summary(out["summary"])

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"wrote json artifact: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
