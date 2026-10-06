#!/usr/bin/env python3
"""Adversarial tests for graph-bound Scenario Evolution evidence receipts."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from join_scenario_evolution_evidence import ARTIFACT_STAGE_MAP, REPORT_STAGE_MAP, REQUIRED_ARTIFACTS, REQUIRED_RECEIPT_STAGES
from release_graph_core import (
    canonical_json,
    graph_file_sha256,
    load_graph,
    make_receipt,
    output_inventory,
    output_root_sha256,
    sha256_text,
    stage_map,
    write_json,
)

sys.dont_write_bytecode = True

SCRIPT_FILES = (
    "scripts/join_scenario_evolution_evidence.py",
    "scripts/release_graph_core.py",
    "scripts/release_result.py",
    "scripts/scenario_genome_common.py",
)
CONFIG_FILES = (
    "config/release/SCENARIO_CAPABILITY_RATCHET.json",
    "config/release/TECHNICAL_DEBT_RATCHET.json",
)


def copy_file(source: Path, destination: Path, relative: str) -> None:
    src = source / relative
    if not src.is_file() or src.is_symlink():
        raise RuntimeError(f"fixture source unavailable:{relative}")
    dst = destination / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def prepare(source: Path, destination: Path) -> None:
    copy_file(source, destination, "config/release/RELEASE_GRAPH.json")
    for relative in SCRIPT_FILES + CONFIG_FILES:
        copy_file(source, destination, relative)

    # A receipt authenticates the complete declared output inventory for its
    # stage, not only the particular report consumed by the evidence join.
    # Build the fixture from the graph-owned output closure so adding a new
    # output to a governed stage cannot leave this test with a partial receipt.
    graph = load_graph(source)
    stages = stage_map(graph)
    required = set(REPORT_STAGE_MAP) | set(REQUIRED_ARTIFACTS)
    stage_outputs: set[str] = set()
    for stage_id in REQUIRED_RECEIPT_STAGES:
        stage = stages.get(stage_id)
        if not isinstance(stage, dict):
            raise RuntimeError(f"fixture stage unavailable:{stage_id}")
        for relative in stage.get("outputs", []):
            if not isinstance(relative, str) or not relative:
                raise RuntimeError(f"fixture stage output malformed:{stage_id}")
            stage_outputs.add(relative)
    for relative in sorted(required):
        copy_file(source, destination, relative)
    # Some complete stage outputs are generated only by dependency-backed
    # commands.  They are not consumed semantically by this focused join test,
    # but the synthetic receipt must still authenticate the stage's complete
    # declared output inventory.  Copy real outputs when available and create a
    # deterministic fixture-only record for otherwise absent ancillary reports.
    for relative in sorted(stage_outputs - required):
        src = source / relative
        dst = destination / relative
        if src.is_file() and not src.is_symlink():
            copy_file(source, destination, relative)
            continue
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, dst)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.suffix == ".json":
            write_json(dst, {
                "schema_version": "1.0.0",
                "classification": "PASS",
                "status": "PASS",
                "fixture_only": True,
                "declared_output": relative,
            })
        else:
            dst.write_text("fixture-only declared stage output\n", encoding="utf-8", newline="\n")


def build_receipts(repo: Path, receipt_dir: Path) -> None:
    graph = load_graph(repo)
    stages = stage_map(graph)
    graph_sha256 = graph_file_sha256(repo)
    receipt_dir.mkdir(parents=True, exist_ok=True)
    for stage_id in REQUIRED_RECEIPT_STAGES:
        stage = stages[stage_id]
        inventory, errors = output_inventory(repo, stage.get("outputs", []))
        if errors:
            raise RuntimeError(f"test fixture output inventory failed:{stage_id}:{errors}")
        receipt = make_receipt(
            graph=graph,
            graph_file_hash=graph_sha256,
            stage=stage,
            command=list(stage["command"]),
            resolved_command={"kind": "test-fixture"},
            input_root="0" * 64,
            output_root=output_root_sha256(inventory),
            output_inventory_value=inventory,
            tool_versions={},
            dependency_receipts={},
            exit_status=0,
            classification="PASS",
            started_at="2026-01-01T00:00:00.000000Z",
            completed_at="2026-01-01T00:00:00.000001Z",
            errors=[],
        )
        write_json(receipt_dir / f"{stage_id}.json", receipt)


def rehash_receipt(path: Path, mutation: Callable[[dict[str, Any]], None]) -> None:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    mutation(receipt)
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = sha256_text(canonical_json(receipt))
    write_json(path, receipt)


def set_production_policy_stage_floor(repo: Path, stage_floor: int) -> None:
    path = repo / "config/release/PRODUCTION_SIMULATION_POLICY.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["evidence_contract"]["minimum_release_graph_stages"] = stage_floor
    write_json(path, value)


def run_join(repo: Path, receipt_dir: Path | None) -> tuple[bool, dict[str, Any]]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if receipt_dir is None:
        env.pop("ASKLEPIOS_RELEASE_RECEIPT_DIR", None)
    else:
        env["ASKLEPIOS_RELEASE_RECEIPT_DIR"] = str(receipt_dir)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/join_scenario_evolution_evidence.py",
            "--repo",
            ".",
            "--json-output",
            "reports/test-scenario-evolution-evidence.json",
        ],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=90,
    )
    try:
        result = json.loads(completed.stdout)
    except Exception:
        result = {
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "errors": [completed.stdout[-2000:]],
        }
    passed = completed.returncode == 0 and result.get("classification") == "PASS"
    return passed, {
        "exit_status": completed.returncode,
        "observed_classification": result.get("classification"),
        "checker_errors": result.get("errors", []),
        "receipt_binding_mode": result.get("receipt_binding_mode"),
        "required_receipts": result.get("required_receipts"),
        "authenticated_receipts": result.get("authenticated_receipts"),
        "receipt_stage_ids": sorted(str(item.get("stage")) for item in result.get("receipt_records", []) if isinstance(item, dict)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    source = args.repo.resolve(strict=True)
    results: list[dict[str, Any]] = []

    def execute(
        case_id: str,
        mutation: Callable[[Path, Path], None] | None,
        expected_pass: bool,
        *,
        graph_bound: bool = True,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"asklepios-evolution-receipt-{case_id}-") as temporary:
            repo = Path(temporary) / "repo"
            receipt_dir = Path(temporary) / "receipts"
            prepare(source, repo)
            if graph_bound:
                build_receipts(repo, receipt_dir)
            if mutation:
                mutation(repo, receipt_dir)
            observed_pass, diagnostics = run_join(repo, receipt_dir if graph_bound else None)
            passed = observed_pass is expected_pass
            results.append({
                "case_id": case_id,
                "classification": "PASS" if expected_pass and passed else ("EXPECTED_REJECTION" if not expected_pass and passed else "FAIL"),
                "expected_pass": expected_pass,
                "observed_pass": observed_pass,
                "pass": passed,
                **diagnostics,
            })

    execute("standalone_report_hash_mode", None, True, graph_bound=False)
    execute("graph_bound_receipt_baseline", None, True)
    execute(
        "production_policy_stage_floor_regression_rejected",
        lambda repo, _receipts: set_production_policy_stage_floor(repo, 1),
        False,
        graph_bound=False,
    )
    execute(
        "graph_below_production_policy_stage_floor_rejected",
        lambda repo, _receipts: set_production_policy_stage_floor(repo, 119),
        False,
        graph_bound=False,
    )
    for case_id, stage in (
        ("behavior_archive_receipt_missing", "scenario.contracts"),
        ("behavior_archive_checker_receipt_missing", "scenario.behavior-archive-check"),
        ("behavior_archive_attack_receipt_missing", "scenario.behavior-archive-attacks"),
        ("missing_genome_receipt_rejected", "scenario.genome-node"),
        ("missing_offline_receipt_rejected", "offline.release-attacks"),
        ("missing_engine_docs_receipt_rejected", "scenario.engine-evolution-doc-attacks"),
        ("missing_node_cli_receipt_rejected", "scenario.node-checker-cli-attacks"),
        ("missing_debt_ratchet_receipt_rejected", "release.debt-ratchet-attacks"),
        ("science_foundation_checker_receipt_missing", "scenario.science-foundation-check"),
        ("stakeholder_product_checker_receipt_missing", "scenario.stakeholder-product-check"),
        ("treatment_admission_receipt_missing", "scenario.treatment-admission-check"),
        ("treatment_admission_attack_receipt_missing", "scenario.treatment-admission-attacks"),
        ("plain_language_summary_receipt_missing", "scenario.plain-language-summary-check"),
        ("plain_language_summary_attack_receipt_missing", "scenario.plain-language-summary-attacks"),
        ("missing_standalone_receipt_rejected", "standalone.contracts"),
        ("artifact_only_standalone_generate_receipt_missing", "standalone.generate"),
    ):
        execute(case_id, lambda _repo, receipts, stage=stage: (receipts / f"{stage}.json").unlink(), False)

    def forge_digest(_repo: Path, receipts: Path) -> None:
        path = receipts / "scenario.verified-example-python.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["receipt_sha256"] = "0" * 64
        write_json(path, receipt)

    execute("forged_receipt_digest_rejected", forge_digest, False)

    for case_id, relative in (
        ("stale_behavior_archive_output", "reports/scenario-behavior-archive.json"),
        ("stale_genome_report_rejected", "reports/scenario-genome-node.json"),
        ("stale_offline_descriptor_rejected", "public/data/scenario_core/offline_scenario_release.json"),
        ("stale_engine_document_rejected", "docs/FACILITY_ARRIVAL_STANDALONE.md"),
        ("stale_treatment_projection_rejected", "public/data/scenario_library/treatment-admission.json"),
        ("stale_plain_language_summary_rejected", "docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md"),
    ):
        execute(
            case_id,
            lambda repo, _receipts, relative=relative: (repo / relative).write_text(
                (repo / relative).read_text(encoding="utf-8") + " ", encoding="utf-8", newline="\n"
            ),
            False,
        )

    execute(
        "wrong_graph_identity_rejected",
        lambda _repo, receipts: rehash_receipt(
            receipts / "scenario.capability-ratchet.json",
            lambda receipt: receipt.__setitem__("graph_id", "forged-graph"),
        ),
        False,
    )
    execute(
        "failed_receipt_rejected_even_when_rehashed",
        lambda _repo, receipts: rehash_receipt(
            receipts / "scenario.engine-evolution-doc-attacks.json",
            lambda receipt: (receipt.__setitem__("classification", "FAIL"), receipt.__setitem__("exit_status", 3)),
        ),
        False,
    )
    execute(
        "stage_configuration_forgery_rejected",
        lambda _repo, receipts: rehash_receipt(
            receipts / "offline.release-node.json",
            lambda receipt: receipt.__setitem__("stage_config_sha256", "0" * 64),
        ),
        False,
    )

    failures = [item["case_id"] for item in results if not item["pass"]]
    report = {
        "schema_version": "1.2.0",
        "classification": "PASS" if not failures else "FAIL",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "required_receipt_count": len(REQUIRED_RECEIPT_STAGES),
        "required_receipt_stages": list(REQUIRED_RECEIPT_STAGES),
        "expected_rejections": sum(1 for item in results if not item["expected_pass"]),
        "accepted_attacks": sum(1 for item in results if not item["expected_pass"] and item["observed_pass"]),
        "errors": failures,
        "results": results,
        "truth_boundary": "Report hashes alone are informative; graph-bound release evidence additionally requires current, authenticated predecessor receipts.",
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.json_output:
        output = args.json_output if args.json_output.is_absolute() else source / args.json_output
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.name}.tmp")
        temporary.write_text(rendered, encoding="utf-8", newline="\n")
        temporary.replace(output)
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
