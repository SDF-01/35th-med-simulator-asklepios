#!/usr/bin/env python3
"""Adversarial differential suite for the RC3.8A.1 offline release."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, exit_code
from scenario_genome_common import atomic_write_json, canonical_sha256, safe_repo_path

CASE_REGISTRY_PROFILE = "UNIQUE_DETERMINISTIC_CASE_REGISTRY_V1"
CASE_SCHEDULER_PROFILE = "BOUNDED_PARALLEL_ISOLATED_FIXTURES_V1"
SOURCE_GUARD_PROFILE = "SOURCE_INVENTORY_PRESERVATION_RATCHET_V1"
DEFAULT_WORKERS = 4
MAX_WORKERS = 8
CASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

CHECKER_FILES = [
    "scripts/build_offline_scenario_release.py",
    "scripts/check_offline_scenario_release.mjs",
    "scripts/engine_evolution_documentation_common.mjs",
    "scripts/offline_scenario_release_common.py",
    "scripts/release_identity_common.py",
    "scripts/engine_evolution_common.py",
    "scripts/scenario_genome_common.py",
    "scripts/release_result.py",
    "scripts/node_checker_cli.mjs",
]
CORE_FILES = [
    "config/release/OFFLINE_SCENARIO_RELEASE.json",
    "config/release/RELEASE_GRAPH.json",
    "config/release/SCENARIO_CAPABILITY_RATCHET.json",
    "config/release/TECHNICAL_DEBT_RATCHET.json",
    "public/data/scenario_core/verified_scenario_genome.json",
    "public/data/scenario_core/offline_scenario_release.json",
    "README.md",
    "docs/FACILITY_ARRIVAL_STANDALONE.md",
    "examples/facility-arrival/README.md",
    "examples/facility-arrival/manifest.json",
    "examples/facility-arrival/playable.html",
    "examples/verified-scenario/README.md",
    "examples/verified-scenario/manifest.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/offline-scenario-release-mutations.json"))
    parser.add_argument(
        "--workers",
        type=int,
        default=min(DEFAULT_WORKERS, max(1, os.cpu_count() or 1)),
        help=f"bounded fixture workers (1-{MAX_WORKERS})",
    )
    return parser.parse_args()


def validate_workers(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")
    return value


def copy_file(source_root: Path, target_root: Path, relative: str) -> None:
    source = safe_repo_path(source_root, relative)
    target = target_root / relative
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"fixture source unavailable:{relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def fixture_files(source_root: Path) -> list[str]:
    """Return the complete fixture closure from the canonical offline descriptor.

    The attack harness must not maintain a second, stale artifact inventory.  It
    starts from the independently reviewed checker/core sources, then adds every
    artifact governed by the current descriptor.  A newly governed artifact is
    therefore included automatically in both the fixture and source-preservation
    ratchet.
    """
    descriptor_path = safe_repo_path(
        source_root, "public/data/scenario_core/offline_scenario_release.json"
    )
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    artifact_paths = [item.get("path") for item in descriptor.get("artifacts", [])]
    if not artifact_paths or any(not isinstance(item, str) or not item for item in artifact_paths):
        raise RuntimeError("offline release descriptor artifact inventory invalid")
    return sorted(set(CHECKER_FILES + CORE_FILES + artifact_paths))


def build_template(source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for relative in fixture_files(source_root):
        copy_file(source_root, target_root, relative)


def source_inventory(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for relative in fixture_files(root):
        path = safe_repo_path(root, relative)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"guarded source unavailable:{relative}")
        raw = path.read_bytes()
        files.append({
            "path": relative,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return {
        "profile": SOURCE_GUARD_PROFILE,
        "files": files,
        "root_sha256": canonical_sha256(files),
    }


def source_mutations(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_files = {item["path"]: item for item in before.get("files", [])}
    after_files = {item["path"]: item for item in after.get("files", [])}
    changed: list[str] = []
    for relative in sorted(set(before_files) | set(after_files)):
        if before_files.get(relative) != after_files.get(relative):
            changed.append(relative)
    return changed


def canonical_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def refresh_descriptor(root: Path, changed_paths: list[str]) -> None:
    path = root / "public/data/scenario_core/offline_scenario_release.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    records = {item["path"]: item for item in value["artifacts"]}
    for relative in changed_paths:
        if relative in records:
            raw = (root / relative).read_bytes()
            records[relative]["bytes"] = len(raw)
            records[relative]["sha256"] = hashlib.sha256(raw).hexdigest()
    if "config/release/OFFLINE_SCENARIO_RELEASE.json" in changed_paths:
        value["policy"]["file_sha256"] = hashlib.sha256((root / "config/release/OFFLINE_SCENARIO_RELEASE.json").read_bytes()).hexdigest()
    value.pop("release_sha256", None)
    value["release_sha256"] = canonical_hash(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def replace_text(root: Path, relative: str, old: str, new: str, *, refresh: bool = True) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"mutation marker absent:{relative}:{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    if refresh:
        refresh_descriptor(root, [relative])


def mutate_json(root: Path, relative: str, operation: Callable[[dict[str, Any]], None], *, refresh: bool = False) -> None:
    path = root / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    operation(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if refresh:
        refresh_descriptor(root, [relative])


def parse_report(stdout: str) -> dict[str, Any]:
    value = json.loads(stdout.strip())
    if not isinstance(value, dict):
        raise RuntimeError("checker result is not an object")
    return value


def run_checkers(root: Path) -> dict[str, Any]:
    python_report = "reports/mutation-python.json"
    node_report = "reports/mutation-node.json"
    py = subprocess.run(
        [sys.executable, "scripts/build_offline_scenario_release.py", "--repo", ".", "--check", "--json-output", python_report],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    node = subprocess.run(
        ["node", "scripts/check_offline_scenario_release.mjs", "--repo", ".", "--json-output", node_report],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    try:
        py_value = parse_report(py.stdout)
    except Exception as exc:  # noqa: BLE001
        py_value = {"classification": INTERNAL_ERROR, "errors": [f"unstructured Python output:{exc}", py.stderr[-1000:]]}
    try:
        node_value = parse_report(node.stdout)
    except Exception as exc:  # noqa: BLE001
        node_value = {"classification": INTERNAL_ERROR, "errors": [f"unstructured Node output:{exc}", node.stderr[-1000:]]}
    return {
        "python_exit_status": py.returncode,
        "node_exit_status": node.returncode,
        "python_classification": py_value.get("classification"),
        "node_classification": node_value.get("classification"),
        "python_errors": py_value.get("errors", []),
        "node_errors": node_value.get("errors", []),
    }


def write_policy_path(root: Path, path_value: str) -> None:
    def operation(value: dict[str, Any]) -> None:
        value["artifact_inventory"][0]["path"] = path_value
    mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", operation)


def mutate_graph_lock_digest(root: Path) -> None:
    path = root / "config/release/RELEASE_GRAPH.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    for set_id in sorted(graph.get("input_sets", {})):
        files = graph["input_sets"][set_id].get("files", {})
        if files:
            first = sorted(files)[0]
            files[first] = "f" * 64
            break
    path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def mutate_graph_structure(root: Path) -> None:
    path = root / "config/release/RELEASE_GRAPH.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    graph["stages"][0]["read_only"] = not bool(graph["stages"][0].get("read_only"))
    path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def reintroduce_raw_graph_hash(root: Path) -> None:
    path = root / "public/data/scenario_core/offline_scenario_release.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["release_graph"]["file_sha256"] = hashlib.sha256((root / "config/release/RELEASE_GRAPH.json").read_bytes()).hexdigest()
    value.pop("release_sha256", None)
    value["release_sha256"] = canonical_hash(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def reintroduce_raw_graph_artifact(root: Path) -> None:
    def operation(value: dict[str, Any]) -> None:
        value["artifact_inventory"].append({"name": "release_graph", "path": "config/release/RELEASE_GRAPH.json"})
    mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", operation)
    refresh_descriptor(root, ["config/release/OFFLINE_SCENARIO_RELEASE.json"])


def remove_graph_binding_mode(root: Path) -> None:
    mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value.pop("release_graph_binding_mode", None))
    refresh_descriptor(root, ["config/release/OFFLINE_SCENARIO_RELEASE.json"])


def verify_writer_ownership(root: Path) -> dict[str, Any]:
    started_ns = time.monotonic_ns()
    protected = [
        "examples/facility-arrival/README.md",
        "examples/verified-scenario/README.md",
    ]
    before = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in protected}
    completed = subprocess.run(
        [sys.executable, "scripts/build_offline_scenario_release.py", "--repo", ".", "--json-output", "reports/writer-ownership.json"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
    )
    try:
        report = parse_report(completed.stdout)
    except Exception as exc:  # noqa: BLE001
        report = {"classification": INTERNAL_ERROR, "errors": [f"unstructured writer output:{exc}", completed.stderr[-1000:]]}
    after = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in protected}
    changed = [relative for relative in protected if before[relative] != after[relative]]
    passed = completed.returncode == 0 and report.get("classification") == PASS and not changed
    return {
        "case_id": "writer_preserves_verification_only_documentation",
        "classification": PASS if passed else FAIL,
        "status": PASS if passed else FAIL,
        "pass": passed,
        "is_attack": False,
        "writer_exit_status": completed.returncode,
        "writer_classification": report.get("classification"),
        "changed_verification_only_paths": changed,
        "duration_ms": max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
        "errors": report.get("errors", []),
    }


def cases() -> list[tuple[str, Callable[[Path], None] | None] | tuple[str, Callable[[Path], None] | None, bool]]:
    return [
        ("baseline", None, True),
        ("release_graph_lock_hash_churn_preserves_offline_identity", mutate_graph_lock_digest, True),
        ("release_graph_structure_change_rejected", mutate_graph_structure, False),
        ("release_graph_raw_hash_cycle_rejected", reintroduce_raw_graph_hash, False),
        ("release_graph_raw_artifact_cycle_rejected", reintroduce_raw_graph_artifact, False),
        ("release_graph_binding_mode_removed", remove_graph_binding_mode, False),
        ("documentation_writer_ownership_expanded", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["documentation_contract"].__setitem__("writer_owned_surfaces", ["root", "standalone", "facility"])), False),
        ("documentation_verification_ownership_reduced", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["documentation_contract"].__setitem__("verification_only_surfaces", ["verified"])), False),
        ("release_self_hash_tampered", lambda root: mutate_json(root, "public/data/scenario_core/offline_scenario_release.json", lambda value: value.__setitem__("release_sha256", "0" * 64)), False),
        ("playable_hash_stale", lambda root: replace_text(root, "examples/facility-arrival/playable.html", "Facility arrival after CUF and TFC", "Facility arrival altered", refresh=False), False),
        ("external_script_rejected", lambda root: replace_text(root, "examples/facility-arrival/playable.html", "</head>", '<script src="https://example.invalid/x.js"></script></head>'), False),
        ("csp_connection_boundary_weakened", lambda root: replace_text(root, "examples/facility-arrival/playable.html", "connect-src 'none'", "connect-src https:"), False),
        ("network_api_reintroduced", lambda root: replace_text(root, "examples/facility-arrival/playable.html", '"use strict";', '"use strict"; fetch("https://example.invalid");'), False),
        ("root_marker_removed", lambda root: replace_text(root, "README.md", "<!-- asklepios-facility-arrival:start -->", "<!-- removed -->", refresh=False)),
        ("root_genome_identity_drift", lambda root: replace_text(root, "README.md", "ASK-GENOME-", "ASK-GENOME-FORGED-")),
        ("facility_readme_evolution_removed", lambda root: replace_text(root, "examples/facility-arrival/README.md", "## Engine evolution binding", "## Removed evolution binding")),
        ("verified_readme_ratchet_removed", lambda root: replace_text(root, "examples/verified-scenario/README.md", "Technical-debt ratchet", "Removed debt ratchet")),
        ("standalone_document_release_stale", lambda root: replace_text(root, "docs/FACILITY_ARRIVAL_STANDALONE.md", "ASK-OFFLINE-RC3.8A.1", "ASK-OFFLINE-RC3.7A.2")),
        ("canonical_repository_url_regressed", lambda root: replace_text(root, "README.md", "https://github.com/SDF-01/ProjectAsklepios", "https://github.com/example/other")),
        ("live_deployment_health_claim_reintroduced", lambda root: replace_text(root, "README.md", "Clinical authority remains NOT_GRANTED.", "The live deployment is healthy. Clinical authority remains NOT_GRANTED.")),
        ("catalog_and_generated_variant_counts_conflated", lambda root: replace_text(root, "README.md", "Static exercise catalog (100 TOON-authored exercises)", "Generated scenario catalog (107 TOON-authored exercises)")),
        ("standalone_document_title_regressed", lambda root: replace_text(root, "docs/FACILITY_ARRIVAL_STANDALONE.md", "## Engine evolution and reproducibility boundary", "## Old standalone release")),
        ("policy_truth_boundary_promoted", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["truth_boundary"].__setitem__("operational_calibration", "CALIBRATED"))),
        ("checker_cli_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("cross_platform_checker_cli_and_atomic_reports"))),
        ("acyclic_release_identity_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("acyclic_release_identity_graph"))),
        ("checker_cli_guardrail_documentation_removed", lambda root: replace_text(root, "README.md", "- Checker boundary:", "- Removed checker boundary:")),
        ("canonical_writer_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("canonical_writer_independent_verifier"))),
        ("route_topology_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("reachable_terminating_route_topology"))),
        ("technical_debt_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("scoped_technical_debt_receipt_gate"))),
        ("technical_debt_ratchet_capability_removed", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["required_capabilities"].remove("monotonic_technical_debt_ratchet"))),
        ("technical_debt_ratchet_artifact_tampered", lambda root: mutate_json(root, "config/release/TECHNICAL_DEBT_RATCHET.json", lambda value: value.__setitem__("ratchet_anchor_sha256", "1" * 64), refresh=True)),
        ("artifact_authority_documentation_removed", lambda root: replace_text(root, "README.md", "- Artifact authority:", "- Removed artifact authority:")),
        ("route_topology_documentation_removed", lambda root: replace_text(root, "README.md", "- Route topology:", "- Removed route topology:")),
        ("technical_debt_documentation_removed", lambda root: replace_text(root, "README.md", "- Technical-debt ratchet: reviewed debt records, blocker classifications, evidence floors, and final receipt obligations cannot be silently removed or weakened.", "- Removed technical-debt ratchet guardrail.")),
        ("technical_debt_ratchet_identity_documentation_removed", lambda root: replace_text(root, "README.md", "asklepios-technical-debt-ratchet-v1", "removed-technical-debt-ratchet")),
        ("policy_offline_network_promoted", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["offline_guarantees"].__setitem__("network_requests", True))),
        ("windows_path_escape_rejected", lambda root: write_policy_path(root, "..\\escape.json")),
        ("absolute_path_rejected", lambda root: write_policy_path(root, "/tmp/escape.json")),
        ("symlink_artifact_rejected", lambda root: ( (root / "outside.txt").write_text("outside\n", encoding="utf-8"), (root / "examples/facility-arrival/manifest.json").unlink(), (root / "examples/facility-arrival/manifest.json").symlink_to(root / "outside.txt") )),
        ("scenario_genome_hash_forged", lambda root: mutate_json(root, "public/data/scenario_core/verified_scenario_genome.json", lambda value: value.__setitem__("genome_sha256", "2" * 64), refresh=True)),
        ("graph_stage_floor_weakened", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value.__setitem__("expected_graph_stage_count", 1)), False),
    ]


def normalized_case_registry() -> tuple[list[tuple[str, Callable[[Path], None] | None, bool]], dict[str, Any]]:
    normalized: list[tuple[str, Callable[[Path], None] | None, bool]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, specification in enumerate(cases()):
        if len(specification) == 3:
            case_id, mutation, expected_pass = specification
        else:
            case_id, mutation = specification
            expected_pass = mutation is None
        if not isinstance(case_id, str) or CASE_ID_RE.fullmatch(case_id) is None:
            errors.append(f"unsafe case ID at index {index}:{case_id!r}")
            continue
        if case_id in seen:
            errors.append(f"duplicate offline release case ID:{case_id}")
            continue
        seen.add(case_id)
        normalized.append((case_id, mutation, bool(expected_pass)))
    case_ids = [case_id for case_id, _, _ in normalized]
    registry = {
        "profile": CASE_REGISTRY_PROFILE,
        "case_ids": case_ids,
        "case_id_inventory_sha256": canonical_sha256(case_ids),
        "declared_cases": len(cases()),
        "unique_cases": len(case_ids),
        "errors": errors,
    }
    return normalized, registry


def execute_case(
    template: Path,
    fixture_parent: Path,
    index: int,
    specification: tuple[str, Callable[[Path], None] | None, bool],
) -> tuple[int, dict[str, Any]]:
    case_id, mutation, expected_pass = specification
    fixture = fixture_parent / f"case-{index:03d}-{case_id}"
    started_ns = time.monotonic_ns()
    try:
        shutil.copytree(template, fixture, symlinks=True)
        if mutation is not None:
            mutation(fixture)
        observed = run_checkers(fixture)
        classifications = {observed["python_classification"], observed["node_classification"]}
        if INTERNAL_ERROR in classifications:
            result = case_result(
                case_id,
                INTERNAL_ERROR,
                errors=[*observed["python_errors"], *observed["node_errors"]],
                **observed,
            )
        else:
            observed_pass = (
                observed["python_exit_status"] == 0
                and observed["node_exit_status"] == 0
                and classifications == {PASS}
            )
            accepted = not expected_pass and observed_pass
            passed = observed_pass if expected_pass else (
                observed["python_exit_status"] == 3
                and observed["node_exit_status"] == 3
                and classifications == {FAIL}
            )
            classification = PASS if expected_pass and passed else EXPECTED_REJECTION if not expected_pass and passed else FAIL
            result = case_result(
                case_id,
                classification,
                errors=[] if passed else ["offline release attack verdict differed"],
                is_attack=not expected_pass,
                expected_artifact_pass=expected_pass,
                observed_artifact_pass=observed_pass,
                accepted_attack=accepted,
                **observed,
            )
    except Exception as exc:  # noqa: BLE001
        result = case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])
    finally:
        shutil.rmtree(fixture, ignore_errors=True)
    result["duration_ms"] = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
    return index, result


def main() -> int:
    args = parse_args()
    source_root = args.repo.resolve(strict=True)
    started_ns = time.monotonic_ns()
    try:
        workers = validate_workers(args.workers)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "2.0.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "case_registry_profile": CASE_REGISTRY_PROFILE,
            "scheduler_profile": CASE_SCHEDULER_PROFILE,
            "source_guard_profile": SOURCE_GUARD_PROFILE,
            "errors": [f"{type(exc).__name__}:{exc}"],
            "results": [],
        }
        atomic_write_json(safe_repo_path(source_root, args.json_output.as_posix()), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return exit_code(INTERNAL_ERROR)

    results: list[dict[str, Any]] = []
    registry_cases, registry = normalized_case_registry()
    registry_ok = not registry["errors"] and registry["declared_cases"] == registry["unique_cases"]
    results.append(case_result(
        "offline-release-case-registry-is-unique",
        PASS if registry_ok else INTERNAL_ERROR,
        errors=[] if registry_ok else list(registry["errors"]),
        is_attack=False,
        declared_cases=registry["declared_cases"],
        unique_cases=registry["unique_cases"],
        case_id_inventory_sha256=registry["case_id_inventory_sha256"],
    ))

    source_before: dict[str, Any]
    try:
        source_before = source_inventory(source_root)
    except Exception as exc:  # noqa: BLE001
        source_before = {"profile": SOURCE_GUARD_PROFILE, "files": [], "root_sha256": None}
        results.append(case_result(
            "offline-release-source-inventory-readable",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
            is_attack=False,
        ))
        registry_ok = False

    if registry_ok:
        with tempfile.TemporaryDirectory(prefix="asklepios-offline-release-") as temp:
            temp_root = Path(temp)
            template = temp_root / "template"
            try:
                build_template(source_root, template)
                ownership_fixture = temp_root / "writer-ownership"
                shutil.copytree(template, ownership_fixture, symlinks=True)
                results.append(verify_writer_ownership(ownership_fixture))
                shutil.rmtree(ownership_fixture, ignore_errors=True)

                ordered: list[dict[str, Any] | None] = [None] * len(registry_cases)
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix="offline-release-case",
                ) as executor:
                    futures = {
                        executor.submit(execute_case, template, temp_root, index, specification): index
                        for index, specification in enumerate(registry_cases)
                    }
                    for future in concurrent.futures.as_completed(futures):
                        index = futures[future]
                        try:
                            returned_index, result = future.result()
                            if returned_index != index:
                                raise RuntimeError(
                                    f"offline release worker index differs:{index}:{returned_index}"
                                )
                        except Exception as exc:  # noqa: BLE001
                            case_id = registry_cases[index][0]
                            result = case_result(
                                case_id,
                                INTERNAL_ERROR,
                                errors=[f"worker failure:{type(exc).__name__}:{exc}"],
                            )
                        ordered[index] = result
                results.extend(
                    result if result is not None else case_result(
                        registry_cases[index][0],
                        INTERNAL_ERROR,
                        errors=["offline release worker did not return a result"],
                    )
                    for index, result in enumerate(ordered)
                )
            except Exception as exc:  # noqa: BLE001
                results.append(case_result(
                    "offline-release-fixture-construction",
                    INTERNAL_ERROR,
                    errors=[f"{type(exc).__name__}:{exc}"],
                    is_attack=False,
                ))

    try:
        source_after = source_inventory(source_root)
        mutations = source_mutations(source_before, source_after)
    except Exception as exc:  # noqa: BLE001
        source_after = {"profile": SOURCE_GUARD_PROFILE, "files": [], "root_sha256": None}
        mutations = [f"inventory failure:{type(exc).__name__}:{exc}"]
    source_preserved = not mutations and source_before.get("root_sha256") == source_after.get("root_sha256")
    results.append(case_result(
        "offline-release-adversarial-suite-preserves-source-tree",
        PASS if source_preserved else FAIL,
        errors=[] if source_preserved else ["offline release adversarial suite mutated guarded source"],
        is_attack=False,
        source_root_before_sha256=source_before.get("root_sha256"),
        source_root_after_sha256=source_after.get("root_sha256"),
        source_mutations=mutations,
    ))

    classification = (
        INTERNAL_ERROR
        if any(item["classification"] == INTERNAL_ERROR for item in results)
        else FAIL
        if any(item["classification"] == FAIL for item in results)
        else PASS
    )
    report = {
        "schema_version": "2.0.0",
        "classification": classification,
        "status": classification,
        "case_registry_profile": CASE_REGISTRY_PROFILE,
        "scheduler_profile": CASE_SCHEDULER_PROFILE,
        "source_guard_profile": SOURCE_GUARD_PROFILE,
        "workers": workers,
        "registry_cases": registry["unique_cases"],
        "registry_case_ids": registry["case_ids"],
        "registry_case_id_inventory_sha256": registry["case_id_inventory_sha256"],
        "source_root_before_sha256": source_before.get("root_sha256"),
        "source_root_after_sha256": source_after.get("root_sha256"),
        "source_mutations": mutations,
        "cases": len(results),
        "attacks": sum(bool(item.get("is_attack")) for item in results),
        "accepted_attacks": sum(bool(item.get("accepted_attack")) for item in results),
        "duration_ms": max(0, (time.monotonic_ns() - started_ns) // 1_000_000),
        "errors": sorted({error for item in results for error in item.get("errors", [])}),
        "results": results,
    }
    atomic_write_json(safe_repo_path(source_root, args.json_output.as_posix()), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
