#!/usr/bin/env python3
"""Adversarial tests for the monotonic scenario capability ratchet."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from scenario_genome_common import canonical_sha256, hash_without

sys.dont_write_bytecode = True

BASE_FILES = (
    "config/release/SCENARIO_CAPABILITY_RATCHET.json",
    "public/data/scenario_core/verified_scenario_genome.json",
    "scripts/check_scenario_capability_ratchet.py",
    "scripts/scenario_genome_common.py",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def prepare(source: Path, destination: Path) -> None:
    policy = read_json(source / "config/release/SCENARIO_CAPABILITY_RATCHET.json")
    source_reports = policy.get("source_reports") if isinstance(policy.get("source_reports"), dict) else {}
    files = set(BASE_FILES) | {str(value) for value in source_reports.values() if isinstance(value, str)}
    for relative in sorted(files):
        source_path = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)


def rehash_genome(path: Path, mutation: Callable[[dict[str, Any]], None]) -> None:
    genome = read_json(path)
    mutation(genome)
    genome["genome_id"] = "PENDING"
    genome["genome_sha256"] = "PENDING"
    digest = hash_without(genome, "genome_id", "genome_sha256")
    genome["genome_id"] = f"ASK-GENOME-{digest[:16].upper()}"
    genome["genome_sha256"] = hash_without(genome, "genome_sha256")
    write_json(path, genome)



def rehash_archive(repo: Path, mutation: Callable[[dict[str, Any]], None]) -> None:
    archive_path = repo / "reports/scenario-behavior-archive.json"
    experience_path = repo / "reports/scenario-experience-assurance.json"
    archive = read_json(archive_path)
    mutation(archive)
    archive["archive_root_sha256"] = hash_without(archive, "archive_root_sha256")
    write_json(archive_path, archive)
    experience = read_json(experience_path)
    if isinstance(experience.get("behavior_archive"), dict):
        experience["behavior_archive"]["archive_root_sha256"] = archive["archive_root_sha256"]
        for key, value in archive.get("summary", {}).items():
            experience["behavior_archive"][key] = value
    write_json(experience_path, experience)


def refresh_policy_anchor(policy: dict[str, Any]) -> None:
    policy["ratchet_anchor_sha256"] = canonical_sha256({
        "ratchet_id": policy.get("ratchet_id"),
        "ratchet_epoch": policy.get("ratchet_epoch"),
        "hard_floors": policy.get("hard_floors"),
        "exact_invariants": policy.get("exact_invariants"),
        "authority_boundary": policy.get("authority_boundary"),
    })


def run_checker(repo: Path, *, timeout_seconds: int = 15) -> tuple[bool, dict[str, Any]]:
    command = [
        sys.executable,
        "scripts/check_scenario_capability_ratchet.py",
        "--repo",
        ".",
        "--json-output",
        "reports/ratchet-test.json",
    ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        return False, {
            "exit_status": 124,
            "observed_classification": "INTERNAL_ERROR",
            "checker_errors": [f"checker timeout after {timeout_seconds} seconds", output[-2000:]],
            "duration_ms": int(round((time.monotonic() - started) * 1000)),
        }
    try:
        result = json.loads(completed.stdout)
    except Exception:
        result = {"classification": "INTERNAL_ERROR", "errors": [completed.stdout[-2000:]]}
    return completed.returncode == 0 and result.get("classification") == "PASS", {
        "exit_status": completed.returncode,
        "observed_classification": result.get("classification"),
        "checker_errors": result.get("errors", []),
        "duration_ms": int(round((time.monotonic() - started) * 1000)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []

    def execute(case_id: str, mutation: Callable[[Path], None] | None, expected_pass: bool) -> None:
        print(f"START_CASE:{case_id}", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"asklepios-ratchet-{case_id}-") as temporary:
            repo = Path(temporary)
            prepare(source, repo)
            if mutation:
                mutation(repo)
            observed_pass, diagnostics = run_checker(repo)
            passed = observed_pass is expected_pass
            result = {
                "case_id": case_id,
                "classification": "PASS" if expected_pass and passed else ("EXPECTED_REJECTION" if not expected_pass and passed else "FAIL"),
                "expected_pass": expected_pass,
                "observed_pass": observed_pass,
                "pass": passed,
                **diagnostics,
            }
            results.append(result)
        print(
            f"END_CASE:{case_id}:{result['classification']}:{result.get('exit_status')}:{result.get('duration_ms')}",
            flush=True,
        )

    experience = Path("reports/scenario-experience-assurance.json")
    contract = Path("reports/scenario-contract-assurance.json")
    policy = Path("config/release/SCENARIO_CAPABILITY_RATCHET.json")
    genome = Path("public/data/scenario_core/verified_scenario_genome.json")
    archive = Path("reports/scenario-behavior-archive.json")
    archive_check = Path("reports/scenario-behavior-archive-check.json")
    plain_summary = Path("reports/plain-language-change-summary.json")

    def mutate_json(relative: Path, mutation: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
        def apply(repo: Path) -> None:
            value = read_json(repo / relative)
            mutation(value)
            write_json(repo / relative, value)
        return apply

    execute("baseline", None, True)
    execute("experience_generated_cases_regression", mutate_json(experience, lambda x: x.__setitem__("generated_cases", 106)), False)
    execute("experience_unique_context_regression", mutate_json(experience, lambda x: x.__setitem__("unique_operational_contexts", 105)), False)
    execute("experience_independent_checks_regression", mutate_json(experience, lambda x: x.__setitem__("independent_checks", 16206)), False)

    def uncover_interaction(value: dict[str, Any]) -> None:
        value["covering_array"]["covered_interactions"] = 1542
        value["covering_array"]["uncovered_interactions"] = 1

    execute("covering_array_regression", mutate_json(experience, uncover_interaction), False)
    execute("evidence_non_authoring_regression", mutate_json(experience, lambda x: x.__setitem__("evidence_non_authoring_cases", 106)), False)
    execute("contract_unique_package_regression", mutate_json(contract, lambda x: x.__setitem__("unique_packages", 639)), False)
    execute("contract_fault_rejection_regression", mutate_json(contract, lambda x: x.__setitem__("fault_challenges_rejected", 23)), False)
    execute("contract_relation_regression", mutate_json(contract, lambda x: x["relation_checks"][0].__setitem__("pass", False)), False)
    execute("behavior_archive_occupied_cell_regression", lambda repo: rehash_archive(repo, lambda x: x["summary"].__setitem__("occupied_cells", 29)), False)
    execute("behavior_archive_duplicate_signature_regression", lambda repo: rehash_archive(repo, lambda x: x["summary"].__setitem__("duplicate_behavior_candidates", 1)), False)
    execute("behavior_archive_selection_boundary_promotion", lambda repo: rehash_archive(repo, lambda x: x.__setitem__("selection_boundary", "LEARNER_SCORING")), False)
    execute("behavior_archive_checker_failure", mutate_json(archive_check, lambda x: x.__setitem__("classification", "FAIL")), False)

    def lower_policy(repo: Path) -> None:
        value = read_json(repo / policy)
        value["hard_floors"]["scenario_experience"]["generated_cases"] = 1
        value["hard_floors"]["behavior_archive"]["occupied_cells"] = 1
        refresh_policy_anchor(value)
        write_json(repo / policy, value)

    execute("policy_floor_cannot_be_lowered_even_when_reanchored", lower_policy, False)
    execute("genome_authority_promotion_rehashed", lambda repo: rehash_genome(repo / genome, lambda g: g["authority_boundary"].__setitem__("operational_calibration", "CALIBRATED")), False)
    execute("genome_route_cycle_regression", lambda repo: rehash_genome(repo / genome, lambda g: g["behavior_descriptor"].__setitem__("cycle_free", False)), False)
    execute("genome_unreachable_node_regression", lambda repo: rehash_genome(repo / genome, lambda g: g["behavior_descriptor"].__setitem__("unreachable_nodes", 1)), False)
    execute("genome_nonterminal_dead_end_regression", lambda repo: rehash_genome(repo / genome, lambda g: g["behavior_descriptor"].__setitem__("nonterminal_dead_ends", 1)), False)
    execute("genome_missing", lambda repo: (repo / genome).unlink(), False)
    execute("noninteger_metric_rejected", mutate_json(experience, lambda x: x.__setitem__("generated_cases", "107")), False)
    execute("plain_language_heading_floor_regression", mutate_json(plain_summary, lambda x: x.__setitem__("headings", 7)), False)

    failures = [item["case_id"] for item in results if not item["pass"]]
    report = {
        "schema_version": "1.0.0",
        "classification": "PASS" if not failures else "FAIL",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "expected_rejections": sum(1 for item in results if not item["expected_pass"]),
        "accepted_regressions": sum(1 for item in results if not item["expected_pass"] and item["observed_pass"]),
        "errors": failures,
        "results": results,
        "anti_circular_note": "Lowering the JSON floor and recomputing its self-anchor is rejected by the independently compiled monotonic anchor.",
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
