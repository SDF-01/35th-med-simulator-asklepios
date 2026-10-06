#!/usr/bin/env python3
"""Adversarial tests for the release-graph attack partition join boundary."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
sys.dont_write_bytecode = True
import tempfile
from pathlib import Path
from typing import Callable

from join_release_graph_attack_partitions import (
    DEFAULT_HEAVY_REPORT,
    DEFAULT_MUTATION_REPORT,
    DEFAULT_SOURCE_CLOSURE_REPORT,
    PARTITION_JOIN_PROFILE,
    _case_inventory_sha256,
    _expected_partition_case_ids,
    validate_join,
)
from release_graph_core import GRAPH_PATH, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, suite_classification
from scenario_genome_common import GenomeError, file_sha256
from test_release_graph import (
    DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS,
    DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
    MUTATION_CASE_ISOLATION,
    MUTATION_CHECKPOINT_PROFILE,
    DEFAULT_MUTATION_CHECKPOINT_ROOT,
    MUTATION_WORKER_EXECUTION,
    MUTATION_WORKER_RESULT_BINDING,
    HEAVY_CHECKPOINT_PROFILE,
    DEFAULT_HEAVY_CHECKPOINT_ROOT,
    DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS,
    DEFAULT_HEAVY_CASE_WORKERS,
    EXCLUSIVE_HEAVY_CASES,
    HEAVY_RESOURCE_SCHEDULER,
    HEAVY_WORKER_EXECUTION,
    HEAVY_WORKER_RESULT_BINDING,
    PARTITION_ISOLATION,
    SOURCE_SNAPSHOT_ISOLATION,
    common_partition_case_ids,
)

OUTPUT = Path("reports/release-graph-partition-join-mutations.json")
Mutator = Callable[[Path], None]


def _row(case_id: str, classification: str) -> dict:
    return {
        "case_id": case_id,
        "classification": classification,
        "status": classification,
        "pass": classification in {PASS, EXPECTED_REJECTION},
        "errors": [],
    }


def _partition_report(repo: Path, partition: str) -> dict:
    graph = json.loads((repo / GRAPH_PATH).read_text(encoding="utf-8"))
    case_ids = _expected_partition_case_ids(partition)
    common = set(common_partition_case_ids())
    results = [
        _row(case_id, PASS if case_id in common or partition == "HEAVY_ONLY" else EXPECTED_REJECTION)
        for case_id in case_ids
    ]
    worker_script_sha256 = file_sha256(repo / "scripts/test_release_graph.py")
    if partition == "MUTATIONS_ONLY":
        for row in results:
            if row["case_id"] in common:
                continue
            checkpoint_sha256 = hashlib.sha256(row["case_id"].encode("utf-8")).hexdigest()
            row.update({
                "worker_execution": MUTATION_WORKER_EXECUTION,
                "worker_result_binding": MUTATION_WORKER_RESULT_BINDING,
                "worker_script_sha256": worker_script_sha256,
                "worker_executable": "scripts/test_release_graph.py",
                "checkpoint_profile": MUTATION_CHECKPOINT_PROFILE,
                "checkpoint_sha256": checkpoint_sha256,
                "checkpoint_reused": False,
                "checkpoint_path": f"{checkpoint_sha256}.json",
            })
    if partition == "HEAVY_ONLY":
        for row in results:
            if row["case_id"] in common:
                continue
            checkpoint_sha256 = hashlib.sha256(row["case_id"].encode("utf-8")).hexdigest()
            row.update({
                "worker_execution": HEAVY_WORKER_EXECUTION,
                "worker_result_binding": HEAVY_WORKER_RESULT_BINDING,
                "worker_script_sha256": worker_script_sha256,
                "worker_executable": "scripts/test_release_graph.py",
                "checkpoint_profile": HEAVY_CHECKPOINT_PROFILE,
                "checkpoint_sha256": checkpoint_sha256,
                "checkpoint_reused": False,
                "checkpoint_path": f"{checkpoint_sha256}.json",
            })
    root = "1" * 64
    return {
        "schema_version": "1.0.0",
        "classification": PASS,
        "status": PASS,
        "cases": len(case_ids),
        "mutation_workers": 4,
        "mutation_case_isolation": MUTATION_CASE_ISOLATION,
        "mutation_worker_execution": MUTATION_WORKER_EXECUTION,
        "mutation_worker_result_binding": MUTATION_WORKER_RESULT_BINDING,
        "mutation_validator_timeout_seconds": DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
        "mutation_case_timeout_seconds": DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS,
        "mutation_checkpoint_profile": MUTATION_CHECKPOINT_PROFILE,
        "mutation_checkpoint_context_sha256": "3" * 64,
        "mutation_checkpoint_root": DEFAULT_MUTATION_CHECKPOINT_ROOT.as_posix(),
        "mutation_checkpoint_reuse_enabled": True,
        "mutation_checkpoints_reused": 0,
        "heavy_case_isolation": "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V2",
        "heavy_checkpoint_profile": HEAVY_CHECKPOINT_PROFILE,
        "heavy_checkpoint_context_sha256": "4" * 64,
        "heavy_checkpoint_root": DEFAULT_HEAVY_CHECKPOINT_ROOT.as_posix(),
        "heavy_checkpoint_reuse_enabled": True,
        "heavy_checkpoints_reused": 0,
        "heavy_resource_scheduler": HEAVY_RESOURCE_SCHEDULER,
        "heavy_worker_execution": HEAVY_WORKER_EXECUTION,
        "heavy_worker_result_binding": HEAVY_WORKER_RESULT_BINDING,
        "exclusive_heavy_cases": sorted(EXCLUSIVE_HEAVY_CASES),
        "heavy_case_timeout_seconds": DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS,
        "heavy_case_workers": DEFAULT_HEAVY_CASE_WORKERS,
        "partition": partition,
        "partition_isolation": PARTITION_ISOLATION,
        "source_snapshot_isolation": SOURCE_SNAPSHOT_ISOLATION,
        "graph_id": graph["graph_id"],
        "graph_file_sha256": file_sha256(repo / GRAPH_PATH),
        "repository_inventory_root_before": root,
        "repository_inventory_root_after": root,
        "case_inventory_sha256": _case_inventory_sha256(case_ids),
        "selected_cases": [],
        "results": results,
        "errors": [],
    }


def _write_fixture(repo: Path) -> None:
    write_json(repo / DEFAULT_MUTATION_REPORT, _partition_report(repo, "MUTATIONS_ONLY"))
    write_json(repo / DEFAULT_HEAVY_REPORT, _partition_report(repo, "HEAVY_ONLY"))
    write_json(repo / DEFAULT_SOURCE_CLOSURE_REPORT, {
        "schema_version": "1.0.0",
        "classification": PASS,
        "status": PASS,
        "cases": 14,
        "attacks": 10,
        "accepted_attacks": 0,
        "results": [],
        "errors": [],
    })


def _edit(path: Path, mutate: Callable[[dict], None]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    write_json(path, value)


def _refresh_inventory(report: dict) -> None:
    case_ids = [row.get("case_id") for row in report.get("results", []) if isinstance(row, dict)]
    report["cases"] = len(case_ids)
    report["case_inventory_sha256"] = _case_inventory_sha256(case_ids)


def _mutation_wrong_partition(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("partition", "FULL"))


def _heavy_graph_hash_forged(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("graph_file_sha256", "0" * 64))


def _mutation_case_removed_and_rehashed(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["results"].pop(2)
        _refresh_inventory(value)
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _heavy_case_duplicated_and_rehashed(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["results"].append(copy.deepcopy(value["results"][2]))
        _refresh_inventory(value)
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _common_case_disagrees(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["results"][0]["evidence_variant"] = "forged"
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _accepted_mutation_attack(repo: Path) -> None:
    def mutate(value: dict) -> None:
        row = value["results"][2]
        row["classification"] = FAIL
        row["status"] = FAIL
        row["pass"] = False
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _partition_source_drift(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("repository_inventory_root_after", "2" * 64))


def _partition_source_roots_differ(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["repository_inventory_root_before"] = "2" * 64
        value["repository_inventory_root_after"] = "2" * 64
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _source_closure_failed(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["classification"] = FAIL
        value["status"] = FAIL
    _edit(repo / DEFAULT_SOURCE_CLOSURE_REPORT, mutate)


def _source_closure_attack_accepted(repo: Path) -> None:
    _edit(repo / DEFAULT_SOURCE_CLOSURE_REPORT, lambda value: value.__setitem__("accepted_attacks", 1))


def _partition_filtered(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("selected_cases", ["canonical_graph_baseline"]))


def _inventory_hash_forged(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("case_inventory_sha256", "f" * 64))


def _partition_isolation_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("partition_isolation", "SHARED_MUTABLE_PROCESS_V0"))


def _mutation_isolation_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_case_isolation", "THREAD_ONLY_UNBOUNDED_V0"))


def _mutation_worker_execution_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_worker_execution", "LIVE_WORKING_TREE_EXECUTABLE_V0"))


def _mutation_worker_result_binding_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_worker_result_binding", "UNBOUND_RESULT_V0"))


def _mutation_timeout_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_case_timeout_seconds", 900))


def _mutation_worker_script_hash_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["worker_script_sha256"] = "0" * 64
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _mutation_worker_executable_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["worker_executable"] = "scripts/live_test_release_graph.py"
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _mutation_checkpoint_profile_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_checkpoint_profile", "UNAUTHENTICATED_CACHE_V0"))


def _mutation_checkpoint_reuse_disabled(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("mutation_checkpoint_reuse_enabled", False))


def _mutation_checkpoint_digest_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["checkpoint_sha256"] = None
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _mutation_checkpoint_path_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["checkpoint_path"] = "../forged.json"
    _edit(repo / DEFAULT_MUTATION_REPORT, mutate)


def _heavy_scheduler_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_resource_scheduler", "UNBOUNDED_HEAVY_FANOUT_V0"))


def _heavy_worker_floor_widened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_case_workers", 4))


def _exclusive_heavy_inventory_reduced(repo: Path) -> None:
    def mutate(value: dict) -> None:
        value["exclusive_heavy_cases"] = value.get("exclusive_heavy_cases", [])[1:]
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _heavy_worker_execution_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_worker_execution", "LIVE_WORKING_TREE_EXECUTABLE_V0"))


def _heavy_worker_result_binding_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_worker_result_binding", "UNBOUND_RESULT_V0"))


def _heavy_worker_script_hash_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["worker_script_sha256"] = "0" * 64
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _heavy_worker_executable_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["worker_executable"] = "scripts/live_test_release_graph.py"
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _heavy_checkpoint_profile_weakened(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_checkpoint_profile", "UNAUTHENTICATED_CACHE_V0"))


def _heavy_checkpoint_reuse_disabled(repo: Path) -> None:
    _edit(repo / DEFAULT_HEAVY_REPORT, lambda value: value.__setitem__("heavy_checkpoint_reuse_enabled", False))


def _heavy_checkpoint_digest_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["checkpoint_sha256"] = "bad"
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _heavy_checkpoint_path_forged(repo: Path) -> None:
    def mutate(value: dict) -> None:
        common = set(common_partition_case_ids())
        row = next(item for item in value["results"] if item["case_id"] not in common)
        row["checkpoint_path"] = "../outside.json"
    _edit(repo / DEFAULT_HEAVY_REPORT, mutate)


def _graph_identity_stale(repo: Path) -> None:
    _edit(repo / DEFAULT_MUTATION_REPORT, lambda value: value.__setitem__("graph_id", "stale-release-graph"))


def _input_report_symlinked(repo: Path) -> None:
    path = repo / DEFAULT_HEAVY_REPORT
    outside = repo.parent / f"{repo.name}-outside-heavy.json"
    shutil.copy2(path, outside)
    path.unlink()
    path.symlink_to(outside)


def _case_specs() -> list[tuple[str, Mutator | None, str | None]]:
    return [
        ("baseline_partition_join", None, None),
        ("mutation_partition_kind_forged", _mutation_wrong_partition, "mutation partition differs"),
        ("heavy_partition_graph_hash_forged", _heavy_graph_hash_forged, "heavy graph hash differs"),
        ("mutation_case_removed_and_rehashed", _mutation_case_removed_and_rehashed, "mutation required cases missing"),
        ("heavy_case_duplicated_and_rehashed", _heavy_case_duplicated_and_rehashed, "heavy result case ID duplicated"),
        ("common_case_evidence_disagrees", _common_case_disagrees, "partition common-case evidence differs"),
        ("accepted_mutation_attack_rejected", _accepted_mutation_attack, "mutation case did not pass"),
        ("partition_source_drift_rejected", _partition_source_drift, "heavy observed caller source drift"),
        ("partition_source_roots_differ", _partition_source_roots_differ, "partition repository inventory roots differ"),
        ("source_closure_failure_rejected", _source_closure_failed, "source-closure attack suite is not PASS"),
        ("source_closure_accepted_attack_rejected", _source_closure_attack_accepted, "source-closure attack was accepted"),
        ("filtered_partition_rejected", _partition_filtered, "mutation partition was not a complete unfiltered run"),
        ("case_inventory_forgery_rejected", _inventory_hash_forged, "mutation case inventory hash differs"),
        ("partition_isolation_weakened", _partition_isolation_weakened, "heavy partition isolation differs"),
        ("mutation_isolation_weakened", _mutation_isolation_weakened, "mutation partition mutation process isolation differs"),
        ("mutation_worker_execution_weakened", _mutation_worker_execution_weakened, "mutation partition mutation worker execution boundary differs"),
        ("mutation_worker_result_binding_weakened", _mutation_worker_result_binding_weakened, "mutation partition mutation worker result binding differs"),
        ("mutation_timeout_weakened", _mutation_timeout_weakened, "mutation partition mutation case timeout differs"),
        ("mutation_worker_script_hash_forged", _mutation_worker_script_hash_forged, "mutation worker script hash differs"),
        ("mutation_worker_executable_forged", _mutation_worker_executable_forged, "mutation worker executable differs"),
        ("mutation_checkpoint_profile_weakened", _mutation_checkpoint_profile_weakened, "mutation partition mutation checkpoint profile differs"),
        ("mutation_checkpoint_reuse_disabled", _mutation_checkpoint_reuse_disabled, "mutation partition mutation checkpoint reuse is disabled"),
        ("mutation_checkpoint_digest_forged", _mutation_checkpoint_digest_forged, "mutation checkpoint digest is malformed"),
        ("mutation_checkpoint_path_forged", _mutation_checkpoint_path_forged, "mutation checkpoint path is malformed"),
        ("heavy_checkpoint_profile_weakened", _heavy_checkpoint_profile_weakened, "heavy partition heavyweight checkpoint profile differs"),
        ("heavy_checkpoint_reuse_disabled", _heavy_checkpoint_reuse_disabled, "heavy partition heavyweight checkpoint reuse is disabled"),
        ("heavy_checkpoint_digest_forged", _heavy_checkpoint_digest_forged, "heavyweight checkpoint digest is malformed"),
        ("heavy_checkpoint_path_forged", _heavy_checkpoint_path_forged, "heavyweight checkpoint path is malformed"),
        ("heavy_scheduler_weakened", _heavy_scheduler_weakened, "heavy heavyweight scheduler differs"),
        ("heavy_worker_floor_widened", _heavy_worker_floor_widened, "heavy heavyweight worker floor differs"),
        ("exclusive_heavy_inventory_reduced", _exclusive_heavy_inventory_reduced, "heavy exclusive heavyweight inventory differs"),
        ("heavy_worker_execution_weakened", _heavy_worker_execution_weakened, "heavy heavyweight worker execution boundary differs"),
        ("heavy_worker_result_binding_weakened", _heavy_worker_result_binding_weakened, "heavy heavyweight worker result binding differs"),
        ("heavy_worker_script_hash_forged", _heavy_worker_script_hash_forged, "heavy worker script hash differs"),
        ("heavy_worker_executable_forged", _heavy_worker_executable_forged, "heavy worker executable differs"),
        ("stale_graph_identity_rejected", _graph_identity_stale, "mutation graph ID differs"),
        ("symlinked_partition_report_rejected", _input_report_symlinked, "symlink forbidden"),
    ]


def _contains(report: dict, fragment: str | None) -> bool:
    if fragment is None:
        return True
    return any(fragment in str(error) for error in report.get("errors", []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = args.repo.resolve(strict=True)
    results: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="asklepios-release-graph-partition-join-") as temp:
        root = Path(temp)
        for case_id, mutator, required_error in _case_specs():
            fixture = root / case_id
            fixture.mkdir(parents=True)
            (fixture / GRAPH_PATH).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / GRAPH_PATH, fixture / GRAPH_PATH)
            (fixture / "scripts").mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / "scripts/test_release_graph.py", fixture / "scripts/test_release_graph.py")
            _write_fixture(fixture)
            if mutator is not None:
                mutator(fixture)
            try:
                report = validate_join(fixture)
            except (GenomeError, FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
                report = {"classification": FAIL, "errors": [f"{type(exc).__name__}:{exc}"]}
            except Exception as exc:  # noqa: BLE001
                results.append(case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"]))
                continue

            observed = report.get("classification")
            expected_pass = mutator is None
            passed = observed == PASS if expected_pass else observed == FAIL and _contains(report, required_error)
            results.append(case_result(
                case_id,
                PASS if expected_pass and passed else EXPECTED_REJECTION if not expected_pass and passed else FAIL,
                errors=[] if passed else [
                    f"partition join verdict differs:{observed}",
                    *([] if _contains(report, required_error) else [f"required error missing:{required_error}"]),
                ],
                expected_classification=PASS if expected_pass else FAIL,
                observed_classification=observed,
                observed_errors=report.get("errors", []),
            ))

    classification = suite_classification(results)
    report = {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "partition_join_profile": PARTITION_JOIN_PROFILE,
        "cases": len(results),
        "attacks": sum(1 for _case_id, mutator, _error in _case_specs() if mutator is not None),
        "accepted_attacks": sum(1 for item in results if item["classification"] == FAIL),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] in {FAIL, INTERNAL_ERROR}],
    }
    output = args.json_output if args.json_output.is_absolute() else source / args.json_output
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if classification == PASS else (4 if classification == INTERNAL_ERROR else 3)


if __name__ == "__main__":
    raise SystemExit(main())
