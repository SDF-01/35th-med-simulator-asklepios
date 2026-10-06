#!/usr/bin/env python3
"""Enforce monotonic scenario-engine capability floors and truth boundaries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scenario_genome_common import (
    GenomeError,
    atomic_write_json,
    canonical_sha256,
    file_sha256,
    hash_without,
    is_sha256,
    load_object,
    safe_repo_path,
)

sys.dont_write_bytecode = True

POLICY_PATH = Path("config/release/SCENARIO_CAPABILITY_RATCHET.json")
COMPILED_RATCHET_ID = "asklepios-scenario-capability-ratchet-v1"
COMPILED_RATCHET_EPOCH = 5
COMPILED_RATCHET_ANCHOR = '870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e'
COMPILED_AUTHORITY_BOUNDARY = {'clinical_authority': 'NOT_GRANTED',
 'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
 'operational_calibration': 'NOT_CALIBRATED',
 'patient_care_use': 'PROHIBITED',
 'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
 'quality_vector_use': 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING',
 'scoring_behavior': 'inherited_unchanged'}
COMPILED_EXACT_INVARIANTS = {'behavior_archive_duplicate_behavior_candidates': 0,
 'behavior_archive_full_observed_cell_coverage': True,
 'behavior_archive_narrative_or_provenance_only_variants_create_new_behavior': False,
 'behavioral_equivalence_accepted_attacks': 0,
 'behavioral_equivalence_context_only_novelty': False,
 'behavioral_equivalence_narrative_only_novelty': False,
 'complete_assignment_cycle_verified_for_each_topic': True,
 'evidence_non_authoring_equals_generated_cases': True,
 'fault_challenges_fully_rejected': True,
 'missing_reviewed_factor_values': 0,
 'operational_pack_accepted_attacks': 0,
 'plain_language_summary_accepted_attacks': 0,
 'relation_checks_all_pass': True,
 'scenario_genome_cycle_free': True,
 'scenario_genome_nonterminal_dead_ends': 0,
 'scenario_genome_unreachable_nodes': 0,
 'scenario_science_accepted_attacks': 0,
 'scenario_science_timing_affects_score': False,
 'stakeholder_concrete_treatments_admitted': 0,
 'stakeholder_orphan_capabilities': 0,
 'stakeholder_product_accepted_attacks': 0,
 'stakeholder_safety_gate_can_be_averaged_away': False,
 'treatment_active_learner_choices': 0,
 'treatment_admission_accepted_attacks': 0,
 'treatment_concrete_treatments_admitted': 0,
 'uncovered_interactions': 0,
 'uncovered_pairs': 0}
COMPILED_FLOORS = {'behavior_archive': {'candidate_count': 107,
                      'candidates_with_unique_interaction_contribution': 107,
                      'elite_count': 30,
                      'minimum_cell_occupancy': 1,
                      'occupied_cell_ratio_bps': 10000,
                      'occupied_cells': 30,
                      'possible_cells_in_observed_domain': 30,
                      'total_strength_three_interactions_observed': 1543,
                      'unique_behavior_signatures': 107},
 'behavior_archive_check': {'checks': 2863},
 'behavioral_equivalence': {'candidate_count': 107,
                            'policy_equivalence_classes': 4,
                            'policy_novelty_ratio_bps': 373,
                            'unique_context_signatures': 107},
 'behavioral_equivalence_attacks': {'attacks': 12, 'cases': 13},
 'behavioral_equivalence_check': {'candidate_count': 107,
                                  'checks': 1131,
                                  'policy_equivalence_classes': 4,
                                  'unique_context_signatures': 107},
 'operational_pack': {'entries': 12, 'minimum_entries_per_profile': 3, 'profiles': 4},
 'operational_pack_attacks': {'attacks': 11, 'cases': 12},
 'plain_language_summary': {'headings': 8, 'sections': 8},
 'plain_language_summary_attacks': {'attacks': 7, 'cases': 8},
 'plain_language_summary_node': {'headings': 8, 'sections': 8},
 'scenario_contract': {'fault_challenges': 24,
                       'generated_cases': 640,
                       'independent_checks': 12190,
                       'local_checks': 26240,
                       'pair_schedule_cases': 24,
                       'topics': 5,
                       'unique_operational_contexts': 499,
                       'unique_packages': 640},
 'scenario_experience': {'covered_interactions': 1543,
                         'covering_array_strength': 3,
                         'deterministic_repeats': 107,
                         'experience_checks': 12519,
                         'feasible_assignments': 5760,
                         'generated_cases': 107,
                         'independent_checks': 16207,
                         'required_interactions': 1543,
                         'schedule_rows': 107,
                         'topics_checked': 5,
                         'total_operational_context_space_per_topic': 1152,
                         'unique_certified_packages': 107,
                         'unique_operational_contexts': 106},
 'scenario_science_attacks': {'attacks': 17, 'cases': 18},
 'scenario_science_telemetry': {'events': 4},
 'stakeholder_product': {'admitted_treatments': 0,
                         'capability_count': 9,
                         'reference_scorecards': 4,
                         'scenario_entries': 12},
 'stakeholder_product_attacks': {'attacks': 15, 'cases': 16},
 'stakeholder_product_node': {'admitted_treatments': 0,
                              'behavior_profiles': 4,
                              'checks': 139,
                              'scenario_entries': 12},
 'stakeholder_product_python': {'admitted_treatments': 0,
                                'behavior_profiles': 4,
                                'checks': 147,
                                'scenario_entries': 12},
 'treatment_admission': {'active_learner_choice_count': 0, 'entry_count': 2, 'simulation_admitted_count': 0},
 'treatment_admission_attacks': {'attacks': 11, 'cases': 12},
 'treatment_admission_node': {'active_learner_choice_count': 0,
                              'entry_count': 2,
                              'simulation_admitted_count': 0}}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def integer_metric(value: Any, label: str, errors: list[str]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"ratchet metric is not an integer:{label}")
        return -1
    return value


def policy_anchor(policy: dict[str, Any]) -> str:
    return canonical_sha256({
        "ratchet_id": policy.get("ratchet_id"),
        "ratchet_epoch": policy.get("ratchet_epoch"),
        "hard_floors": policy.get("hard_floors"),
        "exact_invariants": policy.get("exact_invariants"),
        "authority_boundary": policy.get("authority_boundary"),
    })


def validate(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    policy_path = safe_repo_path(repo, POLICY_PATH.as_posix())
    policy = load_object(policy_path)
    require(policy.get("schema_version") == "1.0.0", "scenario ratchet policy schema differs", errors)
    require(policy.get("ratchet_id") == COMPILED_RATCHET_ID, "scenario ratchet ID differs", errors)
    require(policy.get("ratchet_epoch") == COMPILED_RATCHET_EPOCH, "scenario ratchet epoch differs", errors)
    require(policy.get("authority_boundary") == COMPILED_AUTHORITY_BOUNDARY, "scenario ratchet authority boundary differs", errors)
    require(policy.get("exact_invariants") == COMPILED_EXACT_INVARIANTS, "scenario ratchet exact-invariant inventory differs", errors)
    require(policy.get("hard_floors") == COMPILED_FLOORS, "scenario ratchet hard floors differ from compiled floor", errors)
    observed_anchor = policy_anchor(policy)
    require(observed_anchor == policy.get("ratchet_anchor_sha256"), "scenario ratchet policy self-anchor mismatch", errors)
    require(observed_anchor == COMPILED_RATCHET_ANCHOR, "scenario ratchet anchor differs from compiled monotonic anchor", errors)

    source_reports = policy.get("source_reports")
    require(
        isinstance(source_reports, dict) and set(source_reports) == set(COMPILED_FLOORS),
        "scenario ratchet source report inventory differs",
        errors,
    )
    report_paths: dict[str, Path] = {}
    reports: dict[str, dict[str, Any]] = {}
    for report_id, relative in (source_reports or {}).items():
        if isinstance(relative, str):
            report_paths[report_id] = safe_repo_path(repo, relative)
    for report_id, path in sorted(report_paths.items()):
        try:
            reports[report_id] = load_object(path)
        except Exception as exc:  # noqa: BLE001
            reports[report_id] = {}
            errors.append(f"scenario capability report unavailable:{report_id}:{type(exc).__name__}:{exc}")

    experience = reports.get("scenario_experience", {})
    contract = reports.get("scenario_contract", {})
    behavior_archive = reports.get("behavior_archive", {})
    behavior_archive_check = reports.get("behavior_archive_check", {})
    behavioral_equivalence = reports.get("behavioral_equivalence", {})
    behavioral_equivalence_check = reports.get("behavioral_equivalence_check", {})
    science_telemetry = reports.get("scenario_science_telemetry", {})
    operational_pack = reports.get("operational_pack", {})
    stakeholder_product = reports.get("stakeholder_product", {})
    stakeholder_product_python = reports.get("stakeholder_product_python", {})
    stakeholder_product_node = reports.get("stakeholder_product_node", {})
    behavioral_equivalence_attacks = reports.get("behavioral_equivalence_attacks", {})
    scenario_science_attacks = reports.get("scenario_science_attacks", {})
    operational_pack_attacks = reports.get("operational_pack_attacks", {})
    stakeholder_product_attacks = reports.get("stakeholder_product_attacks", {})
    treatment_admission = reports.get("treatment_admission", {})
    treatment_admission_node = reports.get("treatment_admission_node", {})
    treatment_admission_attacks = reports.get("treatment_admission_attacks", {})
    plain_language_summary = reports.get("plain_language_summary", {})
    plain_language_summary_node = reports.get("plain_language_summary_node", {})
    plain_language_summary_attacks = reports.get("plain_language_summary_attacks", {})

    genome_relative = policy.get("genome_path")
    genome_path = safe_repo_path(repo, genome_relative) if isinstance(genome_relative, str) else repo / "INVALID"
    try:
        genome = load_object(genome_path)
    except Exception as exc:  # noqa: BLE001
        genome = {}
        errors.append(f"scenario genome unavailable:{type(exc).__name__}:{exc}")

    require(experience.get("classification") == "PASS" and experience.get("status") == "PASS", "scenario experience assurance is not PASS", errors)
    require(contract.get("status") == "PASS", "scenario contract assurance is not PASS", errors)
    require(behavior_archive.get("classification") == "PASS" and behavior_archive.get("status") == "PASS", "scenario behavior archive is not PASS", errors)
    require(behavior_archive_check.get("classification") == "PASS" and behavior_archive_check.get("status") == "PASS", "scenario behavior archive independent check is not PASS", errors)
    for label, report in (
        ("behavioral equivalence", behavioral_equivalence),
        ("behavioral equivalence independent check", behavioral_equivalence_check),
        ("scenario science telemetry", science_telemetry),
        ("operational scenario pack", operational_pack),
        ("stakeholder product", stakeholder_product),
        ("stakeholder product Python check", stakeholder_product_python),
        ("stakeholder product Node check", stakeholder_product_node),
        ("behavioral equivalence attacks", behavioral_equivalence_attacks),
        ("scenario science attacks", scenario_science_attacks),
        ("operational scenario pack attacks", operational_pack_attacks),
        ("stakeholder product attacks", stakeholder_product_attacks),
        ("treatment admission", treatment_admission),
        ("treatment admission Node check", treatment_admission_node),
        ("treatment admission attacks", treatment_admission_attacks),
        ("plain-language summary", plain_language_summary),
        ("plain-language summary Node check", plain_language_summary_node),
        ("plain-language summary attacks", plain_language_summary_attacks),
    ):
        classification = report.get("classification", report.get("status"))
        require(classification == "PASS" and report.get("status", classification) == "PASS", f"{label} is not PASS", errors)
    require(is_sha256(behavior_archive.get("archive_root_sha256")), "scenario behavior archive root malformed", errors)
    if behavior_archive:
        require(behavior_archive.get("archive_root_sha256") == hash_without(behavior_archive, "archive_root_sha256"), "scenario behavior archive self-hash mismatch at ratchet", errors)
    require(behavior_archive_check.get("archive_root_sha256") == behavior_archive.get("archive_root_sha256"), "scenario behavior archive checker root differs", errors)
    experience_archive = experience.get("behavior_archive") if isinstance(experience.get("behavior_archive"), dict) else {}
    require(experience_archive.get("archive_root_sha256") == behavior_archive.get("archive_root_sha256"), "scenario experience archive binding differs at ratchet", errors)
    require(genome.get("schema_version") == "1.0.0", "scenario genome schema differs at ratchet", errors)
    require(is_sha256(genome.get("genome_sha256")), "scenario genome hash malformed at ratchet", errors)
    if genome:
        require(genome.get("genome_sha256") == hash_without(genome, "genome_sha256"), "scenario genome self-hash mismatch at ratchet", errors)
        identity_digest = hash_without(genome, "genome_id", "genome_sha256")
        require(genome.get("genome_id") == f"ASK-GENOME-{identity_digest[:16].upper()}", "scenario genome ID mismatch at ratchet", errors)
    require(genome.get("authority_boundary") == {
        "clinical_authority": "NOT_GRANTED",
        "deployment_scope": "research_sandbox_only",
        "evidence_authority": "supporting_only",
        "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
        "operational_calibration": "NOT_CALIBRATED",
        "patient_care_use": "PROHIBITED",
        "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
        "scoring_behavior": "inherited_unchanged",
    }, "scenario genome authority boundary differs at ratchet", errors)

    covering = experience.get("covering_array") if isinstance(experience.get("covering_array"), dict) else {}
    observed_experience = {
        "generated_cases": experience.get("generated_cases"),
        "topics_checked": experience.get("topics_checked"),
        "deterministic_repeats": experience.get("deterministic_repeats"),
        "unique_certified_packages": experience.get("unique_certified_packages"),
        "unique_operational_contexts": experience.get("unique_operational_contexts"),
        "total_operational_context_space_per_topic": experience.get("total_operational_context_space_per_topic"),
        "experience_checks": experience.get("experience_checks"),
        "independent_checks": experience.get("independent_checks"),
        "covering_array_strength": covering.get("strength"),
        "feasible_assignments": covering.get("feasible_assignments"),
        "required_interactions": covering.get("required_feasible_interactions"),
        "covered_interactions": covering.get("covered_interactions"),
        "schedule_rows": covering.get("schedule_rows"),
    }
    observed_contract = {
        "generated_cases": contract.get("generated_cases"),
        "topics": contract.get("topics"),
        "unique_packages": contract.get("unique_packages"),
        "unique_operational_contexts": contract.get("unique_operational_contexts"),
        "local_checks": contract.get("local_checks"),
        "independent_checks": contract.get("independent_checks"),
        "pair_schedule_cases": contract.get("pair_schedule_cases"),
        "fault_challenges": contract.get("fault_challenges"),
    }
    archive_summary = behavior_archive.get("summary") if isinstance(behavior_archive.get("summary"), dict) else {}
    observed_archive = {
        metric: archive_summary.get(metric)
        for metric in COMPILED_FLOORS["behavior_archive"]
    }
    observed_archive_check = {
        "checks": behavior_archive_check.get("checks"),
    }
    equivalence_summary = behavioral_equivalence.get("summary") if isinstance(behavioral_equivalence.get("summary"), dict) else {}
    observed_behavioral_equivalence = {
        "candidate_count": equivalence_summary.get("candidate_count"),
        "unique_context_signatures": equivalence_summary.get("unique_context_signatures"),
        "policy_equivalence_classes": equivalence_summary.get("policy_equivalence_classes"),
        "policy_novelty_ratio_bps": equivalence_summary.get("policy_novelty_ratio_bps"),
    }
    observed_behavioral_equivalence_check = {
        "checks": behavioral_equivalence_check.get("checks"),
        "candidate_count": behavioral_equivalence_check.get("candidate_count"),
        "unique_context_signatures": behavioral_equivalence_check.get("unique_context_signatures"),
        "policy_equivalence_classes": behavioral_equivalence_check.get("policy_equivalence_classes"),
    }
    profile_counts = operational_pack.get("profile_counts") if isinstance(operational_pack.get("profile_counts"), dict) else {}
    observed_operational_pack = {
        "entries": operational_pack.get("entries"),
        "profiles": len(profile_counts),
        "minimum_entries_per_profile": min(profile_counts.values()) if profile_counts and all(isinstance(value, int) and not isinstance(value, bool) for value in profile_counts.values()) else -1,
    }
    observed_domains = {
        "scenario_experience": observed_experience,
        "scenario_contract": observed_contract,
        "behavior_archive": observed_archive,
        "behavior_archive_check": observed_archive_check,
        "behavioral_equivalence": observed_behavioral_equivalence,
        "behavioral_equivalence_check": observed_behavioral_equivalence_check,
        "scenario_science_telemetry": {"events": science_telemetry.get("events")},
        "operational_pack": observed_operational_pack,
        "stakeholder_product": {
            "scenario_entries": stakeholder_product.get("scenario_entries"),
            "capability_count": stakeholder_product.get("capability_count"),
            "reference_scorecards": stakeholder_product.get("reference_scorecards"),
            "admitted_treatments": stakeholder_product.get("admitted_treatments"),
        },
        "stakeholder_product_python": {
            "checks": stakeholder_product_python.get("checks"),
            "scenario_entries": stakeholder_product_python.get("scenario_entries"),
            "behavior_profiles": stakeholder_product_python.get("behavior_profiles"),
            "admitted_treatments": stakeholder_product_python.get("admitted_treatments"),
        },
        "stakeholder_product_node": {
            "checks": stakeholder_product_node.get("checks"),
            "scenario_entries": stakeholder_product_node.get("scenario_entries"),
            "behavior_profiles": stakeholder_product_node.get("behavior_profiles"),
            "admitted_treatments": stakeholder_product_node.get("admitted_treatments"),
        },
        "treatment_admission": {
            "entry_count": treatment_admission.get("entry_count"),
            "simulation_admitted_count": treatment_admission.get("simulation_admitted_count"),
            "active_learner_choice_count": treatment_admission.get("active_learner_choice_count"),
        },
        "treatment_admission_node": {
            "entry_count": treatment_admission_node.get("entry_count"),
            "simulation_admitted_count": treatment_admission_node.get("simulation_admitted_count"),
            "active_learner_choice_count": treatment_admission_node.get("active_learner_choice_count"),
        },
        "treatment_admission_attacks": {
            "cases": treatment_admission_attacks.get("cases"),
            "attacks": treatment_admission_attacks.get("attacks"),
        },
        "plain_language_summary": {
            "headings": plain_language_summary.get("headings"),
            "sections": plain_language_summary.get("sections"),
        },
        "plain_language_summary_node": {
            "headings": plain_language_summary_node.get("headings"),
            "sections": plain_language_summary_node.get("sections"),
        },
        "plain_language_summary_attacks": {
            "cases": plain_language_summary_attacks.get("cases"),
            "attacks": plain_language_summary_attacks.get("attacks"),
        },
        "behavioral_equivalence_attacks": {"cases": behavioral_equivalence_attacks.get("cases"), "attacks": behavioral_equivalence_attacks.get("attacks")},
        "scenario_science_attacks": {"cases": scenario_science_attacks.get("cases"), "attacks": scenario_science_attacks.get("attacks")},
        "operational_pack_attacks": {"cases": operational_pack_attacks.get("cases"), "attacks": operational_pack_attacks.get("attacks")},
        "stakeholder_product_attacks": {"cases": stakeholder_product_attacks.get("cases"), "attacks": stakeholder_product_attacks.get("attacks")},
    }
    margins: dict[str, dict[str, int]] = {domain: {} for domain in observed_domains}
    for domain, observed in observed_domains.items():
        for metric, floor in COMPILED_FLOORS[domain].items():
            value = integer_metric(observed.get(metric), f"{domain}.{metric}", errors)
            require(value >= floor, f"scenario capability regressed:{domain}.{metric}:floor={floor}:observed={value}", errors)
            margins[domain][metric] = value - floor

    require(experience.get("complete_assignment_cycle_verified_for_each_topic") is True, "scenario assignment-cycle proof regressed", errors)
    require(experience.get("missing_reviewed_factor_values") == [], "scenario reviewed factor values are missing", errors)
    require(experience.get("evidence_non_authoring_cases") == experience.get("generated_cases"), "scenario evidence non-authoring coverage regressed", errors)
    require(covering.get("uncovered_interactions", 0) == 0, "scenario covering array has uncovered interactions", errors)
    require(covering.get("covered_interactions") == covering.get("required_feasible_interactions"), "scenario covering array is incomplete", errors)
    relation_checks = contract.get("relation_checks")
    require(isinstance(relation_checks, list) and bool(relation_checks) and all(isinstance(item, dict) and item.get("pass") is True for item in relation_checks), "scenario relation assurance regressed", errors)
    require(contract.get("uncovered_pairs") == 0, "scenario pair coverage regressed", errors)
    require(contract.get("fault_challenges_rejected") == contract.get("fault_challenges"), "scenario fault-challenge rejection regressed", errors)
    require(archive_summary.get("duplicate_behavior_candidates") == 0, "scenario behavior signature uniqueness regressed", errors)
    require(archive_summary.get("occupied_cells") == archive_summary.get("possible_cells_in_observed_domain"), "scenario behavior archive observed cell coverage regressed", errors)
    require(archive_summary.get("narrative_or_provenance_only_variants_create_new_behavior") is False, "narrative or provenance-only variants were promoted to new behavior", errors)
    require(behavior_archive.get("selection_boundary") == "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING", "scenario behavior archive selection boundary regressed", errors)
    require(behavior_archive.get("truth_boundaries") == {
        "clinical_authority": "NOT_GRANTED",
        "patient_care_use": "PROHIBITED",
        "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
        "operational_timing": "NOT_CALIBRATED",
        "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
        "scoring_behavior": "inherited_unchanged",
        "quality_vector_use": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
    }, "scenario behavior archive truth boundary regressed", errors)
    require(equivalence_summary.get("narrative_or_provenance_only_changes_create_policy_novelty") is False, "narrative-only changes were promoted to policy novelty", errors)
    require(equivalence_summary.get("operational_context_change_without_policy_change_counts_as_policy_novelty") is False, "context-only changes were promoted to policy novelty", errors)
    require(equivalence_summary.get("operational_behavior_profiles_observed") == [
        "COMMUNICATION_RELAY_REQUIRED",
        "DIRECT_HANDOFF_BASELINE",
        "DUAL_CONSTRAINT_RELAY_AND_COORDINATION",
        "RESOURCE_COORDINATION_REQUIRED",
    ], "behavioral policy profile inventory differs", errors)
    require(science_telemetry.get("telemetry_profile") == "HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1", "scenario science telemetry profile differs", errors)
    require(operational_pack.get("mismatches") == [], "operational scenario pack contains mismatches", errors)
    require(profile_counts == {
        "COMMUNICATION_RELAY_REQUIRED": 3,
        "DIRECT_HANDOFF_BASELINE": 3,
        "DUAL_CONSTRAINT_RELAY_AND_COORDINATION": 3,
        "RESOURCE_COORDINATION_REQUIRED": 3,
    }, "operational scenario pack profile distribution differs", errors)
    require(stakeholder_product.get("mismatches") == [], "stakeholder product contains mismatches", errors)
    require(stakeholder_product.get("admitted_treatments") == 0, "concrete treatment was prematurely admitted", errors)
    require(treatment_admission.get("simulation_admitted_count") == 0, "treatment admission prematurely admitted concrete content", errors)
    require(treatment_admission.get("active_learner_choice_count") == 0, "unadjudicated treatment became an active learner choice", errors)
    require(treatment_admission_node.get("projection_sha256") == treatment_admission.get("projection_sha256"), "treatment admission independent projection identity differs", errors)
    require(plain_language_summary.get("summary_id") == plain_language_summary_node.get("summary_id"), "plain-language summary independent identity differs", errors)
    require(plain_language_summary.get("headings") == 8 and plain_language_summary.get("sections") == 8, "plain-language summary structure differs", errors)
    for label, report in (
        ("behavioral equivalence", behavioral_equivalence_attacks),
        ("scenario science", scenario_science_attacks),
        ("operational pack", operational_pack_attacks),
        ("stakeholder product", stakeholder_product_attacks),
        ("treatment admission", treatment_admission_attacks),
        ("plain-language summary", plain_language_summary_attacks),
    ):
        require(report.get("accepted_attacks") == 0, f"{label} accepted an adversarial regression", errors)
        require(report.get("errors") == [], f"{label} attack suite contains errors", errors)
    descriptor = genome.get("behavior_descriptor") if isinstance(genome.get("behavior_descriptor"), dict) else {}
    for metric in ("route_nodes", "route_edges", "terminal_nodes", "route_maximum_steps", "evidence_references"):
        require(integer_metric(descriptor.get(metric), f"genome.behavior_descriptor.{metric}", errors) > 0, f"scenario genome descriptor is empty:{metric}", errors)
    require(descriptor.get("cycle_free") is True, "scenario genome route-cycle invariant regressed", errors)
    require(integer_metric(descriptor.get("nonterminal_dead_ends"), "genome.behavior_descriptor.nonterminal_dead_ends", errors) == 0, "scenario genome nonterminal-dead-end invariant regressed", errors)
    require(integer_metric(descriptor.get("unreachable_nodes"), "genome.behavior_descriptor.unreachable_nodes", errors) == 0, "scenario genome reachability invariant regressed", errors)
    require(
        descriptor.get("reachable_nodes") == descriptor.get("route_nodes"),
        "scenario genome reachable-node accounting regressed",
        errors,
    )

    classification = "PASS" if not errors else "FAIL"
    return {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "ratchet_id": COMPILED_RATCHET_ID,
        "ratchet_epoch": COMPILED_RATCHET_EPOCH,
        "ratchet_anchor_sha256": COMPILED_RATCHET_ANCHOR,
        "policy_file_sha256": file_sha256(policy_path),
        "source_report_sha256": {
            name: file_sha256(path) if path.is_file() and not path.is_symlink() else None
            for name, path in sorted(report_paths.items())
        },
        "genome_sha256": genome.get("genome_sha256"),
        "observed": observed_domains,
        "floors": COMPILED_FLOORS,
        "margins": margins,
        "authority_boundary": COMPILED_AUTHORITY_BOUNDARY,
        "errors": sorted(set(errors)),
        "truth_boundary": policy.get("truth_boundary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = validate(repo)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "1.0.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    output = args.json_output or Path("reports/scenario-capability-ratchet.json")
    output = output if output.is_absolute() else repo / output
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["classification"] == "PASS" else (4 if report["classification"] == "INTERNAL_ERROR" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
