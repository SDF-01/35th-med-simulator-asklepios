#!/usr/bin/env python3
"""Canonical RC3.8A.1 offline-scenario release reconstruction primitives."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from engine_evolution_common import (
    DOCUMENTATION_SURFACE_PHRASES,
    EVOLUTION_END_MARKER,
    EVOLUTION_START_MARKER,
    PROHIBITED_LIVE_DEPLOYMENT_CLAIMS,
    render_evolution_block,
)
from release_identity_common import (
    GRAPH_BINDING_MODE,
    release_graph_contract_sha256,
)
from scenario_genome_common import (
    GenomeError,
    canonical_sha256,
    atomic_write_json,
    file_sha256,
    hash_without,
    load_object,
    safe_repo_path,
)

POLICY_PATH = "config/release/OFFLINE_SCENARIO_RELEASE.json"
GRAPH_PATH = "config/release/RELEASE_GRAPH.json"
GENOME_PATH = "public/data/scenario_core/verified_scenario_genome.json"
CAPABILITY_PATH = "config/release/SCENARIO_CAPABILITY_RATCHET.json"
DEBT_PATH = "config/release/TECHNICAL_DEBT_RATCHET.json"

COMPILED_RELEASE_ID = 'ASK-OFFLINE-RC3.8A.1'
COMPILED_DISPLAY_VERSION = 'RC3.8A.1'
COMPILED_ENGINE_EVOLUTION = 'SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8'
COMPILED_GRAPH_ID = 'asklepios-rc3.8a.1-scenario-science-stakeholder-graph'
COMPILED_GRAPH_STAGE_COUNT = 122
COMPILED_GRAPH_TARGET_COUNT = 26
COMPILED_GRAPH_BINDING_MODE = GRAPH_BINDING_MODE
COMPILED_CAPABILITY_RATCHET = ('asklepios-scenario-capability-ratchet-v1', 5)
COMPILED_CAPABILITY_ANCHOR = '870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e'
COMPILED_DEBT_RATCHET = ('asklepios-technical-debt-ratchet-v1', 8)
COMPILED_DEBT_ANCHOR = '84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91'
COMPILED_TRUTH_BOUNDARY = {'clinical_authority': 'NOT_GRANTED',
 'human_team_behavior': 'STRUCTURAL_ONLY_NOT_CALIBRATED',
 'operational_calibration': 'NOT_CALIBRATED',
 'patient_care_use': 'PROHIBITED',
 'patient_dynamics': 'SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY',
 'quality_vector_use': 'SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING',
 'scoring_behavior': 'inherited_unchanged'}
COMPILED_OFFLINE_GUARANTEES = {'content_security_policy_connect_none': True,
 'deterministic_replay': True,
 'external_runtime_assets': False,
 'installation_required': False,
 'network_requests': False,
 'server_required': False,
 'single_file': True}
COMPILED_REQUIRED_CAPABILITIES = {'acyclic_release_identity_graph',
 'after_action_review',
 'behavioral_policy_equivalence_archive',
 'behavioral_quality_diversity_archive',
 'canonical_writer_independent_verifier',
 'capability_ratchet',
 'clock_driven_world_events',
 'complete_release_dag_diagnostics',
 'cross_platform_checker_cli_and_atomic_reports',
 'differential_engine_documentation_verification',
 'event_sourced_replay',
 'hidden_information_release',
 'integer_only_nonclinical_selection_vector',
 'learner_wit_separation',
 'monotonic_technical_debt_ratchet',
 'narrative_and_provenance_invariance_guard',
 'operational_scenario_pack',
 'plain_language_change_summary',
 'plain_language_release_contract',
 'playable_offline_role_model_profiles',
 'privacy_bounded_telemetry',
 'reachable_terminating_route_topology',
 'receipt_bound_evidence',
 'scenario_genome_identity',
 'scoped_technical_debt_receipt_gate',
 'source_bound_scoring',
 'source_conformance_scorecard',
 'stakeholder_capability_dashboard',
 'timeout_branch',
 'treatment_admission_pipeline',
 'unsafe_action_fail_closed_branches'}
COMPILED_DOCUMENTATION_REQUIRED_LITERALS: dict[str, tuple[str, ...]] = {'facility': ('## Engine evolution binding',
              '- Canonical-writer rule:',
              '- Receipt rule:',
              '- Release-identity rule:',
              '- Route topology:',
              '- Technical-debt ratchet:',
              '- Behavioral quality-diversity:',
              'does not establish clinical certification',
              'direct patient care',
              '- Behavioral policy diversity:',
              '- Operational scenario pack:',
              '- Four playable offline role-model teamwork challenges:',
              '- Source-conformance scorecard:',
              '- Treatment-admission pipeline:',
              'Plain-language release translation'),
 'root': ('Canonical repository: https://github.com/SDF-01/ProjectAsklepios',
          '## Static exercise catalog (100 TOON-authored exercises)',
          '- Checker boundary:',
          '- Artifact authority:',
          '- Evidence freshness:',
          '- Release-identity DAG:',
          '- Route topology:',
          '- Technical-debt ratchet:',
          '- Diagnostic model:',
          '- Behavioral quality-diversity:',
          'Clinical authority remains NOT_GRANTED.',
          'Operational timing remains NOT_CALIBRATED.',
          'Direct patient care and clinical decision support remain prohibited.',
          '- Behavioral policy diversity:',
          '- Operational scenario pack:',
          '- Four playable offline role-model teamwork challenges:',
          '- Source-conformance scorecard:',
          '- Treatment-admission pipeline:',
          '- Plain-language release translation:'),
 'standalone': ('## Engine evolution and reproducibility boundary',
                'Canonical writer',
                'Independent verifier',
                'Evidence consumers authenticate',
                'acyclic semantic graph projection',
                'monotonic across ratchet epochs',
                'Behavioral quality-diversity',
                "connect-src 'none'",
                'not an empirically calibrated real-clinical workflow clock',
                'does not establish clinical certification',
                'direct patient care',
                'Behavioral policy diversity',
                'Operational scenario pack',
                'Four playable offline role-model teamwork challenges',
                'Source-conformance scorecard',
                'Treatment-admission pipeline',
                'Plain-language release translation'),
 'verified': ('## Engine evolution binding',
              '- Canonical-writer rule:',
              '- Receipt rule:',
              '- Release-identity rule:',
              '- Route topology:',
              '- Technical-debt ratchet:',
              '- Behavioral quality-diversity:',
              'does not establish clinical certification',
              'direct patient care',
              '- Behavioral policy diversity:',
              '- Operational scenario pack:',
              '- Four playable offline role-model teamwork challenges:',
              '- Source-conformance scorecard:',
              '- Treatment-admission pipeline:',
              'Plain-language release translation')}
COMPILED_DOCUMENTATION_WRITER_OWNED_SURFACES = ('root', 'standalone')
COMPILED_DOCUMENTATION_VERIFICATION_ONLY_SURFACES = ('facility', 'verified')

COMPILED_DOCUMENTATION_FORBIDDEN_CASEFOLD: dict[str, tuple[str, ...]] = {'root': ('deployment is currently healthy',
          'production deployment is healthy',
          'vercel preview is healthy',
          'the live deployment is healthy',
          'generated scenario catalog (107 toon-authored exercises)')}

COMPILED_ARTIFACTS = {'behavioral_diversity_policy': 'config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json',
 'capability_ratchet': 'config/release/SCENARIO_CAPABILITY_RATCHET.json',
 'facility_manifest': 'examples/facility-arrival/manifest.json',
 'facility_readme': 'examples/facility-arrival/README.md',
 'operational_pack_policy': 'config/scenario-science/OPERATIONAL_SCENARIO_PACK_POLICY.json',
 'operational_scenario_pack': 'public/data/scenario_library/operational-pack.json',
 'plain_language_change_summary': 'docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md',
 'plain_language_release_contract': 'config/product/PLAIN_LANGUAGE_RELEASE_CONTRACT.json',
 'playable_html': 'examples/facility-arrival/playable.html',
 'root_readme': 'README.md',
 'scenario_genome': 'public/data/scenario_core/verified_scenario_genome.json',
 'scenario_science_policy': 'config/scenario-science/SCENARIO_SCIENCE_POLICY.json',
 'stakeholder_capability_map': 'config/product/STAKEHOLDER_CAPABILITY_MAP.json',
 'stakeholder_dashboard': 'public/data/scenario_library/stakeholder-dashboard.json',
 'stakeholder_release_summary': 'docs/RC3_8_STAKEHOLDER_RELEASE_SUMMARY.md',
 'standalone_documentation': 'docs/FACILITY_ARRIVAL_STANDALONE.md',
 'technical_debt_ratchet': 'config/release/TECHNICAL_DEBT_RATCHET.json',
 'treatment_admission_projection': 'public/data/scenario_library/treatment-admission.json',
 'treatment_admission_registry': 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json',
 'verified_manifest': 'examples/verified-scenario/manifest.json',
 'verified_readme': 'examples/verified-scenario/README.md'}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenomeError(message)


def _unique_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value) and len(value) == len(set(value))



def load_release_context(repo: Path) -> dict[str, dict[str, Any]]:
    repo = repo.resolve(strict=True)
    policy = load_object(safe_repo_path(repo, POLICY_PATH))
    graph = load_object(safe_repo_path(repo, GRAPH_PATH))
    genome = load_object(safe_repo_path(repo, GENOME_PATH))
    capability = load_object(safe_repo_path(repo, CAPABILITY_PATH))
    debt = load_object(safe_repo_path(repo, DEBT_PATH))

    _require(policy.get("schema_version") == "1.0.0", "offline release policy schema differs")
    _require(policy.get("release_id") == COMPILED_RELEASE_ID, "offline release policy ID differs")
    _require(policy.get("display_version") == COMPILED_DISPLAY_VERSION, "offline release display version differs")
    _require(policy.get("engine_evolution") == COMPILED_ENGINE_EVOLUTION, "offline engine-evolution profile differs")
    _require(policy.get("expected_graph_id") == COMPILED_GRAPH_ID, "offline policy graph ID differs")
    _require(policy.get("expected_graph_stage_count") == COMPILED_GRAPH_STAGE_COUNT, "offline policy graph stage count differs")
    _require(policy.get("expected_graph_target_count") == COMPILED_GRAPH_TARGET_COUNT, "offline policy graph target count differs")
    _require(policy.get("release_graph_binding_mode") == COMPILED_GRAPH_BINDING_MODE, "offline graph binding mode differs")
    _require(
        (policy.get("expected_capability_ratchet_id"), policy.get("expected_capability_ratchet_epoch")) == COMPILED_CAPABILITY_RATCHET,
        "offline policy capability-ratchet floor differs",
    )
    _require(
        (policy.get("expected_technical_debt_ratchet_id"), policy.get("expected_technical_debt_ratchet_epoch")) == COMPILED_DEBT_RATCHET,
        "offline policy technical-debt-ratchet floor differs",
    )
    _require(policy.get("truth_boundary") == COMPILED_TRUTH_BOUNDARY, "offline truth boundary differs")
    _require(policy.get("offline_guarantees") == COMPILED_OFFLINE_GUARANTEES, "offline guarantee contract differs")
    capabilities = policy.get("required_capabilities")
    _require(_unique_strings(capabilities), "offline capability inventory malformed")
    _require(set(capabilities) == COMPILED_REQUIRED_CAPABILITIES, "offline capability inventory differs")

    artifacts = policy.get("artifact_inventory")
    _require(isinstance(artifacts, list) and bool(artifacts), "offline artifact inventory missing")
    observed_artifacts: dict[str, str] = {}
    for index, record in enumerate(artifacts if isinstance(artifacts, list) else []):
        _require(isinstance(record, dict), f"offline artifact record malformed:{index}")
        name = record.get("name")
        relative = record.get("path")
        _require(isinstance(name, str) and name, f"offline artifact name missing:{index}")
        _require(isinstance(relative, str) and relative, f"offline artifact path missing:{name}")
        _require(name not in observed_artifacts, f"offline artifact name duplicated:{name}")
        safe_repo_path(repo, relative)
        observed_artifacts[name] = relative
    _require(observed_artifacts == COMPILED_ARTIFACTS, "offline artifact inventory differs")

    _require(graph.get("graph_id") == COMPILED_GRAPH_ID, "offline release graph identity differs")
    _require(len(graph.get("stages", [])) == COMPILED_GRAPH_STAGE_COUNT, "offline release graph stage count differs")
    _require(len(graph.get("targets", {})) == COMPILED_GRAPH_TARGET_COUNT, "offline release graph target count differs")
    _require(
        (capability.get("ratchet_id"), capability.get("ratchet_epoch")) == COMPILED_CAPABILITY_RATCHET,
        "offline capability ratchet binding differs",
    )
    _require(
        (debt.get("ratchet_id"), debt.get("ratchet_epoch")) == COMPILED_DEBT_RATCHET,
        "offline technical-debt ratchet binding differs",
    )
    _require(capability.get("ratchet_anchor_sha256") == COMPILED_CAPABILITY_ANCHOR, "offline capability ratchet anchor differs")
    _require(debt.get("ratchet_anchor_sha256") == COMPILED_DEBT_ANCHOR, "offline technical-debt ratchet anchor differs")
    _require(capability.get("authority_boundary") == COMPILED_TRUTH_BOUNDARY, "capability-ratchet truth boundary differs")
    identity_digest = hash_without(genome, "genome_id", "genome_sha256")
    _require(genome.get("genome_id") == f"ASK-GENOME-{identity_digest[:16].upper()}", "scenario Genome ID mismatch")
    _require(genome.get("genome_sha256") == hash_without(genome, "genome_sha256"), "scenario Genome self-hash mismatch")

    docs = policy.get("documentation_contract")
    _require(isinstance(docs, dict), "offline documentation contract missing")
    for key in (
        "root_readme", "root_start_marker", "root_end_marker",
        "standalone_readme", "standalone_start_marker", "standalone_end_marker",
        "facility_readme", "verified_readme",
    ):
        _require(isinstance(docs.get(key), str) and docs.get(key), f"offline documentation contract missing:{key}")
    for key in ("root_readme", "standalone_readme", "facility_readme", "verified_readme"):
        safe_repo_path(repo, docs[key])

    observed_required = docs.get("required_literals")
    expected_required = {key: list(value) for key, value in COMPILED_DOCUMENTATION_REQUIRED_LITERALS.items()}
    _require(observed_required == expected_required, "offline documentation required-literal contract differs")
    observed_forbidden = docs.get("forbidden_casefold_phrases")
    expected_forbidden = {key: list(value) for key, value in COMPILED_DOCUMENTATION_FORBIDDEN_CASEFOLD.items()}
    _require(observed_forbidden == expected_forbidden, "offline documentation forbidden-phrase contract differs")
    _require(
        docs.get("writer_owned_surfaces") == list(COMPILED_DOCUMENTATION_WRITER_OWNED_SURFACES),
        "offline documentation writer-owned surface contract differs",
    )
    _require(
        docs.get("verification_only_surfaces") == list(COMPILED_DOCUMENTATION_VERIFICATION_ONLY_SURFACES),
        "offline documentation verification-only surface contract differs",
    )
    _require(
        set(docs["writer_owned_surfaces"]).isdisjoint(docs["verification_only_surfaces"])
        and set(docs["writer_owned_surfaces"]) | set(docs["verification_only_surfaces"]) == {"root", "standalone", "facility", "verified"},
        "offline documentation ownership partition differs",
    )

    _require(policy.get("output_path") == "public/data/scenario_core/offline_scenario_release.json", "offline descriptor path differs")
    _require(policy.get("report_path") == "reports/offline-scenario-release.json", "offline report path differs")
    _require(policy.get("canonical_repository_url") == "https://github.com/SDF-01/ProjectAsklepios", "canonical repository URL differs")
    return {"policy": policy, "graph": graph, "genome": genome, "capability": capability, "debt": debt}


def validate_documentation_semantics(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Validate non-generated documentation truth/UX guardrails.

    Generated block equality alone cannot protect surrounding repository prose.
    This compiled contract makes canonical repository identity, catalog semantics,
    authority warnings, and checker/ratchet explanations monotonic.
    """
    docs = context["policy"]["documentation_contract"]
    paths = {
        "root": docs["root_readme"],
        "facility": docs["facility_readme"],
        "verified": docs["verified_readme"],
        "standalone": docs["standalone_readme"],
    }
    errors: list[str] = []
    for label, relative in paths.items():
        path = safe_repo_path(repo, relative)
        if path.is_symlink() or not path.is_file():
            errors.append(f"offline documentation unavailable or unsafe:{relative}")
            continue
        text = path.read_text(encoding="utf-8")
        folded = text.casefold()
        for literal in COMPILED_DOCUMENTATION_REQUIRED_LITERALS[label]:
            if literal.casefold() not in folded:
                errors.append(f"offline documentation required literal missing:{label}:{literal}")
        for phrase in COMPILED_DOCUMENTATION_FORBIDDEN_CASEFOLD.get(label, ()):
            if phrase in folded:
                errors.append(f"offline documentation forbidden claim:{label}:{phrase}")
    return sorted(set(errors))


