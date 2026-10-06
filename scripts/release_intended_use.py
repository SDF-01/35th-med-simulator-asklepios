#!/usr/bin/env python3
"""Validate the intended-use split between healthcare simulation and patient care."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from release_graph_core import load_graph, read_json, write_json
from release_policy_common import load_release_json, unique_nonempty_strings
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

POLICY = "config/release/SIMULATION_INTENDED_USE.json"
OUTPUT = Path("reports/release-intended-use.json")


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        policy = load_release_json(root, POLICY, errors)
        graph = load_graph(root)
        if policy is None:
            raise ValueError("intended-use policy missing")

        require(policy.get("schema_version") == "1.0.0", "intended-use schema differs")
        require(policy.get("product_scope") == "PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE", "product scope differs")
        permitted_use = policy.get("permitted_use", {})
        simulation = permitted_use.get("healthcare_simulation_training", {})
        require(simulation.get("status") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "healthcare simulation use is not explicitly permitted")
        simulated_care = permitted_use.get("simulated_patient_care_workflows", {})
        require(simulated_care.get("status") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "simulated patient-care workflows are not explicitly permitted")
        require(unique_nonempty_strings(simulated_care.get("conditions")), "simulated patient-care workflow conditions invalid")
        for key in ("permitted_users", "permitted_environments", "scenario_classes", "conditions"):
            require(unique_nonempty_strings(simulation.get(key)), f"simulation intended-use list invalid:{key}")

        prohibited = policy.get("prohibited_use", {})
        for key in (
            "direct_patient_care",
            "clinical_decision_support",
            "real_patient_diagnosis_or_treatment",
            "autonomous_clinical_action",
            "time_critical_real_patient_direction",
        ):
            require(prohibited.get(key) == "PROHIBITED", f"prohibited use boundary differs:{key}")

        restricted = policy.get("restricted_use", {})
        require(restricted.get("generated_unreviewed_variants", {}).get("status") == "RESEARCH_SANDBOX_ONLY", "unreviewed variants escaped the research sandbox")
        require(restricted.get("learner_high_stakes_credentialing", {}).get("status") == "NOT_AUTHORIZED_WITHOUT_EXTERNAL_VALIDATION", "high-stakes assessment boundary changed")

        cycle = policy.get("required_learning_cycle", {})
        for key in (
            "measurable_objectives",
            "prebrief",
            "facilitation_plan",
            "learner_interaction",
            "planned_debrief_or_guided_reflection",
            "evaluation_or_feedback_plan",
        ):
            require(cycle.get(key) is True, f"required simulation learning-cycle element disabled:{key}")

        data = policy.get("data_boundary", {})
        require(data.get("real_patient_data") == "PROHIBITED_BY_DEFAULT", "real-patient-data boundary changed")
        require("synthetic_data" in data.get("allowed_data", []), "synthetic-data route missing")
        require(data.get("secrets_or_credentials_in_scenario_artifacts") == "PROHIBITED", "credential boundary changed")

        claim = policy.get("claim_boundary", {})
        require(claim.get("software_readiness_claim") == "PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE_READY", "simulation software readiness claim differs")
        require(claim.get("clinical_effectiveness_claim") == "NOT_ESTABLISHED_BY_SOFTWARE_RELEASE", "clinical effectiveness was overclaimed")
        require(claim.get("program_accreditation_claim") == "NOT_MADE", "program accreditation was overclaimed")
        require(claim.get("direct_patient_care_authority") == "NOT_GRANTED", "patient-care authority was granted")

        truth = graph.get("truth_boundaries", {})
        require(truth.get("healthcare_simulation_training") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "graph simulation-use boundary differs")
        require(truth.get("simulated_patient_care_workflows") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "graph simulated patient-care workflow boundary differs")
        require(truth.get("direct_patient_care") == "PROHIBITED", "graph direct-patient-care boundary differs")
        require(truth.get("clinical_decision_support") == "PROHIBITED", "graph CDS boundary differs")
        require(truth.get("patient_care_use") == "PROHIBITED", "legacy graph patient-care boundary changed")

        for relative in ("config/facility-arrival/ASK-D-001.json", "config/facility-decision/ASK-D-001.json"):
            authority = read_json(root / relative).get("authority", {})
            require(authority.get("patient_care_use") == "PROHIBITED", f"scenario patient-care boundary changed:{relative}")

        readme = (root / "README.md").read_text(encoding="utf-8")
        require("Healthcare simulation and training use is permitted within the validated release scope." in readme, "README simulation-use statement missing")
        require("Simulated patient-care workflows are permitted within the validated simulation scope." in readme, "README simulated patient-care workflow statement missing")
        require("Direct patient care and clinical decision support remain prohibited." in readme, "README direct-patient-care prohibition missing")

        classification = PASS if not errors else FAIL
        return {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "checks": checks,
            "intended_use": "HEALTHCARE_SIMULATION_AND_TRAINING",
            "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "direct_patient_care": "PROHIBITED",
            "clinical_decision_support": "PROHIBITED",
            "errors": sorted(set(errors)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.0.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "checks": checks,
            "errors": sorted(set(errors + [f"{type(exc).__name__}:{exc}"])),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = validate(args.repo)
    write_json(args.repo.resolve() / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
