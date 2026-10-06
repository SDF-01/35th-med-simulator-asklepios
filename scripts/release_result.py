#!/usr/bin/env python3
"""Shared four-state result vocabulary for Project Asklepios release assurance."""
from __future__ import annotations

from typing import Any, Iterable

PASS = "PASS"
EXPECTED_REJECTION = "EXPECTED_REJECTION"
FAIL = "FAIL"
INTERNAL_ERROR = "INTERNAL_ERROR"
VALID_CLASSIFICATIONS = (PASS, EXPECTED_REJECTION, FAIL, INTERNAL_ERROR)


def require_classification(value: str) -> str:
    if value not in VALID_CLASSIFICATIONS:
        raise ValueError(f"unsupported classification:{value}")
    return value


def case_result(
    case_id: str,
    classification: str,
    *,
    errors: Iterable[str] | None = None,
    **details: Any,
) -> dict[str, Any]:
    """Create one normalized assurance case result.

    PASS means the unmodified subject behaved correctly.
    EXPECTED_REJECTION means a deliberate attack was rejected correctly.
    FAIL means a real contract failure or an accepted attack.
    INTERNAL_ERROR means the assurance harness itself could not form a verdict.
    """
    classification = require_classification(classification)
    payload: dict[str, Any] = {
        "case_id": case_id,
        "classification": classification,
        "status": classification,
        "pass": classification in {PASS, EXPECTED_REJECTION},
        "errors": sorted({str(item) for item in (errors or []) if str(item)}),
    }
    payload.update(details)
    return payload


def suite_classification(results: Iterable[dict[str, Any]]) -> str:
    values = [str(item.get("classification", INTERNAL_ERROR)) for item in results]
    if any(value == INTERNAL_ERROR for value in values):
        return INTERNAL_ERROR
    if any(value == FAIL for value in values):
        return FAIL
    return PASS


def exit_code(classification: str) -> int:
    classification = require_classification(classification)
    if classification in {PASS, EXPECTED_REJECTION}:
        return 0
    if classification == INTERNAL_ERROR:
        return 4
    return 3


def finalize_adversarial_report(
    report: dict[str, Any],
    *,
    baseline_case_ids: Iterable[str] = ("baseline",),
) -> dict[str, Any]:
    """Attach the four-state vocabulary to a legacy adversarial report.

    Legacy suites historically used ``pass: true`` for both an intact baseline
    and a deliberately damaged input that was correctly rejected.  This helper
    preserves the Boolean compatibility field while making the distinction
    explicit and treating harness failures as INTERNAL_ERROR rather than a
    successful rejection.
    """
    baseline = {str(item).lower() for item in baseline_case_ids}
    normalized: list[dict[str, Any]] = []
    for index, original in enumerate(report.get("results", [])):
        item = dict(original) if isinstance(original, dict) else {
            "case_id": f"case-{index + 1}",
            "pass": False,
            "errors": ["result entry is not an object"],
        }
        case_id = str(item.get("case_id", f"case-{index + 1}"))
        lower = case_id.lower()
        expected_pass = item.get("expected_pass")
        is_baseline = (
            lower in baseline
            or lower.startswith("baseline")
            or lower.startswith("canonical_graph_baseline")
            or expected_pass is True
        )
        explicit = item.get("classification")
        expected = str(item.get("expected", "")).upper()
        # A deliberate crash challenge is a meta-test: the observed subject
        # outcome must remain INTERNAL_ERROR, while the outer test passes only
        # when that internal error was expected and was not miscounted as a
        # semantic rejection.  Preserve the observation separately so evidence
        # consumers can distinguish it from an ordinary PASS.
        if expected == INTERNAL_ERROR and explicit == INTERNAL_ERROR and bool(item.get("pass", False)):
            item["observed_classification"] = INTERNAL_ERROR
            classification = PASS
        elif explicit in VALID_CLASSIFICATIONS:
            classification = str(explicit)
        else:
            internal_markers = [
                item.get("checker_status"),
                item.get("observed_classification"),
                item.get("python_classification"),
                item.get("node_classification"),
            ]
            internal = any(str(value).upper() == INTERNAL_ERROR for value in internal_markers)
            passed = bool(item.get("pass", False))
            if internal:
                classification = INTERNAL_ERROR
            elif not passed:
                classification = FAIL
            elif is_baseline:
                classification = PASS
            else:
                classification = EXPECTED_REJECTION
        item["classification"] = classification
        item["status"] = classification
        item["pass"] = classification in {PASS, EXPECTED_REJECTION}
        normalized.append(item)
    report["results"] = normalized
    classification = suite_classification(normalized)
    # Suites without result rows retain their old top-level verdict.
    if not normalized:
        old = str(report.get("classification", report.get("status", FAIL))).upper()
        classification = old if old in VALID_CLASSIFICATIONS else (PASS if old == PASS else FAIL)
    report["classification"] = classification
    report["status"] = classification
    return report
