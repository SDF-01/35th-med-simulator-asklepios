#!/usr/bin/env python3
"""Compute the evidence-bound production designation for healthcare simulation.

The designation is intentionally scoped to production healthcare-simulation
software. It never grants direct patient-care authority, clinical decision
support authority, clinical effectiveness, accreditation, high-stakes
credentialing validity, or real-world clinical timing calibration.

RC3.8A.1 treatment-admission convergence hardens this gate in four ways:

1. The production policy has a self-anchor and an independently compiled floor.
2. Required reports and receipt stages are exact monotonic inventories, not
   editable suggestions.
3. Every required report is bound to its authenticated producing-stage receipt
   from the current final release graph.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from join_scenario_evolution_evidence import (
    BEHAVIORAL_ARCHIVE_PROFILE,
    BEHAVIORAL_POLICY_FLOORS,
    BEHAVIORAL_POLICY_PROFILE,
    EVIDENCE_PROFILE as SCENARIO_EVOLUTION_EVIDENCE_PROFILE,
    REQUIRED_RECEIPT_STAGES as SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES,
    behavioral_policy_summary,
)

from release_graph_core import (
    canonical_json,
    load_graph,
    sha256_file,
    sha256_text,
    stage_map,
    write_json,
)
from release_policy_common import (
    authenticate_stage_receipt,
    classification_of,
    load_release_json,
    receipt_directory,
    require_json_pass,
    unique_nonempty_strings,
)
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

POLICY = "config/release/PRODUCTION_SIMULATION_POLICY.json"
OUTPUT = Path("reports/production-simulation-designation.json")
GRANT = "PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE_READY"
DEFAULT = "NOT_GRANTED"
POLICY_SCHEMA = "1.1.0"
POLICY_ID = "asklepios-production-simulation-v1"
POLICY_EPOCH = 9
EVIDENCE_PROFILE = 'PRODUCTION_SIMULATION_EVIDENCE_JOIN_V9'
RELEASE_GRAPH_ID = 'asklepios-rc3.8a.1-scenario-science-stakeholder-graph'
OFFLINE_RELEASE_ID = 'ASK-OFFLINE-RC3.8A.1'
COMPILED_POLICY_ANCHOR = 'fb561dc97a4b78750871faab9f70a63b2b27dedce1c5530cda6a2161f4c5824c'

CAPABILITY_RATCHET_ID = 'asklepios-scenario-capability-ratchet-v1'
CAPABILITY_RATCHET_EPOCH = 5
CAPABILITY_RATCHET_ANCHOR = '870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e'
TECHNICAL_DEBT_RATCHET_ID = 'asklepios-technical-debt-ratchet-v1'
TECHNICAL_DEBT_RATCHET_EPOCH = 8
TECHNICAL_DEBT_RATCHET_ANCHOR = '84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91'
TECHNICAL_DEBT_RATCHET_RECEIPTS = 40

MIN_GRAPH_CHECKS = 2500
MIN_GRAPH_MUTATION_CASES = 40
MIN_GRAPH_STAGES = 122
MIN_SCENARIO_EVOLUTION_RECEIPTS = len(SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES)

COMPILED_REQUIRED_REPORTS = ('reports/facility-decision-build-reproducibility.json',
 'reports/hub-runtime-smoke.json',
 'reports/hub-security.json',
 'reports/node-checker-cli-mutations.json',
 'reports/offline-scenario-release-check.json',
 'reports/offline-scenario-release-mutations.json',
 'reports/offline-scenario-release-node.json',
 'reports/operational-scenario-pack-generation.json',
 'reports/operational-scenario-pack-mutations.json',
 'reports/operational-scenario-pack-node.json',
 'reports/plain-language-change-summary-mutations.json',
 'reports/plain-language-change-summary-node.json',
 'reports/plain-language-change-summary.json',
 'reports/production-simulation-designation-mutations.json',
 'reports/release-graph-consistency.json',
 'reports/release-graph-final-evidence.json',
 'reports/release-graph-mutations.json',
 'reports/release-intended-use.json',
 'reports/release-technical-debt-final.json',
 'reports/release-technical-debt-mutations.json',
 'reports/release-technical-debt-policy.json',
 'reports/scenario-behavior-archive-check.json',
 'reports/scenario-behavior-archive-mutations.json',
 'reports/scenario-behavior-archive.json',
 'reports/scenario-behavioral-equivalence-generation.json',
 'reports/scenario-behavioral-equivalence-mutations.json',
 'reports/scenario-behavioral-equivalence-python.json',
 'reports/scenario-behavioral-equivalence.json',
 'reports/scenario-capability-ratchet-mutations.json',
 'reports/scenario-capability-ratchet.json',
 'reports/scenario-engine-evolution-doc-attacks.json',
 'reports/scenario-engine-evolution-docs-node.json',
 'reports/scenario-engine-evolution-docs-python.json',
 'reports/scenario-evolution-evidence-mutations.json',
 'reports/scenario-evolution-evidence.json',
 'reports/scenario-science-telemetry-mutations.json',
 'reports/scenario-science-telemetry-node.json',
 'reports/scenario-science-telemetry-python.json',
 'reports/simulation-quality-assurance.json',
 'reports/simulation-timing-assurance.json',
 'reports/stakeholder-product-bundle-mutations.json',
 'reports/stakeholder-product-bundle-node.json',
 'reports/stakeholder-product-bundle-python.json',
 'reports/stakeholder-product-bundle.json',
 'reports/technical-debt-ratchet-mutations.json',
 'reports/technical-debt-ratchet.json',
 'reports/treatment-admission-registry-mutations.json',
 'reports/treatment-admission-registry-node.json',
 'reports/treatment-admission-registry.json')

COMPILED_REQUIRED_RECEIPTS = ('orchestration.graph-check',
 'orchestration.graph-attacks',
 'release.intended-use-policy',
 'release.intended-use-attacks',
 'release.simulation-quality',
 'release.simulation-quality-attacks',
 'hub.security-source',
 'hub.security-attacks',
 'release.debt-ratchet',
 'release.debt-ratchet-attacks',
 'release.debt-policy',
 'release.debt-attacks',
 'release.production-policy-attacks',
 'standalone.contracts',
 'offline.release-python',
 'offline.release-node',
 'offline.release-attacks',
 'content.registry-source',
 'arrival.runtime-evidence-join',
 'decision.artifact-attacks',
 'scenario.contracts',
 'scenario.behavior-archive-check',
 'scenario.behavior-archive-attacks',
 'scenario.behavioral-policy',
 'scenario.behavioral-policy-attacks',
 'scenario.science-foundation',
 'scenario.science-foundation-check',
 'scenario.science-foundation-attacks',
 'scenario.treatment-admission',
 'scenario.treatment-admission-check',
 'scenario.treatment-admission-attacks',
 'scenario.stakeholder-product',
 'scenario.stakeholder-product-check',
 'scenario.stakeholder-product-attacks',
 'scenario.verified-example-attacks',
 'scenario.node-checker-cli-attacks',
 'scenario.engine-evolution-docs-python',
 'scenario.engine-evolution-docs-node',
 'scenario.engine-evolution-doc-attacks',
 'scenario.plain-language-summary',
 'scenario.plain-language-summary-check',
 'scenario.plain-language-summary-attacks',
 'scenario.capability-ratchet',
 'scenario.capability-ratchet-attacks',
 'scenario.evolution-evidence',
 'scenario.evolution-evidence-attacks',
 'scenario.release-validation',
 'hub.runtime-smoke',
 'simulation.timing-assurance',
 'formal.exact-audit',
 'build.app-typecheck',
 'build.double-reproducibility',
 'final.decision-evidence',
 'release.debt-evidence',
 'final.graph-evidence')

REPORT_PRODUCERS: Mapping[str, str] = {'reports/facility-decision-build-reproducibility.json': 'build.double-reproducibility',
 'reports/hub-runtime-smoke.json': 'hub.runtime-smoke',
 'reports/hub-security.json': 'hub.security-source',
 'reports/node-checker-cli-mutations.json': 'scenario.node-checker-cli-attacks',
 'reports/offline-scenario-release-check.json': 'offline.release-python',
 'reports/offline-scenario-release-mutations.json': 'offline.release-attacks',
 'reports/offline-scenario-release-node.json': 'offline.release-node',
 'reports/operational-scenario-pack-generation.json': 'scenario.stakeholder-product-check',
 'reports/operational-scenario-pack-mutations.json': 'scenario.stakeholder-product-attacks',
 'reports/operational-scenario-pack-node.json': 'scenario.stakeholder-product-check',
 'reports/plain-language-change-summary-mutations.json': 'scenario.plain-language-summary-attacks',
 'reports/plain-language-change-summary-node.json': 'scenario.plain-language-summary-check',
 'reports/plain-language-change-summary.json': 'scenario.plain-language-summary-check',
 'reports/production-simulation-designation-mutations.json': 'release.production-policy-attacks',
 'reports/release-graph-consistency.json': 'orchestration.graph-check',
 'reports/release-graph-final-evidence.json': 'final.graph-evidence',
 'reports/release-graph-mutations.json': 'orchestration.graph-attacks',
 'reports/release-intended-use.json': 'release.intended-use-policy',
 'reports/release-technical-debt-final.json': 'release.debt-evidence',
 'reports/release-technical-debt-mutations.json': 'release.debt-attacks',
 'reports/release-technical-debt-policy.json': 'release.debt-policy',
 'reports/scenario-behavior-archive-check.json': 'scenario.behavior-archive-check',
 'reports/scenario-behavior-archive-mutations.json': 'scenario.behavior-archive-attacks',
 'reports/scenario-behavior-archive.json': 'scenario.contracts',
 'reports/scenario-behavioral-equivalence-generation.json': 'scenario.behavioral-policy',
 'reports/scenario-behavioral-equivalence-mutations.json': 'scenario.behavioral-policy-attacks',
 'reports/scenario-behavioral-equivalence-python.json': 'scenario.behavioral-policy',
 'reports/scenario-behavioral-equivalence.json': 'scenario.behavioral-policy',
 'reports/scenario-capability-ratchet-mutations.json': 'scenario.capability-ratchet-attacks',
 'reports/scenario-capability-ratchet.json': 'scenario.capability-ratchet',
 'reports/scenario-engine-evolution-doc-attacks.json': 'scenario.engine-evolution-doc-attacks',
 'reports/scenario-engine-evolution-docs-node.json': 'scenario.engine-evolution-docs-node',
 'reports/scenario-engine-evolution-docs-python.json': 'scenario.engine-evolution-docs-python',
 'reports/scenario-evolution-evidence-mutations.json': 'scenario.evolution-evidence-attacks',
 'reports/scenario-evolution-evidence.json': 'scenario.evolution-evidence',
 'reports/scenario-science-telemetry-mutations.json': 'scenario.science-foundation-attacks',
 'reports/scenario-science-telemetry-node.json': 'scenario.science-foundation-check',
 'reports/scenario-science-telemetry-python.json': 'scenario.science-foundation-check',
 'reports/simulation-quality-assurance.json': 'release.simulation-quality',
 'reports/simulation-timing-assurance.json': 'simulation.timing-assurance',
 'reports/stakeholder-product-bundle-mutations.json': 'scenario.stakeholder-product-attacks',
 'reports/stakeholder-product-bundle-node.json': 'scenario.stakeholder-product-check',
 'reports/stakeholder-product-bundle-python.json': 'scenario.stakeholder-product-check',
 'reports/stakeholder-product-bundle.json': 'scenario.stakeholder-product-check',
 'reports/technical-debt-ratchet-mutations.json': 'release.debt-ratchet-attacks',
 'reports/technical-debt-ratchet.json': 'release.debt-ratchet',
 'reports/treatment-admission-registry-mutations.json': 'scenario.treatment-admission-attacks',
 'reports/treatment-admission-registry-node.json': 'scenario.treatment-admission-check',
 'reports/treatment-admission-registry.json': 'scenario.treatment-admission-check'}

EXPECTED_CAPABILITY_AUTHORITY = {'clinical_authority': 'NOT_GRANTED',
 'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
 'operational_calibration': 'NOT_CALIBRATED',
 'patient_care_use': 'PROHIBITED',
 'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
 'quality_vector_use': 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING',
 'scoring_behavior': 'inherited_unchanged'}

CAPABILITY_FLOORS = {'behavior_archive': {'candidate_count': 107,
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
 'treatment_admission_node': {'active_learner_choice_count': 0, 'entry_count': 2, 'simulation_admitted_count': 0}}


def policy_anchor(policy: Mapping[str, Any]) -> str:
    payload = dict(policy)
    payload.pop("policy_anchor_sha256", None)
    return sha256_text(canonical_json(payload))


def _exact_pass_descriptors(paths: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"classification": PASS, "path": path} for path in paths]


def _integer_at_least(value: Any, floor: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _all_result_case_ids(report: Mapping[str, Any]) -> set[str]:
    results = report.get("results")
    if not isinstance(results, list):
        return set()
    return {
        str(item.get("case_id"))
        for item in results
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def evaluate(root: Path, receipt_dir: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        policy = load_release_json(root, POLICY, errors)
        graph = load_graph(root)
        if policy is None:
            raise ValueError("production simulation policy missing")
        stages = stage_map(graph)

        observed_policy_anchor = policy_anchor(policy)
        require(policy.get("schema_version") == POLICY_SCHEMA, "production simulation schema differs")
        require(policy.get("policy_id") == POLICY_ID, "production simulation policy ID differs")
        require(policy.get("policy_epoch") == POLICY_EPOCH, "production simulation policy epoch differs")
        require(policy.get("evidence_profile") == EVIDENCE_PROFILE, "production simulation evidence profile differs")
        require(policy.get("policy_anchor_sha256") == observed_policy_anchor, "production simulation policy self-anchor differs")
        require(observed_policy_anchor == COMPILED_POLICY_ANCHOR, "production simulation policy differs from compiled monotonic floor")
        require(policy.get("default_designation") == DEFAULT, "production simulation default is not fail-closed")
        require(policy.get("grantable_designation") == GRANT, "production simulation grantable designation differs")
        require(policy.get("designation_vocabulary") == [DEFAULT, GRANT], "production simulation designation vocabulary differs")

        scope = policy.get("designation_scope", {})
        includes = scope.get("includes")
        excludes = scope.get("excludes")
        require(unique_nonempty_strings(includes), "production simulation included scope invalid")
        require(unique_nonempty_strings(excludes), "production simulation excluded scope invalid")
        for included in (
            "software_build_and_runtime_readiness",
            "reviewed_source_bound_scenarios",
            "deterministic_simulation_orchestration",
            "facilitator_and_learner_interfaces",
            "simulated_patient_care_workflows",
            "secure_multiplayer_exercise_coordination",
        ):
            require(included in (includes or []), f"production simulation inclusion missing:{included}")

        for excluded in (
            "direct_patient_care",
            "clinical_decision_support",
            "clinical_effectiveness",
            "facility_specific_timing_accuracy",
            "program_accreditation",
            "high_stakes_credentialing",
        ):
            require(excluded in (excludes or []), f"production simulation exclusion missing:{excluded}")

        rules = policy.get("grant_rules", {})
        for key in (
            "all_required_receipts_authenticated",
            "all_required_reports_pass",
            "clinical_operational_timing_remains_not_calibrated",
            "direct_patient_care_remains_prohibited",
            "simulation_logical_clock_validated",
            "simulated_patient_care_workflows_permitted_within_validated_scope",
            "hub_authorization_and_identity_controls_validated",
        ):
            require(rules.get(key) is True, f"production simulation grant rule disabled:{key}")
        require(rules.get("known_release_blockers_remaining") == 0, "production simulation blocker threshold differs")

        contract = policy.get("evidence_contract", {})
        require(contract.get("release_graph_id") == RELEASE_GRAPH_ID, "production evidence graph ID differs")
        require(contract.get("offline_release_id") == OFFLINE_RELEASE_ID, "production evidence offline release ID differs")
        require(contract.get("minimum_release_graph_checks") == MIN_GRAPH_CHECKS, "production evidence graph-check floor differs")
        require(contract.get("minimum_release_graph_mutation_cases") == MIN_GRAPH_MUTATION_CASES, "production evidence graph-mutation floor differs")
        require(contract.get("minimum_release_graph_stages") == MIN_GRAPH_STAGES, "production evidence graph-stage floor differs")
        require(contract.get("minimum_scenario_evolution_authenticated_receipts") == MIN_SCENARIO_EVOLUTION_RECEIPTS, "production evidence scenario-receipt floor differs")
        capability_contract = contract.get("scenario_capability_ratchet", {})
        require(capability_contract == {
            "ratchet_id": CAPABILITY_RATCHET_ID,
            "ratchet_epoch": CAPABILITY_RATCHET_EPOCH,
            "ratchet_anchor_sha256": CAPABILITY_RATCHET_ANCHOR,
        }, "production evidence capability-ratchet contract differs")
        debt_contract = contract.get("technical_debt_ratchet", {})
        require(debt_contract == {
            "ratchet_id": TECHNICAL_DEBT_RATCHET_ID,
            "ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
            "ratchet_anchor_sha256": TECHNICAL_DEBT_RATCHET_ANCHOR,
            "required_receipt_count": TECHNICAL_DEBT_RATCHET_RECEIPTS,
        }, "production evidence technical-debt-ratchet contract differs")

        truth = graph.get("truth_boundaries", {})
        require(graph.get("graph_id") == RELEASE_GRAPH_ID, "current release graph ID differs from production evidence contract")
        require(len(graph.get("stages", [])) >= MIN_GRAPH_STAGES, "current release graph stage count regressed")
        require(graph.get("production_designation") == DEFAULT, "static graph production designation is not fail-closed")
        require(truth.get("healthcare_simulation_training") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "graph simulation intended-use boundary differs")
        require(truth.get("simulated_patient_care_workflows") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "graph simulated patient-care workflow boundary differs")
        require(truth.get("simulation_logical_timing") == "VALIDATED_FOR_DETERMINISTIC_SIMULATION", "graph simulation timing boundary differs")
        require(truth.get("clinical_operational_timing") == "NOT_CALIBRATED", "graph clinical timing boundary was promoted")
        require(truth.get("clinical_timing_transferability") == "NOT_ESTABLISHED", "graph clinical timing transferability was promoted")
        require(truth.get("direct_patient_care") == "PROHIBITED", "graph direct patient care boundary was promoted")
        require(truth.get("clinical_decision_support") == "PROHIBITED", "graph clinical decision support boundary was promoted")
        require(truth.get("patient_care_use") == "PROHIBITED", "legacy patient-care boundary was promoted")
        require(truth.get("production_ready") is False, "legacy clinical production-ready flag was promoted")

        required_reports = policy.get("required_reports")
        require(required_reports == _exact_pass_descriptors(COMPILED_REQUIRED_REPORTS), "production simulation report inventory differs from compiled floor")
        reports: dict[str, dict[str, Any]] = {}
        for relative in COMPILED_REQUIRED_REPORTS:
            report = require_json_pass(root, relative, errors)
            if report is not None:
                reports[relative] = report

        required_receipts = policy.get("required_stage_receipts")
        require(required_receipts == list(COMPILED_REQUIRED_RECEIPTS), "production simulation receipt inventory differs from compiled floor")
        for stage_id in COMPILED_REQUIRED_RECEIPTS:
            require(stage_id in stages, f"production simulation evidence stage absent:{stage_id}")

        graph_report = reports.get("reports/release-graph-consistency.json", {})
        require(graph_report.get("graph_id") == RELEASE_GRAPH_ID, "release graph report ID differs")
        require(graph_report.get("stages") == len(graph.get("stages", [])), "release graph report stage count differs")
        require(_integer_at_least(graph_report.get("stages"), MIN_GRAPH_STAGES), "release graph stage floor regressed")
        require(_integer_at_least(graph_report.get("checks"), MIN_GRAPH_CHECKS), "release graph structural-check floor regressed")
        require(graph_report.get("errors") == [], "release graph report contains errors")

        graph_attacks = reports.get("reports/release-graph-mutations.json", {})
        require(_integer_at_least(graph_attacks.get("cases"), MIN_GRAPH_MUTATION_CASES), "release graph adversarial-case floor regressed")
        require(graph_attacks.get("errors") == [], "release graph adversarial report contains errors")

        intended = reports.get("reports/release-intended-use.json", {})
        require(intended.get("healthcare_simulation_training") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "intended-use report does not permit validated simulation")
        require(intended.get("simulated_patient_care_workflows") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "intended-use report does not permit validated simulated patient-care workflows")
        require(intended.get("direct_patient_care") == "PROHIBITED", "intended-use report promoted direct patient care")
        require(intended.get("clinical_decision_support") == "PROHIBITED", "intended-use report promoted CDS")

        quality = reports.get("reports/simulation-quality-assurance.json", {})
        require(quality.get("scope") == "reviewed_healthcare_simulation_scenarios", "simulation quality scope differs")
        require(quality.get("learner_answer_leakage_findings", 1) == 0, "simulation quality reports learner answer leakage")
        require(quality.get("reachable_active_dead_ends", 1) == 0, "simulation quality reports reachable active dead ends")
        require(quality.get("strength_three_coverage_ratio") == 1.0, "simulation quality strength-three coverage regressed")

        timing = reports.get("reports/simulation-timing-assurance.json", {})
        require(timing.get("simulation_logical_clock") == "VALIDATED_FOR_DETERMINISTIC_SIMULATION", "simulation timing was not validated")
        require(timing.get("clinical_operational_timing") == "NOT_CALIBRATED", "clinical operational timing was promoted in timing evidence")
        require(timing.get("clinical_timing_transferability") == "NOT_ESTABLISHED", "clinical timing transferability was promoted in timing evidence")
        require(timing.get("clinical_timing_calibrated") is False, "timing evidence asserts clinical calibration")
        require(timing.get("response_time_budgets_met") is True, "software response-time engineering budget not met")

        hub_source = reports.get("reports/hub-security.json", {})
        require(hub_source.get("direct_patient_care") == "PROHIBITED", "hub security report promoted direct patient care")
        require(hub_source.get("clinical_decision_support") == "PROHIBITED", "hub security report promoted CDS")

        hub_runtime = reports.get("reports/hub-runtime-smoke.json", {})
        require(hub_runtime.get("direct_patient_care") == "PROHIBITED", "hub runtime promoted direct patient care")
        require(hub_runtime.get("clinical_decision_support") == "PROHIBITED", "hub runtime promoted CDS")
        require(hub_runtime.get("healthcare_simulation_training") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "hub runtime simulation scope differs")
        response_time = hub_runtime.get("response_time", {})
        require(_integer_at_least(response_time.get("samples"), 40), "hub runtime response sample too small")
        require(isinstance(response_time.get("p99_ms"), (int, float)) and response_time.get("p99_ms") <= response_time.get("engineering_budget_p99_ms", 0), "hub runtime response budget exceeded")

        build = reports.get("reports/facility-decision-build-reproducibility.json", {})
        require(_integer_at_least(build.get("files_compared"), 1), "production build compared no files")
        require(build.get("first_build_root_sha256") == build.get("second_build_root_sha256"), "production builds are not byte-identical")
        require(build.get("source_mutations") == [], "production build mutated reviewed source")
        require(build.get("provenance", {}).get("status") == PASS, "production build provenance not PASS")

        offline_python = reports.get("reports/offline-scenario-release-check.json", {})
        require(offline_python.get("schema_version") == "1.2.0", "offline Python release schema differs")
        require(offline_python.get("release_id") == OFFLINE_RELEASE_ID, "offline Python release ID differs")
        require(offline_python.get("graph_id") == RELEASE_GRAPH_ID, "offline Python graph ID differs")
        require(offline_python.get("capability_ratchet_epoch") == CAPABILITY_RATCHET_EPOCH, "offline Python capability epoch differs")
        require(offline_python.get("technical_debt_ratchet_epoch") == TECHNICAL_DEBT_RATCHET_EPOCH, "offline Python debt epoch differs")
        require(_integer_at_least(offline_python.get("artifacts"), 10), "offline Python artifact inventory regressed")
        require(offline_python.get("mismatches") == [], "offline Python release reports mismatches")

        offline_node = reports.get("reports/offline-scenario-release-node.json", {})
        require(offline_node.get("checker_profile") == "INDEPENDENT_NODE_OFFLINE_SCENARIO_RELEASE_V5", "offline Node checker profile differs")
        require(offline_node.get("release_id") == OFFLINE_RELEASE_ID, "offline Node release ID differs")
        require(offline_node.get("graph_id") == RELEASE_GRAPH_ID, "offline Node graph ID differs")
        require(offline_node.get("capability_ratchet_epoch") == CAPABILITY_RATCHET_EPOCH, "offline Node capability epoch differs")
        require(offline_node.get("technical_debt_ratchet_epoch") == TECHNICAL_DEBT_RATCHET_EPOCH, "offline Node debt epoch differs")
        require(_integer_at_least(offline_node.get("artifacts"), 10), "offline Node artifact inventory regressed")
        require(offline_node.get("release_sha256") == offline_python.get("release_sha256"), "offline independent release identities differ")

        offline_attacks = reports.get("reports/offline-scenario-release-mutations.json", {})
        require(_integer_at_least(offline_attacks.get("cases"), 42), "offline release adversarial-case floor regressed")
        require(_integer_at_least(offline_attacks.get("attacks"), 39), "offline release attack floor regressed")
        require(offline_attacks.get("accepted_attacks") == 0, "offline release attack was accepted")

        docs_python = reports.get("reports/scenario-engine-evolution-docs-python.json", {})
        docs_node = reports.get("reports/scenario-engine-evolution-docs-node.json", {})
        for label, report, profile in (
            ("Python", docs_python, "PYTHON_ENGINE_EVOLUTION_DOCUMENTATION_V4"),
            ("Node", docs_node, "INDEPENDENT_NODE_ENGINE_EVOLUTION_DOCUMENTATION_V5"),
        ):
            require(report.get("checker_profile") == profile, f"engine documentation {label} profile differs")
            require(report.get("release_id") == OFFLINE_RELEASE_ID, f"engine documentation {label} release ID differs")
            require(report.get("graph_id") == RELEASE_GRAPH_ID, f"engine documentation {label} graph ID differs")
            require(report.get("capability_ratchet_epoch") == CAPABILITY_RATCHET_EPOCH, f"engine documentation {label} capability epoch differs")
            require(report.get("technical_debt_ratchet_epoch") == TECHNICAL_DEBT_RATCHET_EPOCH, f"engine documentation {label} debt epoch differs")
            require(_integer_at_least(report.get("documents"), 4), f"engine documentation {label} inventory regressed")
        require(docs_python.get("genome_id") == docs_node.get("genome_id"), "engine documentation independent Genome identities differ")

        docs_attacks = reports.get("reports/scenario-engine-evolution-doc-attacks.json", {})
        require(_integer_at_least(docs_attacks.get("cases"), 23), "engine documentation adversarial-case floor regressed")
        require(_integer_at_least(docs_attacks.get("attacks"), 22), "engine documentation attack floor regressed")
        require(docs_attacks.get("accepted_attacks") == 0, "engine documentation attack was accepted")

        cli_attacks = reports.get("reports/node-checker-cli-mutations.json", {})
        require(_integer_at_least(cli_attacks.get("cases"), 20), "Node checker CLI case floor regressed")
        require(_integer_at_least(cli_attacks.get("checker_count"), 3), "Node checker CLI checker inventory regressed")
        require(_integer_at_least(cli_attacks.get("expected_rejections"), 9), "Node checker CLI rejection floor regressed")
        require(cli_attacks.get("accepted_attacks") == 0, "Node checker CLI attack was accepted")

        behavior_archive = reports.get("reports/scenario-behavior-archive.json", {})
        behavior_summary = behavior_archive.get("summary", {}) if isinstance(behavior_archive.get("summary"), dict) else {}
        behavior_truth = behavior_archive.get("truth_boundaries", {}) if isinstance(behavior_archive.get("truth_boundaries"), dict) else {}
        require(behavior_archive.get("schema_version") == "1.0.0", "scenario behavior archive schema differs")
        require(behavior_archive.get("selection_boundary") == "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING", "scenario behavior archive was promoted to learner scoring")
        require(behavior_truth.get("human_team_behavior") == "STRUCTURAL_ONLY_NOT_CALIBRATED", "scenario behavior archive falsely calibrated human behavior")
        require(behavior_truth.get("clinical_authority") == "NOT_GRANTED", "scenario behavior archive grants clinical authority")
        require(behavior_truth.get("patient_care_use") == "PROHIBITED", "scenario behavior archive grants patient-care use")
        for metric, floor in CAPABILITY_FLOORS["behavior_archive"].items():
            require(_integer_at_least(behavior_summary.get(metric), floor), f"scenario behavior archive regressed:{metric}")
        require(behavior_summary.get("duplicate_behavior_candidates") == 0, "scenario behavior archive contains duplicate behavior candidates")
        require(behavior_summary.get("narrative_or_provenance_only_variants_create_new_behavior") is False, "scenario behavior archive accepts cosmetic diversity")

        behavior_check = reports.get("reports/scenario-behavior-archive-check.json", {})
        require(behavior_check.get("archive_root_sha256") == behavior_archive.get("archive_root_sha256"), "scenario behavior archive checker root differs")
        require(_integer_at_least(behavior_check.get("checks"), CAPABILITY_FLOORS["behavior_archive_check"]["checks"]), "scenario behavior archive independent-check floor regressed")
        require(behavior_check.get("selection_boundary") == "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING", "scenario behavior archive checker selection boundary differs")

        behavior_attacks = reports.get("reports/scenario-behavior-archive-mutations.json", {})
        require(_integer_at_least(behavior_attacks.get("cases"), 20), "scenario behavior archive mutation-case floor regressed")
        require(_integer_at_least(behavior_attacks.get("expected_rejections"), 19), "scenario behavior archive rejection floor regressed")
        require(behavior_attacks.get("accepted_attacks") == 0, "scenario behavior archive attack was accepted")

        behavioral = reports.get("reports/scenario-behavioral-equivalence.json", {})
        behavioral_generation = reports.get("reports/scenario-behavioral-equivalence-generation.json", {})
        behavioral_check = reports.get("reports/scenario-behavioral-equivalence-python.json", {})
        behavioral_attacks = reports.get("reports/scenario-behavioral-equivalence-mutations.json", {})
        behavioral_summary = behavioral_policy_summary(behavioral)
        require(behavioral.get("archive_profile") == BEHAVIORAL_ARCHIVE_PROFILE, "behavioral-policy archive profile differs")
        require(behavioral.get("policy_profile") == BEHAVIORAL_POLICY_PROFILE, "behavioral-policy signature profile differs")
        for metric, floor in BEHAVIORAL_POLICY_FLOORS.items():
            require(_integer_at_least(behavioral_summary.get(metric), floor), f"behavioral-policy floor regressed:{metric}")
            require(behavioral_generation.get(metric) == behavioral_summary.get(metric), f"behavioral-policy generation summary differs:{metric}")
        require(behavioral_generation.get("archive_root_sha256") == behavioral.get("archive_root_sha256"), "behavioral-policy generation archive root differs")
        require(behavioral_check.get("archive_root_sha256") == behavioral.get("archive_root_sha256"), "behavioral-policy independent archive root differs")
        require(behavioral_check.get("policy_equivalence_classes") == behavioral_summary.get("policy_equivalence_classes") and behavioral_check.get("unique_context_signatures") == behavioral_summary.get("unique_context_signatures") and _integer_at_least(behavioral_check.get("checks"), 1131), "behavioral-policy independent checker floor differs")
        require(_integer_at_least(behavioral_attacks.get("cases"), 13) and behavioral_attacks.get("accepted_attacks") == 0, "behavioral-policy attack boundary differs")

        telemetry_python = reports.get("reports/scenario-science-telemetry-python.json", {})
        telemetry_node = reports.get("reports/scenario-science-telemetry-node.json", {})
        telemetry_attacks = reports.get("reports/scenario-science-telemetry-mutations.json", {})
        require(telemetry_python.get("telemetry_profile") == "HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1", "scenario-science telemetry profile differs")
        require(telemetry_python.get("event_chain_root_sha256") == telemetry_node.get("event_chain_root_sha256"), "scenario-science telemetry independent roots differ")
        require(_integer_at_least(telemetry_attacks.get("cases"), 18) and telemetry_attacks.get("accepted_attacks") == 0, "scenario-science telemetry attack boundary differs")

        pack = reports.get("reports/operational-scenario-pack-generation.json", {})
        pack_node = reports.get("reports/operational-scenario-pack-node.json", {})
        pack_attacks = reports.get("reports/operational-scenario-pack-mutations.json", {})
        profile_counts = pack.get("profile_counts", {}) if isinstance(pack.get("profile_counts"), dict) else {}
        require(sum(profile_counts.values()) == 12 and set(profile_counts.values()) == {3}, "operational scenario pack is not balanced 12-by-four")
        require(pack.get("catalog_root_sha256") == pack_node.get("catalog_root_sha256"), "operational scenario pack independent root differs")
        require(_integer_at_least(pack_attacks.get("cases"), 12) and pack_attacks.get("accepted_attacks") == 0, "operational scenario pack attack boundary differs")

        stakeholder = reports.get("reports/stakeholder-product-bundle.json", {})
        stakeholder_python = reports.get("reports/stakeholder-product-bundle-python.json", {})
        stakeholder_node = reports.get("reports/stakeholder-product-bundle-node.json", {})
        stakeholder_attacks = reports.get("reports/stakeholder-product-bundle-mutations.json", {})
        require(stakeholder.get("capability_count") == 9, "stakeholder capability count differs")
        require(stakeholder.get("reference_scorecards") == 4, "stakeholder scorecard inventory differs")
        require(stakeholder.get("admitted_treatments") == 0, "stakeholder bundle admits a treatment")
        require(stakeholder_python.get("scenario_entries") == 12 and stakeholder_node.get("scenario_entries") == 12, "stakeholder independent scenario inventory differs")
        require(stakeholder_python.get("admitted_treatments") == 0 and stakeholder_node.get("admitted_treatments") == 0, "stakeholder independent checker admits treatment")
        require(_integer_at_least(stakeholder_attacks.get("cases"), 16) and stakeholder_attacks.get("accepted_attacks") == 0, "stakeholder product attack boundary differs")

        treatment = reports.get("reports/treatment-admission-registry.json", {})
        treatment_node = reports.get("reports/treatment-admission-registry-node.json", {})
        treatment_attacks = reports.get("reports/treatment-admission-registry-mutations.json", {})
        require(treatment.get("entry_count") == 2, "treatment registry inventory differs")
        require(treatment.get("simulation_admitted_count") == 0 and treatment.get("active_learner_choice_count") == 0, "unadjudicated treatment became active")
        require(treatment.get("projection_sha256") == treatment_node.get("projection_sha256"), "treatment registry independent projection differs")
        require(treatment_node.get("entry_count") == 2 and treatment_node.get("simulation_admitted_count") == 0 and treatment_node.get("active_learner_choice_count") == 0, "treatment Node checker floor differs")
        require(_integer_at_least(treatment_attacks.get("cases"), 12) and treatment_attacks.get("accepted_attacks") == 0, "treatment admission attack boundary differs")

        plain_summary = reports.get("reports/plain-language-change-summary.json", {})
        plain_node = reports.get("reports/plain-language-change-summary-node.json", {})
        plain_attacks = reports.get("reports/plain-language-change-summary-mutations.json", {})
        require(plain_summary.get("summary_id") == "asklepios-rc3.8d-plain-language-change-summary", "plain-language summary identity differs")
        require(plain_summary.get("headings") == 8 and plain_summary.get("sections") == 8, "plain-language summary structural floor differs")
        require(plain_node.get("summary_id") == plain_summary.get("summary_id"), "plain-language independent identity differs")
        require(plain_node.get("headings") == 8 and plain_node.get("sections") == 8, "plain-language independent structural floor differs")
        require(_integer_at_least(plain_attacks.get("cases"), 8) and plain_attacks.get("accepted_attacks") == 0, "plain-language attack boundary differs")

        capability = reports.get("reports/scenario-capability-ratchet.json", {})
        require(capability.get("ratchet_id") == CAPABILITY_RATCHET_ID, "scenario capability ratchet ID differs")
        require(capability.get("ratchet_epoch") == CAPABILITY_RATCHET_EPOCH, "scenario capability ratchet epoch differs")
        require(capability.get("ratchet_anchor_sha256") == CAPABILITY_RATCHET_ANCHOR, "scenario capability ratchet anchor differs")
        require(capability.get("authority_boundary") == EXPECTED_CAPABILITY_AUTHORITY, "scenario capability authority boundary differs")
        floors = capability.get("floors", {})
        observed = capability.get("observed", {})
        require(floors == CAPABILITY_FLOORS, "scenario capability floor differs from compiled production floor")
        for domain, metrics in CAPABILITY_FLOORS.items():
            observed_domain = observed.get(domain, {})
            for metric, floor in metrics.items():
                require(_integer_at_least(observed_domain.get(metric), floor), f"scenario capability regressed:{domain}.{metric}")

        capability_attacks = reports.get("reports/scenario-capability-ratchet-mutations.json", {})
        require(_integer_at_least(capability_attacks.get("cases"), 20), "scenario capability mutation-case floor regressed")
        require(_integer_at_least(capability_attacks.get("expected_rejections"), 19), "scenario capability rejection floor regressed")
        require(capability_attacks.get("accepted_regressions") == 0, "scenario capability regression was accepted")

        evolution = reports.get("reports/scenario-evolution-evidence.json", {})
        require(evolution.get("schema_version") == "3.0.0", "scenario evolution evidence schema differs")
        require(evolution.get("evidence_profile") == SCENARIO_EVOLUTION_EVIDENCE_PROFILE, "scenario evolution evidence profile differs")
        require(evolution.get("receipt_binding_mode") == "GRAPH_RECEIPTS_REQUIRED", "scenario evolution evidence is not graph-receipt-bound")
        require(evolution.get("graph_id") == RELEASE_GRAPH_ID, "scenario evolution graph ID differs")
        require(evolution.get("offline_release_id") == OFFLINE_RELEASE_ID, "scenario evolution offline release ID differs")
        require(evolution.get("capability_ratchet_epoch") == CAPABILITY_RATCHET_EPOCH, "scenario evolution capability epoch differs")
        require(evolution.get("technical_debt_ratchet_epoch") == TECHNICAL_DEBT_RATCHET_EPOCH, "scenario evolution debt epoch differs")
        require(_integer_at_least(evolution.get("required_reports"), 49), "scenario evolution report inventory regressed")
        require(_integer_at_least(evolution.get("required_artifacts"), 27), "scenario evolution artifact inventory regressed")
        require(evolution.get("required_receipts") == MIN_SCENARIO_EVOLUTION_RECEIPTS, "scenario evolution receipt inventory differs")
        require(evolution.get("authenticated_receipts") == MIN_SCENARIO_EVOLUTION_RECEIPTS, "scenario evolution receipt set incomplete")
        evolution_receipt_records = evolution.get("receipt_records") if isinstance(evolution.get("receipt_records"), list) else []
        evolution_receipt_stages = tuple(sorted(str(record.get("stage")) for record in evolution_receipt_records if isinstance(record, dict)))
        require(evolution_receipt_stages == SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES, "scenario evolution receipt stage inventory differs")

        evolution_attacks = reports.get("reports/scenario-evolution-evidence-mutations.json", {})
        require(_integer_at_least(evolution_attacks.get("cases"), 22), "scenario evolution mutation-case floor regressed")
        require(_integer_at_least(evolution_attacks.get("expected_rejections"), 20), "scenario evolution rejection floor regressed")
        require(evolution_attacks.get("accepted_attacks") == 0, "scenario evolution attack was accepted")
        evolution_case_ids = _all_result_case_ids(evolution_attacks)
        require("standalone_report_hash_mode" in evolution_case_ids, "scenario evolution standalone baseline missing")
        require("graph_bound_receipt_baseline" in evolution_case_ids, "scenario evolution graph-bound baseline missing")
        for case_id in (
            "behavior_archive_receipt_missing",
            "behavior_archive_checker_receipt_missing",
            "behavior_archive_attack_receipt_missing",
            "stale_behavior_archive_output",
            "treatment_admission_receipt_missing",
            "treatment_admission_attack_receipt_missing",
            "stale_treatment_projection_rejected",
            "plain_language_summary_receipt_missing",
            "plain_language_summary_attack_receipt_missing",
            "stale_plain_language_summary_rejected",
        ):
            require(case_id in evolution_case_ids, f"scenario evolution behavior-archive regression missing:{case_id}")

        debt_policy = reports.get("reports/release-technical-debt-policy.json", {})
        require(debt_policy.get("absolute_debt_free_claim_permitted") is False, "absolute debt-free claim was enabled in source policy")
        require(debt_policy.get("accepted_risks") == [], "technical-debt source policy accepted risk")
        require(debt_policy.get("known_release_blockers_remaining") == 0, "known release-blocking debt remains in source policy")
        require(_integer_at_least(debt_policy.get("entries"), 19), "technical-debt register inventory regressed")
        require(_integer_at_least(debt_policy.get("required_receipt_count"), TECHNICAL_DEBT_RATCHET_RECEIPTS), "technical-debt source receipt floor regressed")

        debt_attacks = reports.get("reports/release-technical-debt-mutations.json", {})
        require(_integer_at_least(debt_attacks.get("cases"), 20), "technical-debt adversarial-case floor regressed")
        require(debt_attacks.get("errors") == [], "technical-debt adversarial report contains errors")

        debt_ratchet = reports.get("reports/technical-debt-ratchet.json", {})
        require(debt_ratchet.get("ratchet_id") == TECHNICAL_DEBT_RATCHET_ID, "technical-debt ratchet ID differs")
        require(debt_ratchet.get("ratchet_epoch") == TECHNICAL_DEBT_RATCHET_EPOCH, "technical-debt ratchet epoch differs")
        require(debt_ratchet.get("ratchet_anchor_sha256") == TECHNICAL_DEBT_RATCHET_ANCHOR, "technical-debt ratchet anchor differs")
        require(debt_ratchet.get("accepted_risks") == 0, "technical-debt ratchet accepted risk")
        require(debt_ratchet.get("required_receipt_count") == TECHNICAL_DEBT_RATCHET_RECEIPTS, "technical-debt ratchet receipt floor differs")
        require(_integer_at_least(debt_ratchet.get("entry_count"), 19), "technical-debt ratchet entry floor regressed")

        debt_ratchet_attacks = reports.get("reports/technical-debt-ratchet-mutations.json", {})
        require(_integer_at_least(debt_ratchet_attacks.get("cases"), 14), "technical-debt ratchet mutation-case floor regressed")
        require(_integer_at_least(debt_ratchet_attacks.get("expected_rejections"), 13), "technical-debt ratchet rejection floor regressed")
        require(debt_ratchet_attacks.get("accepted_regressions") == 0, "technical-debt ratchet regression was accepted")

        production_attacks = reports.get("reports/production-simulation-designation-mutations.json", {})
        require(_integer_at_least(production_attacks.get("cases"), 45), "production designation adversarial-case floor regressed")
        require(production_attacks.get("accepted_regressions", 0) == 0, "production designation regression was accepted")
        require(production_attacks.get("errors") == [], "production designation adversarial report contains errors")

        debt = reports.get("reports/release-technical-debt-final.json", {})
        require(debt.get("known_release_blockers_remaining") == 0, "known release-blocking technical debt remains")
        require(debt.get("absolute_debt_free_claim_permitted") is False, "absolute debt-free claim was enabled")
        require(debt.get("authenticated_receipt_count") == debt.get("required_receipt_count"), "technical-debt evidence receipt set incomplete")
        require(_integer_at_least(debt.get("required_receipt_count"), TECHNICAL_DEBT_RATCHET_RECEIPTS), "final technical-debt receipt floor regressed")

        final_graph = reports.get("reports/release-graph-final-evidence.json", {})
        require(final_graph.get("authenticated_receipt_count") == final_graph.get("predecessor_stage_count"), "final graph evidence chain incomplete")
        final_truth = final_graph.get("truth_boundaries", {})
        require(final_truth == truth, "final graph truth boundaries differ from current graph")
        require(final_graph.get("operational_timing_calibrated") is False, "final graph evidence asserts clinical timing calibration")
        require(final_graph.get("patient_care_authority_granted") is False, "final graph evidence grants patient-care authority")

        receipts_root = receipt_directory(root, graph, receipt_dir)
        chain_evidence, chain_errors = authenticate_stage_receipt(
            root,
            graph,
            "final.graph-evidence",
            receipt_dir=receipts_root,
        )
        errors.extend(chain_errors)
        chain = chain_evidence.get("chain", {}) if isinstance(chain_evidence, dict) else {}
        authenticated: dict[str, Any] = {}
        for stage_id in COMPILED_REQUIRED_RECEIPTS:
            stage_evidence = chain.get(stage_id)
            require(isinstance(stage_evidence, dict), f"production simulation required receipt absent from authenticated chain:{stage_id}")
            if isinstance(stage_evidence, dict) and all(stage_evidence.get("checks", {}).values()):
                authenticated[stage_id] = stage_evidence
        require(len(authenticated) == len(COMPILED_REQUIRED_RECEIPTS), "production simulation required receipt set incomplete")

        for relative, producer in REPORT_PRODUCERS.items():
            stage_evidence = chain.get(producer)
            require(isinstance(stage_evidence, dict), f"required report producer receipt absent:{relative}:{producer}")
            inventory = stage_evidence.get("output_inventory", {}) if isinstance(stage_evidence, dict) else {}
            require(isinstance(inventory, dict) and relative in inventory, f"required report absent from producer receipt:{relative}:{producer}")
            item = inventory.get(relative, {}) if isinstance(inventory, dict) else {}
            require(isinstance(item, dict) and item.get("type") == "file", f"required report producer output is not a regular file:{relative}:{producer}")
            report_path = root / relative
            require(report_path.is_file() and not report_path.is_symlink(), f"required report is not a regular file:{relative}")
            if report_path.is_file() and isinstance(item, dict):
                require(item.get("sha256") == sha256_file(report_path), f"required report hash differs from producer receipt:{relative}:{producer}")

        designation = GRANT if not errors else DEFAULT
        classification = PASS if designation == GRANT else FAIL
        evidence_root = sha256_text(canonical_json({
            "policy_anchor_sha256": observed_policy_anchor,
            "graph_truth_boundaries": truth,
            "reports": {
                key: {
                    "classification": classification_of(value),
                    "sha256": sha256_file(root / key),
                    "producer": REPORT_PRODUCERS[key],
                }
                for key, value in sorted(reports.items())
            },
            "receipts": {key: value.get("receipt_sha256") for key, value in sorted(authenticated.items())},
            "designation": designation,
        }))
        return {
            "schema_version": "1.1.0",
            "classification": classification,
            "status": classification,
            "designation": designation,
            "designation_scope": "PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE",
            "evidence_profile": EVIDENCE_PROFILE,
            "policy_epoch": POLICY_EPOCH,
            "policy_anchor_sha256": observed_policy_anchor,
            "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE" if designation == GRANT else "NOT_GRANTED_BY_THIS_EVALUATION",
            "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE" if designation == GRANT else "NOT_GRANTED_BY_THIS_EVALUATION",
            "simulation_logical_timing": truth.get("simulation_logical_timing"),
            "clinical_operational_timing": "NOT_CALIBRATED",
            "clinical_timing_transferability": "NOT_ESTABLISHED",
            "direct_patient_care": "PROHIBITED",
            "clinical_decision_support": "PROHIBITED",
            "patient_care_authority_granted": False,
            "clinical_effectiveness_established": False,
            "program_accreditation_claimed": False,
            "high_stakes_credentialing_authorized": False,
            "legacy_clinical_production_ready": False,
            "checks": checks,
            "required_report_count": len(COMPILED_REQUIRED_REPORTS),
            "required_receipt_count": len(COMPILED_REQUIRED_RECEIPTS),
            "authenticated_receipt_count": len(authenticated),
            "authenticated_receipts": authenticated,
            "evidence_root_sha256": evidence_root,
            "revocation_rules": policy.get("revocation_rules", []),
            "errors": sorted(set(errors)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.1.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "designation": DEFAULT,
            "checks": checks,
            "patient_care_authority_granted": False,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = evaluate(root, args.receipt_dir)
    write_json(root / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
