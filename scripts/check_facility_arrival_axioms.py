#!/usr/bin/env python3
"""Independently enforce the exact zero-axiom budget for FacilityArrival.lean."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

EXPECTED_THEOREMS = [
    "ScenarioContracts.facility_operational_transition_preserves_clinical",
    "ScenarioContracts.facility_operational_action_has_no_source_binding",
    "ScenarioContracts.facility_operational_action_has_zero_clinical_points",
    "ScenarioContracts.facility_wit_transition_preserves_clinical_score",
    "ScenarioContracts.facility_wit_observation_has_no_clinical_directive",
    "ScenarioContracts.facility_hidden_findings_before_diagnostics_are_empty",
    "ScenarioContracts.facility_diagnostics_ready_reveals_exact_hidden_findings",
    "ScenarioContracts.facility_timeout_event_maps_to_timeout_terminal",
    "ScenarioContracts.facility_unsafe_event_maps_to_failed_terminal",
    "ScenarioContracts.facility_handoff_event_maps_to_completed_terminal",
    "ScenarioContracts.facility_production_training_prohibits_patient_care",
    "ScenarioContracts.facility_operational_replay_preserves_clinical",
]
EXPECTED_AXIOMS = {name: [] for name in EXPECTED_THEOREMS}
FORBIDDEN_DEPENDENCIES = [
    "sorryAx",
    "Classical.choice",
    "Quot.sound",
    "Lean.trustCompiler",
    "Lean.ofReduceBool",
]
NO_AXIOMS = "does not depend on any axioms"
WITH_AXIOMS = re.compile(r"^depends on axioms:\s*\[([^\]]*)\]\s*$", re.IGNORECASE)


def _split_theorem_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("'"):
        closing = stripped.find("'", 1)
        if closing < 0:
            return None
        name = stripped[1:closing]
        rest = stripped[closing + 1 :].strip()
    else:
        pieces = stripped.split(maxsplit=1)
        if len(pieces) != 2:
            return None
        name, rest = pieces
    if not name.startswith("ScenarioContracts."):
        return None
    return name, rest


def parse_axiom_log(text: str) -> tuple[dict[str, list[str]], list[str]]:
    observed: dict[str, list[str]] = {}
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        parsed = _split_theorem_line(line)
        if parsed is None:
            folded = line.casefold()
            if "ScenarioContracts." in line and (
                "depends on axioms" in folded or "does not depend on any axioms" in folded
            ):
                errors.append(f"malformed theorem audit line:{line_number}")
            continue
        name, rest = parsed
        if rest.casefold() == NO_AXIOMS:
            axioms: list[str] = []
        else:
            match = WITH_AXIOMS.match(rest)
            if not match:
                errors.append(f"malformed theorem audit result:{name}")
                continue
            raw = match.group(1).strip()
            axioms = [] if not raw else [item.strip() for item in raw.split(",") if item.strip()]
        if name in observed:
            errors.append(f"duplicate theorem audit entry:{name}")
            continue
        observed[name] = axioms
    return observed, errors


def validate(log_text: str, manifest: dict) -> dict:
    errors: list[str] = []
    if manifest.get("required_theorems") != EXPECTED_THEOREMS:
        errors.append("manifest theorem inventory differs from independent checker policy")
    if manifest.get("per_theorem_axioms") != EXPECTED_AXIOMS:
        errors.append("manifest axiom budget differs from independent zero-axiom policy")
    if manifest.get("forbidden_dependencies") != FORBIDDEN_DEPENDENCIES:
        errors.append("manifest forbidden dependency policy differs")
    if manifest.get("module") != "ScenarioContracts.FacilityArrival":
        errors.append("manifest module differs")
    if manifest.get("formal_root_module") != "ScenarioContracts":
        errors.append("manifest root module differs")

    observed, parse_errors = parse_axiom_log(log_text)
    errors.extend(parse_errors)
    expected_set = set(EXPECTED_THEOREMS)
    observed_set = set(observed)
    for theorem in sorted(expected_set - observed_set):
        errors.append(f"theorem missing:{theorem}")
    for theorem in sorted(observed_set - expected_set):
        errors.append(f"unexpected theorem audit entry:{theorem}")
    for theorem in EXPECTED_THEOREMS:
        if theorem in observed and observed[theorem] != []:
            errors.append(f"axiom budget mismatch:{theorem}:{','.join(observed[theorem])}")

    folded = log_text.casefold()
    for dependency in FORBIDDEN_DEPENDENCIES:
        if dependency.casefold() in folded:
            errors.append(f"forbidden dependency:{dependency}")

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "policy": "independently encoded exact zero-axiom budget",
        "theorems_expected": len(EXPECTED_THEOREMS),
        "theorems_observed": len(observed),
        "per_theorem_axioms": observed,
        "errors": sorted(set(errors)),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--manifest", default="formal/FACILITY_ARRIVAL_TRUST_MANIFEST.json")
    parser.add_argument("--output", default="reports/facility-arrival-axiom-check.json")
    args = parser.parse_args(argv)
    log_text = Path(args.log).read_text(encoding="utf-8", errors="replace")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = validate(log_text, manifest)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
