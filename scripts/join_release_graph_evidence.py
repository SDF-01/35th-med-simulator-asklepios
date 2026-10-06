#!/usr/bin/env python3
"""Authenticate and join release-graph evidence without trusting stage summaries.

This is an in-toto/SLSA-inspired local evidence join: every predecessor receipt
is content-addressed, bound to the exact graph and stage configuration, linked to
its dependency receipts, and rechecked against current outputs before the join is
accepted.  It deliberately grants no production or patient-care authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from release_graph_core import (
    GRAPH_PATH,
    ReleaseGraphError,
    canonical_json,
    collect_tool_versions,
    compute_stage_input_root,
    graph_file_sha256,
    load_graph,
    load_receipt,
    output_inventory,
    output_root_sha256,
    read_json,
    receipt_valid,
    resolve_command,
    sha256_text,
    stage_input_snapshot,
    stage_map,
    target_plan,
    target_stage_ids,
    verify_input_set,
    write_json,
)
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

OUTPUTS = {
    "runtime": Path("reports/release-graph-runtime-join.json"),
    "final": Path("reports/release-graph-final-evidence.json"),
}
CURRENT_STAGE = {
    "runtime": "release.runtime-evidence-join",
    "final": "final.graph-evidence",
}


def _receipt_dir(root: Path, graph: dict[str, Any], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else root / explicit
    environment = os.environ.get("ASKLEPIOS_RELEASE_RECEIPT_DIR")
    if environment:
        return Path(environment).resolve()
    return root / ".asklepios/release-receipts" / graph["graph_id"]


def _target(scope: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    environment = os.environ.get("ASKLEPIOS_RELEASE_TARGET")
    if environment:
        return environment
    return "canonical-runtime" if scope == "runtime" else "package-rehearsal"


def _expected_predecessors(graph: dict[str, Any], target: str, current_stage: str) -> list[str]:
    stage_ids = target_stage_ids(graph, target)
    if current_stage not in stage_ids:
        raise ReleaseGraphError(f"evidence join stage absent from target:{target}:{current_stage}")
    return stage_ids[: stage_ids.index(current_stage)]


def join(
    root: Path,
    *,
    scope: str,
    graph_path: Path = GRAPH_PATH,
    target: str | None = None,
    receipt_dir: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    try:
        graph = load_graph(root, graph_path)
        target_id = _target(scope, target)
        current_stage = CURRENT_STAGE[scope]
        predecessors = _expected_predecessors(graph, target_id, current_stage)
        stages = stage_map(graph)
        graph_hash = graph_file_sha256(root, graph_path)
        receipts_root = _receipt_dir(root, graph, receipt_dir)
        package = read_json(root / "package.json")
        scripts = package.get("scripts", {})
        if not isinstance(scripts, dict):
            raise ReleaseGraphError("package scripts missing")

        # Revalidate every input lock used by the joined predecessor plan.
        used_sets = sorted({set_id for stage_id in predecessors for set_id in stages[stage_id].get("input_sets", [])})
        for set_id in used_sets:
            errors.extend(verify_input_set(root, set_id, graph["input_sets"][set_id]))

        authenticated: dict[str, Any] = {}
        receipt_roots: dict[str, str] = {}
        authenticated_receipts: dict[str, dict[str, Any]] = {}
        output_roots: dict[str, str] = {}
        for stage_id in predecessors:
            stage = stages[stage_id]
            receipt = load_receipt(receipts_root, stage_id)
            if not receipt_valid(receipt):
                errors.append(f"receipt invalid or missing:{stage_id}")
                continue
            assert receipt is not None
            dependency_receipts = {
                dependency: authenticated_receipts[dependency]
                for dependency in stage.get("needs", [])
                if dependency in authenticated_receipts
            }
            expected_dependencies = {
                dependency: dependency_receipts[dependency].get("receipt_sha256")
                for dependency in sorted(dependency_receipts)
            }
            if len(dependency_receipts) != len(stage.get("needs", [])):
                errors.append(f"receipt predecessor unavailable:{stage_id}")
            current_tool_versions = collect_tool_versions(list(stage["command"]))
            try:
                inputs = stage_input_snapshot(root, graph, stage)
                expected_input_root = compute_stage_input_root(
                    graph,
                    stage,
                    inputs,
                    dependency_receipts,
                    current_tool_versions,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"receipt input root unavailable:{stage_id}:{type(exc).__name__}:{exc}")
                expected_input_root = "UNAVAILABLE"
            observed_outputs, output_errors = output_inventory(root, stage.get("outputs", []))
            errors.extend(f"{stage_id}:{item}" for item in output_errors)
            observed_output_root = output_root_sha256(observed_outputs)
            expected_resolved = resolve_command(list(stage["command"]), scripts)
            checks = {
                "graph_id": receipt.get("graph_id") == graph.get("graph_id"),
                "graph_sha256": receipt.get("graph_sha256") == graph_hash,
                "stage": receipt.get("stage") == stage_id,
                "stage_config_sha256": receipt.get("stage_config_sha256") == sha256_text(canonical_json(stage)),
                "command": receipt.get("command") == stage.get("command"),
                "resolved_command": receipt.get("resolved_command") == expected_resolved,
                "dependency_receipts": receipt.get("dependency_receipts") == expected_dependencies,
                "tool_versions": receipt.get("tool_versions") == current_tool_versions,
                "input_root_sha256": receipt.get("input_root_sha256") == expected_input_root,
                "classification": receipt.get("classification") == PASS,
                "exit_status": receipt.get("exit_status") == 0,
                "output_root_sha256": receipt.get("output_root_sha256") == observed_output_root,
                "output_inventory": receipt.get("output_inventory") == observed_outputs,
            }
            for name, passed in checks.items():
                if not passed:
                    errors.append(f"receipt binding differs:{stage_id}:{name}")
            if all(checks.values()):
                receipt_roots[stage_id] = str(receipt.get("receipt_sha256"))
                authenticated_receipts[stage_id] = receipt
                output_roots[stage_id] = observed_output_root
                authenticated[stage_id] = {
                    "receipt_sha256": receipt.get("receipt_sha256"),
                    "input_root_sha256": expected_input_root,
                    "output_root_sha256": observed_output_root,
                    "checks": checks,
                }

        plan = target_plan(root, graph, target_id)
        plan_prefix = plan[: len(predecessors)]
        plan_root = sha256_text(canonical_json(plan_prefix))
        evidence_root = sha256_text(canonical_json({
            "graph_sha256": graph_hash,
            "target": target_id,
            "scope": scope,
            "plan_root_sha256": plan_root,
            "receipt_roots": receipt_roots,
            "output_roots": output_roots,
            "truth_boundaries": graph.get("truth_boundaries", {}),
        }))
        classification = PASS if not errors and len(authenticated) == len(predecessors) else FAIL
        report = {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "scope": scope,
            "target": target_id,
            "graph_id": graph.get("graph_id"),
            "graph_sha256": graph_hash,
            "production_designation": graph.get("production_designation"),
            "truth_boundaries": graph.get("truth_boundaries", {}),
            "patient_care_authority_granted": False,
            "operational_timing_calibrated": False,
            "predecessor_stage_count": len(predecessors),
            "authenticated_receipt_count": len(authenticated),
            "plan_root_sha256": plan_root,
            "evidence_root_sha256": evidence_root,
            "receipts": authenticated,
            "errors": sorted(set(errors)),
        }
        return report
    except ReleaseGraphError as exc:
        return {
            "schema_version": "1.0.0",
            "classification": FAIL,
            "status": FAIL,
            "scope": scope,
            "errors": [str(exc)],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.0.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "scope": scope,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--scope", choices=sorted(OUTPUTS), required=True)
    parser.add_argument("--target")
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = join(
        root,
        scope=args.scope,
        graph_path=args.graph,
        target=args.target,
        receipt_dir=args.receipt_dir,
    )
    output = args.json_output or OUTPUTS[args.scope]
    write_json(root / output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
