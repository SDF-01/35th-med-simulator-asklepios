#!/usr/bin/env python3
"""Adversarial tests for the graph-owned Facility Arrival release boundary."""
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

from check_facility_arrival_release_static import validate
from release_graph_core import GRAPH_PATH, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, exit_code, suite_classification

OUTPUT = Path("reports/facility-arrival-release-static-mutations.json")


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


def mutate_json(repo: Path, relative: str, mutation: Callable[[dict], None]) -> None:
    path = repo / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def graph_stage(graph: dict, stage_id: str) -> dict:
    return next(stage for stage in graph["stages"] if stage["id"] == stage_id)


def facility_event(document: dict) -> dict:
    return next(item for item in document["events"] if item.get("event_id") == "second_casualty_inbound")


def decision_event(document: dict) -> dict:
    return next(item for item in document["operational_model"]["world_events"] if item.get("event_id") == "second_casualty_inbound")


def run_attack(
    source: Path,
    temp_root: Path,
    case_id: str,
    mutation: Callable[[Path], None],
    required_errors: Iterable[str],
    *,
    validate_graph: bool = False,
) -> dict:
    candidate = temp_root / case_id
    copy_repo(source, candidate)
    try:
        mutation(candidate)
        report = validate(candidate, validate_graph=validate_graph)
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
    except Exception as exc:  # noqa: BLE001 - mutation harness failures are explicit
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

    with tempfile.TemporaryDirectory(prefix="asklepios-arrival-static-attacks-") as directory:
        root = Path(directory)
        attacks: list[tuple[str, Callable[[Path], None], list[str]]] = [
            (
                "calibration-record-missing",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: doc["operational_model"].__setitem__("world_events", [item for item in doc["operational_model"]["world_events"] if item.get("event_id") != "second_casualty_inbound"])),
                ["calibration record missing:second_casualty_inbound"],
            ),
            (
                "calibration-status-promoted",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("calibration_status", "CALIBRATED")),
                ["calibration status changed:second_casualty_inbound:CALIBRATED"],
            ),
            (
                "calibration-time-disagrees",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("at_elapsed_seconds", 241)),
                ["event times disagree:second_casualty_inbound:facility=240:decision=241"],
            ),
            (
                "exercise-assumption-note-removed",
                lambda repo: mutate_json(repo, "config/facility-decision/ASK-D-001.json", lambda doc: decision_event(doc).__setitem__("note", "Clock event.")),
                ["exercise-assumption note missing:second_casualty_inbound"],
            ),
            (
                "clock-event-action-trigger-regression",
                lambda repo: mutate_json(repo, "config/facility-arrival/ASK-D-001.json", lambda doc: facility_event(doc).__setitem__("trigger", {"kind": "after_action", "action_id": "order_imaging"})),
                ["facility clock event trigger kind changed:second_casualty_inbound"],
            ),
            (
                "facility-clock-time-changed",
                lambda repo: mutate_json(repo, "config/facility-arrival/ASK-D-001.json", lambda doc: facility_event(doc)["trigger"].__setitem__("at_elapsed_seconds", 241)),
                ["facility clock event time changed:second_casualty_inbound:241", "event times disagree:second_casualty_inbound:facility=241:decision=240"],
            ),
            (
                "source-attestation-command-weakened",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "arrival.source-attestations").__setitem__("command", ["npm", "run", "compile:facility-arrival"])),
                ["runtime source-attestation stage differs"],
            ),
            (
                "source-attestation-order-bypassed",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "arrival.source-attestations").__setitem__("needs", ["arrival.generate"])),
                ["runtime source attestations are not ordered after artifact boundary"],
            ),
            (
                "runtime-chain-bypasses-source-attestations",
                lambda repo: mutate_json(repo, str(GRAPH_PATH), lambda graph: graph_stage(graph, "arrival.runtime-tests").__setitem__("needs", ["arrival.artifact-boundary"])),
                ["runtime assurance omits stage:arrival.source-attestations"],
            ),
            (
                "complete-attestation-leaf-weakened",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("check:facility-arrival-source-attestations", "npm run compile:facility-arrival")),
                ["package script differs:check:facility-arrival-source-attestations"],
            ),
            (
                "runtime-wrapper-approximated",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("verify:facility-arrival-runtime", "npm run test:facility-arrival")),
                ["package script differs:verify:facility-arrival-runtime"],
            ),
            (
                "workflow-duplicates-direct-gate",
                lambda repo: replace(repo, ".github/workflows/facility-arrival-ci.yml", "run: python scripts/run_release_graph.py --repo . --target ci-source --no-reuse", "run: npm run check:facility-arrival-source-attestations && python scripts/run_release_graph.py --repo . --target ci-source --no-reuse"),
                ["canonical release graph consistency failed"],
                True,
            ),
            (
                "workflow-action-unpinned",
                lambda repo: replace(repo, ".github/workflows/facility-arrival-ci.yml", "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e", "actions/setup-node@v4"),
                ["GitHub action is not pinned to a full SHA:actions/setup-node@v4"],
            ),
            (
                "workflow-persists-checkout-credentials",
                lambda repo: replace(repo, ".github/workflows/facility-arrival-ci.yml", "persist-credentials: false", "persist-credentials: true"),
                ["checkout credentials are persisted"],
            ),
            (
                "workflow-runtime-lane-removed",
                lambda repo: replace(repo, ".github/workflows/facility-arrival-ci.yml", "--target ci-runtime --no-reuse", "--target ci-source --no-reuse"),
                ["Linux/Windows runtime lanes do not share the canonical graph target"],
            ),
            (
                "total-duration-resolver-removed",
                lambda repo: replace(repo, "src/facility-arrival/engine.ts", "return dueAt === null ? null : Math.max(0, dueAt - state.elapsed_seconds);", "return Math.max(0, Number(dueAt) - state.elapsed_seconds);"),
                ["total dynamic-duration resolver missing"],
            ),
            (
                "execution-guard-removed",
                lambda repo: replace(repo, "src/facility-arrival/engine.ts", "  if (duration === null) {\n    throw new Error('Facility action duration was unresolved after admission.');\n  }\n", ""),
                ["execution-time unresolved-duration guard missing"],
            ),
            (
                "typescript-generator-offline-route-removed",
                lambda repo: replace(repo, "scripts/generateFacilityArrivalArtifacts.ts", "[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request.", "Offline scenario removed."),
                ["TypeScript generator omits offline standalone route"],
            ),
            (
                "typescript-generator-shared-evolution-renderer-bypassed",
                lambda repo: replace(repo, "scripts/generateFacilityArrivalArtifacts.ts", "import { graphContractSha256, renderEvolutionBlock } from './engine_evolution_documentation_common.mjs';", ""),
                ["TypeScript parity checker bypasses shared evolution renderer"],
            ),
            (
                "typescript-generator-evolution-block-removed",
                lambda repo: replace(repo, "scripts/generateFacilityArrivalArtifacts.ts", r"    `${evolutionBlock}\n\n` +" + "\n", ""),
                ["TypeScript parity checker omits engine-evolution block"],
            ),
            (
                "typescript-generator-graph-contract-helper-duplicated",
                lambda repo: replace(repo, "scripts/generateFacilityArrivalArtifacts.ts", "const evolutionBlock = renderEvolutionBlock", "function graphContractSha256() { return '0'.repeat(64); }\nconst evolutionBlock = renderEvolutionBlock"),
                ["TypeScript parity checker duplicates graph-contract authority"],
            ),
            (
                "node-builtin-capability-profile-weakened",
                lambda repo: replace(
                    repo,
                    "scripts/check_facility_arrival_module_resolution.py",
                    'NODE_BUILTIN_CAPABILITY_PROFILE = "EXACT_SOURCE_SCOPED_NODE_BUILTINS_V1"',
                    'NODE_BUILTIN_CAPABILITY_PROFILE = "GLOBAL_NODE_BUILTINS_V0"',
                ),
                ["Facility Arrival Node builtin capability profile differs"],
            ),
            (
                "node-crypto-capability-broadened",
                lambda repo: replace(
                    repo,
                    "scripts/check_facility_arrival_module_resolution.py",
                    '"scripts/engine_evolution_documentation_common.mjs": frozenset({"node:crypto"})',
                    '"scripts/engine_evolution_documentation_common.mjs": frozenset({"node:crypto", "node:fs"})',
                ),
                ["engine-evolution renderer Node crypto capability differs"],
            ),
            (
                "node-capability-regression-case-removed",
                lambda repo: replace(
                    repo,
                    "scripts/test_facility_arrival_module_resolution.py",
                    '"reviewed_crypto_capability_wrong_source_rejected"',
                    '"removed_crypto_capability_case"',
                ),
                ["Facility Arrival Node capability regression missing:reviewed_crypto_capability_wrong_source_rejected"],
            ),
            (
                "python-canonical-generator-offline-route-removed",
                lambda repo: replace(repo, "scripts/build_facility_arrival_example.py", "[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request.", "Offline scenario removed."),
                ["Python canonical generator omits offline standalone route"],
            ),
            (
                "typescript-parity-checker-write-mode-restored",
                lambda repo: replace(repo, "scripts/generateFacilityArrivalArtifacts.ts", "if (!check) {\n  throw new Error('TypeScript Facility Arrival generation is verification-only; use npm run generate:facility-arrival.');\n}\n", ""),
                ["TypeScript generator is not verification-only"],
            ),
            (
                "generation-bypasses-canonical-python-writer",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("generate:facility-arrival", "npm run compile:facility-arrival && npm run bind:facility-arrival && tsx --tsconfig tsconfig.app.json scripts/generateFacilityArrivalArtifacts.ts")),
                ["package script differs:generate:facility-arrival"],
            ),
            (
                "generation-bypasses-independent-parity-check",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("generate:facility-arrival", "npm run compile:facility-arrival && npm run bind:facility-arrival && node scripts/run_python.mjs scripts/build_facility_arrival_example.py --repo .")),
                ["package script differs:generate:facility-arrival"],
            ),
            (
                "source-attestations-bypass-independent-parity-check",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("check:facility-arrival-source-attestations", "node scripts/run_python.mjs scripts/compile_facility_arrival_spec.py --repo . --check && node scripts/run_python.mjs scripts/build_facility_arrival_bindings.py --repo . --check && node scripts/run_python.mjs scripts/build_facility_arrival_example.py --repo . --check")),
                ["package script differs:check:facility-arrival-source-attestations"],
            ),
            (
                "application-build-generation-bypassed",
                lambda repo: mutate_json(repo, "package.json", lambda package: package["scripts"].__setitem__("build:generate", "npm run generate:exercises && npm run generate:scenario-blueprints && npm run generate:verified-scenario")),
                ["application build omits facility generation"],
            ),
            (
                "readme-route-removed",
                lambda repo: replace(repo, "README.md", "examples/facility-arrival/README.md", "examples/removed/README.md"),
                ["facility walkthrough not linked from root README"],
            ),
            (
                "root-canonical-heading-stale",
                lambda repo: replace(repo, "README.md", "## Current canonical offline scenario and engine evolution (RC3.8A.1)", "## Current canonical offline scenario and engine evolution (RC3.3.5)"),
                ["current policy-bound canonical facility heading missing"],
            ),
            (
                "facility-example-heading-removed",
                lambda repo: replace(repo, "examples/facility-arrival/README.md", "# Facility-arrival canonical interactive scenario", "# Facility example"),
                ["facility example canonical heading missing"],
            ),
            (
                "spec-attestation-authentication-removed",
                lambda repo: replace(repo, "scripts/validate_facility_arrival_release.py", 'require(attestation_valid(spec), "spec compiler attestation digest invalid", errors)', 'require(True, "spec compiler attestation digest invalid", errors)'),
                ["final validator does not authenticate spec attestation"],
            ),
            (
                "workflow-yaml-anchor-rejected",
                lambda repo: replace(repo, ".github/workflows/facility-arrival-ci.yml", "jobs:\n", "jobs: &shared-jobs\n"),
                ["workflow syntax rejected:YAML anchors, aliases, and merge keys are forbidden"],
            ),
        ]
        for attack in attacks:
            case_id, mutation, markers = attack[:3]
            full_graph = bool(attack[3]) if len(attack) > 3 else False
            results.append(run_attack(source, root, case_id, mutation, markers, validate_graph=full_graph))

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
