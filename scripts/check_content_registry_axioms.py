#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

EXPECTED_THEOREMS = [
    "ScenarioContracts.generated_content_cannot_define_clinical_rule",
    "ScenarioContracts.generated_content_cannot_define_scoring_truth",
    "ScenarioContracts.generated_content_cannot_define_physiology",
    "ScenarioContracts.supporting_evidence_cannot_define_clinical_rule",
    "ScenarioContracts.supporting_evidence_cannot_define_scoring_truth",
    "ScenarioContracts.capability_inclusion_reflexive",
    "ScenarioContracts.capability_inclusion_transitive",
    "ScenarioContracts.admitted_claim_has_identity",
    "ScenarioContracts.admitted_claim_has_entailment",
    "ScenarioContracts.admitted_claim_has_contradiction_clearance",
    "ScenarioContracts.admitted_claim_has_human_review",
    "ScenarioContracts.admitted_claim_has_authority_permission",
    "ScenarioContracts.admitted_import_has_integrity",
    "ScenarioContracts.admitted_import_clears_public_boundary",
    "ScenarioContracts.admitted_import_preserves_authority",
    "ScenarioContracts.admitted_import_resolves_references",
    "ScenarioContracts.admitted_import_is_staging_only",
    "ScenarioContracts.staged_content_cannot_activate",
    "ScenarioContracts.activated_content_has_compatibility",
    "ScenarioContracts.activated_content_has_independent_check",
    "ScenarioContracts.activated_content_has_human_review",
    "ScenarioContracts.activated_content_preserves_authority",
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
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2:
            return None
        name, rest = parts
    if not name.startswith("ScenarioContracts."):
        return None
    return name, rest


def parse_axiom_log(text: str) -> tuple[dict[str, list[str]], list[str]]:
    observed: dict[str, list[str]] = {}
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        parsed = _split_theorem_line(line)
        if parsed is None:
            if "ScenarioContracts." in line and (
                "depends on axioms" in line.casefold()
                or "does not depend on any axioms" in line.casefold()
            ):
                errors.append(f"malformed theorem audit line:{line_number}")
            continue
        name, rest = parsed
        rest_folded = rest.casefold()
        if rest_folded == NO_AXIOMS:
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

    manifest_theorems = manifest.get("required_theorems")
    if manifest_theorems != EXPECTED_THEOREMS:
        errors.append("manifest theorem inventory differs from independent checker policy")

    manifest_axioms = manifest.get("per_theorem_axioms")
    if manifest_axioms != EXPECTED_AXIOMS:
        errors.append("manifest axiom budget differs from independent zero-axiom policy")

    if manifest.get("authority_policy_model") != "closed-total-boolean-function-with-explicit-constructor-cases":
        errors.append("manifest authority policy model differs from independent checker policy")
    if manifest.get("proof_mode_for_capability_denials") != "definitional-equality-rfl":
        errors.append("manifest proof mode differs from independent checker policy")

    manifest_forbidden = manifest.get("forbidden_dependencies")
    if manifest_forbidden != FORBIDDEN_DEPENDENCIES:
        errors.append("manifest forbidden dependency policy differs from independent checker policy")

    observed, parse_errors = parse_axiom_log(log_text)
    errors.extend(parse_errors)

    expected_set = set(EXPECTED_THEOREMS)
    observed_set = set(observed)
    for missing in sorted(expected_set - observed_set):
        errors.append(f"theorem missing:{missing}")
    for unexpected in sorted(observed_set - expected_set):
        errors.append(f"unexpected theorem audit entry:{unexpected}")

    for theorem in EXPECTED_THEOREMS:
        if theorem not in observed:
            continue
        actual = observed[theorem]
        expected = EXPECTED_AXIOMS[theorem]
        if actual != expected:
            rendered = ",".join(actual) if actual else "none"
            errors.append(f"axiom budget mismatch:{theorem}:{rendered}")

    folded = log_text.casefold()
    for forbidden in FORBIDDEN_DEPENDENCIES:
        if forbidden.casefold() in folded:
            errors.append(f"forbidden dependency:{forbidden}")

    return {
        "schema_version": "1.1.0",
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
    parser.add_argument(
        "--manifest", default="formal/CONTENT_REGISTRY_TRUST_MANIFEST.json"
    )
    args = parser.parse_args(argv)

    log_text = Path(args.log).read_text(encoding="utf-8", errors="replace")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    report = validate(log_text, manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
