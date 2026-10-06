#!/usr/bin/env python3
"""Independently verify the deterministic scenario behavior archive.

The archive is a nonclinical scenario-selection index.  It must never become a
learner score, a claim of calibrated human behavior, or a source of clinical
rules.  This checker reconstructs every signature, cell, quality vector, elite,
and archive root from the durable JSON evidence.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scenario_genome_common import (
    GenomeError,
    atomic_write_json,
    canonical_sha256,
    hash_without,
    is_sha256,
    load_object,
    normalize,
    safe_repo_path,
)

sys.dont_write_bytecode = True

ARCHIVE_PATH = "reports/scenario-behavior-archive.json"
EXPERIENCE_PATH = "reports/scenario-experience-assurance.json"
DESCRIPTOR_PROFILE = "INTERPRETABLE_OPERATIONAL_BEHAVIOR_DESCRIPTOR_V1"
CELL_PROFILE = "TOPIC_COMMUNICATIONS_RESOURCES_ROUTE_SHAPE_V1"
FEASIBILITY_PROFILE = "TOPIC_X_OBSERVED_FEASIBLE_OPERATIONAL_POLICY_SHAPE_V1"
QUALITY_PROFILE = "NONCLINICAL_ASSURANCE_AND_COVERAGE_VECTOR_V1"
ARCHIVE_PROFILE = "DETERMINISTIC_QUALITY_DIVERSITY_ARCHIVE_V1"
SELECTION_BOUNDARY = "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING"
HUMAN_BEHAVIOR_BOUNDARY = "STRUCTURAL_ONLY_NOT_CALIBRATED"
QUALITY_FIELDS = (
    "unique_interactions",
    "rarity_points",
    "certificate_checks_passed",
    "experience_checks",
    "independent_checks",
    "provenance_records",
    "learning_cycle_records",
)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def integer(value: Any, label: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"nonnegative integer required:{label}")
        return 0
    return value


def sorted_record(value: dict[str, Any], label: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict) or any(not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()):
        errors.append(f"string mapping required:{label}")
        return {}
    observed_keys = list(value)
    expected_keys = sorted(observed_keys)
    require(observed_keys == expected_keys, f"mapping is not canonically ordered:{label}", errors)
    return {key: value[key] for key in expected_keys}


def interaction_keys(assignment: dict[str, str]) -> list[str]:
    entries = sorted(assignment.items())
    return [json.dumps(group, ensure_ascii=False, separators=(",", ":")) for group in itertools.combinations(entries, 3)]


def expected_cell(descriptor: dict[str, Any], errors: list[str], label: str) -> dict[str, Any]:
    context = descriptor.get("operational_context") if isinstance(descriptor.get("operational_context"), dict) else {}
    route = descriptor.get("route_shape") if isinstance(descriptor.get("route_shape"), dict) else {}
    return {
        "schema_version": "1.0.0",
        "cell_profile": CELL_PROFILE,
        "topic_id": descriptor.get("topic_id"),
        "communications": context.get("communications"),
        "resources": context.get("resources"),
        "branching_nodes": integer(route.get("branching_nodes"), f"{label}.route_shape.branching_nodes", errors),
        "maximum_route_steps": integer(route.get("maximum_route_steps"), f"{label}.route_shape.maximum_route_steps", errors),
    }


def factor_assignment_from_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
    context = descriptor.get("operational_context") if isinstance(descriptor.get("operational_context"), dict) else {}
    return {
        "communications": context.get("communications"),
        "location": context.get("location"),
        "resource_event": context.get("resource_event"),
        "resources": context.get("resources"),
        "topic": descriptor.get("topic_id"),
        "visibility": context.get("visibility"),
        "weather": context.get("weather"),
    }


def quality_tuple(candidate: dict[str, Any], errors: list[str], label: str) -> tuple[int, ...]:
    vector = candidate.get("quality_vector") if isinstance(candidate.get("quality_vector"), dict) else {}
    require(vector.get("schema_version") == "1.0.0", f"quality schema differs:{label}", errors)
    require(vector.get("quality_profile") == QUALITY_PROFILE, f"quality profile differs:{label}", errors)
    return tuple(integer(vector.get(field), f"{label}.quality_vector.{field}", errors) for field in QUALITY_FIELDS)


def candidate_sort_key(candidate: dict[str, Any], errors: list[str], label: str) -> tuple[Any, ...]:
    quality = quality_tuple(candidate, errors, label)
    package_sha = candidate.get("package_sha256") if isinstance(candidate.get("package_sha256"), str) else ""
    return tuple(-item for item in quality) + (package_sha,)


def validate(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    archive = load_object(safe_repo_path(repo, ARCHIVE_PATH))
    experience = load_object(safe_repo_path(repo, EXPERIENCE_PATH))
    # This recursively rejects floats, unsafe integers, and unsupported JSON values.
    normalize(archive)

    require(archive.get("schema_version") == "1.0.0", "behavior archive schema differs", errors)
    require(archive.get("classification") == "PASS" and archive.get("status") == "PASS", "behavior archive is not PASS", errors)
    require(archive.get("archive_profile") == ARCHIVE_PROFILE, "behavior archive profile differs", errors)
    require(archive.get("behavior_descriptor_profile") == DESCRIPTOR_PROFILE, "behavior descriptor profile differs", errors)
    require(archive.get("cell_profile") == CELL_PROFILE, "behavior cell profile differs", errors)
    require(archive.get("cell_feasibility_profile") == FEASIBILITY_PROFILE, "behavior cell feasibility profile differs", errors)
    require(archive.get("quality_profile") == QUALITY_PROFILE, "behavior quality profile differs", errors)
    require(archive.get("selection_boundary") == SELECTION_BOUNDARY, "behavior archive selection boundary differs", errors)
    require(archive.get("archive_root_sha256") == hash_without(archive, "archive_root_sha256"), "behavior archive root mismatch", errors)

    truth = archive.get("truth_boundaries") if isinstance(archive.get("truth_boundaries"), dict) else {}
    require(truth == {
        "clinical_authority": "NOT_GRANTED",
        "patient_care_use": "PROHIBITED",
        "human_team_behavior": HUMAN_BEHAVIOR_BOUNDARY,
        "operational_timing": "NOT_CALIBRATED",
        "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
        "scoring_behavior": "inherited_unchanged",
        "quality_vector_use": SELECTION_BOUNDARY,
    }, "behavior archive truth boundary differs", errors)

    candidates = archive.get("candidates") if isinstance(archive.get("candidates"), list) else []
    cells = archive.get("cells") if isinstance(archive.get("cells"), list) else []
    require(bool(candidates), "behavior archive candidate inventory is empty", errors)
    require(bool(cells), "behavior archive cell inventory is empty", errors)
    candidate_ids = [item.get("candidate_id") for item in candidates if isinstance(item, dict)]
    require(len(candidate_ids) == len(candidates), "behavior archive candidate is not an object", errors)
    require(candidate_ids == sorted(candidate_ids), "behavior archive candidates are not canonically ordered", errors)
    require(len(set(candidate_ids)) == len(candidate_ids), "behavior archive candidate ID duplicated", errors)

    package_hashes: list[str] = []
    signatures: list[str] = []
    cell_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    interaction_frequency: Counter[str] = Counter()
    preliminary: list[tuple[dict[str, Any], list[str]]] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        label = f"candidate[{index}]"
        package_sha = candidate.get("package_sha256")
        require(is_sha256(package_sha), f"package hash malformed:{label}", errors)
        if isinstance(package_sha, str):
            package_hashes.append(package_sha)
            require(candidate.get("candidate_id") == f"ASK-QD-CAND-{package_sha[:16].upper()}", f"candidate ID mismatch:{label}", errors)
        require(isinstance(candidate.get("source_scenario_id"), str) and bool(candidate.get("source_scenario_id")), f"source scenario ID missing:{label}", errors)
        require(isinstance(candidate.get("topic_id"), str) and bool(candidate.get("topic_id")), f"topic ID missing:{label}", errors)
        integer(candidate.get("seed"), f"{label}.seed", errors)
        require(isinstance(candidate.get("retriever_track"), str) and bool(candidate.get("retriever_track")), f"retriever track missing:{label}", errors)

        descriptor = candidate.get("behavior_descriptor") if isinstance(candidate.get("behavior_descriptor"), dict) else {}
        require(descriptor.get("schema_version") == "1.0.0", f"descriptor schema differs:{label}", errors)
        require(descriptor.get("descriptor_profile") == DESCRIPTOR_PROFILE, f"descriptor profile differs:{label}", errors)
        require(descriptor.get("topic_id") == candidate.get("topic_id"), f"descriptor topic differs:{label}", errors)
        signature = canonical_sha256(descriptor)
        require(candidate.get("behavior_signature_sha256") == signature, f"behavior signature mismatch:{label}", errors)
        signatures.append(signature)

        assignment = sorted_record(candidate.get("factor_assignment"), f"{label}.factor_assignment", errors)
        require(set(assignment) == {"communications", "location", "resource_event", "resources", "topic", "visibility", "weather"}, f"factor assignment inventory differs:{label}", errors)
        require(assignment == factor_assignment_from_descriptor(descriptor), f"factor assignment differs from behavior descriptor:{label}", errors)
        interactions = interaction_keys(assignment)
        interaction_frequency.update(interactions)
        preliminary.append((candidate, interactions))

        cell_descriptor = candidate.get("cell_descriptor") if isinstance(candidate.get("cell_descriptor"), dict) else {}
        expected = expected_cell(descriptor, errors, label)
        require(cell_descriptor == expected, f"behavior cell descriptor mismatch:{label}", errors)
        expected_cell_id = f"ASK-QD-CELL-{canonical_sha256(expected)[:16].upper()}"
        require(candidate.get("cell_id") == expected_cell_id, f"behavior cell ID mismatch:{label}", errors)
        if isinstance(candidate.get("cell_id"), str):
            cell_groups[candidate["cell_id"]].append(candidate)

        # Validate invariant descriptor values without claiming empirical human behavior.
        route = descriptor.get("route_shape") if isinstance(descriptor.get("route_shape"), dict) else {}
        require(route.get("topology_profile") == "REACHABLE_TERMINATING_DAG_V1", f"route topology profile differs:{label}", errors)
        require(integer(route.get("route_nodes"), f"{label}.route_nodes", errors) > 0, f"route node count empty:{label}", errors)
        require(integer(route.get("route_edges"), f"{label}.route_edges", errors) > 0, f"route edge count empty:{label}", errors)
        require(integer(route.get("terminal_nodes"), f"{label}.terminal_nodes", errors) > 0, f"terminal node count empty:{label}", errors)
        require(integer(route.get("successful_route_count"), f"{label}.successful_route_count", errors) > 0, f"successful route count empty:{label}", errors)
        actions = descriptor.get("expected_action_counts") if isinstance(descriptor.get("expected_action_counts"), dict) else {}
        require(set(actions) == {"critical", "important", "optional", "unsafe"}, f"expected-action count inventory differs:{label}", errors)
        for priority in sorted(actions):
            integer(actions.get(priority), f"{label}.expected_action_counts.{priority}", errors)

    require(len(set(package_hashes)) == len(package_hashes), "behavior archive package identity duplicated", errors)

    # Reconstruct every archive-level quality vector from the candidate inventory.
    for index, (candidate, interactions) in enumerate(preliminary):
        label = f"candidate[{index}]"
        vector = candidate.get("quality_vector") if isinstance(candidate.get("quality_vector"), dict) else {}
        expected_unique = sum(1 for key in interactions if interaction_frequency[key] == 1)
        expected_rarity = sum(1_000_000 // interaction_frequency[key] for key in interactions)
        require(vector.get("unique_interactions") == expected_unique, f"unique-interaction quality differs:{label}", errors)
        require(vector.get("rarity_points") == expected_rarity, f"rarity quality differs:{label}", errors)
        quality_tuple(candidate, errors, label)

    cell_ids = [item.get("cell_id") for item in cells if isinstance(item, dict)]
    require(len(cell_ids) == len(cells), "behavior archive cell is not an object", errors)
    require(cell_ids == sorted(cell_ids), "behavior archive cells are not canonically ordered", errors)
    require(len(set(cell_ids)) == len(cell_ids), "behavior archive cell ID duplicated", errors)
    require(set(cell_ids) == set(cell_groups), "behavior archive cell inventory differs from candidates", errors)

    candidate_by_id = {item.get("candidate_id"): item for item in candidates if isinstance(item, dict)}
    occupancies: list[int] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        label = f"cell[{index}]"
        cell_id = cell.get("cell_id")
        group = cell_groups.get(cell_id, [])
        expected_ids = sorted(item.get("candidate_id") for item in group)
        require(cell.get("candidate_ids") == expected_ids, f"behavior cell candidate inventory differs:{label}", errors)
        occupancies.append(len(expected_ids))
        require(bool(group), f"behavior cell is empty:{label}", errors)
        if group:
            descriptor = group[0].get("cell_descriptor")
            require(cell.get("cell_descriptor") == descriptor, f"behavior cell descriptor differs:{label}", errors)
            require(all(item.get("cell_descriptor") == descriptor for item in group), f"candidate cell descriptors disagree:{label}", errors)
            ranked = sorted(group, key=lambda item: candidate_sort_key(item, errors, label))
            require(cell.get("elite_candidate_id") == ranked[0].get("candidate_id"), f"behavior cell elite differs:{label}", errors)
            require(cell.get("elite_candidate_id") in candidate_by_id, f"behavior cell elite is unknown:{label}", errors)

    summary = archive.get("summary") if isinstance(archive.get("summary"), dict) else {}
    unique_signatures = len(set(signatures))
    topics = len({item.get("topic_id") for item in candidates if isinstance(item, dict)})
    communications = len({item.get("cell_descriptor", {}).get("communications") for item in candidates if isinstance(item, dict)})
    resources = len({item.get("cell_descriptor", {}).get("resources") for item in candidates if isinstance(item, dict)})
    route_shapes = len({canonical_sha256({
        "branching_nodes": item.get("cell_descriptor", {}).get("branching_nodes"),
        "maximum_route_steps": item.get("cell_descriptor", {}).get("maximum_route_steps"),
    }) for item in candidates if isinstance(item, dict)})
    feasible_operational_policy_shapes = len({canonical_sha256({
        "communications": item.get("cell_descriptor", {}).get("communications"),
        "resources": item.get("cell_descriptor", {}).get("resources"),
        "branching_nodes": item.get("cell_descriptor", {}).get("branching_nodes"),
        "maximum_route_steps": item.get("cell_descriptor", {}).get("maximum_route_steps"),
    }) for item in candidates if isinstance(item, dict)})
    possible_cells = topics * feasible_operational_policy_shapes
    marginal_cartesian_cells = topics * communications * resources * route_shapes
    infeasible_cartesian_cells_excluded = marginal_cartesian_cells - possible_cells
    require(possible_cells > 0, "observed feasible behavior-cell domain is empty", errors)
    require(
        possible_cells <= marginal_cartesian_cells and infeasible_cartesian_cells_excluded >= 0,
        "feasible behavior-cell domain exceeds marginal Cartesian envelope",
        errors,
    )
    expected_summary = {
        "candidate_count": len(candidates),
        "unique_behavior_signatures": unique_signatures,
        "duplicate_behavior_candidates": len(candidates) - unique_signatures,
        "occupied_cells": len(cells),
        "possible_cells_in_observed_domain": possible_cells,
        "feasible_operational_policy_shapes": feasible_operational_policy_shapes,
        "marginal_cartesian_cells_in_observed_domain": marginal_cartesian_cells,
        "infeasible_cartesian_cells_excluded": infeasible_cartesian_cells_excluded,
        "occupied_cell_ratio_bps": (len(cells) * 10_000) // possible_cells if possible_cells else 0,
        "elite_count": len(cells),
        "minimum_cell_occupancy": min(occupancies) if occupancies else 0,
        "maximum_cell_occupancy": max(occupancies) if occupancies else 0,
        "total_strength_three_interactions_observed": len(interaction_frequency),
        "candidates_with_unique_interaction_contribution": sum(1 for item in candidates if isinstance(item, dict) and item.get("quality_vector", {}).get("unique_interactions", 0) > 0),
        "narrative_or_provenance_only_variants_create_new_behavior": False,
    }
    require(summary == expected_summary, "behavior archive summary differs from reconstruction", errors)

    require(experience.get("schema_version") == "1.2.0", "scenario experience report schema differs for behavior archive", errors)
    require(experience.get("classification") == "PASS" and experience.get("status") == "PASS", "scenario experience report is not PASS", errors)
    experience_archive = experience.get("behavior_archive") if isinstance(experience.get("behavior_archive"), dict) else {}
    require(experience_archive.get("path") == ARCHIVE_PATH, "scenario experience archive path differs", errors)
    require(experience_archive.get("archive_root_sha256") == archive.get("archive_root_sha256"), "scenario experience archive root differs", errors)
    for key, value in expected_summary.items():
        require(experience_archive.get(key) == value, f"scenario experience archive summary differs:{key}", errors)
    realized = experience.get("realized_rows") if isinstance(experience.get("realized_rows"), list) else []
    realized_packages = sorted(item.get("package_sha256") for item in realized if isinstance(item, dict))
    require(realized_packages == sorted(package_hashes), "behavior archive candidate packages differ from realized covering rows", errors)
    covering = experience.get("covering_array") if isinstance(experience.get("covering_array"), dict) else {}
    require(expected_summary["total_strength_three_interactions_observed"] == covering.get("required_feasible_interactions"), "behavior archive interaction inventory differs from covering certificate", errors)
    relation_checks = experience.get("relation_checks") if isinstance(experience.get("relation_checks"), list) else []
    required_relations = {
        "provenance_only_change_does_not_create_new_behavior",
        "retriever_only_change_does_not_create_new_behavior",
        "narrative_only_change_does_not_create_new_behavior",
        "operational_factor_change_creates_new_behavior",
        "successful_route_witness_inventory_is_complete",
        "route_witness_replay_is_edge_order_independent",
        "every_successful_route_preserves_teamwork_requirements",
        "optional_pressure_branch_converges_before_required_teamwork",
        "profile_direct_handoff_baseline_graph_derived_witnesses_preserve_requirements",
        "profile_communication_relay_required_graph_derived_witnesses_preserve_requirements",
        "profile_resource_coordination_required_graph_derived_witnesses_preserve_requirements",
        "profile_dual_constraint_relay_and_coordination_graph_derived_witnesses_preserve_requirements",
    }
    observed_relations = {item.get("id") for item in relation_checks if isinstance(item, dict) and item.get("pass") is True}
    require(required_relations.issubset(observed_relations), "behavior archive metamorphic relation inventory incomplete", errors)

    classification = "PASS" if not errors else "FAIL"
    return {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "checks": 55 + len(candidates) * 24 + len(cells) * 8,
        "errors": sorted(set(errors)),
        "archive_profile": ARCHIVE_PROFILE,
        "candidate_count": len(candidates),
        "unique_behavior_signatures": unique_signatures,
        "occupied_cells": len(cells),
        "possible_cells_in_observed_domain": possible_cells,
        "feasible_operational_policy_shapes": feasible_operational_policy_shapes,
        "marginal_cartesian_cells_in_observed_domain": marginal_cartesian_cells,
        "infeasible_cartesian_cells_excluded": infeasible_cartesian_cells_excluded,
        "archive_root_sha256": archive.get("archive_root_sha256"),
        "selection_boundary": SELECTION_BOUNDARY,
        "human_team_behavior": HUMAN_BEHAVIOR_BOUNDARY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-behavior-archive-check.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = validate(repo)
    except GenomeError as exc:
        report = {
            "schema_version": "1.0.0",
            "classification": "FAIL",
            "status": "FAIL",
            "checks": 0,
            "errors": [str(exc)],
        }
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "1.0.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "checks": 0,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    output = args.json_output if args.json_output.is_absolute() else safe_repo_path(repo, args.json_output.as_posix())
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["classification"] == "PASS" else (4 if report["classification"] == "INTERNAL_ERROR" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