def evolution_binding(context: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    policy = context["policy"]
    graph = context["graph"]
    genome = context["genome"]
    capability = context["capability"]
    debt = context["debt"]
    return {
        "release_id": policy["release_id"],
        "display_version": policy["display_version"],
        "engine_evolution": policy["engine_evolution"],
        "scenario_genome": {
            "genome_id": genome["genome_id"],
            "genome_sha256": genome["genome_sha256"],
        },
        "capability_ratchet": {
            "ratchet_id": capability["ratchet_id"],
            "ratchet_epoch": capability["ratchet_epoch"],
            "ratchet_anchor_sha256": capability["ratchet_anchor_sha256"],
        },
        "technical_debt_ratchet": {
            "ratchet_id": debt["ratchet_id"],
            "ratchet_epoch": debt["ratchet_epoch"],
            "ratchet_anchor_sha256": debt["ratchet_anchor_sha256"],
        },
        "release_graph": {
            "graph_id": graph["graph_id"],
            "stage_count": len(graph["stages"]),
            "target_count": len(graph["targets"]),
            "binding_mode": COMPILED_GRAPH_BINDING_MODE,
            "contract_sha256": release_graph_contract_sha256(graph),
        },
        "capability_floor": {
            "scenario_experience": capability["hard_floors"]["scenario_experience"],
            "scenario_contract": capability["hard_floors"]["scenario_contract"],
        },
        "offline_guarantees": policy["offline_guarantees"],
        "truth_boundary": policy["truth_boundary"],
    }


def replace_exact_block(text: str, start: str, end: str, replacement: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise GenomeError(f"documentation marker inventory differs:{start}:{end}")
    first = text.index(start)
    last = text.index(end, first) + len(end)
    if last <= first:
        raise GenomeError(f"documentation marker order differs:{start}:{end}")
    # Keep a blank line around a generated block when surrounding content is
    # present, but never manufacture an empty Markdown line at end-of-file.
    # `git diff --check` treats that trailing blank line as a release defect,
    # so canonical documentation must end with exactly one LF byte.
    prefix = text[:first].rstrip()
    suffix = text[last:].lstrip("\n")
    rendered = prefix + "\n\n" + replacement.rstrip()
    if suffix:
        rendered += "\n\n" + suffix.rstrip("\n")
    return rendered.rstrip("\n") + "\n"


def render_root_section(context: Mapping[str, Mapping[str, Any]]) -> str:
    p = context["policy"]
    g = context["genome"]
    c = context["capability"]
    d = context["debt"]
    graph = context["graph"]
    experience = c["hard_floors"]["scenario_experience"]
    contract = c["hard_floors"]["scenario_contract"]
    docs = p["documentation_contract"]
    return "\n".join([
        docs["root_start_marker"],
        f"## Current canonical offline scenario and engine evolution ({p['display_version']})",
        "",
        "[Open the complete Facility Arrival walkthrough](examples/facility-arrival/README.md), or download [`playable.html`](examples/facility-arrival/playable.html?raw=1) and double-click it.",
        "",
        "[Open the browser-based Facility Arrival experience](/examples/facility-arrival).",
        "",
        "The standalone file embeds the learner interface, WIT process view, deterministic state machine, hidden-information schedule, clock-driven world events, timeout and unsafe-action branches, provenance view, replay, and after-action review. It requires no server, package installation, API, WebSocket, Vercel deployment, or network request.",
        "",
        "### Four playable offline role-model teamwork challenges",
        "",
        "- **Direct handoff baseline** — complete the normal closed-loop receiving workflow.",
        "- **Communications relay** — establish an intermediate relay and confirm receipt before the final handoff.",
        "- **Resource coordination** — coordinate a constrained resource and confirm ownership before the final handoff.",
        "- **Relay and resource coordination** — establish the relay first, coordinate the constrained resource second, and then close the handoff.",
        "",
        "Open `examples/facility-arrival/playable.html`, choose a role-model challenge at the top, and play it manually, with **Watch autoplay**, or with **Complete canonical replay**. These profiles keep the same source-bound clinical template; their added teamwork actions award zero clinical points and their timing remains uncalibrated exercise timing.",
        "",
        "[Open the canonical verified example](examples/verified-scenario/README.md) for the source package, Scenario Genome, evidence identity ledger, route topology, and open validity gates.",
        "",
        "### Scenario Genome, dual ratchets, and authenticated evidence",
        "",
        f"This documentation is generated from **{p['display_version']}** (`{p['release_id']}`) and `{graph['graph_id']}`.",
        "",
        f"- Engine evolution profile: `{p['engine_evolution']}`",
        f"- Scenario Genome: `{g['genome_id']}` (`{g['genome_sha256']}`)",
        f"- Capability ratchet: `{c['ratchet_id']}`, epoch `{c['ratchet_epoch']}` (`{c['ratchet_anchor_sha256']}`)",
        f"- Technical-debt ratchet: `{d['ratchet_id']}`, epoch `{d['ratchet_epoch']}` (`{d['ratchet_anchor_sha256']}`)",
        f"- Canonical release graph: `{graph['graph_id']}` with `{len(graph['stages'])}` stages and `{len(graph['targets'])}` targets",
        f"- Structural floor: `{experience['generated_cases']}` generated scenarios, `{experience['unique_operational_contexts']}` distinct contexts, strength-`{experience['covering_array_strength']}` coverage, `{experience['covered_interactions']}/{experience['required_interactions']}` feasible interactions, and zero uncovered interactions",
        f"- Contract floor: `{contract['generated_cases']}` cases across `{contract['unique_operational_contexts']}` distinct contract contexts",
        "- Behavioral quality-diversity: 107 unique structural behavior signatures occupy all 30 observed behavior cells; narrative-only and provenance-only variants do not create new behavior, and the integer quality vector is limited to scenario selection rather than learner scoring.",
        "- Behavioral policy diversity: four verified policy-equivalence classes require materially different learner coordination rather than cosmetic context changes.",
        "- Operational scenario pack: 12 reviewed scenarios are balanced three-per-profile across the four operational behavior classes.",
        "- Four playable offline role-model teamwork challenges: the no-server file exposes direct handoff, communications relay, resource coordination, and the combined route as selectable, replayable examples.",
        "- Source-conformance scorecard: four reference scorecards show evidence by dimension, preserve hard safety failure, and explicitly distinguish insufficient evidence from proficiency.",
        "- Treatment-admission pipeline: two concepts are tracked, zero are simulation-admitted, and no treatment choice is activated before source, applicability, scope, and SME gates pass.",
        "- Plain-language release translation: each release must explain stakeholder-visible changes and remaining scientific limitations without implementation jargon.",
        "- Checker boundary: all Node scenario-release checkers share one strict cross-platform CLI, repository-relative path guard, and atomic report writer.",
        "- Artifact authority: every governed artifact class has one canonical writer and at least one independently implemented read-only verifier.",
        "- Evidence freshness: final joins authenticate the current graph, stage configuration, input hashes, output hashes, and receipt chain; a copied `PASS` report is insufficient.",
        f"- Release-identity DAG: the offline descriptor binds `{COMPILED_GRAPH_BINDING_MODE}` contract `{release_graph_contract_sha256(graph)}` rather than the graph's raw file hash, while the graph independently locks the descriptor. This prevents self-referential hash cycles.",
        "- Route topology: only reachable, terminating, cycle-free routes with zero reachable nonterminal dead ends are admitted.",
        "- Technical-debt ratchet: reviewed debt records, blocker classifications, evidence floors, and final receipt obligations cannot be silently removed or weakened.",
        "- Diagnostic model: independent read-only branches may continue after a failure so one run can report the complete safe failure inventory; publication still fails closed.",
        "",
        "Clinical authority remains NOT_GRANTED. Operational timing remains NOT_CALIBRATED. Patient dynamics remain SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY. Direct patient care and clinical decision support remain prohibited.",
        "",
        "Rebuild and verify the offline boundary:",
        "",
        "```bash",
        "npm run generate:facility-arrival",
        "npm run generate:verified-scenario",
        "npm run generate:facility-arrival-standalone",
        "npm run generate:offline-scenario-release",
        "npm run verify:offline-scenario-release",
        "npm run verify:engine-evolution-docs",
        "npm run verify:facility-arrival-standalone",
        "```",
        docs["root_end_marker"],
    ])


def render_standalone_section(context: Mapping[str, Mapping[str, Any]]) -> str:
    p = context["policy"]
    g = context["genome"]
    c = context["capability"]
    d = context["debt"]
    graph = context["graph"]
    docs = p["documentation_contract"]
    return "\n".join([
        docs["standalone_start_marker"],
        "## Engine evolution and reproducibility boundary",
        "",
        f"The canonical offline artifact is bound to **{p['display_version']}** (`{p['release_id']}`) and `{p['engine_evolution']}`.",
        "",
        f"- Scenario Genome: `{g['genome_id']}` (`{g['genome_sha256']}`)",
        f"- Capability ratchet: `{c['ratchet_id']}`, epoch `{c['ratchet_epoch']}` (`{c['ratchet_anchor_sha256']}`)",
        f"- Technical-debt ratchet: `{d['ratchet_id']}`, epoch `{d['ratchet_epoch']}` (`{d['ratchet_anchor_sha256']}`)",
        f"- Release graph: `{graph['graph_id']}` with `{len(graph['stages'])}` stages and `{len(graph['targets'])}` targets",
        f"- Release-identity DAG: `{COMPILED_GRAPH_BINDING_MODE}` contract `{release_graph_contract_sha256(graph)}`",
        "- Canonical writer: `scripts/build_facility_arrival_standalone.py`",
        "- Independent verifier: `scripts/check_facility_arrival_standalone.py`",
        "- Offline release writer: `scripts/build_offline_scenario_release.py`",
        "- Independent offline verifier: `scripts/check_offline_scenario_release.mjs`",
        "",
        "The single-file artifact has no external runtime asset, server, API, WebSocket, or network request. Its content-security policy includes `connect-src 'none'`. The embedded simulation clock is deterministic and reproducible; it is not an empirically calibrated real-clinical workflow clock.",
        "",
        "Behavioral quality-diversity is structural and deterministic: 107 unique behavior signatures occupy all 30 observed cells. Narrative-only and provenance-only changes do not create new behavior, and the integer quality vector is restricted to scenario selection rather than learner scoring.",
        "",
        "Behavioral policy diversity distinguishes four genuinely different coordination policies. The operational scenario pack contains 12 reviewed scenarios, balanced three per policy profile.",
        "",
        "### Four playable offline role-model teamwork challenges",
        "",
        "The standalone page itself exposes **Direct handoff baseline**, **Communications relay**, **Resource coordination**, and **Relay and resource coordination**. The user can select any challenge and complete it manually, replay the canonical route immediately, or watch the deterministic autoplay. Added relay and resource actions are operational only, carry zero clinical points, and do not claim calibrated human timing.",
        "",
        "The source-conformance scorecard preserves hard safety failure and reports insufficient evidence rather than fabricated proficiency. The treatment-admission pipeline tracks two discovered concepts, but zero are simulation-admitted and zero active learner treatment choices exist. Plain-language release translation is required for every release.",
        "",
        "A release report is not accepted merely because it says `PASS`. Evidence consumers authenticate the current release graph, stage configuration, source inputs, output inventory, output hashes, and receipt chain. The offline descriptor uses an acyclic semantic graph projection instead of a raw graph-file digest, and capability and technical-debt floors are monotonic across ratchet epochs.",
        "",
        "This boundary demonstrates software integrity and simulation behavior only. It does not establish clinical certification, treatment authority, dynamic physiology, causal effect, human-team calibration, psychometric validity, or suitability for direct patient care.",
        docs["standalone_end_marker"],
    ])


def expected_documentation(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    policy = context["policy"]
    docs = policy["documentation_contract"]
    root_path = safe_repo_path(repo, docs["root_readme"])
    standalone_path = safe_repo_path(repo, docs["standalone_readme"])
    if root_path.is_symlink() or not root_path.is_file():
        raise GenomeError("root README unavailable or unsafe")
    if standalone_path.is_symlink() or not standalone_path.is_file():
        raise GenomeError("standalone documentation unavailable or unsafe")
    root = replace_exact_block(
        root_path.read_text(encoding="utf-8"),
        docs["root_start_marker"],
        docs["root_end_marker"],
        render_root_section(context),
    )
    standalone = replace_exact_block(
        standalone_path.read_text(encoding="utf-8"),
        docs["standalone_start_marker"],
        docs["standalone_end_marker"],
        render_standalone_section(context),
    )
    return {docs["root_readme"]: root, docs["standalone_readme"]: standalone}


def atomic_write_text(path: Path, text: str) -> None:
    if "\r" in text:
        raise GenomeError(f"generated text contains carriage return:{path}")
    # Canonical text has one and only one terminal LF.  This prevents a
    # generated file from passing semantic verification yet failing the
    # repository's staged-diff whitespace gate during publication.
    text = text.rstrip("\n") + "\n"
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise GenomeError(f"text output parent is unsafe:{parent}")
    if path.is_symlink():
        raise GenomeError(f"text output is a symlink:{path}")
    mode = 0o644
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise GenomeError(f"text output is not a regular file:{path}")
        mode = stat.S_IMODE(info.st_mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n", closefd=True) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _artifact_bytes(repo: Path, relative: str, overrides: Mapping[str, str] | None = None) -> bytes:
    if overrides and relative in overrides:
        return overrides[relative].encode("utf-8")
    path = safe_repo_path(repo, relative)
    if path.is_symlink() or not path.is_file():
        raise GenomeError(f"offline release artifact unavailable or unsafe:{relative}")
    return path.read_bytes()


def build_descriptor(repo: Path, context: Mapping[str, Mapping[str, Any]], *, text_overrides: Mapping[str, str] | None = None) -> dict[str, Any]:
    policy = context["policy"]
    graph = context["graph"]
    genome = context["genome"]
    capability = context["capability"]
    debt = context["debt"]
    artifacts: list[dict[str, Any]] = []
    for record in sorted(policy["artifact_inventory"], key=lambda item: item["name"]):
        raw = _artifact_bytes(repo, record["path"], text_overrides)
        import hashlib
        artifacts.append({
            "name": record["name"],
            "path": record["path"],
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    experience = capability["hard_floors"]["scenario_experience"]
    descriptor: dict[str, Any] = {
        "schema_version": "1.1.0",
        "release_id": policy["release_id"],
        "display_version": policy["display_version"],
        "engine_evolution": policy["engine_evolution"],
        "policy": {
            "path": POLICY_PATH,
            "file_sha256": file_sha256(safe_repo_path(repo, POLICY_PATH)),
        },
        "scenario_genome": {
            "path": GENOME_PATH,
            "genome_id": genome["genome_id"],
            "genome_sha256": genome["genome_sha256"],
        },
        "capability_ratchet": {
            "path": CAPABILITY_PATH,
            "ratchet_id": capability["ratchet_id"],
            "ratchet_epoch": capability["ratchet_epoch"],
            "ratchet_anchor_sha256": capability["ratchet_anchor_sha256"],
        },
        "technical_debt_ratchet": {
            "path": DEBT_PATH,
            "ratchet_id": debt["ratchet_id"],
            "ratchet_epoch": debt["ratchet_epoch"],
            "ratchet_anchor_sha256": debt["ratchet_anchor_sha256"],
        },
        "release_graph": {
            "path": GRAPH_PATH,
            "graph_id": graph["graph_id"],
            "stage_count": len(graph["stages"]),
            "target_count": len(graph["targets"]),
            "binding_mode": COMPILED_GRAPH_BINDING_MODE,
            "contract_sha256": release_graph_contract_sha256(graph),
        },
        "artifacts": artifacts,
        "required_capabilities": sorted(policy["required_capabilities"]),
        "offline_guarantees": policy["offline_guarantees"],
        "truth_boundary": policy["truth_boundary"],
        "repository_documentation": {
            "canonical_repository_url": policy["canonical_repository_url"],
            "root_start_marker": policy["documentation_contract"]["root_start_marker"],
            "root_end_marker": policy["documentation_contract"]["root_end_marker"],
            "scenario_experience_floor": experience["generated_cases"],
            "scenario_context_floor": experience["unique_operational_contexts"],
            "static_exercise_catalog_count": 100,
            "deployment_claim_mode": "CONFIGURATION_INSTRUCTIONS_ONLY_NO_LIVE_HEALTH_CLAIM",
        },
    }
    descriptor["release_sha256"] = canonical_sha256(descriptor)
    return descriptor


def write_generated_release(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    documentation = expected_documentation(repo, context)
    docs = context["policy"]["documentation_contract"]
    surface_paths = {
        "root": docs["root_readme"],
        "standalone": docs["standalone_readme"],
        "facility": docs["facility_readme"],
        "verified": docs["verified_readme"],
    }
    # This stage owns only root and standalone documentation. Facility and
    # verified README files are generated by their domain-specific canonical
    # writers and are verification-only here. This prevents a later offline
    # stage from invalidating manifests produced by earlier stages.
    for surface in COMPILED_DOCUMENTATION_WRITER_OWNED_SURFACES:
        relative = surface_paths[surface]
        atomic_write_text(safe_repo_path(repo, relative), documentation[relative])
    descriptor = build_descriptor(repo, context)
    atomic_write_json(safe_repo_path(repo, context["policy"]["output_path"]), descriptor)
    return descriptor

# Offline runtime constraints are independently reimplemented in the Node checker.
_PLAYABLE_PAYLOAD_RE = __import__("re").compile(
    r'<script\s+type="application/json"\s+id="asklepios-scenario-data">(.*?)</script>',
    __import__("re").DOTALL,
)
_FORBIDDEN_RUNTIME_PATTERNS = (
    r"<script\b[^>]*\bsrc\s*=",
    r"<link\b[^>]*\brel\s*=\s*['\"]?stylesheet",
    r"\bfetch\s*\(",
    r"\bXMLHttpRequest\b",
    r"\bWebSocket\s*\(",
    r"\bEventSource\s*\(",
    r"\bnavigator\.sendBeacon\s*\(",
    r"\bimport\s*\(\s*['\"]https?://",
)


def load_playable_payload(repo: Path) -> dict[str, Any]:
    import re

    path = safe_repo_path(repo, "examples/facility-arrival/playable.html")
    if path.is_symlink() or not path.is_file():
        raise GenomeError("offline playable unavailable or unsafe")
    text = path.read_text(encoding="utf-8")
    match = _PLAYABLE_PAYLOAD_RE.search(text)
    if not match:
        raise GenomeError("offline playable embedded payload missing")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise GenomeError(f"offline playable embedded payload malformed:{exc.msg}") from exc
    if not isinstance(value, dict):
        raise GenomeError("offline playable embedded payload root is not an object")
    return value


def validate_playable(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> list[str]:
    import re

    path = safe_repo_path(repo, "examples/facility-arrival/playable.html")
    if path.is_symlink() or not path.is_file():
        return ["offline playable unavailable or unsafe"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    csp = re.search(r'<meta\s+http-equiv="Content-Security-Policy"\s+content="([^"]+)"', text, re.IGNORECASE)
    if not csp or "connect-src 'none'" not in csp.group(1):
        errors.append("offline playable CSP does not block connections")
    for pattern in _FORBIDDEN_RUNTIME_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            errors.append(f"offline playable forbidden runtime pattern:{pattern}")
    try:
        payload = load_playable_payload(repo)
    except GenomeError as exc:
        errors.append(str(exc))
        return sorted(set(errors))
    expected = evolution_binding(context)
    if payload.get("release_id") != context["policy"]["release_id"]:
        errors.append("offline playable release identity differs")
    if payload.get("standalone_mode") != "single_file_no_network":
        errors.append("offline playable standalone mode differs")
    if payload.get("scenario_evolution") != expected:
        errors.append("offline playable scenario-evolution binding differs")
    authority = payload.get("authority") if isinstance(payload.get("authority"), dict) else {}
    if authority.get("patient_care_use") != "PROHIBITED":
        errors.append("offline playable patient-care authority escalated")
    return sorted(set(errors))


def validate_documentation(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Validate semantic documentation guardrails independently of descriptor hashes."""
    import re

    errors: list[str] = []
    policy = context["policy"]
    docs = policy["documentation_contract"]
    paths = {
        "root": docs["root_readme"],
        "standalone": docs["standalone_readme"],
        "facility": docs["facility_readme"],
        "verified": docs["verified_readme"],
    }
    texts: dict[str, str] = {}
    for surface, relative in paths.items():
        try:
            path = safe_repo_path(repo, relative)
            if path.is_symlink() or not path.is_file():
                raise GenomeError("unsafe")
            texts[surface] = path.read_text(encoding="utf-8")
        except (GenomeError, OSError, UnicodeError):
            errors.append(f"engine-evolution document missing or unsafe:{relative}")

    identity_tokens = (
        policy["release_id"],
        policy["display_version"],
        policy["engine_evolution"],
        context["genome"]["genome_id"],
        context["genome"]["genome_sha256"],
        context["capability"]["ratchet_id"],
        str(context["capability"]["ratchet_epoch"]),
        context["capability"]["ratchet_anchor_sha256"],
        context["debt"]["ratchet_id"],
        str(context["debt"]["ratchet_epoch"]),
        context["debt"]["ratchet_anchor_sha256"],
        context["graph"]["graph_id"],
        str(len(context["graph"]["stages"])),
        str(len(context["graph"]["targets"])),
    )
    for surface, current in texts.items():
        folded = current.casefold()
        for token in identity_tokens:
            if token not in current:
                errors.append(f"engine-evolution identity missing:{surface}:{token}")
        for phrase in DOCUMENTATION_SURFACE_PHRASES[surface]:
            if phrase.casefold() not in folded:
                errors.append(f"engine-evolution guardrail missing:{surface}:{phrase}")

    canonical_block = render_evolution_block(repo).strip()
    for surface in ("facility", "verified"):
        current = texts.get(surface)
        if current is None:
            continue
        if current.count(EVOLUTION_START_MARKER) != 1 or current.count(EVOLUTION_END_MARKER) != 1:
            errors.append(f"documentation marker inventory differs:{surface}")
            continue
        first = current.index(EVOLUTION_START_MARKER)
        last = current.index(EVOLUTION_END_MARKER, first) + len(EVOLUTION_END_MARKER)
        if current[first:last].strip() != canonical_block:
            errors.append(f"canonical engine-evolution block differs:{surface}")

    root = texts.get("root", "")
    canonical_line = f"Canonical repository: {policy['canonical_repository_url']}"
    repository_lines = [line.strip() for line in root.splitlines() if line.strip().casefold().startswith("canonical repository:")]
    if repository_lines != [canonical_line]:
        errors.append("canonical repository declaration differs")
    if "## Static exercise catalog (100 TOON-authored exercises)" not in root:
        errors.append("static exercise catalog identity differs")
    for prohibited in PROHIBITED_LIVE_DEPLOYMENT_CLAIMS:
        if prohibited in root.casefold():
            errors.append(f"unsupported live deployment claim:{prohibited}")
    if re.search(r"(?im)^##\s+Generated scenario catalog \(107 TOON-authored exercises\)\s*$", root):
        errors.append("static exercise catalog conflated with generated scenarios")

    return sorted(set(errors))


def compare_generated_release(repo: Path, context: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """Reconstruct the complete release without trusting committed generated outputs."""
    documentation = expected_documentation(repo, context)
    expected = build_descriptor(repo, context, text_overrides=documentation)
    mismatches: list[str] = []
    for relative, text in documentation.items():
        path = safe_repo_path(repo, relative)
        if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != text:
            mismatches.append(relative)
    output_path = context["policy"]["output_path"]
    try:
        current = load_object(safe_repo_path(repo, output_path))
    except GenomeError:
        current = None
    if current != expected:
        mismatches.append(output_path)
    return expected, sorted(set(mismatches))


def validate_descriptor(repo: Path, context: Mapping[str, Mapping[str, Any]], descriptor: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    release_hash = descriptor.get("release_sha256")
    unsigned = dict(descriptor)
    unsigned.pop("release_sha256", None)
    if not isinstance(release_hash, str) or len(release_hash) != 64:
        errors.append("offline release digest malformed")
    elif release_hash != canonical_sha256(unsigned):
        errors.append("offline release self hash differs")
    if descriptor.get("release_id") != context["policy"]["release_id"]:
        errors.append("offline descriptor release identity differs")
    if descriptor.get("engine_evolution") != context["policy"]["engine_evolution"]:
        errors.append("offline descriptor engine-evolution profile differs")
    if descriptor.get("scenario_genome", {}).get("genome_id") != context["genome"].get("genome_id"):
        errors.append("offline descriptor Scenario Genome identity differs")
    if descriptor.get("capability_ratchet", {}).get("ratchet_epoch") != context["capability"].get("ratchet_epoch"):
        errors.append("offline descriptor capability-ratchet epoch differs")
    if descriptor.get("technical_debt_ratchet", {}).get("ratchet_epoch") != context["debt"].get("ratchet_epoch"):
        errors.append("offline descriptor technical-debt-ratchet epoch differs")
    if descriptor.get("release_graph", {}).get("graph_id") != context["graph"].get("graph_id"):
        errors.append("offline descriptor release-graph identity differs")
    graph_binding = descriptor.get("release_graph") if isinstance(descriptor.get("release_graph"), Mapping) else {}
    if graph_binding.get("binding_mode") != COMPILED_GRAPH_BINDING_MODE:
        errors.append("offline descriptor release-graph binding mode differs")
    if graph_binding.get("contract_sha256") != release_graph_contract_sha256(context["graph"]):
        errors.append("offline descriptor release-graph contract differs")
    if "file_sha256" in graph_binding:
        errors.append("offline descriptor raw release-graph hash creates an identity cycle")
    artifacts = descriptor.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != len(COMPILED_ARTIFACTS):
        errors.append("offline descriptor artifact inventory differs")
    else:
        names = [item.get("name") for item in artifacts if isinstance(item, dict)]
        if names != sorted(COMPILED_ARTIFACTS):
            errors.append("offline descriptor artifact order or names differ")
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            relative = item.get("path")
            if name not in COMPILED_ARTIFACTS or relative != COMPILED_ARTIFACTS.get(name):
                errors.append(f"offline descriptor artifact binding differs:{name}")
                continue
            try:
                path = safe_repo_path(repo, relative)
                if path.is_symlink() or not path.is_file():
                    raise GenomeError("unsafe")
                if item.get("bytes") != path.stat().st_size or item.get("sha256") != file_sha256(path):
                    errors.append(f"offline descriptor artifact identity differs:{name}")
            except (GenomeError, OSError):
                errors.append(f"offline descriptor artifact unavailable:{name}")
    errors.extend(validate_playable(repo, context))
    errors.extend(validate_documentation(repo, context))
    return sorted(set(errors))
