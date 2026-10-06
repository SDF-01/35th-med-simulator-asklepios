#!/usr/bin/env python3
"""Adversarial tests for source/final technical-debt evidence separation."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from release_graph_core import read_json, write_json
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification
from release_technical_debt import CRITICAL_FINAL_EVIDENCE, PERMITTED_CLAIM, validate

Mutator = Callable[[Path], None]


def _isolated_environment() -> dict[str, str]:
    """Prevent an outer release graph from redirecting nested fixture evidence."""
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("ASKLEPIOS_RELEASE_"):
            environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _copy(root: Path, destination: Path) -> None:
    shutil.copytree(
        root,
        destination,
        ignore=shutil.ignore_patterns(".git", "node_modules", ".asklepios", "dist", "__pycache__", "*.pyc"),
    )


def _fixture(root: Path) -> tuple[Path, list[str], dict[str, str]]:
    """Build one receipt fixture from the current ratcheted evidence contract.

    The older harness duplicated a hand-maintained stage list.  When the release
    added stakeholder and scenario-science evidence stages, that local list could
    drift from the compiled technical-debt floor.  The fixture now derives its
    complete receipt inventory from the current reviewed register and requires it
    to equal the independently compiled floor before any mutation is scheduled.
    """
    package = read_json(root / "package.json")
    production_register = read_json(root / "config/release/TECHNICAL_DEBT_REGISTER.json")
    production_contract = production_register.get("final_evidence_contract", {})
    required_receipts = production_contract.get("required_stage_receipts")
    terminal_stage = production_contract.get("terminal_evidence_stage")
    if not isinstance(required_receipts, list) or not required_receipts:
        raise RuntimeError("production technical-debt receipt inventory missing")
    if any(not isinstance(stage_id, str) or not stage_id for stage_id in required_receipts):
        raise RuntimeError("production technical-debt receipt inventory malformed")
    if len(required_receipts) != len(set(required_receipts)):
        raise RuntimeError("production technical-debt receipt inventory contains duplicates")
    if set(required_receipts) != set(CRITICAL_FINAL_EVIDENCE):
        raise RuntimeError("production technical-debt receipt inventory differs from compiled floor")
    if terminal_stage != "final.decision-evidence" or required_receipts[-1] != terminal_stage:
        raise RuntimeError("production technical-debt terminal receipt is not the final chain stage")

    stage_specs: list[tuple[str, str, list[str]]] = []
    output_by_stage: dict[str, str] = {}
    previous: str | None = None
    for index, stage_id in enumerate(required_receipts):
        safe_id = "".join(character if character.isalnum() else "-" for character in stage_id)
        output = f"reports/debt-fixture/{index:02d}-{safe_id}.json"
        needs = [] if previous is None else [previous]
        stage_specs.append((stage_id, output, needs))
        output_by_stage[stage_id] = output
        previous = stage_id

    scripts = dict(package.get("scripts", {}))
    for index, (_stage_id, output, _needs) in enumerate(stage_specs):
        name = f"fixture:evidence:{index}"
        scripts[name] = (
            "node -e \"const fs=require('fs');fs.mkdirSync('reports/debt-fixture',{recursive:true});"
            f"fs.writeFileSync('{output}',JSON.stringify({{classification:'PASS'}})+'\\n')\""
        )
    package["scripts"] = scripts
    write_json(root / "package.json", package)

    graph = {
        "schema_version": "1.0.0",
        "graph_id": "asklepios-debt-fixture-v2",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "release_candidate": "technical debt evidence fixture derived from current receipt floor",
        "production_designation": "NOT_GRANTED",
        "truth_boundaries": {
            "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "direct_patient_care": "PROHIBITED",
            "clinical_decision_support": "PROHIBITED",
            "patient_care_use": "PROHIBITED",
            "simulation_logical_timing": "VALIDATED_FOR_DETERMINISTIC_SIMULATION",
            "clinical_operational_timing": "NOT_CALIBRATED",
            "clinical_timing_transferability": "NOT_ESTABLISHED",
            "operational_timing": "NOT_CALIBRATED",
            "production_ready": False,
            "concrete_treatments_admitted": 0,
        },
        "input_sets": {
            "policy-source": {
                "include": ["config/release/TECHNICAL_DEBT_REGISTER.json", "package.json", "server/hubSecurity.ts"],
                "exclude": [],
                "files": {},
            }
        },
        "managed_package_scripts": {
            f"fixture:evidence:{index}": scripts[f"fixture:evidence:{index}"]
            for index in range(len(stage_specs))
        },
        "integrations": {},
        "stages": [
            {
                "id": stage_id,
                "command": ["npm", "run", f"fixture:evidence:{index}"],
                "needs": needs,
                "input_sets": ["policy-source"],
                "outputs": [output],
                "failure_classification": "FAIL",
                "read_only": False,
            }
            for index, (stage_id, output, needs) in enumerate(stage_specs)
        ],
        "targets": {"fixture": {"terminal_stages": [terminal_stage]}},
    }
    write_json(root / "config/release/RELEASE_GRAPH.json", graph)
    register = {
        "schema_version": "1.0.0",
        "register_id": "asklepios-release-debt-v1",
        "absolute_debt_free_claim_permitted": False,
        "states": ["CLOSED", "ACCEPTED_RISK", "OUT_OF_SCOPE"],
        "permitted_release_claim": PERMITTED_CLAIM,
        "entries": [
            {
                "debt_id": "TD-FIXTURE-001",
                "title": "Fixture source evidence",
                "closure": "Bound to source and runtime evidence.",
                "state": "CLOSED",
                "release_blocker": True,
                "evidence_stages": [required_receipts[0], "hub.runtime-smoke"],
            },
            {
                "debt_id": "TD-FIXTURE-002",
                "title": "Fixture final evidence",
                "closure": "Bound to the final decision evidence chain.",
                "state": "CLOSED",
                "release_blocker": True,
                "evidence_stages": [terminal_stage],
            },
        ],
        "final_evidence_contract": {
            "required_stage_receipts": required_receipts,
            "terminal_evidence_stage": terminal_stage,
            "requires_current_graph_hash": True,
            "requires_current_output_hashes": True,
            "stale_committed_reports_may_satisfy_gate": False,
        },
    }
    write_json(root / "config/release/TECHNICAL_DEBT_REGISTER.json", register)
    subprocess.run(
        ["python3", "scripts/lock_release_graph.py", "--repo", "."],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
        env=_isolated_environment(),
    )
    return root, required_receipts, output_by_stage


def _run_receipts(root: Path) -> None:
    completed = subprocess.run(
        ["python3", "scripts/run_release_graph.py", "--repo", ".", "--target", "fixture", "--no-reuse"],
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
        env=_isolated_environment(),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"fixture receipt generation failed:{completed.stdout[-2000:]}:{completed.stderr[-1000:]}")


def _edit(path: Path, mutate: Callable[[dict], None]) -> None:
    value = read_json(path)
    mutate(value)
    write_json(path, value)


def run(root: Path) -> dict:
    results = []
    # Construct and attest the hermetic fixture exactly once.  Every case gets
    # an independent copy, but the expensive 40-stage receipt chain is produced
    # only once.  This keeps the suite exhaustive without turning it into a
    # platform-dependent timeout risk.
    with tempfile.TemporaryDirectory(prefix="asklepios-debt-template-") as template_directory:
        template = Path(template_directory) / "repo"
        _copy(root, template)
        _fixture_root, required_receipts, output_by_stage = _fixture(template)
        _run_receipts(template)
        receipt_root = Path(".asklepios/release-receipts/asklepios-debt-fixture-v2")

        cases: list[tuple[str, str, Mutator | None, str | None, bool]] = [
            ("source_baseline_without_receipts", "source", None, None, False),
            ("final_baseline_authenticated", "final", None, None, True),
            ("absolute_debt_free_claim_rejected", "source", lambda r: _edit(r / "config/release/TECHNICAL_DEBT_REGISTER.json", lambda d: d.__setitem__("absolute_debt_free_claim_permitted", True)), "absolute debt-free claim was enabled", False),
            ("open_release_blocker_rejected", "source", lambda r: _edit(r / "config/release/TECHNICAL_DEBT_REGISTER.json", lambda d: d["entries"][0].__setitem__("state", "ACCEPTED_RISK")), "release-blocking technical debt remains", False),
            ("duplicate_debt_id_rejected", "source", lambda r: _edit(r / "config/release/TECHNICAL_DEBT_REGISTER.json", lambda d: d["entries"][1].__setitem__("debt_id", d["entries"][0]["debt_id"])), "technical-debt ID duplicated", False),
            ("missing_evidence_stage_rejected", "source", lambda r: _edit(r / "config/release/TECHNICAL_DEBT_REGISTER.json", lambda d: d["entries"][0].__setitem__("evidence_stages", ["missing.stage"])), "technical-debt evidence stage absent", False),
            ("terminal_stage_changed_rejected", "source", lambda r: _edit(r / "config/release/TECHNICAL_DEBT_REGISTER.json", lambda d: d["final_evidence_contract"].__setitem__("terminal_evidence_stage", "hub.runtime-smoke")), "technical-debt terminal evidence stage differs", False),
        ]

        # Ratchet every required receipt in both source-policy and final-evidence
        # modes.  A newly added receipt automatically gains both regression cases;
        # no second hand-maintained case list can drift behind the release policy.
        for stage_id in required_receipts:
            token = "".join(character if character.isalnum() else "_" for character in stage_id)
            cases.append((
                f"required_receipt_{token}_cannot_be_removed",
                "source",
                lambda r, current=stage_id: _edit(
                    r / "config/release/TECHNICAL_DEBT_REGISTER.json",
                    lambda d, selected=current: d["final_evidence_contract"]["required_stage_receipts"].remove(selected),
                ),
                f"technical-debt critical final evidence missing:{stage_id}",
                False,
            ))
            cases.append((
                f"final_receipt_{token}_must_exist",
                "final",
                lambda r, current=stage_id: (r / receipt_root / f"{current}.json").unlink(),
                f"required evidence receipt invalid or missing:{stage_id}",
                True,
            ))

        hub_output = output_by_stage["hub.runtime-smoke"]
        cases.extend([
            ("forged_runtime_receipt_rejected", "final", lambda r: _edit(r / receipt_root / "hub.runtime-smoke.json", lambda d: d.__setitem__("classification", "FAIL")), "required evidence receipt invalid or missing:hub.runtime-smoke", True),
            ("stale_runtime_output_rejected", "final", lambda r: (r / hub_output).write_text('{"classification":"FAIL"}\n', encoding="utf-8"), "required evidence receipt differs:hub.runtime-smoke:output_root_sha256", True),
            ("changed_hub_input_invalidates_evidence", "final", lambda r: (r / "server/hubSecurity.ts").write_text((r / "server/hubSecurity.ts").read_text(encoding="utf-8") + "\n// mutation\n", encoding="utf-8"), "input set hash differs:policy-source", True),
        ])

        for case_id, mode, mutator, required, need_receipts in cases:
            print(f"START_CASE:{case_id}", flush=True)
            started = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="asklepios-debt-test-") as temporary:
                repo = Path(temporary) / "repo"
                shutil.copytree(template, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                if mutator:
                    mutator(repo)
                explicit_receipts = repo / receipt_root if need_receipts else None
                observed = validate(repo, mode, explicit_receipts)
                errors = observed.get("errors", [])
                if mutator is None:
                    passed = observed.get("classification") == PASS
                    classification = PASS if passed else FAIL
                else:
                    passed = observed.get("classification") == FAIL and required is not None and any(required in error for error in errors)
                    classification = EXPECTED_REJECTION if passed else FAIL
                result = case_result(
                    case_id,
                    classification,
                    errors=[] if passed else errors,
                    required_error=required,
                    observed_classification=observed.get("classification"),
                    mode=mode,
                    duration_ms=int(round((time.monotonic() - started) * 1000)),
                )
                results.append(result)
            print(f"END_CASE:{case_id}:{classification}:{result['duration_ms']}", flush=True)

    classification = suite_classification(results)
    expected_rejections = sum(1 for result in results if result.get("classification") == EXPECTED_REJECTION)
    return {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "fixture_profile": "CURRENT_COMPILED_RECEIPT_FLOOR_DERIVED_CHAIN_V1",
        "required_receipt_count": len(required_receipts),
        "source_receipt_removal_attacks": len(required_receipts),
        "final_missing_receipt_attacks": len(required_receipts),
        "cases": len(results),
        "expected_rejections": expected_rejections,
        "accepted_regressions": 0 if classification == PASS else sum(1 for result in results if not result.get("pass")),
        "results": results,
        "errors": [] if classification == PASS else ["technical-debt mutation suite failed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/release-technical-debt-mutations.json"))
    args = parser.parse_args()
    root = args.repo.resolve()
    report = run(root)
    write_json(root / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
