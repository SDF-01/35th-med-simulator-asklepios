#!/usr/bin/env python3
"""Join RC3.8A.1 Scenario Evolution evidence with optional graph receipts.

This V7 join binds the verified example, Scenario Genome, cross-platform checker
boundary, offline single-file release, human-readable evolution documentation,
dual monotonic ratchets, and standalone runtime/UI evidence into one canonical
record.  A committed PASS report is informative only; when the release graph is
running, every report is additionally authenticated by the current stage receipt
and the stage's complete output inventory.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from release_graph_core import (
    canonical_json,
    graph_file_sha256,
    load_graph,
    load_receipt,
    output_inventory,
    output_root_sha256,
    receipt_valid,
    sha256_text,
    stage_map,
)
from scenario_genome_common import atomic_write_json, canonical_sha256, file_sha256, load_object, safe_repo_path

sys.dont_write_bytecode = True

EVIDENCE_PROFILE = 'AUTHENTICATED_SCENARIO_EVOLUTION_EVIDENCE_JOIN_V7'
COMPILED_GRAPH_ID = 'asklepios-rc3.8a.1-scenario-science-stakeholder-graph'
COMPILED_GRAPH_STAGE_FLOOR = 122
COMPILED_GRAPH_TARGET_FLOOR = 26
COMPILED_OFFLINE_RELEASE = 'ASK-OFFLINE-RC3.8A.1'
COMPILED_CAPABILITY = ('asklepios-scenario-capability-ratchet-v1',
 5,
 '870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e')
COMPILED_DEBT = ('asklepios-technical-debt-ratchet-v1', 8, '84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91')
COMPILED_DEBT_RECEIPTS = 40
BEHAVIORAL_ARCHIVE_PROFILE = "DETERMINISTIC_BEHAVIORAL_EQUIVALENCE_ARCHIVE_V1"
BEHAVIORAL_POLICY_PROFILE = "SOURCE_BOUND_POLICY_AND_TRAJECTORY_QUOTIENT_V1"
BEHAVIORAL_POLICY_FLOORS = {
    "unique_context_signatures": 107,
    "policy_equivalence_classes": 4,
    "policy_novelty_ratio_bps": 373,
}


def behavioral_policy_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    return summary if isinstance(summary, dict) else {}

REQUIRED_AUTHORITY = {
    "clinical_authority": "NOT_GRANTED",
    "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
    "operational_calibration": "NOT_CALIBRATED",
    "patient_care_use": "PROHIBITED",
    "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
    "scoring_behavior": "inherited_unchanged",
}
REQUIRED_CAPABILITY_AUTHORITY = {
    **REQUIRED_AUTHORITY,
    "quality_vector_use": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
}

REPORT_STAGE_MAP: dict[str, str] = {'.asklepios/facility-standalone/gate-report.json': 'standalone.contracts',
 'reports/facility-arrival-standalone-mutations.json': 'standalone.contracts',
 'reports/facility-arrival-standalone-runtime.json': 'standalone.contracts',
 'reports/facility-arrival-standalone-ui.json': 'standalone.contracts',
 'reports/facility-arrival-standalone.json': 'standalone.contracts',
 'reports/node-checker-cli-mutations.json': 'scenario.node-checker-cli-attacks',
 'reports/offline-scenario-release-check.json': 'offline.release-python',
 'reports/offline-scenario-release-mutations.json': 'offline.release-attacks',
 'reports/offline-scenario-release-node.json': 'offline.release-node',
 'reports/offline-scenario-release.json': 'offline.release-generate',
 'reports/operational-scenario-pack-generation.json': 'scenario.stakeholder-product-check',
 'reports/operational-scenario-pack-mutations.json': 'scenario.stakeholder-product-attacks',
 'reports/operational-scenario-pack-node.json': 'scenario.stakeholder-product-check',
 'reports/plain-language-change-summary-mutations.json': 'scenario.plain-language-summary-attacks',
 'reports/plain-language-change-summary-node.json': 'scenario.plain-language-summary-check',
 'reports/plain-language-change-summary.json': 'scenario.plain-language-summary-check',
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
 'reports/scenario-genome-mutations.json': 'scenario.genome-attacks',
 'reports/scenario-genome-node.json': 'scenario.genome-node',
 'reports/scenario-genome-python-check.json': 'scenario.genome-python',
 'reports/scenario-genome.json': 'scenario.verified-artifacts-generate',
 'reports/scenario-science-telemetry-mutations.json': 'scenario.science-foundation-attacks',
 'reports/scenario-science-telemetry-node.json': 'scenario.science-foundation-check',
 'reports/scenario-science-telemetry-python.json': 'scenario.science-foundation-check',
 'reports/stakeholder-product-bundle-mutations.json': 'scenario.stakeholder-product-attacks',
 'reports/stakeholder-product-bundle-node.json': 'scenario.stakeholder-product-check',
 'reports/stakeholder-product-bundle-python.json': 'scenario.stakeholder-product-check',
 'reports/stakeholder-product-bundle.json': 'scenario.stakeholder-product-check',
 'reports/technical-debt-ratchet-mutations.json': 'release.debt-ratchet-attacks',
 'reports/technical-debt-ratchet.json': 'release.debt-ratchet',
 'reports/treatment-admission-registry-mutations.json': 'scenario.treatment-admission-attacks',
 'reports/treatment-admission-registry-node.json': 'scenario.treatment-admission-check',
 'reports/treatment-admission-registry.json': 'scenario.treatment-admission-check',
 'reports/verified-example-generation-check.json': 'scenario.verified-example-generation-check',
 'reports/verified-example-generation.json': 'scenario.verified-artifacts-generate',
 'reports/verified-example-mutations.json': 'scenario.verified-example-attacks',
 'reports/verified-example-node.json': 'scenario.verified-example-node',
 'reports/verified-example-python.json': 'scenario.verified-example-python'}
REQUIRED_REPORTS = ('.asklepios/facility-standalone/gate-report.json',
 'reports/facility-arrival-standalone-mutations.json',
 'reports/facility-arrival-standalone-runtime.json',
 'reports/facility-arrival-standalone-ui.json',
 'reports/facility-arrival-standalone.json',
 'reports/node-checker-cli-mutations.json',
 'reports/offline-scenario-release-check.json',
 'reports/offline-scenario-release-mutations.json',
 'reports/offline-scenario-release-node.json',
 'reports/offline-scenario-release.json',
 'reports/operational-scenario-pack-generation.json',
 'reports/operational-scenario-pack-mutations.json',
 'reports/operational-scenario-pack-node.json',
 'reports/plain-language-change-summary-mutations.json',
 'reports/plain-language-change-summary-node.json',
 'reports/plain-language-change-summary.json',
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
 'reports/scenario-genome-mutations.json',
 'reports/scenario-genome-node.json',
 'reports/scenario-genome-python-check.json',
 'reports/scenario-genome.json',
 'reports/scenario-science-telemetry-mutations.json',
 'reports/scenario-science-telemetry-node.json',
 'reports/scenario-science-telemetry-python.json',
 'reports/stakeholder-product-bundle-mutations.json',
 'reports/stakeholder-product-bundle-node.json',
 'reports/stakeholder-product-bundle-python.json',
 'reports/stakeholder-product-bundle.json',
 'reports/technical-debt-ratchet-mutations.json',
 'reports/technical-debt-ratchet.json',
 'reports/treatment-admission-registry.json',
 'reports/treatment-admission-registry-node.json',
 'reports/treatment-admission-registry-mutations.json',
 'reports/verified-example-generation-check.json',
 'reports/verified-example-generation.json',
 'reports/verified-example-mutations.json',
 'reports/verified-example-node.json',
 'reports/verified-example-python.json')
ARTIFACT_STAGE_MAP = {
    'README.md': 'offline.release-generate',
    'docs/FACILITY_ARRIVAL_STANDALONE.md': 'offline.release-generate',
    'examples/facility-arrival/README.md': 'arrival.generate',
    'examples/facility-arrival/manifest.json': 'arrival.generate',
    'examples/facility-arrival/playable.html': 'standalone.generate',
    'examples/verified-scenario/README.md': 'scenario.verified-artifacts-generate',
    'examples/verified-scenario/manifest.json': 'scenario.verified-artifacts-generate',
    'public/data/scenario_core/offline_scenario_release.json': 'offline.release-generate',
    'public/data/scenario_core/verified_scenario.json': 'scenario.verified-artifacts-generate',
    'public/data/scenario_core/verified_scenario_package.json': 'scenario.verified-artifacts-generate',
    'public/data/scenario_core/verified_scenario_genome.json': 'scenario.verified-artifacts-generate',
    'docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md': 'scenario.plain-language-summary',
    'public/data/scenario_library/operational-pack.json': 'scenario.stakeholder-product',
    'public/data/scenario_library/stakeholder-dashboard.json': 'scenario.stakeholder-product',
    'public/data/scenario_library/treatment-admission.json': 'scenario.treatment-admission',
}


REQUIRED_RECEIPT_STAGES = tuple(sorted(set(REPORT_STAGE_MAP.values()) | set(ARTIFACT_STAGE_MAP.values())))


REQUIRED_ARTIFACTS = ('README.md',
 'config/release/OFFLINE_SCENARIO_RELEASE.json',
 'config/release/PRODUCTION_SIMULATION_POLICY.json',
 'config/release/RELEASE_GRAPH.json',
 'config/release/SCENARIO_CAPABILITY_RATCHET.json',
 'config/release/TECHNICAL_DEBT_RATCHET.json',
 'docs/FACILITY_ARRIVAL_STANDALONE.md',
 'examples/facility-arrival/README.md',
 'examples/facility-arrival/manifest.json',
 'examples/facility-arrival/playable.html',
 'examples/verified-scenario/README.md',
 'examples/verified-scenario/manifest.json',
 'public/data/scenario_core/offline_scenario_release.json',
 'public/data/scenario_core/verified_scenario.json',
 'public/data/scenario_core/verified_scenario_package.json',
 'public/data/scenario_core/verified_scenario_genome.json',
 'config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json',
 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json',
 'config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json',
 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json',
 'config/product/STAKEHOLDER_CAPABILITY_MAP.json',
 'config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json',
 'docs/RC3_8_STAKEHOLDER_RELEASE_SUMMARY.md',
 'docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md',
 'public/data/scenario_library/operational-pack.json',
 'public/data/scenario_library/stakeholder-dashboard.json',
 'public/data/scenario_library/treatment-admission.json')


def report_pass(value: dict[str, Any]) -> bool:
    classification = value.get("classification", value.get("status"))
    return classification == "PASS" and value.get("status", classification) == "PASS"


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _receipt_binding(
    repo: Path,
    report_records: list[dict[str, Any]],
    artifact_records: list[dict[str, Any]],
    errors: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    receipt_root = os.environ.get("ASKLEPIOS_RELEASE_RECEIPT_DIR")
    if not receipt_root:
        return "STANDALONE_REPORT_HASH_ONLY", []
    receipt_dir = Path(receipt_root).resolve()
    if receipt_dir.is_symlink() or not receipt_dir.is_dir():
        errors.append("scenario evolution receipt directory unavailable or unsafe")
        return "GRAPH_RECEIPTS_REQUIRED", []
    try:
        graph = load_graph(repo)
        stages = stage_map(graph)
        graph_sha256 = graph_file_sha256(repo)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"scenario evolution graph unavailable:{type(exc).__name__}:{exc}")
        return "GRAPH_RECEIPTS_REQUIRED", []

    reports_by_path = {record["path"]: record for record in report_records}
    artifacts_by_path = {record["path"]: record for record in artifact_records}
    receipt_records: list[dict[str, Any]] = []
    receipt_stage_ids = REQUIRED_RECEIPT_STAGES
    for stage_id in sorted(receipt_stage_ids):
        stage = stages.get(stage_id)
        if not isinstance(stage, dict):
            errors.append(f"scenario evolution receipt stage absent:{stage_id}")
            continue
        receipt = load_receipt(receipt_dir, stage_id)
        if not receipt_valid(receipt):
            errors.append(f"scenario evolution receipt invalid or missing:{stage_id}")
            continue
        assert receipt is not None
        current_inventory, inventory_errors = output_inventory(repo, stage.get("outputs", []))
        errors.extend(f"scenario evolution receipt output invalid:{stage_id}:{item}" for item in inventory_errors)
        expected_stage_sha = sha256_text(canonical_json(stage))
        conditions = {
            "schema": receipt.get("schema_version") == "1.0.0",
            "graph_id": receipt.get("graph_id") == graph.get("graph_id"),
            "graph_sha256": receipt.get("graph_sha256") == graph_sha256,
            "stage": receipt.get("stage") == stage_id,
            "stage_config_sha256": receipt.get("stage_config_sha256") == expected_stage_sha,
            "classification": receipt.get("classification") == "PASS",
            "exit_status": receipt.get("exit_status") == 0,
            "output_inventory": receipt.get("output_inventory") == current_inventory,
            "output_root_sha256": receipt.get("output_root_sha256") == output_root_sha256(current_inventory),
        }
        for field, passed in conditions.items():
            if not passed:
                errors.append(f"scenario evolution receipt differs:{stage_id}:{field}")
        for report_path, expected_stage in REPORT_STAGE_MAP.items():
            if expected_stage != stage_id:
                continue
            report_record = reports_by_path.get(report_path)
            output_record = current_inventory.get(report_path)
            if not isinstance(report_record, dict) or not isinstance(output_record, dict):
                errors.append(f"scenario evolution report is not receipt-bound:{stage_id}:{report_path}")
                continue
            if output_record.get("type") != "file" or output_record.get("sha256") != report_record.get("sha256"):
                errors.append(f"scenario evolution report hash differs from receipt output:{stage_id}:{report_path}")
        for artifact_path, expected_stage in ARTIFACT_STAGE_MAP.items():
            if expected_stage != stage_id:
                continue
            artifact_record = artifacts_by_path.get(artifact_path)
            output_record = current_inventory.get(artifact_path)
            if not isinstance(artifact_record, dict) or not isinstance(output_record, dict):
                errors.append(f"scenario evolution artifact is not receipt-bound:{stage_id}:{artifact_path}")
                continue
            if output_record.get("type") != "file" or output_record.get("sha256") != artifact_record.get("sha256"):
                errors.append(f"scenario evolution artifact hash differs from receipt output:{stage_id}:{artifact_path}")
        receipt_records.append({
            "stage": stage_id,
            "receipt_sha256": receipt.get("receipt_sha256"),
            "output_root_sha256": receipt.get("output_root_sha256"),
        })
    return "GRAPH_RECEIPTS_REQUIRED", receipt_records


def validate(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    reports: dict[str, dict[str, Any]] = {}
    report_records: list[dict[str, Any]] = []
    for relative in REQUIRED_REPORTS:
        path = safe_repo_path(repo, relative)
        try:
            value = load_object(path)
            reports[relative] = value
            if not report_pass(value):
                errors.append(f"scenario evolution report not PASS:{relative}")
            report_records.append({
                "path": relative,
                "sha256": file_sha256(path),
                "classification": value.get("classification", value.get("status")),
            })
        except Exception as exc:  # noqa: BLE001
            errors.append(f"scenario evolution report unavailable:{relative}:{type(exc).__name__}:{exc}")

    artifact_records: list[dict[str, Any]] = []
    for relative in REQUIRED_ARTIFACTS:
        path = safe_repo_path(repo, relative)
        if path.is_symlink() or not path.is_file():
            errors.append(f"scenario evolution artifact unavailable:{relative}")
            continue
        artifact_records.append({"path": relative, "bytes": path.stat().st_size, "sha256": file_sha256(path)})

    genome_id = genome_sha256 = offline_release_sha256 = None
    capability_epoch = debt_epoch = None
    try:
        graph = load_object(safe_repo_path(repo, "config/release/RELEASE_GRAPH.json"))
        production_policy = load_object(safe_repo_path(repo, "config/release/PRODUCTION_SIMULATION_POLICY.json"))
        evidence_contract = production_policy.get("evidence_contract") if isinstance(production_policy.get("evidence_contract"), dict) else {}
        policy_stage_floor = evidence_contract.get("minimum_release_graph_stages")
        _require(graph.get("graph_id") == COMPILED_GRAPH_ID, errors, "scenario evolution graph identity differs")
        _require(evidence_contract.get("release_graph_id") == COMPILED_GRAPH_ID, errors, "scenario evolution production-policy graph identity differs")
        _require(
            isinstance(policy_stage_floor, int) and policy_stage_floor >= COMPILED_GRAPH_STAGE_FLOOR,
            errors,
            "scenario evolution production-policy graph stage floor regressed",
        )
        _require(
            isinstance(policy_stage_floor, int) and len(graph.get("stages", [])) >= policy_stage_floor,
            errors,
            "scenario evolution graph stage count is below the production-policy floor",
        )
        _require(
            len(graph.get("targets", {})) >= COMPILED_GRAPH_TARGET_FLOOR,
            errors,
            "scenario evolution graph target count is below the compiled floor",
        )

        genome = load_object(safe_repo_path(repo, "public/data/scenario_core/verified_scenario_genome.json"))
        authority = genome.get("authority_boundary") if isinstance(genome.get("authority_boundary"), dict) else {}
        for field, expected in REQUIRED_AUTHORITY.items():
            _require(authority.get(field) == expected, errors, f"scenario evolution authority differs:{field}")
        genome_id = genome.get("genome_id")
        genome_sha256 = genome.get("genome_sha256")

        capability = load_object(safe_repo_path(repo, "config/release/SCENARIO_CAPABILITY_RATCHET.json"))
        _require(
            (capability.get("ratchet_id"), capability.get("ratchet_epoch"), capability.get("ratchet_anchor_sha256")) == COMPILED_CAPABILITY,
            errors,
            "scenario evolution capability-ratchet binding differs",
        )
        _require(capability.get("authority_boundary") == REQUIRED_CAPABILITY_AUTHORITY, errors, "scenario evolution capability-ratchet authority differs")
        capability_epoch = capability.get("ratchet_epoch")

        debt = load_object(safe_repo_path(repo, "config/release/TECHNICAL_DEBT_RATCHET.json"))
        _require(
            (debt.get("ratchet_id"), debt.get("ratchet_epoch"), debt.get("ratchet_anchor_sha256")) == COMPILED_DEBT,
            errors,
            "scenario evolution technical-debt-ratchet binding differs",
        )
        _require(len(debt.get("required_final_stage_receipts", [])) == COMPILED_DEBT_RECEIPTS, errors, "scenario evolution technical-debt receipt floor differs")
        debt_epoch = debt.get("ratchet_epoch")

        offline = load_object(safe_repo_path(repo, "public/data/scenario_core/offline_scenario_release.json"))
        _require(offline.get("release_id") == COMPILED_OFFLINE_RELEASE, errors, "scenario evolution offline release identity differs")
        _require(offline.get("engine_evolution") == "SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8", errors, "scenario evolution offline profile differs")
        _require(offline.get("scenario_genome", {}).get("genome_id") == genome_id, errors, "scenario evolution offline Genome identity differs")
        _require(offline.get("capability_ratchet", {}).get("ratchet_epoch") == capability_epoch, errors, "scenario evolution offline capability epoch differs")
        _require(offline.get("technical_debt_ratchet", {}).get("ratchet_epoch") == debt_epoch, errors, "scenario evolution offline debt epoch differs")
        _require(offline.get("release_graph", {}).get("graph_id") == COMPILED_GRAPH_ID, errors, "scenario evolution offline graph differs")
        offline_release_sha256 = offline.get("release_sha256")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"scenario evolution core binding unavailable:{type(exc).__name__}:{exc}")

    # Behavioral quality-diversity and ratchet/report semantic floors are checked here in addition to their own stages.
    archive = reports.get("reports/scenario-behavior-archive.json", {})
    archive_summary = archive.get("summary") if isinstance(archive.get("summary"), dict) else {}
    archive_truth = archive.get("truth_boundaries") if isinstance(archive.get("truth_boundaries"), dict) else {}
    _require(archive.get("selection_boundary") == "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING", errors, "scenario behavior archive selection boundary differs")
    _require(archive_truth.get("human_team_behavior") == "STRUCTURAL_ONLY_NOT_CALIBRATED", errors, "scenario behavior archive human behavior boundary differs")
    _require(archive_truth.get("clinical_authority") == "NOT_GRANTED", errors, "scenario behavior archive grants clinical authority")
    _require(archive_summary.get("candidate_count") == 107, errors, "scenario behavior archive candidate floor differs")
    _require(archive_summary.get("unique_behavior_signatures") == 107, errors, "scenario behavior archive signature floor differs")
    _require(archive_summary.get("duplicate_behavior_candidates") == 0, errors, "scenario behavior archive contains duplicates")
    _require(archive_summary.get("occupied_cells") == 30 and archive_summary.get("possible_cells_in_observed_domain") == 30, errors, "scenario behavior archive cell coverage differs")
    _require(archive_summary.get("occupied_cell_ratio_bps") == 10000, errors, "scenario behavior archive coverage ratio differs")
    _require(archive_summary.get("narrative_or_provenance_only_variants_create_new_behavior") is False, errors, "scenario behavior archive admits cosmetic diversity")
    archive_check = reports.get("reports/scenario-behavior-archive-check.json", {})
    _require(archive_check.get("archive_root_sha256") == archive.get("archive_root_sha256"), errors, "scenario behavior archive independent root differs")
    _require(isinstance(archive_check.get("checks"), int) and archive_check.get("checks") >= 2863, errors, "scenario behavior archive checker floor differs")
    archive_attacks = reports.get("reports/scenario-behavior-archive-mutations.json", {})
    _require(isinstance(archive_attacks.get("cases"), int) and archive_attacks.get("cases") >= 20, errors, "scenario behavior archive attack inventory weakened")
    _require(archive_attacks.get("accepted_attacks") == 0, errors, "scenario behavior archive attack accepted")

    behavioral = reports.get("reports/scenario-behavioral-equivalence.json", {})
    behavioral_generation = reports.get("reports/scenario-behavioral-equivalence-generation.json", {})
    behavioral_check = reports.get("reports/scenario-behavioral-equivalence-python.json", {})
    behavioral_attacks = reports.get("reports/scenario-behavioral-equivalence-mutations.json", {})
    behavioral_summary = behavioral_policy_summary(behavioral)
    _require(behavioral.get("archive_profile") == BEHAVIORAL_ARCHIVE_PROFILE, errors, "scenario behavioral archive profile differs")
    _require(behavioral.get("policy_profile") == BEHAVIORAL_POLICY_PROFILE, errors, "scenario behavioral policy profile differs")
    for metric, floor in BEHAVIORAL_POLICY_FLOORS.items():
        observed = behavioral_summary.get(metric)
        _require(isinstance(observed, int) and not isinstance(observed, bool) and observed >= floor, errors, f"scenario behavioral floor regressed:{metric}")
        _require(behavioral_generation.get(metric) == observed, errors, f"scenario behavioral generation summary differs:{metric}")
    _require(behavioral_generation.get("archive_root_sha256") == behavioral.get("archive_root_sha256"), errors, "scenario behavioral generation archive root differs")
    _require(behavioral_check.get("archive_root_sha256") == behavioral.get("archive_root_sha256"), errors, "scenario behavioral independent archive root differs")
    _require(behavioral_check.get("policy_equivalence_classes") == behavioral_summary.get("policy_equivalence_classes") and behavioral_check.get("unique_context_signatures") == behavioral_summary.get("unique_context_signatures") and behavioral_check.get("checks", 0) >= 1131, errors, "scenario behavioral independent-check floor differs")
    _require(behavioral_attacks.get("cases", 0) >= 13 and behavioral_attacks.get("accepted_attacks") == 0, errors, "scenario behavioral attack boundary differs")

    telemetry_python = reports.get("reports/scenario-science-telemetry-python.json", {})
    telemetry_node = reports.get("reports/scenario-science-telemetry-node.json", {})
    telemetry_attacks = reports.get("reports/scenario-science-telemetry-mutations.json", {})
    _require(telemetry_python.get("telemetry_profile") == "HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1", errors, "scenario telemetry profile differs")
    _require(telemetry_python.get("event_chain_root_sha256") == telemetry_node.get("event_chain_root_sha256"), errors, "scenario telemetry independent roots differ")
    _require(telemetry_attacks.get("cases", 0) >= 18 and telemetry_attacks.get("accepted_attacks") == 0, errors, "scenario telemetry attack boundary differs")

    pack = reports.get("reports/operational-scenario-pack-generation.json", {})
    pack_node = reports.get("reports/operational-scenario-pack-node.json", {})
    pack_attacks = reports.get("reports/operational-scenario-pack-mutations.json", {})
    _require(sum((pack.get("profile_counts") or {}).values()) == 12, errors, "operational scenario pack size differs")
    _require(set((pack.get("profile_counts") or {}).values()) == {3}, errors, "operational scenario pack balance differs")
    _require(pack.get("catalog_root_sha256") == pack_node.get("catalog_root_sha256"), errors, "operational scenario pack independent root differs")
    _require(pack_attacks.get("cases", 0) >= 12 and pack_attacks.get("accepted_attacks") == 0, errors, "operational scenario pack attack boundary differs")

    stakeholder = reports.get("reports/stakeholder-product-bundle.json", {})
    stakeholder_python = reports.get("reports/stakeholder-product-bundle-python.json", {})
    stakeholder_node = reports.get("reports/stakeholder-product-bundle-node.json", {})
    stakeholder_attacks = reports.get("reports/stakeholder-product-bundle-mutations.json", {})
    _require(stakeholder.get("capability_count") == 9, errors, "stakeholder capability count differs")
    _require(stakeholder.get("reference_scorecards") == 4, errors, "stakeholder scorecard inventory differs")
    _require(stakeholder.get("admitted_treatments") == 0, errors, "stakeholder bundle admits treatments")
    _require(stakeholder_python.get("scenario_entries") == 12 and stakeholder_node.get("scenario_entries") == 12, errors, "stakeholder independent scenario inventory differs")
    _require(stakeholder_python.get("admitted_treatments") == 0 and stakeholder_node.get("admitted_treatments") == 0, errors, "stakeholder independent checker admits treatment")
    _require(stakeholder_attacks.get("cases", 0) >= 16 and stakeholder_attacks.get("accepted_attacks") == 0, errors, "stakeholder attack boundary differs")

    treatment = reports.get("reports/treatment-admission-registry.json", {})
    treatment_node = reports.get("reports/treatment-admission-registry-node.json", {})
    treatment_attacks = reports.get("reports/treatment-admission-registry-mutations.json", {})
    _require(treatment.get("entry_count") == 2 and treatment.get("simulation_admitted_count") == 0 and treatment.get("active_learner_choice_count") == 0, errors, "treatment admission floor differs")
    _require(treatment.get("projection_sha256") == treatment_node.get("projection_sha256"), errors, "treatment admission independent projection differs")
    _require(treatment_node.get("entry_count") == 2 and treatment_node.get("simulation_admitted_count") == 0 and treatment_node.get("active_learner_choice_count") == 0, errors, "treatment admission Node floor differs")
    _require(treatment_attacks.get("cases", 0) >= 12 and treatment_attacks.get("accepted_attacks") == 0, errors, "treatment admission attack boundary differs")

    plain_python = reports.get("reports/plain-language-change-summary.json", {})
    plain_node = reports.get("reports/plain-language-change-summary-node.json", {})
    plain_attacks = reports.get("reports/plain-language-change-summary-mutations.json", {})
    _require(plain_python.get("summary_id") == "asklepios-rc3.8d-plain-language-change-summary", errors, "plain-language summary identity differs")
    _require(plain_python.get("headings") == 8 and plain_python.get("sections") == 8, errors, "plain-language summary structural floor differs")
    _require(plain_node.get("headings") == 8 and plain_node.get("sections") == 8, errors, "plain-language independent structural floor differs")
    _require(plain_node.get("summary_id") == plain_python.get("summary_id"), errors, "plain-language independent identity differs")
    _require(plain_attacks.get("cases", 0) >= 8 and plain_attacks.get("accepted_attacks") == 0, errors, "plain-language attack boundary differs")

    capability_report = reports.get("reports/scenario-capability-ratchet.json", {})
    _require(capability_report.get("ratchet_epoch") == COMPILED_CAPABILITY[1], errors, "scenario capability report epoch differs")
    _require(capability_report.get("ratchet_anchor_sha256") == COMPILED_CAPABILITY[2], errors, "scenario capability report anchor differs")
    debt_report = reports.get("reports/technical-debt-ratchet.json", {})
    _require(debt_report.get("ratchet_epoch") == COMPILED_DEBT[1], errors, "technical-debt report epoch differs")
    _require(debt_report.get("ratchet_anchor_sha256") == COMPILED_DEBT[2], errors, "technical-debt report anchor differs")
    _require(debt_report.get("accepted_risks") == 0, errors, "technical-debt report accepted risk")
    _require(debt_report.get("required_receipt_count") == COMPILED_DEBT_RECEIPTS, errors, "technical-debt report receipt floor differs")
    _require(reports.get("reports/node-checker-cli-mutations.json", {}).get("cases", 0) >= 20, errors, "Node checker CLI regression inventory weakened")
    _require(reports.get("reports/offline-scenario-release-mutations.json", {}).get("accepted_attacks") == 0, errors, "offline release attack accepted")
    _require(reports.get("reports/scenario-engine-evolution-doc-attacks.json", {}).get("accepted_attacks") == 0, errors, "engine documentation attack accepted")
    standalone = reports.get(".asklepios/facility-standalone/gate-report.json", {})
    subgates = standalone.get("subgates") if isinstance(standalone.get("subgates"), list) else []
    _require(len(subgates) == 5 and all(item.get("classification") == "PASS" and item.get("exit_status") == 0 for item in subgates if isinstance(item, dict)), errors, "standalone Scenario Evolution subgate inventory differs")

    receipt_binding_mode, receipt_records = _receipt_binding(repo, report_records, artifact_records, errors)
    if receipt_binding_mode == "GRAPH_RECEIPTS_REQUIRED":
        observed_receipt_stages = tuple(sorted(str(record.get("stage")) for record in receipt_records if isinstance(record, dict)))
        _require(observed_receipt_stages == REQUIRED_RECEIPT_STAGES, errors, "scenario evolution receipt set incomplete")
    classification = "PASS" if not errors else "FAIL"
    evidence_payload = {
        "reports": report_records,
        "artifacts": artifact_records,
        "genome_id": genome_id,
        "genome_sha256": genome_sha256,
        "offline_release_sha256": offline_release_sha256,
        "capability_ratchet_epoch": capability_epoch,
        "technical_debt_ratchet_epoch": debt_epoch,
        "authority_boundary": REQUIRED_CAPABILITY_AUTHORITY,
        "receipt_binding_mode": receipt_binding_mode,
        "receipt_records": receipt_records,
    }
    return {
        "schema_version": "3.0.0",
        "classification": classification,
        "status": classification,
        "evidence_profile": EVIDENCE_PROFILE,
        "required_reports": len(REQUIRED_REPORTS),
        "authenticated_reports": len(report_records),
        "required_artifacts": len(REQUIRED_ARTIFACTS),
        "authenticated_artifacts": len(artifact_records),
        "receipt_binding_mode": receipt_binding_mode,
        "required_receipts": len(REQUIRED_RECEIPT_STAGES) if receipt_binding_mode == "GRAPH_RECEIPTS_REQUIRED" else 0,
        "authenticated_receipts": len(receipt_records),
        "receipt_records": receipt_records,
        "graph_id": COMPILED_GRAPH_ID,
        "genome_id": genome_id,
        "genome_sha256": genome_sha256,
        "offline_release_id": COMPILED_OFFLINE_RELEASE,
        "offline_release_sha256": offline_release_sha256,
        "capability_ratchet_epoch": capability_epoch,
        "technical_debt_ratchet_epoch": debt_epoch,
        "technical_debt_required_receipts": COMPILED_DEBT_RECEIPTS,
        "authority_boundary": REQUIRED_CAPABILITY_AUTHORITY,
        "report_records": report_records,
        "artifact_records": artifact_records,
        "evidence_root_sha256": canonical_sha256(evidence_payload),
        "truth_boundary": "This join authenticates deterministic scenario-evolution identity, documentation, offline execution, structural capability floors, and known technical-debt evidence. It does not promote clinical authority, empirical timing, human-behavior calibration, patient physiology, treatment legitimacy, causal validity, or psychometric validity.",
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-evolution-evidence.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = validate(repo)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "3.0.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "evidence_profile": EVIDENCE_PROFILE,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    output = args.json_output if args.json_output.is_absolute() else repo / args.json_output
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["classification"] == "PASS" else (4 if report["classification"] == "INTERNAL_ERROR" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
