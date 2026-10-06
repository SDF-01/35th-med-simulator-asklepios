#!/usr/bin/env python3
"""Measure ordered interaction coverage using independently replayed facility sessions."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

from build_facility_arrival_example import (
    BINDING_PATH,
    SPEC_PATH,
    build_claim_ledger,
    build_session,
    reconstruct_source_snapshot,
)

REPORT = Path("reports/facility-arrival-sequence-assurance.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_sequence(session: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for transition in session["transitions"]:
        if transition["kind"] == "system_event":
            values.append(transition["event_id"])
        else:
            values.append(transition["action_id"])
    terminal = session["final_state"]["terminal_status"]
    if terminal != "active":
        values.append(terminal)
    return values


def contains_ordered(sequence: list[str], pattern: tuple[str, ...]) -> bool:
    cursor = 0
    for value in sequence:
        if cursor < len(pattern) and value == pattern[cursor]:
            cursor += 1
    return cursor == len(pattern)


def successful_cases() -> list[list[str]]:
    prefix = ["receive_handoff", "primary_assessment"]
    flexible = ["monitor_vitals", "differential", "order_imaging", "order_labs"]
    suffix = [
        "pain_management",
        "confirm_surge_roles",
        "documentation",
        "wait_for_diagnostics",
        "review_diagnostics",
        "escalation",
        "complete_handoff",
    ]
    cases = [prefix + list(order) + suffix for order in itertools.permutations(flexible)]
    cases.extend([
        prefix + [
            "pain_management", "monitor_vitals", "differential", "order_labs", "order_imaging",
            "documentation", "confirm_surge_roles", "wait_for_diagnostics", "review_diagnostics",
            "escalation", "complete_handoff",
        ],
        prefix + [
            "documentation", "order_imaging", "order_labs", "monitor_vitals", "differential",
            "pain_management", "confirm_surge_roles", "wait_for_diagnostics", "review_diagnostics",
            "escalation", "complete_handoff",
        ],
        prefix + [
            "monitor_vitals", "differential", "order_imaging", "order_labs", "pain_management",
            "confirm_surge_roles", "wait_for_diagnostics", "review_diagnostics", "documentation",
            "escalation", "complete_handoff",
        ],
    ])
    return cases


def required_pairs() -> list[tuple[str, str]]:
    return [
        ("prearrival_notice", "receive_handoff"),
        ("receive_handoff", "primary_assessment"),
        ("primary_assessment", "monitor_vitals"),
        ("primary_assessment", "differential"),
        ("primary_assessment", "order_imaging"),
        ("primary_assessment", "order_labs"),
        ("primary_assessment", "pain_management"),
        ("monitor_vitals", "differential"),
        ("differential", "monitor_vitals"),
        ("monitor_vitals", "pain_management"),
        ("pain_management", "monitor_vitals"),
        ("differential", "pain_management"),
        ("pain_management", "differential"),
        ("order_imaging", "order_labs"),
        ("order_labs", "order_imaging"),
        ("prearrival_notice", "second_casualty_inbound"),
        ("second_casualty_inbound", "confirm_surge_roles"),
        ("confirm_surge_roles", "documentation"),
        ("documentation", "confirm_surge_roles"),
        ("order_imaging", "documentation"),
        ("documentation", "order_imaging"),
        ("order_labs", "documentation"),
        ("documentation", "order_labs"),
        ("order_imaging", "diagnostics_ready"),
        ("order_labs", "diagnostics_ready"),
        ("diagnostics_ready", "review_diagnostics"),
        ("review_diagnostics", "escalation"),
        ("escalation", "complete_handoff"),
        ("documentation", "complete_handoff"),
        ("confirm_surge_roles", "complete_handoff"),
        ("discharge_without_workup", "failed"),
        ("remove_tourniquet", "failed"),
        ("wait_60", "timeout_reached"),
        ("timeout_reached", "timeout"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default=str(REPORT))
    args = parser.parse_args()
    repo = args.repo.resolve()
    spec = load(repo / SPEC_PATH)
    binding = load(repo / BINDING_PATH)
    source = reconstruct_source_snapshot(repo)
    ledger = build_claim_ledger(spec)

    sessions: list[dict[str, Any]] = []
    case_records: list[dict[str, Any]] = []
    failures: list[str] = []

    for index, sequence in enumerate(successful_cases(), start=1):
        try:
            session = build_session(spec, source, binding, ledger, sequence, f"coverage-success-{index:02d}")
            sessions.append(session)
            if session["final_state"]["terminal_status"] != "completed":
                failures.append(f"success case did not complete:{index}")
            case_records.append({
                "case_id": f"success-{index:02d}",
                "expected_terminal": "completed",
                "observed_terminal": session["final_state"]["terminal_status"],
                "sequence": semantic_sequence(session),
                "session_sha256": session["certificate"]["session_sha256"],
            })
        except Exception as exc:
            failures.append(f"success case exception:{index}:{exc}")

    terminal_cases = [
        ("unsafe-discharge", ["receive_handoff", "discharge_without_workup"], "failed"),
        ("unsafe-tourniquet", ["receive_handoff", "remove_tourniquet"], "failed"),
        ("source-timeout", ["wait_60"] * 20, "timeout"),
    ]
    for case_id, sequence, expected in terminal_cases:
        try:
            session = build_session(spec, source, binding, ledger, sequence, f"coverage-{case_id}")
            sessions.append(session)
            if session["final_state"]["terminal_status"] != expected:
                failures.append(f"terminal mismatch:{case_id}:{session['final_state']['terminal_status']}")
            case_records.append({
                "case_id": case_id,
                "expected_terminal": expected,
                "observed_terminal": session["final_state"]["terminal_status"],
                "sequence": semantic_sequence(session),
                "session_sha256": session["certificate"]["session_sha256"],
            })
        except Exception as exc:
            failures.append(f"terminal case exception:{case_id}:{exc}")

    sequences = [record["sequence"] for record in case_records]
    pairs = required_pairs()
    selected_triples = [tuple(value) for value in spec["sequence_assurance"]["selected_three_event_sequences"]]
    pair_results = {" -> ".join(pair): any(contains_ordered(sequence, pair) for sequence in sequences) for pair in pairs}
    triple_results = {" -> ".join(triple): any(contains_ordered(sequence, triple) for sequence in sequences) for triple in selected_triples}
    covered_pairs = sum(pair_results.values())
    covered_triples = sum(triple_results.values())
    second_casualty_transitions = [
        transition
        for session in sessions
        for transition in session["transitions"]
        if transition.get("event_id") == "second_casualty_inbound"
    ]
    properties = {
        "second_casualty_event_is_clock_due": bool(second_casualty_transitions) and all(
            transition["completed_at_seconds"] >= 240
            and transition.get("command_id") is None
            and transition.get("action_id") is None
            for transition in second_casualty_transitions
        ),
        "all_generated_success_paths_completed": all(
            record["observed_terminal"] == "completed" for record in case_records if record["case_id"].startswith("success-")
        ),
        "all_required_ordered_pairs_covered": covered_pairs == len(pairs),
        "all_selected_ordered_triples_covered": covered_triples == len(selected_triples),
        "unsafe_and_timeout_terminal_sequences_covered": all(
            any(record["case_id"] == case_id and record["observed_terminal"] == expected for record in case_records)
            for case_id, _sequence, expected in terminal_cases
        ),
    }
    if not all(properties.values()):
        failures.extend(name for name, passed in properties.items() if not passed)

    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not failures else "FAIL",
        "coverage_semantics": "ordered subsequence coverage over independently replayed valid traces",
        "case_count": len(case_records),
        "successful_completion_cases": sum(record["observed_terminal"] == "completed" for record in case_records),
        "terminal_failure_cases": sum(record["observed_terminal"] == "failed" for record in case_records),
        "timeout_cases": sum(record["observed_terminal"] == "timeout" for record in case_records),
        "required_ordered_pairs": len(pairs),
        "covered_ordered_pairs": covered_pairs,
        "pair_coverage_fraction": covered_pairs / len(pairs),
        "selected_ordered_triples": len(selected_triples),
        "covered_ordered_triples": covered_triples,
        "triple_coverage_fraction": covered_triples / len(selected_triples),
        "pair_results": pair_results,
        "triple_results": triple_results,
        "properties": properties,
        "failed_cases": failures,
        "cases": case_records,
    }
    output = repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "schema_version", "status", "case_count", "successful_completion_cases", "terminal_failure_cases",
        "timeout_cases", "required_ordered_pairs", "covered_ordered_pairs", "selected_ordered_triples",
        "covered_ordered_triples", "properties", "failed_cases",
    )}, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
