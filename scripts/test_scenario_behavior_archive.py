#!/usr/bin/env python3
"""Adversarial tests for the deterministic scenario behavior archive."""
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

from scenario_genome_common import atomic_write_json, hash_without

sys.dont_write_bytecode = True

FILES = (
    "reports/scenario-behavior-archive.json",
    "reports/scenario-experience-assurance.json",
    "scripts/check_scenario_behavior_archive.py",
    "scripts/scenario_genome_common.py",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    atomic_write_json(path, value)




def write_raw_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def prepare(source: Path, destination: Path) -> None:
    for relative in FILES:
        source_path = source / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)


def sync_archive(repo: Path) -> None:
    archive_path = repo / "reports/scenario-behavior-archive.json"
    experience_path = repo / "reports/scenario-experience-assurance.json"
    archive = read_json(archive_path)
    archive["archive_root_sha256"] = hash_without(archive, "archive_root_sha256")
    write_json(archive_path, archive)
    experience = read_json(experience_path)
    binding = experience.get("behavior_archive")
    if isinstance(binding, dict):
        binding["archive_root_sha256"] = archive["archive_root_sha256"]
        for key, value in archive.get("summary", {}).items():
            binding[key] = value
    write_json(experience_path, experience)


def run_checker(repo: Path, timeout_seconds: int = 30) -> tuple[bool, dict[str, Any]]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/check_scenario_behavior_archive.py",
                "--repo",
                ".",
                "--json-output",
                "reports/behavior-archive-test.json",
            ],
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
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-behavior-archive-mutations.json"))
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []

    def execute(
        case_id: str,
        mutation: Callable[[Path], None] | None,
        expected_pass: bool,
        required_error: str | None = None,
    ) -> None:
        print(f"START_CASE:{case_id}", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"asklepios-behavior-archive-{case_id}-") as temporary:
            repo = Path(temporary)
            prepare(source, repo)
            if mutation:
                mutation(repo)
            observed_pass, diagnostics = run_checker(repo)
            errors = diagnostics.get("checker_errors") if isinstance(diagnostics.get("checker_errors"), list) else []
            error_text = "\n".join(str(item) for item in errors)
            exact = required_error is None or required_error in error_text
            passed = observed_pass is expected_pass and exact
            classification = "PASS" if expected_pass and passed else ("EXPECTED_REJECTION" if not expected_pass and passed else "FAIL")
            result = {
                "case_id": case_id,
                "classification": classification,
                "expected_pass": expected_pass,
                "observed_pass": observed_pass,
                "required_error": required_error,
                "required_error_observed": exact,
                "pass": passed,
                **diagnostics,
            }
            results.append(result)
        print(f"END_CASE:{case_id}:{result['classification']}:{result.get('exit_status')}:{result.get('duration_ms')}", flush=True)

    archive_rel = Path("reports/scenario-behavior-archive.json")
    experience_rel = Path("reports/scenario-experience-assurance.json")

    def mutate_archive(mutation: Callable[[dict[str, Any]], None], *, sync: bool = True) -> Callable[[Path], None]:
        def apply(repo: Path) -> None:
            archive = read_json(repo / archive_rel)
            mutation(archive)
            write_json(repo / archive_rel, archive)
            if sync:
                sync_archive(repo)
        return apply

    execute("baseline", None, True)
    execute(
        "archive_root_forgery",
        mutate_archive(lambda value: value.__setitem__("archive_root_sha256", "0" * 64), sync=False),
        False,
        "behavior archive root mismatch",
    )
    execute(
        "feasible_cell_domain_profile_removed",
        mutate_archive(lambda value: value.__setitem__("cell_feasibility_profile", "MARGINAL_CARTESIAN_PRODUCT_V0")),
        False,
        "behavior cell feasibility profile differs",
    )

    def restore_marginal_cartesian_overcount(value: dict[str, Any]) -> None:
        summary = value["summary"]
        summary["possible_cells_in_observed_domain"] = summary["marginal_cartesian_cells_in_observed_domain"]
        summary["occupied_cell_ratio_bps"] = (
            summary["occupied_cells"] * 10_000 // summary["possible_cells_in_observed_domain"]
        )

    execute(
        "marginal_cartesian_overcount_rejected",
        mutate_archive(restore_marginal_cartesian_overcount),
        False,
        "behavior archive summary differs from reconstruction",
    )
    execute(
        "behavior_signature_forgery_rehashed",
        mutate_archive(lambda value: value["candidates"][0].__setitem__("behavior_signature_sha256", "1" * 64)),
        False,
        "behavior signature mismatch",
    )
    execute(
        "cell_id_forgery_rehashed",
        mutate_archive(lambda value: value["candidates"][0].__setitem__("cell_id", "ASK-QD-CELL-" + "2" * 16)),
        False,
        "behavior cell ID mismatch",
    )
    execute(
        "factor_assignment_diverges_from_descriptor",
        mutate_archive(lambda value: value["candidates"][0]["factor_assignment"].__setitem__("weather", "forged weather")),
        False,
        "factor assignment differs from behavior descriptor",
    )
    execute(
        "rarity_quality_forgery",
        mutate_archive(lambda value: value["candidates"][0]["quality_vector"].__setitem__("rarity_points", 999_999_999)),
        False,
        "rarity quality differs",
    )
    def inject_float(repo: Path) -> None:
        archive = read_json(repo / archive_rel)
        archive["candidates"][0]["quality_vector"]["rarity_points"] = 1.5
        write_raw_json(repo / archive_rel, archive)

    execute(
        "floating_quality_metric_rejected",
        inject_float,
        False,
        "floating-point value forbidden",
    )
    execute(
        "learner_scoring_authority_promotion",
        mutate_archive(lambda value: (value.__setitem__("selection_boundary", "LEARNER_SCORING"), value["truth_boundaries"].__setitem__("quality_vector_use", "LEARNER_SCORING"))),
        False,
        "behavior archive selection boundary differs",
    )
    execute(
        "human_behavior_calibration_promotion",
        mutate_archive(lambda value: value["truth_boundaries"].__setitem__("human_team_behavior", "CALIBRATED")),
        False,
        "behavior archive truth boundary differs",
    )
    execute(
        "operational_timing_calibration_promotion",
        mutate_archive(lambda value: value["truth_boundaries"].__setitem__("operational_timing", "CALIBRATED")),
        False,
        "behavior archive truth boundary differs",
    )
    execute(
        "patient_care_authority_escalation",
        mutate_archive(lambda value: value["truth_boundaries"].__setitem__("patient_care_use", "PERMITTED")),
        False,
        "behavior archive truth boundary differs",
    )

    def forge_summary(value: dict[str, Any]) -> None:
        value["summary"]["unique_behavior_signatures"] += 1
        value["summary"]["duplicate_behavior_candidates"] -= 1

    execute(
        "narrative_only_clone_falsely_counted_as_unique",
        mutate_archive(forge_summary),
        False,
        "behavior archive summary differs from reconstruction",
    )
    execute(
        "candidate_order_reversed",
        mutate_archive(lambda value: value["candidates"].reverse()),
        False,
        "behavior archive candidates are not canonically ordered",
    )
    execute(
        "cell_order_reversed",
        mutate_archive(lambda value: value["cells"].reverse()),
        False,
        "behavior archive cells are not canonically ordered",
    )

    def swap_elite(value: dict[str, Any]) -> None:
        cell = next(item for item in value["cells"] if len(item["candidate_ids"]) > 1)
        candidates = {item["candidate_id"]: item for item in value["candidates"]}
        ranked = sorted(cell["candidate_ids"], key=lambda candidate_id: (
            -candidates[candidate_id]["quality_vector"]["unique_interactions"],
            -candidates[candidate_id]["quality_vector"]["rarity_points"],
            -candidates[candidate_id]["quality_vector"]["certificate_checks_passed"],
            -candidates[candidate_id]["quality_vector"]["experience_checks"],
            -candidates[candidate_id]["quality_vector"]["independent_checks"],
            -candidates[candidate_id]["quality_vector"]["provenance_records"],
            -candidates[candidate_id]["quality_vector"]["learning_cycle_records"],
            candidates[candidate_id]["package_sha256"],
        ))
        cell["elite_candidate_id"] = ranked[-1]

    execute(
        "inferior_candidate_replaces_elite",
        mutate_archive(swap_elite),
        False,
        "behavior cell elite differs",
    )

    def remove_candidate_from_cell(value: dict[str, Any]) -> None:
        cell = next(item for item in value["cells"] if len(item["candidate_ids"]) > 1)
        cell["candidate_ids"] = cell["candidate_ids"][:-1]

    execute(
        "cell_candidate_inventory_reduced",
        mutate_archive(remove_candidate_from_cell),
        False,
        "behavior cell candidate inventory differs",
    )
    execute(
        "cell_descriptor_forged",
        mutate_archive(lambda value: value["cells"][0]["cell_descriptor"].__setitem__("communications", "normal")),
        False,
        "behavior cell descriptor differs",
    )

    def remove_realized_package(repo: Path) -> None:
        experience = read_json(repo / experience_rel)
        experience["realized_rows"] = experience["realized_rows"][1:]
        write_json(repo / experience_rel, experience)

    execute(
        "candidate_package_inventory_differs_from_covering_rows",
        remove_realized_package,
        False,
        "behavior archive candidate packages differ from realized covering rows",
    )

    def remove_behavior_relation(repo: Path) -> None:
        experience = read_json(repo / experience_rel)
        experience["relation_checks"] = [
            item for item in experience["relation_checks"]
            if item.get("id") != "narrative_only_change_does_not_create_new_behavior"
        ]
        write_json(repo / experience_rel, experience)

    execute(
        "behavior_metamorphic_guard_removed",
        remove_behavior_relation,
        False,
        "behavior archive metamorphic relation inventory incomplete",
    )

    def remove_profile_witness_relation(repo: Path) -> None:
        experience = read_json(repo / experience_rel)
        experience["relation_checks"] = [
            item for item in experience["relation_checks"]
            if item.get("id") != "profile_resource_coordination_required_graph_derived_witnesses_preserve_requirements"
        ]
        write_json(repo / experience_rel, experience)

    execute(
        "profile_route_witness_guard_removed",
        remove_profile_witness_relation,
        False,
        "behavior archive metamorphic relation inventory incomplete",
    )

    def change_archive_binding(repo: Path) -> None:
        experience = read_json(repo / experience_rel)
        experience["behavior_archive"]["archive_root_sha256"] = "f" * 64
        write_json(repo / experience_rel, experience)

    execute(
        "experience_archive_binding_forged",
        change_archive_binding,
        False,
        "scenario experience archive root differs",
    )

    failures = [item["case_id"] for item in results if not item["pass"]]
    report = {
        "schema_version": "1.0.0",
        "classification": "PASS" if not failures else "FAIL",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "expected_rejections": sum(1 for item in results if not item["expected_pass"]),
        "accepted_attacks": sum(1 for item in results if not item["expected_pass"] and item["observed_pass"]),
        "errors": failures,
        "results": results,
        "truth_boundary": "The archive selects structurally diverse scenario representatives only. It does not score learners or calibrate human behavior, operational timing, patient dynamics, or clinical authority.",
    }
    output = args.json_output if args.json_output.is_absolute() else source / args.json_output
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
