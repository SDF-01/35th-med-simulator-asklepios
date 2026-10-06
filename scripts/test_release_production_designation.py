#!/usr/bin/env python3
"""Adversarial tests for the evidence-computed simulation designation.

The suite builds one minimal authenticated current-floor fixture, then hard-links it
into isolated cases. Mutations use atomic replacement, and the immutable source
fixture is rehashed after every case. This keeps the suite fast without allowing
one mutation to contaminate another case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from release_graph_core import (
    canonical_json,
    collect_tool_versions,
    compute_stage_input_root,
    graph_file_sha256,
    make_receipt,
    output_inventory,
    output_root_sha256,
    read_json,
    receipt_path,
    resolve_command,
    sha256_file,
    sha256_text,
    stage_input_snapshot,
    write_json,
)
from release_production_designation import (
    BEHAVIORAL_ARCHIVE_PROFILE,
    BEHAVIORAL_POLICY_FLOORS,
    BEHAVIORAL_POLICY_PROFILE,
    CAPABILITY_FLOORS,
    CAPABILITY_RATCHET_ANCHOR,
    CAPABILITY_RATCHET_EPOCH,
    CAPABILITY_RATCHET_ID,
    COMPILED_POLICY_ANCHOR,
    COMPILED_REQUIRED_RECEIPTS,
    COMPILED_REQUIRED_REPORTS,
    DEFAULT,
    EVIDENCE_PROFILE,
    EXPECTED_CAPABILITY_AUTHORITY,
    GRANT,
    MIN_GRAPH_CHECKS,
    MIN_GRAPH_MUTATION_CASES,
    MIN_GRAPH_STAGES,
    MIN_SCENARIO_EVOLUTION_RECEIPTS,
    SCENARIO_EVOLUTION_EVIDENCE_PROFILE,
    SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES,
    OFFLINE_RELEASE_ID,
    POLICY_EPOCH,
    RELEASE_GRAPH_ID,
    REPORT_PRODUCERS,
    TECHNICAL_DEBT_RATCHET_ANCHOR,
    TECHNICAL_DEBT_RATCHET_EPOCH,
    TECHNICAL_DEBT_RATCHET_ID,
    TECHNICAL_DEBT_RATCHET_RECEIPTS,
    evaluate,
)
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification

Mutator = Callable[[Path], None]
FIXTURE_SOURCE_PROFILE = "COMPILED_REPORT_PRODUCER_AND_RECEIPT_DERIVED_FIXTURE_V1"
MINIMAL_SOURCE_FILES = (
    "config/release/PRODUCTION_SIMULATION_POLICY.json",
    "scripts/join_scenario_evolution_evidence.py",
    "scripts/lock_release_graph.py",
    "scripts/release_graph_core.py",
    "scripts/release_policy_common.py",
    "scripts/release_production_designation.py",
    "scripts/release_result.py",
    "scripts/run_release_graph.py",
    "scripts/scenario_genome_common.py",
)


def _copy_source(root: Path, destination: Path) -> None:
    """Create the closed minimal source boundary needed by the fixture."""
    destination.mkdir(parents=True, exist_ok=False)
    for relative in MINIMAL_SOURCE_FILES:
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_json(destination / "package.json", {"name": "asklepios-production-fixture", "private": True, "scripts": {}})


def _copy_authenticated_fixture(root: Path, destination: Path) -> None:
    """Hard-link the immutable authenticated fixture for one mutation case."""
    shutil.copytree(
        root,
        destination,
        copy_function=os.link,
        ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", "*.pyc"),
    )


def _isolated_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("ASKLEPIOS_RELEASE_"):
            environment.pop(name, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    environment["TZ"] = "UTC"
    return environment


def _fixture_tree_root(root: Path) -> str:
    inventory: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            inventory[relative] = {"type": "symlink", "target": os.readlink(path)}
        elif path.is_file():
            inventory[relative] = {"type": "file", "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return sha256_text(canonical_json(inventory))


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.mutation-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _refresh_policy_anchor(path: Path) -> None:
    value = read_json(path)
    value.pop("policy_anchor_sha256", None)
    value["policy_anchor_sha256"] = sha256_text(canonical_json(value))
    write_json(path, value)




def _generate_fixture_receipts(root: Path, graph: dict, stages: list[dict]) -> None:
    package = read_json(root / "package.json")
    scripts = package.get("scripts", {})
    graph_hash = graph_file_sha256(root)
    receipt_dir = root / ".asklepios" / "release-receipts" / str(graph["graph_id"])
    receipt_dir.mkdir(parents=True, exist_ok=True)
    authenticated: dict[str, dict] = {}
    for stage in stages:
        dependencies = {dependency: authenticated[dependency] for dependency in stage.get("needs", [])}
        tools = collect_tool_versions(list(stage["command"]))
        inputs = stage_input_snapshot(root, graph, stage)
        input_root = compute_stage_input_root(graph, stage, inputs, dependencies, tools)
        inventory, inventory_errors = output_inventory(root, stage.get("outputs", []))
        if inventory_errors:
            raise RuntimeError(f"fixture output inventory failed:{stage['id']}:{inventory_errors}")
        receipt = make_receipt(
            graph=graph,
            graph_file_hash=graph_hash,
            stage=stage,
            command=list(stage["command"]),
            resolved_command=resolve_command(list(stage["command"]), scripts),
            input_root=input_root,
            output_root=output_root_sha256(inventory),
            output_inventory_value=inventory,
            tool_versions=tools,
            dependency_receipts=dependencies,
            exit_status=0,
            classification=PASS,
            started_at="2000-01-01T00:00:00.000000Z",
            completed_at="2000-01-01T00:00:00.000000Z",
            errors=[],
        )
        write_json(receipt_path(receipt_dir, str(stage["id"])), receipt)
        authenticated[str(stage["id"])] = receipt


def _fixture(root: Path) -> Path:
    """Create a minimal, fully authenticated RC3.8A.1 designation fixture."""
    truth = {
        "concrete_treatments_admitted": 0,
        "patient_care_use": "PROHIBITED",
        "operational_timing": "NOT_CALIBRATED",
        "production_ready": False,
        "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "direct_patient_care": "PROHIBITED",
        "clinical_decision_support": "PROHIBITED",
        "simulation_logical_timing": "VALIDATED_FOR_DETERMINISTIC_SIMULATION",
        "clinical_operational_timing": "NOT_CALIBRATED",
        "clinical_timing_transferability": "NOT_ESTABLISHED",
    }

    policy_path = root / "config/release/PRODUCTION_SIMULATION_POLICY.json"
    policy = read_json(policy_path)
    if policy.get("policy_anchor_sha256") != COMPILED_POLICY_ANCHOR:
        raise RuntimeError("production fixture policy is not the compiled policy")
    required_receipts = list(policy.get("required_stage_receipts", []))
    if required_receipts != list(COMPILED_REQUIRED_RECEIPTS):
        raise RuntimeError("production fixture receipt inventory differs from compiled floor")
    if list(path.get("path") for path in policy.get("required_reports", [])) != list(COMPILED_REQUIRED_REPORTS):
        raise RuntimeError("production fixture report inventory differs from compiled floor")

    outputs_by_stage: dict[str, list[str]] = {
        "orchestration.graph-check": ["reports/release-graph-consistency.json"],
        "orchestration.graph-attacks": ["reports/release-graph-mutations.json"],
        "release.intended-use-policy": ["reports/release-intended-use.json"],
        "release.intended-use-attacks": ["reports/fixture-intended-use-attacks.json"],
        "release.simulation-quality": ["reports/simulation-quality-assurance.json"],
        "release.simulation-quality-attacks": ["reports/fixture-simulation-quality-attacks.json"],
        "hub.security-source": ["reports/hub-security.json"],
        "hub.security-attacks": ["reports/fixture-hub-security-attacks.json"],
        "release.debt-ratchet": ["reports/technical-debt-ratchet.json"],
        "release.debt-ratchet-attacks": ["reports/technical-debt-ratchet-mutations.json"],
        "release.debt-policy": ["reports/release-technical-debt-policy.json"],
        "release.debt-attacks": ["reports/release-technical-debt-mutations.json"],
        "release.production-policy-attacks": ["reports/production-simulation-designation-mutations.json"],
        "standalone.contracts": [".asklepios/facility-standalone/gate-report.json"],
        "offline.release-python": ["reports/offline-scenario-release-check.json"],
        "offline.release-node": ["reports/offline-scenario-release-node.json"],
        "offline.release-attacks": ["reports/offline-scenario-release-mutations.json"],
        "content.registry-source": ["reports/fixture-content-registry.json"],
        "arrival.runtime-evidence-join": ["reports/fixture-arrival-runtime.json"],
        "decision.artifact-attacks": ["reports/fixture-decision-artifacts.json"],
        "scenario.contracts": ["reports/scenario-behavior-archive.json"],
        "scenario.behavior-archive-check": ["reports/scenario-behavior-archive-check.json"],
        "scenario.behavior-archive-attacks": ["reports/scenario-behavior-archive-mutations.json"],
        "scenario.verified-example-attacks": ["reports/fixture-verified-example-attacks.json"],
        "scenario.node-checker-cli-attacks": ["reports/node-checker-cli-mutations.json"],
        "scenario.engine-evolution-docs-python": ["reports/scenario-engine-evolution-docs-python.json"],
        "scenario.engine-evolution-docs-node": ["reports/scenario-engine-evolution-docs-node.json"],
        "scenario.engine-evolution-doc-attacks": ["reports/scenario-engine-evolution-doc-attacks.json"],
        "scenario.capability-ratchet": ["reports/scenario-capability-ratchet.json"],
        "scenario.capability-ratchet-attacks": ["reports/scenario-capability-ratchet-mutations.json"],
        "scenario.evolution-evidence": ["reports/scenario-evolution-evidence.json"],
        "scenario.evolution-evidence-attacks": ["reports/scenario-evolution-evidence-mutations.json"],
        "scenario.release-validation": ["reports/fixture-scenario-release-validation.json"],
        "hub.runtime-smoke": ["reports/hub-runtime-smoke.json"],
        "simulation.timing-assurance": ["reports/simulation-timing-assurance.json"],
        "formal.exact-audit": ["reports/fixture-formal-exact-audit.json"],
        "build.app-typecheck": ["reports/fixture-app-typecheck.json"],
        "build.double-reproducibility": ["dist", "reports/facility-decision-build-reproducibility.json"],
        "final.decision-evidence": ["reports/facility-decision-release.json"],
        "release.debt-evidence": ["reports/release-technical-debt-final.json"],
        "final.graph-evidence": ["reports/release-graph-final-evidence.json"],
    }
    # The evaluator owns the report-to-producer map.  Extend the fixture from
    # that compiled map so a newly required stakeholder or scientific report
    # cannot be omitted from its producer receipt by a second hand-maintained
    # inventory.
    for relative, producer in REPORT_PRODUCERS.items():
        stage_outputs = outputs_by_stage.setdefault(producer, [])
        if relative not in stage_outputs:
            stage_outputs.append(relative)
    for stage_outputs in outputs_by_stage.values():
        stage_outputs.sort()

    # The filler count is derived so policy growth cannot silently desynchronize the fixture.
    filler_count = MIN_GRAPH_STAGES - len(required_receipts)
    if filler_count < 0:
        raise RuntimeError("production receipt inventory exceeds graph stage floor")
    stage_order = [*required_receipts[:-1], *[f"fixture.filler-{index:03d}" for index in range(1, filler_count + 1)], required_receipts[-1]]
    if len(stage_order) != MIN_GRAPH_STAGES:
        raise RuntimeError("production fixture stage count differs")

    stages: list[dict] = []
    previous: str | None = None
    for stage_id in stage_order:
        outputs = outputs_by_stage.get(stage_id, [f"reports/fixture-stage-{stage_id.replace('.', '-')}.json"])
        stages.append({
            "id": stage_id,
            "command": ["python3", "-c", f"print({stage_id!r} + ' fixture PASS')"],
            "needs": [] if previous is None else [previous],
            "input_sets": ["policy-source"],
            "outputs": outputs,
            "failure_classification": "FAIL",
            "read_only": False,
        })
        previous = stage_id

    graph = {
        "schema_version": "1.0.0",
        "graph_id": RELEASE_GRAPH_ID,
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "release_candidate": "RC3.8A.1 production simulation fixture",
        "production_designation": DEFAULT,
        "truth_boundaries": truth,
        "input_sets": {
            "policy-source": {
                "include": ["config/release/PRODUCTION_SIMULATION_POLICY.json", "package.json"],
                "exclude": [],
                "files": {},
            }
        },
        "managed_package_scripts": {},
        "integrations": {},
        "stages": stages,
        "targets": {"fixture": {"terminal_stages": ["final.graph-evidence"]}},
    }
    write_json(root / "config/release/RELEASE_GRAPH.json", graph)

    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    write_json(reports / "release-graph-consistency.json", {
        "classification": "PASS", "status": "PASS", "graph_id": RELEASE_GRAPH_ID,
        "stages": MIN_GRAPH_STAGES, "checks": MIN_GRAPH_CHECKS + 200, "errors": [],
    })
    write_json(reports / "release-graph-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": MIN_GRAPH_MUTATION_CASES, "errors": [],
    })
    write_json(reports / "release-intended-use.json", {
        "classification": "PASS",
        "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "direct_patient_care": "PROHIBITED",
        "clinical_decision_support": "PROHIBITED",
    })
    write_json(reports / "simulation-quality-assurance.json", {
        "classification": "PASS", "scope": "reviewed_healthcare_simulation_scenarios",
        "learner_answer_leakage_findings": 0, "reachable_active_dead_ends": 0,
        "strength_three_coverage_ratio": 1.0,
    })
    write_json(reports / "hub-security.json", {
        "classification": "PASS", "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "direct_patient_care": "PROHIBITED", "clinical_decision_support": "PROHIBITED",
    })
    write_json(reports / "hub-runtime-smoke.json", {
        "classification": "PASS", "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "direct_patient_care": "PROHIBITED", "clinical_decision_support": "PROHIBITED",
        "response_time": {"samples": 64, "p99_ms": 24, "engineering_budget_p99_ms": 250},
    })
    write_json(reports / "simulation-timing-assurance.json", {
        "classification": "PASS", "simulation_logical_clock": "VALIDATED_FOR_DETERMINISTIC_SIMULATION",
        "clinical_operational_timing": "NOT_CALIBRATED", "clinical_timing_transferability": "NOT_ESTABLISHED",
        "clinical_timing_calibrated": False, "response_time_budgets_met": True,
    })
    build_root = "a" * 64
    write_json(reports / "facility-decision-build-reproducibility.json", {
        "classification": "PASS", "files_compared": 1,
        "first_build_root_sha256": build_root, "second_build_root_sha256": build_root,
        "source_mutations": [], "provenance": {"status": "PASS"},
    })
    (root / "dist").mkdir(exist_ok=True)
    _atomic_text(root / "dist/index.html", "fixture\n")

    release_sha = "b" * 64
    write_json(reports / "offline-scenario-release-check.json", {
        "schema_version": "1.2.0", "classification": "PASS", "status": "PASS",
        "release_id": OFFLINE_RELEASE_ID, "graph_id": RELEASE_GRAPH_ID,
        "capability_ratchet_epoch": CAPABILITY_RATCHET_EPOCH,
        "technical_debt_ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
        "artifacts": 10, "mismatches": [], "release_sha256": release_sha,
    })
    write_json(reports / "offline-scenario-release-node.json", {
        "schema_version": "1.2.0", "classification": "PASS", "status": "PASS",
        "checker_profile": "INDEPENDENT_NODE_OFFLINE_SCENARIO_RELEASE_V5",
        "release_id": OFFLINE_RELEASE_ID, "graph_id": RELEASE_GRAPH_ID,
        "capability_ratchet_epoch": CAPABILITY_RATCHET_EPOCH,
        "technical_debt_ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
        "artifacts": 10, "release_sha256": release_sha,
    })
    write_json(reports / "offline-scenario-release-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 42, "attacks": 39,
        "accepted_attacks": 0, "errors": [],
    })

    genome_id = "ASK-GENOME-FIXTURE0001"
    for name, profile in (
        ("scenario-engine-evolution-docs-python.json", "PYTHON_ENGINE_EVOLUTION_DOCUMENTATION_V4"),
        ("scenario-engine-evolution-docs-node.json", "INDEPENDENT_NODE_ENGINE_EVOLUTION_DOCUMENTATION_V5"),
    ):
        write_json(reports / name, {
            "schema_version": "1.1.0", "classification": "PASS", "status": "PASS",
            "checker_profile": profile, "release_id": OFFLINE_RELEASE_ID,
            "graph_id": RELEASE_GRAPH_ID, "capability_ratchet_epoch": CAPABILITY_RATCHET_EPOCH,
            "technical_debt_ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
            "documents": 4, "genome_id": genome_id, "errors": [],
        })
    write_json(reports / "scenario-engine-evolution-doc-attacks.json", {
        "classification": "PASS", "status": "PASS", "cases": 23, "attacks": 22,
        "accepted_attacks": 0, "errors": [],
    })
    write_json(reports / "node-checker-cli-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 20, "checker_count": 3,
        "expected_rejections": 9, "accepted_attacks": 0, "errors": [],
    })
    archive_root = "8" * 64
    behavior_summary = {
        "candidate_count": 107,
        "unique_behavior_signatures": 107,
        "duplicate_behavior_candidates": 0,
        "occupied_cells": 30,
        "possible_cells_in_observed_domain": 30,
        "occupied_cell_ratio_bps": 10000,
        "elite_count": 30,
        "minimum_cell_occupancy": 1,
        "total_strength_three_interactions_observed": 1543,
        "candidates_with_unique_interaction_contribution": 107,
        "narrative_or_provenance_only_variants_create_new_behavior": False,
    }
    write_json(reports / "scenario-behavior-archive.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "archive_root_sha256": archive_root,
        "selection_boundary": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
        "summary": behavior_summary,
        "truth_boundaries": {
            "clinical_authority": "NOT_GRANTED",
            "patient_care_use": "PROHIBITED",
            "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
            "operational_timing": "NOT_CALIBRATED",
            "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
            "scoring_behavior": "inherited_unchanged",
            "quality_vector_use": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
        },
    })
    write_json(reports / "scenario-behavior-archive-check.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "archive_root_sha256": archive_root, "checks": 2863,
        "selection_boundary": "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING",
    })
    write_json(reports / "scenario-behavior-archive-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 20, "expected_rejections": 19, "accepted_attacks": 0, "errors": [],
    })

    # Stakeholder and scenario-science evidence is represented explicitly in
    # the authenticated fixture.  These are the minimum fields independently
    # consumed by the production designation evaluator; no generated report is
    # allowed to fall back to a generic fixture placeholder.
    policy_root = "5" * 64
    behavioral_summary = {
        "candidate_count": 107,
        "unique_context_signatures": 107,
        "unique_policy_signatures": 4,
        "operational_behavior_profiles_observed": [
            "COMMUNICATION_RELAY_REQUIRED",
            "DIRECT_HANDOFF_BASELINE",
            "DUAL_CONSTRAINT_RELAY_AND_COORDINATION",
            "RESOURCE_COORDINATION_REQUIRED",
        ],
        "policy_equivalence_classes": 4,
        "context_only_variant_count": 103,
        "policy_novelty_ratio_bps": 373,
        "maximum_contexts_in_one_policy_class": 27,
        "minimum_contexts_in_one_policy_class": 26,
        "behavioral_uniqueness_status": "MIXED_CONTEXT_AND_POLICY_DIVERSITY",
        "narrative_or_provenance_only_changes_create_policy_novelty": False,
        "operational_context_change_without_policy_change_counts_as_policy_novelty": False,
    }
    write_json(reports / "scenario-behavioral-equivalence-generation.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "archive_root_sha256": policy_root,
        **{metric: behavioral_summary[metric] for metric in BEHAVIORAL_POLICY_FLOORS},
    })
    write_json(reports / "scenario-behavioral-equivalence.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "archive_profile": BEHAVIORAL_ARCHIVE_PROFILE,
        "policy_profile": BEHAVIORAL_POLICY_PROFILE,
        "archive_root_sha256": policy_root,
        "summary": behavioral_summary,
    })
    write_json(reports / "scenario-behavioral-equivalence-python.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "archive_root_sha256": policy_root, "candidate_count": 107,
        "unique_context_signatures": 107, "policy_equivalence_classes": 4,
        "checks": 1131, "errors": [],
    })
    write_json(reports / "scenario-behavioral-equivalence-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 13, "attacks": 12, "accepted_attacks": 0, "errors": [],
    })

    telemetry_root = "6" * 64
    telemetry_profile = "HASH_CHAINED_PRIVACY_BOUNDED_SIMULATION_TELEMETRY_V1"
    for name, checker in (
        ("scenario-science-telemetry-python.json", "PYTHON_INDEPENDENT_RECONSTRUCTION_V1"),
        ("scenario-science-telemetry-node.json", "INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1"),
    ):
        write_json(reports / name, {
            "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
            "telemetry_profile": telemetry_profile, "event_chain_root_sha256": telemetry_root,
            "events": 4, "checker": checker, "errors": [],
        })
    write_json(reports / "scenario-science-telemetry-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 18, "attacks": 17, "accepted_attacks": 0, "errors": [],
    })

    catalog_root = "7" * 64
    profile_counts = {
        "DIRECT_HANDOFF_BASELINE": 3,
        "COMMUNICATION_RELAY_REQUIRED": 3,
        "RESOURCE_COORDINATION_REQUIRED": 3,
        "DUAL_CONSTRAINT_RELAY_AND_COORDINATION": 3,
    }
    write_json(reports / "operational-scenario-pack-generation.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "catalog_root_sha256": catalog_root, "scenario_entries": 12,
        "profile_counts": profile_counts, "errors": [],
    })
    write_json(reports / "operational-scenario-pack-node.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "catalog_root_sha256": catalog_root, "scenario_entries": 12, "errors": [],
    })
    write_json(reports / "operational-scenario-pack-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 12, "attacks": 11, "accepted_attacks": 0, "errors": [],
    })

    write_json(reports / "stakeholder-product-bundle.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "capability_count": 9, "reference_scorecards": 4,
        "scenario_entries": 12, "admitted_treatments": 0, "errors": [],
    })
    write_json(reports / "stakeholder-product-bundle-python.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "checks": 147, "scenario_entries": 12, "admitted_treatments": 0, "errors": [],
    })
    write_json(reports / "stakeholder-product-bundle-node.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "checks": 139, "scenario_entries": 12, "admitted_treatments": 0, "errors": [],
    })
    write_json(reports / "stakeholder-product-bundle-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 16, "attacks": 15, "accepted_attacks": 0, "errors": [],
    })

    treatment_root = "9" * 64
    for name, checker in (
        ("treatment-admission-registry.json", "PYTHON_INDEPENDENT_RECONSTRUCTION_V1"),
        ("treatment-admission-registry-node.json", "INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1"),
    ):
        write_json(reports / name, {
            "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
            "checker": checker, "entry_count": 2, "simulation_admitted_count": 0,
            "active_learner_choice_count": 0, "projection_sha256": treatment_root,
            "errors": [],
        })
    write_json(reports / "treatment-admission-registry-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 12, "attacks": 11, "accepted_attacks": 0, "errors": [],
    })

    plain_id = "asklepios-rc3.8d-plain-language-change-summary"
    for name, checker in (
        ("plain-language-change-summary.json", "PYTHON_INDEPENDENT_RECONSTRUCTION_V1"),
        ("plain-language-change-summary-node.json", "INDEPENDENT_NODE_STDLIB_RECONSTRUCTION_V1"),
    ):
        write_json(reports / name, {
            "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
            "checker": checker, "summary_id": plain_id, "headings": 8, "sections": 8,
            "errors": [],
        })
    write_json(reports / "plain-language-change-summary-mutations.json", {
        "schema_version": "1.0.0", "classification": "PASS", "status": "PASS",
        "cases": 8, "attacks": 7, "accepted_attacks": 0, "errors": [],
    })

    write_json(reports / "scenario-capability-ratchet.json", {
        "classification": "PASS", "status": "PASS", "ratchet_id": CAPABILITY_RATCHET_ID,
        "ratchet_epoch": CAPABILITY_RATCHET_EPOCH, "ratchet_anchor_sha256": CAPABILITY_RATCHET_ANCHOR,
        "authority_boundary": EXPECTED_CAPABILITY_AUTHORITY, "floors": CAPABILITY_FLOORS,
        "observed": CAPABILITY_FLOORS, "errors": [],
    })
    write_json(reports / "scenario-capability-ratchet-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 20,
        "expected_rejections": 19, "accepted_regressions": 0, "errors": [],
    })
    write_json(reports / "scenario-evolution-evidence.json", {
        "schema_version": "3.0.0", "classification": "PASS", "status": "PASS",
        "evidence_profile": SCENARIO_EVOLUTION_EVIDENCE_PROFILE,
        "receipt_binding_mode": "GRAPH_RECEIPTS_REQUIRED", "graph_id": RELEASE_GRAPH_ID,
        "offline_release_id": OFFLINE_RELEASE_ID,
        "capability_ratchet_epoch": CAPABILITY_RATCHET_EPOCH,
        "technical_debt_ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
        "required_reports": 49, "required_artifacts": 27,
        "required_receipts": MIN_SCENARIO_EVOLUTION_RECEIPTS,
        "authenticated_receipts": MIN_SCENARIO_EVOLUTION_RECEIPTS,
        "receipt_records": [{"stage": stage_id, "receipt_sha256": hashlib.sha256(stage_id.encode("utf-8")).hexdigest()} for stage_id in SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES],
        "errors": [],
    })
    write_json(reports / "scenario-evolution-evidence-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 22,
        "expected_rejections": 20, "accepted_attacks": 0, "errors": [],
        "results": [
            {"case_id": "standalone_report_hash_mode", "classification": "PASS"},
            {"case_id": "graph_bound_receipt_baseline", "classification": "PASS"},
            {"case_id": "behavior_archive_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "behavior_archive_checker_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "behavior_archive_attack_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "stale_behavior_archive_output", "classification": "EXPECTED_REJECTION"},
            {"case_id": "treatment_admission_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "treatment_admission_attack_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "stale_treatment_projection_rejected", "classification": "EXPECTED_REJECTION"},
            {"case_id": "plain_language_summary_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "plain_language_summary_attack_receipt_missing", "classification": "EXPECTED_REJECTION"},
            {"case_id": "stale_plain_language_summary_rejected", "classification": "EXPECTED_REJECTION"},
        ],
    })

    write_json(reports / "release-technical-debt-policy.json", {
        "classification": "PASS", "status": "PASS", "absolute_debt_free_claim_permitted": False,
        "accepted_risks": [], "known_release_blockers_remaining": 0,
        "entries": 19, "required_receipt_count": TECHNICAL_DEBT_RATCHET_RECEIPTS, "errors": [],
    })
    write_json(reports / "release-technical-debt-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 20, "errors": [],
    })
    write_json(reports / "technical-debt-ratchet.json", {
        "classification": "PASS", "status": "PASS", "ratchet_id": TECHNICAL_DEBT_RATCHET_ID,
        "ratchet_epoch": TECHNICAL_DEBT_RATCHET_EPOCH,
        "ratchet_anchor_sha256": TECHNICAL_DEBT_RATCHET_ANCHOR,
        "accepted_risks": 0, "required_receipt_count": TECHNICAL_DEBT_RATCHET_RECEIPTS,
        "entry_count": 19, "errors": [],
    })
    write_json(reports / "technical-debt-ratchet-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": 14,
        "expected_rejections": 13, "accepted_regressions": 0, "errors": [],
    })
    write_json(reports / "production-simulation-designation-mutations.json", {
        "classification": "PASS", "status": "PASS", "cases": len(_case_specs()),
        "expected_rejections": len(_case_specs()) - 1, "accepted_regressions": 0, "errors": [],
    })

    write_json(reports / "facility-decision-release.json", {"classification": "PASS"})
    write_json(reports / "release-technical-debt-final.json", {
        "classification": "PASS", "known_release_blockers_remaining": 0,
        "absolute_debt_free_claim_permitted": False,
        "required_receipt_count": TECHNICAL_DEBT_RATCHET_RECEIPTS,
        "authenticated_receipt_count": TECHNICAL_DEBT_RATCHET_RECEIPTS,
    })
    write_json(reports / "release-graph-final-evidence.json", {
        "classification": "PASS", "authenticated_receipt_count": MIN_GRAPH_STAGES - 1,
        "predecessor_stage_count": MIN_GRAPH_STAGES - 1, "truth_boundaries": truth,
        "operational_timing_calibrated": False, "patient_care_authority_granted": False,
        "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
        "direct_patient_care": "PROHIBITED", "clinical_decision_support": "PROHIBITED",
        "clinical_timing_transferability": "NOT_ESTABLISHED",
    })

    for stage in stages:
        for relative in stage["outputs"]:
            path = root / relative
            if relative == "dist":
                path.mkdir(parents=True, exist_ok=True)
                continue
            if path.exists():
                continue
            write_json(path, {"classification": "PASS", "status": "PASS", "fixture_stage": stage["id"]})

    lock = subprocess.run(
        ["python3", "scripts/lock_release_graph.py", "--repo", "."], cwd=root,
        check=False, capture_output=True, text=True, env=_isolated_environment(),
    )
    if lock.returncode != 0:
        raise RuntimeError(f"production fixture graph lock failed:{lock.stdout[-3000:]}:{lock.stderr[-1000:]}")
    locked_graph = read_json(root / "config/release/RELEASE_GRAPH.json")
    _generate_fixture_receipts(root, locked_graph, locked_graph["stages"])
    return root


def _edit(path: Path, mutate: Callable[[dict], None]) -> None:
    value = read_json(path)
    mutate(value)
    write_json(path, value)


def _case_specs() -> list[tuple[str, Mutator | None, str | None]]:
    return [
        ("baseline_grants_scoped_simulation_designation", None, None),
        ("policy_self_anchor_tampered", lambda r: _edit(r / "config/release/PRODUCTION_SIMULATION_POLICY.json", lambda d: d.__setitem__("policy_anchor_sha256", "0" * 64)), "production simulation policy self-anchor differs"),
        ("policy_report_floor_lowered_and_reanchored", lambda r: (_edit(r / "config/release/PRODUCTION_SIMULATION_POLICY.json", lambda d: d["required_reports"].pop()), _refresh_policy_anchor(r / "config/release/PRODUCTION_SIMULATION_POLICY.json")), "production simulation policy differs from compiled monotonic floor"),
        ("policy_receipt_floor_lowered_and_reanchored", lambda r: (_edit(r / "config/release/PRODUCTION_SIMULATION_POLICY.json", lambda d: d["required_stage_receipts"].remove("scenario.evolution-evidence-attacks")), _refresh_policy_anchor(r / "config/release/PRODUCTION_SIMULATION_POLICY.json")), "production simulation policy differs from compiled monotonic floor"),
        ("missing_required_report_rejected", lambda r: (r / "reports/simulation-quality-assurance.json").unlink(), "required report unavailable:reports/simulation-quality-assurance.json"),
        ("failed_required_report_rejected", lambda r: _edit(r / "reports/simulation-quality-assurance.json", lambda d: d.__setitem__("classification", "FAIL")), "required report not PASS:reports/simulation-quality-assurance.json"),
        ("graph_check_floor_rejected", lambda r: _edit(r / "reports/release-graph-consistency.json", lambda d: d.__setitem__("checks", MIN_GRAPH_CHECKS - 1)), "release graph structural-check floor regressed"),
        ("graph_mutation_floor_rejected", lambda r: _edit(r / "reports/release-graph-mutations.json", lambda d: d.__setitem__("cases", MIN_GRAPH_MUTATION_CASES - 1)), "release graph adversarial-case floor regressed"),
        ("simulated_workflow_permission_removed_rejected", lambda r: _edit(r / "reports/release-intended-use.json", lambda d: d.__setitem__("simulated_patient_care_workflows", "PROHIBITED")), "intended-use report does not permit validated simulated patient-care workflows"),
        ("clinical_timing_promotion_rejected", lambda r: _edit(r / "reports/simulation-timing-assurance.json", lambda d: d.__setitem__("clinical_operational_timing", "CALIBRATED")), "clinical operational timing was promoted in timing evidence"),
        ("clinical_timing_transferability_promotion_rejected", lambda r: _edit(r / "reports/simulation-timing-assurance.json", lambda d: d.__setitem__("clinical_timing_transferability", "ESTABLISHED")), "clinical timing transferability was promoted in timing evidence"),
        ("direct_patient_care_promotion_rejected", lambda r: _edit(r / "reports/release-intended-use.json", lambda d: d.__setitem__("direct_patient_care", "PERMITTED")), "intended-use report promoted direct patient care"),
        ("hub_source_failure_rejected", lambda r: _edit(r / "reports/hub-security.json", lambda d: d.__setitem__("classification", "FAIL")), "required report not PASS:reports/hub-security.json"),
        ("hub_runtime_sample_too_small_rejected", lambda r: _edit(r / "reports/hub-runtime-smoke.json", lambda d: d["response_time"].__setitem__("samples", 39)), "hub runtime response sample too small"),
        ("hub_runtime_p99_budget_rejected", lambda r: _edit(r / "reports/hub-runtime-smoke.json", lambda d: d["response_time"].__setitem__("p99_ms", 251)), "hub runtime response budget exceeded"),
        ("offline_release_identity_drift_rejected", lambda r: _edit(r / "reports/offline-scenario-release-check.json", lambda d: d.__setitem__("release_id", "ASK-OFFLINE-STALE")), "offline Python release ID differs"),
        ("offline_attack_accepted_rejected", lambda r: _edit(r / "reports/offline-scenario-release-mutations.json", lambda d: d.__setitem__("accepted_attacks", 1)), "offline release attack was accepted"),
        ("documentation_profile_drift_rejected", lambda r: _edit(r / "reports/scenario-engine-evolution-docs-node.json", lambda d: d.__setitem__("checker_profile", "WEAK")), "engine documentation Node profile differs"),
        ("node_cli_attack_accepted_rejected", lambda r: _edit(r / "reports/node-checker-cli-mutations.json", lambda d: d.__setitem__("accepted_attacks", 1)), "Node checker CLI attack was accepted"),
        ("behavior_archive_duplicate_rejected", lambda r: _edit(r / "reports/scenario-behavior-archive.json", lambda d: d["summary"].__setitem__("duplicate_behavior_candidates", 1)), "scenario behavior archive contains duplicate behavior candidates"),
        ("behavior_archive_selection_promotion_rejected", lambda r: _edit(r / "reports/scenario-behavior-archive.json", lambda d: d.__setitem__("selection_boundary", "LEARNER_SCORING")), "scenario behavior archive was promoted to learner scoring"),
        ("behavior_archive_checker_root_drift_rejected", lambda r: _edit(r / "reports/scenario-behavior-archive-check.json", lambda d: d.__setitem__("archive_root_sha256", "0" * 64)), "scenario behavior archive checker root differs"),
        ("behavior_archive_attack_accepted_rejected", lambda r: _edit(r / "reports/scenario-behavior-archive-mutations.json", lambda d: d.__setitem__("accepted_attacks", 1)), "scenario behavior archive attack was accepted"),
        ("behavioral_policy_class_floor_rejected", lambda r: _edit(r / "reports/scenario-behavioral-equivalence.json", lambda d: d["summary"].__setitem__("policy_equivalence_classes", BEHAVIORAL_POLICY_FLOORS["policy_equivalence_classes"] - 1)), "behavioral-policy floor regressed:policy_equivalence_classes"),
        ("behavioral_policy_context_floor_rejected", lambda r: _edit(r / "reports/scenario-behavioral-equivalence.json", lambda d: d["summary"].__setitem__("unique_context_signatures", BEHAVIORAL_POLICY_FLOORS["unique_context_signatures"] - 1)), "behavioral-policy floor regressed:unique_context_signatures"),
        ("behavioral_policy_novelty_floor_rejected", lambda r: _edit(r / "reports/scenario-behavioral-equivalence.json", lambda d: d["summary"].__setitem__("policy_novelty_ratio_bps", BEHAVIORAL_POLICY_FLOORS["policy_novelty_ratio_bps"] - 1)), "behavioral-policy floor regressed:policy_novelty_ratio_bps"),
        ("behavioral_policy_generation_divergence_rejected", lambda r: _edit(r / "reports/scenario-behavioral-equivalence-generation.json", lambda d: d.__setitem__("policy_equivalence_classes", 3)), "behavioral-policy generation summary differs:policy_equivalence_classes"),
        ("behavioral_policy_archive_profile_rejected", lambda r: _edit(r / "reports/scenario-behavioral-equivalence.json", lambda d: d.__setitem__("archive_profile", "WEAK_ARCHIVE")), "behavioral-policy archive profile differs"),
        ("telemetry_cross_checker_root_drift_rejected", lambda r: _edit(r / "reports/scenario-science-telemetry-node.json", lambda d: d.__setitem__("event_chain_root_sha256", "0" * 64)), "scenario-science telemetry independent roots differ"),
        ("operational_pack_imbalance_rejected", lambda r: _edit(r / "reports/operational-scenario-pack-generation.json", lambda d: d["profile_counts"].__setitem__("DIRECT_HANDOFF_BASELINE", 2)), "operational scenario pack is not balanced 12-by-four"),
        ("stakeholder_treatment_promotion_rejected", lambda r: _edit(r / "reports/stakeholder-product-bundle.json", lambda d: d.__setitem__("admitted_treatments", 1)), "stakeholder bundle admits a treatment"),
        ("treatment_projection_drift_rejected", lambda r: _edit(r / "reports/treatment-admission-registry-node.json", lambda d: d.__setitem__("projection_sha256", "0" * 64)), "treatment registry independent projection differs"),
        ("plain_language_identity_drift_rejected", lambda r: _edit(r / "reports/plain-language-change-summary-node.json", lambda d: d.__setitem__("summary_id", "stale-summary")), "plain-language independent identity differs"),
        ("capability_floor_regression_rejected", lambda r: _edit(r / "reports/scenario-capability-ratchet.json", lambda d: d["observed"]["scenario_experience"].__setitem__("generated_cases", 106)), "scenario capability regressed:scenario_experience.generated_cases"),
        ("capability_attack_accepted_rejected", lambda r: _edit(r / "reports/scenario-capability-ratchet-mutations.json", lambda d: d.__setitem__("accepted_regressions", 1)), "scenario capability regression was accepted"),
        ("scenario_evolution_hash_only_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence.json", lambda d: d.__setitem__("receipt_binding_mode", "STANDALONE_REPORT_HASH_ONLY")), "scenario evolution evidence is not graph-receipt-bound"),
        ("scenario_evolution_profile_regression_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence.json", lambda d: d.__setitem__("evidence_profile", "AUTHENTICATED_SCENARIO_EVOLUTION_EVIDENCE_JOIN_V6")), "scenario evolution evidence profile differs"),
        ("scenario_evolution_required_receipt_floor_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence.json", lambda d: d.__setitem__("required_receipts", MIN_SCENARIO_EVOLUTION_RECEIPTS - 1)), "scenario evolution receipt inventory differs"),
        ("scenario_evolution_authenticated_receipt_shortfall_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence.json", lambda d: d.__setitem__("authenticated_receipts", MIN_SCENARIO_EVOLUTION_RECEIPTS - 1)), "scenario evolution receipt set incomplete"),
        ("scenario_evolution_receipt_stage_missing_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence.json", lambda d: d.__setitem__("receipt_records", d["receipt_records"][:-1])), "scenario evolution receipt stage inventory differs"),
        ("scenario_evolution_attack_accepted_rejected", lambda r: _edit(r / "reports/scenario-evolution-evidence-mutations.json", lambda d: d.__setitem__("accepted_attacks", 1)), "scenario evolution attack was accepted"),
        ("debt_policy_blocker_rejected", lambda r: _edit(r / "reports/release-technical-debt-policy.json", lambda d: d.__setitem__("known_release_blockers_remaining", 1)), "known release-blocking debt remains in source policy"),
        ("debt_attack_floor_rejected", lambda r: _edit(r / "reports/release-technical-debt-mutations.json", lambda d: d.__setitem__("cases", 19)), "technical-debt adversarial-case floor regressed"),
        ("debt_ratchet_epoch_drift_rejected", lambda r: _edit(r / "reports/technical-debt-ratchet.json", lambda d: d.__setitem__("ratchet_epoch", 2)), "technical-debt ratchet epoch differs"),
        ("debt_ratchet_attack_accepted_rejected", lambda r: _edit(r / "reports/technical-debt-ratchet-mutations.json", lambda d: d.__setitem__("accepted_regressions", 1)), "technical-debt ratchet regression was accepted"),
        ("production_attack_report_regressed", lambda r: _edit(r / "reports/production-simulation-designation-mutations.json", lambda d: d.__setitem__("accepted_regressions", 1)), "production designation regression was accepted"),
        ("known_blocker_rejected", lambda r: _edit(r / "reports/release-technical-debt-final.json", lambda d: d.__setitem__("known_release_blockers_remaining", 1)), "known release-blocking technical debt remains"),
        ("build_provenance_failure_rejected", lambda r: _edit(r / "reports/facility-decision-build-reproducibility.json", lambda d: d["provenance"].__setitem__("status", "FAIL")), "production build provenance not PASS"),
        ("build_root_divergence_rejected", lambda r: _edit(r / "reports/facility-decision-build-reproducibility.json", lambda d: d.__setitem__("second_build_root_sha256", "c" * 64)), "production builds are not byte-identical"),
        ("build_source_mutation_rejected", lambda r: _edit(r / "reports/facility-decision-build-reproducibility.json", lambda d: d.__setitem__("source_mutations", ["src/App.tsx"])), "production build mutated reviewed source"),
        ("stale_final_graph_receipt_rejected", lambda r: _edit(r / f".asklepios/release-receipts/{RELEASE_GRAPH_ID}/final.graph-evidence.json", lambda d: d.__setitem__("classification", "FAIL")), "required evidence receipt invalid or missing:final.graph-evidence"),
        ("missing_final_decision_receipt_rejected", lambda r: (r / f".asklepios/release-receipts/{RELEASE_GRAPH_ID}/final.decision-evidence.json").unlink(), "required evidence receipt invalid or missing:final.decision-evidence"),
        ("missing_offline_node_receipt_rejected", lambda r: (r / f".asklepios/release-receipts/{RELEASE_GRAPH_ID}/offline.release-node.json").unlink(), "required evidence receipt invalid or missing:offline.release-node"),
        ("missing_behavior_archive_receipt_rejected", lambda r: (r / f".asklepios/release-receipts/{RELEASE_GRAPH_ID}/scenario.behavior-archive-attacks.json").unlink(), "required evidence receipt invalid or missing:scenario.behavior-archive-attacks"),
        ("build_output_mutation_rejected", lambda r: _atomic_text(r / "dist/index.html", "mutated\n"), "required evidence receipt differs:build.double-reproducibility:output_root_sha256"),
        ("graph_simulated_workflow_removed_rejected", lambda r: _edit(r / "config/release/RELEASE_GRAPH.json", lambda d: d["truth_boundaries"].__setitem__("simulated_patient_care_workflows", "PROHIBITED")), "graph simulated patient-care workflow boundary differs"),
        ("graph_direct_care_promotion_rejected", lambda r: _edit(r / "config/release/RELEASE_GRAPH.json", lambda d: d["truth_boundaries"].__setitem__("direct_patient_care", "PERMITTED")), "graph direct patient care boundary was promoted"),
        ("final_graph_evidence_removed_rejected", lambda r: (r / "reports/release-graph-final-evidence.json").unlink(), "required report unavailable:reports/release-graph-final-evidence.json"),
    ]


def run(root: Path) -> dict:
    cases = _case_specs()
    results = []
    with tempfile.TemporaryDirectory(prefix="asklepios-production-suite-") as temporary:
        suite_root = Path(temporary)
        authenticated_fixture = suite_root / "authenticated-fixture"
        _copy_source(root, authenticated_fixture)
        _fixture(authenticated_fixture)
        immutable_root = _fixture_tree_root(authenticated_fixture)
        for index, (case_id, mutator, required) in enumerate(cases):
            print(f"START_CASE:{case_id}", flush=True)
            repo = suite_root / f"case-{index:02d}-{case_id}"
            _copy_authenticated_fixture(authenticated_fixture, repo)
            if mutator:
                mutator(repo)
            explicit_receipts = repo / ".asklepios/release-receipts" / RELEASE_GRAPH_ID
            observed = evaluate(repo, explicit_receipts)
            errors = observed.get("errors", [])
            if mutator is None:
                passed = observed.get("classification") == PASS and observed.get("designation") == GRANT
                classification = PASS if passed else FAIL
            else:
                passed = (
                    observed.get("classification") == FAIL
                    and observed.get("designation") == DEFAULT
                    and required is not None
                    and any(required in error for error in errors)
                )
                classification = EXPECTED_REJECTION if passed else FAIL
            fixture_unchanged = _fixture_tree_root(authenticated_fixture) == immutable_root
            if not fixture_unchanged:
                passed = False
                classification = FAIL
                errors = [*errors, "authenticated fixture mutated across isolated case"]
            print(f"END_CASE:{case_id}:{observed.get('classification')}:{len(errors)}", flush=True)
            results.append(case_result(
                case_id,
                classification,
                errors=[] if passed else errors,
                required_error=required,
                observed_classification=observed.get("classification"),
                observed_designation=observed.get("designation"),
                fixture_unchanged=fixture_unchanged,
            ))
    classification = suite_classification(results)
    accepted_regressions = sum(1 for result in results if result.get("classification") == FAIL)
    return {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "expected_rejections": len(results) - 1,
        "accepted_regressions": accepted_regressions,
        "fixture_copy_mode": "HARDLINKED_IMMUTABLE_FIXTURE_WITH_ROOT_RECHECK_V1",
        "fixture_source_profile": FIXTURE_SOURCE_PROFILE,
        "results": results,
        "errors": [] if classification == PASS else ["production simulation designation mutation suite failed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/production-simulation-designation-mutations.json"))
    args = parser.parse_args()
    root = args.repo.resolve()
    report = run(root)
    write_json(root / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
