#!/usr/bin/env python3
"""Adversarial tests for the graph-owned Facility Decision release boundary."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_facility_decision_release_static import validate
from release_graph_core import GRAPH_PATH, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, exit_code, suite_classification

OUTPUT = Path("reports/facility-decision-release-static-mutations.json")


def copy_repo(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git", ".lake", ".asklepios", "node_modules", "dist", "__pycache__", "*.pyc", "*.pyo",
        ),
    )


def replace(repo: Path, relative: str, old: str, new: str) -> None:
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"mutation marker absent:{relative}:{old[:120]}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def replace_last(repo: Path, relative: str, old: str, new: str) -> None:
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    index = text.rfind(old)
    if index < 0:
        raise RuntimeError(f"mutation marker absent:{relative}:{old[:120]}")
    path.write_text(text[:index] + new + text[index + len(old):], encoding="utf-8", newline="\n")


def mutate_json(repo: Path, relative: str, mutation: Callable[[dict], None]) -> None:
    path = repo / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def graph_stage(graph: dict, stage_id: str) -> dict:
    return next(stage for stage in graph["stages"] if stage["id"] == stage_id)


def decision_event(document: dict) -> dict:
    return next(item for item in document["operational_model"]["world_events"] if item.get("event_id") == "second_casualty_inbound")


def run_attack(
    source: Path,
    temp_root: Path,
    case_id: str,
    mutation: Callable[[Path], None],
    required_errors: Iterable[str],
) -> dict:
    candidate = temp_root / case_id
    copy_repo(source, candidate)
    try:
        mutation(candidate)
        report = validate(candidate)
        observed = [str(item) for item in report.get("errors", [])]
        missing = [marker for marker in required_errors if not any(marker in error for error in observed)]
        rejected = report.get("classification") == FAIL
        healthy = rejected and not missing
        return case_result(
            case_id,
            EXPECTED_REJECTION if healthy else FAIL,
            errors=[] if healthy else (["mutated release boundary was accepted"] if not rejected else []) + [f"required diagnostic missing:{item}" for item in missing],
            observed_classification=report.get("classification"),
            observed_errors=observed,
            required_errors=list(required_errors),
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = args.repo.resolve()

    baseline = validate(source)
    results = [case_result(
        "baseline",
        PASS if baseline.get("classification") == PASS else FAIL,
        errors=baseline.get("errors", []),
        observed_classification=baseline.get("classification"),
    )]

    with tempfile.TemporaryDirectory(prefix="asklepios-decision-static-attacks-") as directory:
        root = Path(directory)
        attacks: list[tuple[str, Callable[[Path], None], list[str]]] = [
            (
                "graph-patient-care-boundary-promoted",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph["truth_boundaries"].__setitem__("patient_care_use", "AUTHORIZED")),
                ["graph patient-care boundary changed"],
            ),
            (
                "graph-production-ready-promoted",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph["truth_boundaries"].__setitem__("production_ready", True)),
                ["graph production-ready flag was promoted"],
            ),
            (
                "decision-profile-patient-care-promoted",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: doc["authority"].__setitem__("patient_care_use", "AUTHORIZED")),
                ["decision profile patient-care boundary changed"],
            ),
            (
                "concrete-treatment-activation-promoted",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: doc["authority"].__setitem__("concrete_treatment_activation", True)),
                ["decision profile concrete treatment activation changed"],
            ),
            (
                "calibration-record-missing",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: doc["operational_model"].__setitem__("world_events", [item for item in doc["operational_model"]["world_events"] if item.get("event_id") != "second_casualty_inbound"])),
                ["calibration record missing:second_casualty_inbound"],
            ),
            (
                "calibration-time-changed",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("at_elapsed_seconds", 241)),
                ["decision calibration time changed:second_casualty_inbound:241"],
            ),
            (
                "calibration-status-promoted",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("calibration_status", "CALIBRATED")),
                ["decision calibration status changed:second_casualty_inbound:CALIBRATED"],
            ),
            (
                "calibration-note-removed",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("note", "Clock event.")),
                ["decision exercise-assumption note missing:second_casualty_inbound"],
            ),
            (
                "source-preflight-bypassed",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "decision.typecheck").__setitem__("needs", ["decision.release-validator-attacks"])),
                ["decision runtime bypasses source preflight"],
            ),
            (
                "static-validator-bypassed",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "decision.static-attacks").__setitem__("needs", ["decision.axiom-checker-attacks"])),
                ["decision static attacks bypass validator"],
            ),
            (
                "runtime-evidence-join-detached",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "release.runtime-evidence-join").__setitem__("needs", ["decision.artifacts-node"])),
                ["runtime evidence join is detached"],
            ),
            (
                "combined-verification-wrapper-drift",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("verify:facility-decision", "npm run release:graph -- --target facility-decision-runtime")),
                ["combined verification graph target differs"],
            ),
            (
                "learner-route-escalated",
                lambda repo: replace(repo, "src/App.tsx", '<Route path="/examples/facility-decision/learner" element={<FacilityDecisionLearnerPage />} />', '<Route path="/examples/facility-decision/learner" element={<FacilityDecisionInstructorPage />} />'),
                ["route missing or duplicated:/examples/facility-decision/learner:FacilityDecisionLearnerPage"],
            ),
            (
                "query-string-role-selection-added",
                lambda repo: replace(repo, "src/pages/FacilityDecisionSessionPage.tsx", "import ", "import { useSearchParams } from 'react-router-dom';\nimport "),
                ["role selectable from query string"],
            ),
            (
                "restricted-high-risk-field-read-added",
                lambda repo: replace(
                    repo,
                    "src/pages/FacilityDecisionSessionPage.tsx",
                    "action.requires_deliberate_confirmation",
                    "action.high_risk",
                ),
                ["decision UI reads restricted high-risk field"],
            ),
            (
                "learner-progress-bypasses-projection",
                lambda repo: replace(
                    repo,
                    "src/pages/FacilityDecisionSessionPage.tsx",
                    "const completedCount = view.completed_decision_count;",
                    "const completedCount = session.decision_records.length;",
                ),
                ["decision UI bypasses learner-safe progress projection", "decision UI reads raw decision records"],
            ),
            (
                "instructor-timeline-bypasses-projection",
                lambda repo: replace(
                    repo,
                    "src/pages/FacilityDecisionSessionPage.tsx",
                    "const instructorTimeline = view.instructor?.decision_timeline ?? [];",
                    "const instructorTimeline = session.decision_records;",
                ),
                ["decision UI omits instructor-safe timeline projection", "decision UI reads raw decision records"],
            ),
            (
                "client-role-switcher-added",
                lambda repo: replace(repo, "src/pages/FacilityDecisionIntegrityPage.tsx", "export function FacilityDecisionIntegrityPage()", "const setMode = () => undefined;\nsetMode();\nexport function FacilityDecisionIntegrityPage()"),
                ["overview contains client role switcher"],
            ),
            (
                "readme-patient-care-boundary-removed",
                lambda repo: replace_last(repo, "README.md", "Direct patient care and clinical decision support remain prohibited.", "Direct patient care is under review."),
                ["README patient-care boundary missing"],
            ),
            (
                "readme-simulation-intended-use-removed",
                lambda repo: replace_last(repo, "README.md", "Healthcare simulation and training use is permitted within the validated release scope.", "Healthcare simulation scope is under review."),
                ["README intended-use disclaimer missing"],
            ),
            (
                "formal-import-removed",
                lambda repo: replace(repo, "formal/ScenarioContracts.lean", "import ScenarioContracts.FacilityDecisionIntegrity\n", ""),
                ["formal decision import count differs"],
            ),
            (
                "provenance-falsely-signed",
                lambda repo: replace(repo, "scripts/build_facility_decision_provenance.py", "'signature_status': 'UNSIGNED'", "'signature_status': 'SIGNED'"),
                ["provenance signature state changed"],
            ),
            (
                "manual-accessibility-boundary-removed",
                lambda repo: replace(repo, "docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md", "MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED", "AUTOMATED_ACCESSIBILITY_COMPLETE"),
                ["manual accessibility requirement missing"],
            ),
            (
                "validity-domain-removed",
                lambda repo: mutate_json(repo, "config/facility-decision/VALIDITY_BOUNDARIES.json", lambda doc: doc["domains"].pop("causal_aar")),
                ["validity domain inventory differs"],
            ),
            (
                "core-tsconfig-broadened",
                lambda repo: mutate_json(repo, "tsconfig.facility-decision-core.json", lambda doc: doc.__setitem__("include", ["src"])),
                ["core tsconfig inherits broad include"],
            ),
            (
                "artifact-attack-closed-inventory-removed",
                lambda repo: replace(
                    repo,
                    "scripts/test_facility_decision_artifact_mutations.py",
                    'FIXTURE_POLICY = "MANIFEST_DECLARED_CLOSED_REGULAR_FILE_INVENTORY_V1"',
                    'FIXTURE_POLICY = "AMBIENT_DISCOVERY_V0"',
                ),
                ["artifact mutation harness hardening missing:FIXTURE_POLICY"],
            ),
            (
                "artifact-attack-stdout-verdict-reintroduced",
                lambda repo: replace(
                    repo,
                    "scripts/test_facility_decision_artifact_mutations.py",
                    'CHECKER_RESULT_TRANSPORT = "UNIQUE_REPORT_FILES_NOT_STDOUT_V1"',
                    'CHECKER_RESULT_TRANSPORT = "STDOUT_JSON_V0"',
                ),
                ["artifact mutation harness hardening missing:CHECKER_RESULT_TRANSPORT"],
            ),
            (
                "workflow-duplicates-direct-gate",
                lambda repo: replace(repo, ".github/workflows/facility-decision-integrity-ci.yml", "run: python scripts/run_release_graph.py --repo . --target ci-source --no-reuse", "run: npm run check:facility-decision-integrity && python scripts/run_release_graph.py --repo . --target ci-source --no-reuse"),
                ["canonical release graph consistency failed"],
            ),
            (
                "workflow-action-unpinned",
                lambda repo: replace(repo, ".github/workflows/facility-decision-integrity-ci.yml", "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e", "actions/setup-node@v4"),
                ["canonical release graph consistency failed"],
            ),
            (
                "workflow-persists-checkout-credentials",
                lambda repo: replace(repo, ".github/workflows/facility-decision-integrity-ci.yml", "persist-credentials: false", "persist-credentials: true"),
                ["canonical release graph consistency failed"],
            ),
            (
                "artifact-generator-closed-inventory-removed",
                lambda repo: replace(repo, "scripts/generateFacilityDecisionArtifacts.ts", "artifact_inventory_policy: 'CLOSED_REGULAR_FILE_INVENTORY_V1'", "artifact_inventory_policy: 'OPEN_INVENTORY_V0'"),
                ["artifact generator closed inventory missing"],
            ),
            (
                "artifact-generator-atomic-write-removed",
                lambda repo: replace(repo, "scripts/generateFacilityDecisionArtifacts.ts", "write_policy: 'ATOMIC_RENAME_NO_SYMLINK_V1'", "write_policy: 'DIRECT_WRITE_V0'"),
                ["artifact generator atomic write policy missing"],
            ),
            (
                "artifact-generator-symlink-guard-removed",
                lambda repo: replace(repo, "scripts/generateFacilityDecisionArtifacts.ts", "status.isSymbolicLink() || !status.isFile()", "!status.isFile()"),
                ["artifact generator symlink guard missing"],
            ),
        ]
        for case_id, mutation, markers in attacks:
            results.append(run_attack(source, root, case_id, mutation, markers))

    classification = suite_classification(results)
    report = {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "attacks": len(results) - 1,
        "accepted_mutations": sum(1 for item in results[1:] if item.get("observed_classification") == PASS),
        "internal_errors": sum(1 for item in results if item["classification"] == INTERNAL_ERROR),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] in {FAIL, INTERNAL_ERROR}],
    }
    write_json(source / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
