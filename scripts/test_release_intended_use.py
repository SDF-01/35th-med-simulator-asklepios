#!/usr/bin/env python3
"""Mutation tests for the healthcare-simulation intended-use boundary."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from release_intended_use import validate
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification

Mutator = Callable[[Path], None]


def edit_json(repo: Path, relative: str, fn: Callable[[dict], None]) -> None:
    path = repo / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    fn(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(root: Path) -> dict:
    cases: list[tuple[str, Mutator | None, str | None]] = [
        ("baseline", None, None),
        ("direct_patient_care_promoted", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["prohibited_use"].__setitem__("direct_patient_care", "PERMITTED")), "prohibited use boundary differs:direct_patient_care"),
        ("simulation_use_removed", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["permitted_use"]["healthcare_simulation_training"].__setitem__("status", "NOT_GRANTED")), "healthcare simulation use is not explicitly permitted"),
        ("simulated_patient_care_workflow_removed", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["permitted_use"]["simulated_patient_care_workflows"].__setitem__("status", "NOT_GRANTED")), "simulated patient-care workflows are not explicitly permitted"),
        ("debrief_disabled", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["required_learning_cycle"].__setitem__("planned_debrief_or_guided_reflection", False)), "required simulation learning-cycle element disabled"),
        ("unreviewed_variants_promoted", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["restricted_use"]["generated_unreviewed_variants"].__setitem__("status", "PRODUCTION")), "unreviewed variants escaped"),
        ("graph_direct_patient_care_promoted", lambda r: edit_json(r, "config/release/RELEASE_GRAPH.json", lambda d: d["truth_boundaries"].__setitem__("direct_patient_care", "PERMITTED")), "graph direct-patient-care boundary differs"),
        ("clinical_effectiveness_overclaimed", lambda r: edit_json(r, "config/release/SIMULATION_INTENDED_USE.json", lambda d: d["claim_boundary"].__setitem__("clinical_effectiveness_claim", "ESTABLISHED")), "clinical effectiveness was overclaimed"),
        ("readme_boundary_removed", lambda r: (r / "README.md").write_text((r / "README.md").read_text(encoding="utf-8").replace("Direct patient care and clinical decision support remain prohibited.", ""), encoding="utf-8"), "README direct-patient-care prohibition missing"),
        ("readme_simulated_care_scope_removed", lambda r: (r / "README.md").write_text((r / "README.md").read_text(encoding="utf-8").replace("Simulated patient-care workflows are permitted within the validated simulation scope.", ""), encoding="utf-8"), "README simulated patient-care workflow statement missing"),
    ]
    results = []
    for case_id, mutator, expected_error in cases:
        with tempfile.TemporaryDirectory(prefix="asklepios-intended-use-") as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(root, repo, ignore=shutil.ignore_patterns(".git", "node_modules", ".asklepios", "dist"))
            if mutator:
                mutator(repo)
            observed = validate(repo)
            errors = observed.get("errors", [])
            if mutator is None:
                ok = observed.get("classification") == PASS
                classification = PASS if ok else FAIL
            else:
                ok = observed.get("classification") == FAIL and expected_error is not None and any(expected_error in item for item in errors)
                classification = EXPECTED_REJECTION if ok else FAIL
            results.append(case_result(case_id, classification, errors=[] if ok else errors, observed_classification=observed.get("classification"), required_error=expected_error))
    classification = suite_classification(results)
    return {"schema_version":"1.0.0","classification":classification,"status":classification,"cases":len(results),"results":results,"errors":[] if classification == PASS else ["intended-use mutation suite failed"]}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,default=Path(".")); parser.add_argument("--json-output",type=Path,default=Path("reports/release-intended-use-mutations.json")); args=parser.parse_args()
    report=run(args.repo.resolve()); args.json_output.parent.mkdir(parents=True,exist_ok=True); (args.repo.resolve()/args.json_output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(report,indent=2,sort_keys=True)); return exit_code(report["classification"])

if __name__ == "__main__": raise SystemExit(main())
