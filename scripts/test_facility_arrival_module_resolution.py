#!/usr/bin/env python3
"""Adversarial tests for the Facility Arrival tsx module-resolution contract."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable
from release_result import finalize_adversarial_report


def load_checker(root: Path):
    path = root / "scripts/check_facility_arrival_module_resolution.py"
    spec = importlib.util.spec_from_file_location("facility_module_resolution", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("module-resolution checker could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_repo(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git", "node_modules", "dist", ".lake", "__pycache__", "*.pyc", "*.tsbuildinfo"),
    )


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"mutation anchor missing:{path}:{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def cases() -> list[tuple[object, ...]]:
    return [
        (
            "missing_explicit_tsconfig_rejected",
            lambda repo: replace(
                repo / "package.json",
                "tsx --tsconfig tsconfig.app.json scripts/generateFacilityArrivalArtifacts.ts --check --json-output reports/facility-arrival-generator-parity.json",
                "tsx scripts/generateFacilityArrivalArtifacts.ts --check --json-output reports/facility-arrival-generator-parity.json",
            ),
        ),
        (
            "parity_check_write_mode_rejected",
            lambda repo: replace(
                repo / "package.json",
                "scripts/generateFacilityArrivalArtifacts.ts --check --json-output",
                "scripts/generateFacilityArrivalArtifacts.ts --json-output",
            ),
        ),
        (
            "canonical_python_writer_removed_rejected",
            lambda repo: replace(
                repo / "package.json",
                "node scripts/run_python.mjs scripts/build_facility_arrival_example.py --repo . && npm run check:facility-arrival-generator-parity",
                "npm run check:facility-arrival-generator-parity",
            ),
        ),
        (
            "missing_explicit_test_file_rejected",
            lambda repo: replace(
                repo / "package.json",
                " src/tests/facilityArrivalRelations.test.ts",
                "",
            ),
        ),
        (
            "wrong_alias_mapping_rejected",
            lambda repo: replace(repo / "tsconfig.app.json", '"@/*": ["src/*"]', '"@/*": ["wrong/*"]'),
        ),
        (
            "missing_relative_target_rejected",
            lambda repo: replace(
                repo / "src/facility-arrival/context.ts",
                "../content/scenarios",
                "../content/scenarios-missing",
            ),
        ),
        (
            "repository_escape_rejected",
            lambda repo: replace(
                repo / "src/facility-arrival/context.ts",
                "../content/scenarios",
                "../../../outside-repository",
            ),
        ),
        (
            "unreviewed_bare_package_rejected",
            lambda repo: (repo / "scripts/generateFacilityArrivalArtifacts.ts").write_text(
                "import 'unreviewed-runtime-package';\n" + (repo / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
        ),
        (
            "dynamic_alias_missing_target_rejected",
            lambda repo: (repo / "scripts/generateFacilityArrivalArtifacts.ts").write_text(
                "void import('@/missing/facility-module');\n" + (repo / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
        ),
        (
            "export_from_missing_target_rejected",
            lambda repo: (repo / "src/facility-arrival/types.ts").write_text(
                (repo / "src/facility-arrival/types.ts").read_text(encoding="utf-8") + "\nexport type { MissingFacilityType } from './missing-module';\n",
                encoding="utf-8",
            ),
        ),
        (
            "nonliteral_dynamic_import_rejected",
            lambda repo: (repo / "scripts/generateFacilityArrivalArtifacts.ts").write_text(
                "const dynamicTarget = './missing';\nvoid import(dynamicTarget);\n" + (repo / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
        ),
        (
            "commonjs_require_rejected",
            lambda repo: (repo / "scripts/generateFacilityArrivalArtifacts.ts").write_text(
                "const forbiddenModule = require('./missing');\nvoid forbiddenModule;\n" + (repo / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
        ),
        (
            "unreviewed_node_builtin_rejected",
            lambda repo: (repo / "scripts/generateFacilityArrivalArtifacts.ts").write_text(
                "import 'node:not-a-real-builtin';\n" + (repo / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
        ),
        (
            "reviewed_crypto_capability_wrong_source_rejected",
            lambda repo: (repo / "src/facility-arrival/engine.ts").write_text(
                "import 'node:crypto';\n" + (repo / "src/facility-arrival/engine.ts").read_text(encoding="utf-8"),
                encoding="utf-8",
            ),
            "unreviewed Node builtin in facility runtime closure:src/facility-arrival/engine.ts:node:crypto",
        ),
        (
            "reviewed_crypto_capability_substitution_rejected",
            lambda repo: replace(
                repo / "scripts/engine_evolution_documentation_common.mjs",
                "import crypto from 'node:crypto';",
                "import crypto from 'node:fs';",
            ),
            "unreviewed Node builtin in facility runtime closure:scripts/engine_evolution_documentation_common.mjs:node:fs",
        ),
        (
            "unused_reviewed_crypto_capability_rejected",
            lambda repo: replace(
                repo / "scripts/engine_evolution_documentation_common.mjs",
                "import crypto from 'node:crypto';\n",
                "",
            ),
            "declared Node builtin capability unused:scripts/engine_evolution_documentation_common.mjs:node:crypto",
        ),
        (
            "runtime_smoke_entry_missing_rejected",
            lambda repo: (repo / "scripts/checkFacilityArrivalRuntimeResolution.ts").unlink(),
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()
    source = args.repo.resolve()
    checker = load_checker(source)
    results: list[dict[str, object]] = []

    baseline = checker.verify(source, Path(tempfile.gettempdir()) / "asklepios-facility-module-baseline.json", emit=False)
    baseline_declared = baseline.get("declared_node_builtin_capabilities")
    baseline_observed = baseline.get("observed_node_builtin_edges")
    results.append({
        "case_id": "reviewed_module_graph",
        "pass": (
            baseline.get("status") == "PASS"
            and baseline.get("node_builtin_capability_profile") == "EXACT_SOURCE_SCOPED_NODE_BUILTINS_V1"
            and baseline_declared == baseline_observed
        ),
        "checker_status": baseline.get("status"),
        "capability_profile": baseline.get("node_builtin_capability_profile"),
        "declared_capabilities": baseline_declared,
        "observed_capabilities": baseline_observed,
        "errors": baseline.get("errors", []),
    })

    with tempfile.TemporaryDirectory(prefix="asklepios-module-resolution-") as temp:
        root = Path(temp)
        for index, case in enumerate(cases(), start=1):
            case_id = str(case[0])
            mutate = case[1]
            required_error = str(case[2]) if len(case) > 2 else None
            candidate = root / f"{index:02d}-{case_id}"
            try:
                copy_repo(source, candidate)
                mutate(candidate)
                report = checker.verify(candidate, candidate / "module-resolution-test.json", emit=False)
                checker_errors = [str(item) for item in report.get("errors", [])]
                results.append({
                    "case_id": case_id,
                    "pass": (
                        report.get("status") == "FAIL"
                        and bool(checker_errors)
                        and (required_error is None or any(required_error in item for item in checker_errors))
                    ),
                    "checker_status": report.get("status"),
                    "required_error": required_error,
                    "errors": checker_errors,
                })
            except Exception as exc:  # noqa: BLE001 - harness faults are evidence
                results.append({
                    "case_id": case_id,
                    "classification": "INTERNAL_ERROR",
                    "pass": False,
                    "checker_status": "INTERNAL_ERROR",
                    "errors": [f"{type(exc).__name__}:{exc}"],
                })

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if all(item["pass"] for item in results) else "FAIL",
        "cases": len(results),
        "errors": [],
        "results": results,
    }
    if report["status"] != "PASS":
        report["errors"] = [str(item["case_id"]) for item in results if not item["pass"]]
    report = finalize_adversarial_report(report, baseline_case_ids=("reviewed_module_graph",))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
