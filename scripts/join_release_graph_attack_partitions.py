#!/usr/bin/env python3
"""Authenticate and join split release-graph adversarial partitions.

The mutation and heavyweight suites are separate graph stages so each has an
independent timeout, checkpoint receipt, and diagnostic log.  This joiner is the
single fail-closed boundary consumed by downstream production evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

from release_graph_core import GRAPH_PATH, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, suite_classification
from scenario_genome_common import GenomeError, file_sha256, load_object, safe_repo_path
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
    heavy_case_functions,
    mutation_case_functions,
)

SCHEMA_VERSION = "1.0.0"
PARTITION_JOIN_PROFILE = "AUTHENTICATED_RELEASE_GRAPH_ATTACK_PARTITION_JOIN_V2"
DEFAULT_MUTATION_REPORT = "reports/release-graph-mutation-partition.json"
DEFAULT_HEAVY_REPORT = "reports/release-graph-heavy-partition.json"
DEFAULT_SOURCE_CLOSURE_REPORT = "reports/release-source-closure-mutations.json"
DEFAULT_OUTPUT = "reports/release-graph-mutations.json"
VALID_RESULT_CLASSIFICATIONS = {PASS, EXPECTED_REJECTION}


def _case_inventory_sha256(case_ids: list[str]) -> str:
    payload = json.dumps(sorted(case_ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _current_graph_identity(repo: Path) -> tuple[str, str]:
    graph_path = safe_repo_path(repo, GRAPH_PATH.as_posix())
    graph = load_object(graph_path)
    graph_id = graph.get("graph_id")
    if not isinstance(graph_id, str) or not graph_id:
        raise GenomeError("release graph ID unavailable")
    return graph_id, file_sha256(graph_path)


def _expected_partition_case_ids(partition: str) -> list[str]:
    common = list(common_partition_case_ids())
    if partition == "MUTATIONS_ONLY":
        return [*common[:2], *(case_id for case_id, _ in mutation_case_functions()), *common[2:]]
    if partition == "HEAVY_ONLY":
        return [*common[:2], *heavy_case_functions().keys(), *common[2:]]
    raise GenomeError(f"unsupported release-graph attack partition:{partition}")


def _expected_full_case_ids() -> list[str]:
    common = list(common_partition_case_ids())
    return [
        *common[:2],
        *(case_id for case_id, _ in mutation_case_functions()),
        *heavy_case_functions().keys(),
        *common[2:],
    ]


def _result_map(report: dict[str, Any], label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    rows = report.get("results")
    if not isinstance(rows, list):
        errors.append(f"{label} results are not a list")
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{label} result is not an object:{index}")
            continue
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{label} result case ID is malformed:{index}")
            continue
        if case_id in mapped:
            errors.append(f"{label} result case ID duplicated:{case_id}")
            continue
        mapped[case_id] = row
        classification = row.get("classification")
        if classification not in VALID_RESULT_CLASSIFICATIONS or row.get("pass") is not True:
            errors.append(f"{label} case did not pass:{case_id}:{classification}")
    return mapped


def _validate_partition(
    report: dict[str, Any],
    *,
    label: str,
    expected_partition: str,
    graph_id: str,
    graph_sha256: str,
    worker_script_sha256: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if report.get("partition") != expected_partition:
        errors.append(f"{label} partition differs:{report.get('partition')}")
    if report.get("classification") != PASS or report.get("status") != PASS:
        errors.append(f"{label} partition is not PASS")
    if report.get("errors") != []:
        errors.append(f"{label} partition reports errors")
    if report.get("selected_cases") != []:
        errors.append(f"{label} partition was not a complete unfiltered run")
    if report.get("partition_isolation") != PARTITION_ISOLATION:
        errors.append(f"{label} partition isolation differs")
    if report.get("source_snapshot_isolation") != SOURCE_SNAPSHOT_ISOLATION:
        errors.append(f"{label} source snapshot isolation differs")
    mutation_workers = report.get("mutation_workers")
    if not isinstance(mutation_workers, int) or isinstance(mutation_workers, bool) or not 1 <= mutation_workers <= 8:
        errors.append(f"{label} partition mutation worker count is invalid")
    if report.get("mutation_case_isolation") != MUTATION_CASE_ISOLATION:
        errors.append(f"{label} partition mutation process isolation differs")
    if report.get("mutation_worker_execution") != MUTATION_WORKER_EXECUTION:
        errors.append(f"{label} partition mutation worker execution boundary differs")
    if report.get("mutation_worker_result_binding") != MUTATION_WORKER_RESULT_BINDING:
        errors.append(f"{label} partition mutation worker result binding differs")
    if report.get("mutation_validator_timeout_seconds") != DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS:
        errors.append(f"{label} partition mutation validator timeout differs")
    if report.get("mutation_case_timeout_seconds") != DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS:
        errors.append(f"{label} partition mutation case timeout differs")
    if report.get("mutation_checkpoint_profile") != MUTATION_CHECKPOINT_PROFILE:
        errors.append(f"{label} partition mutation checkpoint profile differs")
    context_sha256 = report.get("mutation_checkpoint_context_sha256")
    if not isinstance(context_sha256, str) or len(context_sha256) != 64:
        errors.append(f"{label} partition mutation checkpoint context is malformed")
    if report.get("mutation_checkpoint_root") != DEFAULT_MUTATION_CHECKPOINT_ROOT.as_posix():
        errors.append(f"{label} partition mutation checkpoint root differs")
    if report.get("mutation_checkpoint_reuse_enabled") is not True:
        errors.append(f"{label} partition mutation checkpoint reuse is disabled")
    reused_count = report.get("mutation_checkpoints_reused")
    if not isinstance(reused_count, int) or isinstance(reused_count, bool) or reused_count < 0:
        errors.append(f"{label} partition mutation checkpoint reuse count is invalid")
    if report.get("heavy_checkpoint_profile") != HEAVY_CHECKPOINT_PROFILE:
        errors.append(f"{label} partition heavyweight checkpoint profile differs")
    heavy_context_sha256 = report.get("heavy_checkpoint_context_sha256")
    if not isinstance(heavy_context_sha256, str) or len(heavy_context_sha256) != 64:
        errors.append(f"{label} partition heavyweight checkpoint context is malformed")
    if report.get("heavy_checkpoint_root") != DEFAULT_HEAVY_CHECKPOINT_ROOT.as_posix():
        errors.append(f"{label} partition heavyweight checkpoint root differs")
    if report.get("heavy_checkpoint_reuse_enabled") is not True:
        errors.append(f"{label} partition heavyweight checkpoint reuse is disabled")
    heavy_reused_count = report.get("heavy_checkpoints_reused")
    if not isinstance(heavy_reused_count, int) or isinstance(heavy_reused_count, bool) or heavy_reused_count < 0:
        errors.append(f"{label} partition heavyweight checkpoint reuse count is invalid")
    if report.get("heavy_resource_scheduler") != HEAVY_RESOURCE_SCHEDULER:
        errors.append(f"{label} heavyweight scheduler differs")
    if report.get("heavy_worker_execution") != HEAVY_WORKER_EXECUTION:
        errors.append(f"{label} heavyweight worker execution boundary differs")
    if report.get("heavy_worker_result_binding") != HEAVY_WORKER_RESULT_BINDING:
        errors.append(f"{label} heavyweight worker result binding differs")
    if report.get("exclusive_heavy_cases") != sorted(EXCLUSIVE_HEAVY_CASES):
        errors.append(f"{label} exclusive heavyweight inventory differs")
    if report.get("heavy_case_workers") != DEFAULT_HEAVY_CASE_WORKERS:
        errors.append(f"{label} heavyweight worker floor differs")
    if report.get("heavy_case_timeout_seconds") != DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS:
        errors.append(f"{label} heavyweight timeout differs")
    if report.get("graph_id") != graph_id:
        errors.append(f"{label} graph ID differs")
    if report.get("graph_file_sha256") != graph_sha256:
        errors.append(f"{label} graph hash differs")
    before = report.get("repository_inventory_root_before")
    after = report.get("repository_inventory_root_after")
    if not isinstance(before, str) or len(before) != 64:
        errors.append(f"{label} repository inventory root is malformed")
    if before != after:
        errors.append(f"{label} observed caller source drift")

    expected_ids = _expected_partition_case_ids(expected_partition)
    mapped = _result_map(report, label, errors)
    if expected_partition == "MUTATIONS_ONLY":
        for case_id, _mutate in mutation_case_functions():
            row = mapped.get(case_id)
            if row is None:
                continue
            if row.get("worker_execution") != MUTATION_WORKER_EXECUTION:
                errors.append(f"mutation worker execution evidence differs:{case_id}")
            if row.get("worker_result_binding") != MUTATION_WORKER_RESULT_BINDING:
                errors.append(f"mutation worker result-binding evidence differs:{case_id}")
            if row.get("worker_script_sha256") != worker_script_sha256:
                errors.append(f"mutation worker script hash differs:{case_id}")
            if row.get("worker_executable") != "scripts/test_release_graph.py":
                errors.append(f"mutation worker executable differs:{case_id}")
            if row.get("checkpoint_profile") != MUTATION_CHECKPOINT_PROFILE:
                errors.append(f"mutation checkpoint profile differs:{case_id}")
            checkpoint_sha256 = row.get("checkpoint_sha256")
            if not isinstance(checkpoint_sha256, str) or len(checkpoint_sha256) != 64:
                errors.append(f"mutation checkpoint digest is malformed:{case_id}")
            if row.get("checkpoint_reused") not in {True, False}:
                errors.append(f"mutation checkpoint reuse flag is malformed:{case_id}")
            checkpoint_path = row.get("checkpoint_path")
            if (
                not isinstance(checkpoint_path, str)
                or len(checkpoint_path) != 69
                or not checkpoint_path.endswith(".json")
                or any(ch not in "0123456789abcdef" for ch in checkpoint_path[:-5])
            ):
                errors.append(f"mutation checkpoint path is malformed:{case_id}")
    if expected_partition == "HEAVY_ONLY":
        for case_id in heavy_case_functions():
            row = mapped.get(case_id)
            if row is None:
                continue
            if row.get("worker_execution") != HEAVY_WORKER_EXECUTION:
                errors.append(f"heavy worker execution evidence differs:{case_id}")
            if row.get("worker_result_binding") != HEAVY_WORKER_RESULT_BINDING:
                errors.append(f"heavy worker result-binding evidence differs:{case_id}")
            if row.get("worker_script_sha256") != worker_script_sha256:
                errors.append(f"heavy worker script hash differs:{case_id}")
            if row.get("worker_executable") != "scripts/test_release_graph.py":
                errors.append(f"heavy worker executable differs:{case_id}")
            if row.get("checkpoint_profile") != HEAVY_CHECKPOINT_PROFILE:
                errors.append(f"heavyweight checkpoint profile differs:{case_id}")
            checkpoint_sha256 = row.get("checkpoint_sha256")
            if not isinstance(checkpoint_sha256, str) or len(checkpoint_sha256) != 64:
                errors.append(f"heavyweight checkpoint digest is malformed:{case_id}")
            if row.get("checkpoint_reused") not in {True, False}:
                errors.append(f"heavyweight checkpoint reuse flag is malformed:{case_id}")
            checkpoint_path = row.get("checkpoint_path")
            if (
                not isinstance(checkpoint_path, str)
                or len(checkpoint_path) != 69
                or not checkpoint_path.endswith(".json")
                or any(ch not in "0123456789abcdef" for ch in checkpoint_path[:-5])
            ):
                errors.append(f"heavyweight checkpoint path is malformed:{case_id}")
    observed_ids = list(mapped)
    if set(observed_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(observed_ids))
        extra = sorted(set(observed_ids) - set(expected_ids))
        if missing:
            errors.append(f"{label} required cases missing:{','.join(missing)}")
        if extra:
            errors.append(f"{label} unexpected cases present:{','.join(extra)}")
    if report.get("cases") != len(expected_ids):
        errors.append(f"{label} case count differs")
    expected_inventory = _case_inventory_sha256(expected_ids)
    if report.get("case_inventory_sha256") != expected_inventory:
        errors.append(f"{label} case inventory hash differs")
    return mapped


def validate_join(
    repo: Path,
    *,
    mutation_report_path: str | Path = DEFAULT_MUTATION_REPORT,
    heavy_report_path: str | Path = DEFAULT_HEAVY_REPORT,
    source_closure_report_path: str | Path = DEFAULT_SOURCE_CLOSURE_REPORT,
) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    errors: list[str] = []
    graph_id, graph_sha256 = _current_graph_identity(repo)
    worker_script_sha256 = file_sha256(safe_repo_path(repo, "scripts/test_release_graph.py"))

    mutation_path = safe_repo_path(repo, mutation_report_path)
    heavy_path = safe_repo_path(repo, heavy_report_path)
    closure_path = safe_repo_path(repo, source_closure_report_path)
    mutation_report = load_object(mutation_path)
    heavy_report = load_object(heavy_path)
    closure_report = load_object(closure_path)

    mutation_rows = _validate_partition(
        mutation_report,
        label="mutation",
        expected_partition="MUTATIONS_ONLY",
        graph_id=graph_id,
        graph_sha256=graph_sha256,
        worker_script_sha256=worker_script_sha256,
        errors=errors,
    )
    heavy_rows = _validate_partition(
        heavy_report,
        label="heavy",
        expected_partition="HEAVY_ONLY",
        graph_id=graph_id,
        graph_sha256=graph_sha256,
        worker_script_sha256=worker_script_sha256,
        errors=errors,
    )

    mutation_root = mutation_report.get("repository_inventory_root_before")
    heavy_root = heavy_report.get("repository_inventory_root_before")
    if mutation_root != heavy_root:
        errors.append("partition repository inventory roots differ")

    if closure_report.get("classification") != PASS or closure_report.get("status") != PASS:
        errors.append("source-closure attack suite is not PASS")
    if closure_report.get("errors") != []:
        errors.append("source-closure attack suite reports errors")
    if closure_report.get("accepted_attacks") != 0:
        errors.append("source-closure attack was accepted")

    for case_id in common_partition_case_ids():
        left = mutation_rows.get(case_id)
        right = heavy_rows.get(case_id)
        if left is None or right is None:
            continue
        if left != right:
            errors.append(f"partition common-case evidence differs:{case_id}")

    full_ids = _expected_full_case_ids()
    merged_rows: list[dict[str, Any]] = []
    for case_id in full_ids:
        if case_id in mutation_rows:
            merged_rows.append(mutation_rows[case_id])
        elif case_id in heavy_rows:
            merged_rows.append(heavy_rows[case_id])
        else:
            errors.append(f"joined case unavailable:{case_id}")

    classification = PASS if not errors and suite_classification(merged_rows) == PASS else FAIL
    return {
        "schema_version": SCHEMA_VERSION,
        "classification": classification,
        "status": classification,
        "partition_join_profile": PARTITION_JOIN_PROFILE,
        "partition_isolation": PARTITION_ISOLATION,
        "source_snapshot_isolation": SOURCE_SNAPSHOT_ISOLATION,
        "mutation_case_isolation": MUTATION_CASE_ISOLATION,
        "mutation_worker_execution": MUTATION_WORKER_EXECUTION,
        "mutation_worker_result_binding": MUTATION_WORKER_RESULT_BINDING,
        "mutation_worker_script_sha256": worker_script_sha256,
        "mutation_validator_timeout_seconds": DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
        "mutation_case_timeout_seconds": DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS,
        "mutation_checkpoint_profile": MUTATION_CHECKPOINT_PROFILE,
        "mutation_checkpoint_context_sha256": mutation_report.get("mutation_checkpoint_context_sha256"),
        "mutation_checkpoint_root": DEFAULT_MUTATION_CHECKPOINT_ROOT.as_posix(),
        "mutation_checkpoint_reuse_enabled": True,
        "mutation_checkpoints_reused": mutation_report.get("mutation_checkpoints_reused"),
        "heavy_checkpoint_profile": HEAVY_CHECKPOINT_PROFILE,
        "heavy_checkpoint_context_sha256": heavy_report.get("heavy_checkpoint_context_sha256"),
        "heavy_checkpoint_root": DEFAULT_HEAVY_CHECKPOINT_ROOT.as_posix(),
        "heavy_checkpoint_reuse_enabled": True,
        "heavy_checkpoints_reused": heavy_report.get("heavy_checkpoints_reused"),
        "heavy_resource_scheduler": HEAVY_RESOURCE_SCHEDULER,
        "heavy_worker_execution": HEAVY_WORKER_EXECUTION,
        "heavy_worker_result_binding": HEAVY_WORKER_RESULT_BINDING,
        "heavy_worker_script_sha256": worker_script_sha256,
        "exclusive_heavy_cases": sorted(EXCLUSIVE_HEAVY_CASES),
        "heavy_case_workers": DEFAULT_HEAVY_CASE_WORKERS,
        "heavy_case_timeout_seconds": DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS,
        "graph_id": graph_id,
        "graph_file_sha256": graph_sha256,
        "repository_inventory_root_sha256": mutation_root,
        "cases": len(merged_rows),
        "case_inventory_sha256": _case_inventory_sha256(full_ids),
        "partitions": {
            "mutations": {
                "path": Path(mutation_report_path).as_posix(),
                "sha256": file_sha256(mutation_path),
                "cases": mutation_report.get("cases"),
                "case_inventory_sha256": mutation_report.get("case_inventory_sha256"),
            },
            "heavyweight": {
                "path": Path(heavy_report_path).as_posix(),
                "sha256": file_sha256(heavy_path),
                "cases": heavy_report.get("cases"),
                "case_inventory_sha256": heavy_report.get("case_inventory_sha256"),
            },
            "source_closure": {
                "path": Path(source_closure_report_path).as_posix(),
                "sha256": file_sha256(closure_path),
                "cases": closure_report.get("cases"),
                "accepted_attacks": closure_report.get("accepted_attacks"),
            },
        },
        "results": merged_rows,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--mutation-report", default=DEFAULT_MUTATION_REPORT)
    parser.add_argument("--heavy-report", default=DEFAULT_HEAVY_REPORT)
    parser.add_argument("--source-closure-report", default=DEFAULT_SOURCE_CLOSURE_REPORT)
    parser.add_argument("--json-output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = validate_join(
            repo,
            mutation_report_path=args.mutation_report,
            heavy_report_path=args.heavy_report,
            source_closure_report_path=args.source_closure_report,
        )
    except (GenomeError, FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        report = {
            "schema_version": SCHEMA_VERSION,
            "classification": FAIL,
            "status": FAIL,
            "partition_join_profile": PARTITION_JOIN_PROFILE,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": SCHEMA_VERSION,
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "partition_join_profile": PARTITION_JOIN_PROFILE,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    output = safe_repo_path(repo, args.json_output)
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("classification") == PASS:
        return 0
    return 4 if report.get("classification") == INTERNAL_ERROR else 3


if __name__ == "__main__":
    raise SystemExit(main())
