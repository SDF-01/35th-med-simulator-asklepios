#!/usr/bin/env python3
"""Shared RC3.8A.1 engine-evolution bindings used by canonical writers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from release_identity_common import GRAPH_BINDING_MODE, release_graph_contract_sha256
from scenario_genome_common import GenomeError, load_object, safe_repo_path

POLICY = "config/release/OFFLINE_SCENARIO_RELEASE.json"
GENOME = "public/data/scenario_core/verified_scenario_genome.json"
CAPABILITY = "config/release/SCENARIO_CAPABILITY_RATCHET.json"
DEBT = "config/release/TECHNICAL_DEBT_RATCHET.json"
GRAPH = "config/release/RELEASE_GRAPH.json"

EVOLUTION_START_MARKER = "<!-- asklepios-offline-evolution:start -->"
EVOLUTION_END_MARKER = "<!-- asklepios-offline-evolution:end -->"
DOCUMENTATION_SURFACE_PHRASES: dict[str, tuple[str, ...]] = {'facility': ('## Engine evolution binding',
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
              '- Treatment-admission pipeline:'),
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
                'Treatment-admission pipeline'),
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
              '- Treatment-admission pipeline:')}
PROHIBITED_LIVE_DEPLOYMENT_CLAIMS: tuple[str, ...] = (
    "deployment is currently healthy",
    "production deployment is healthy",
    "vercel preview is healthy",
    "the live deployment is healthy",
)


def load_evolution(repo: Path) -> dict[str, Any]:
    policy = load_object(safe_repo_path(repo, POLICY))
    genome = load_object(safe_repo_path(repo, GENOME))
    capability = load_object(safe_repo_path(repo, CAPABILITY))
    debt = load_object(safe_repo_path(repo, DEBT))
    graph = load_object(safe_repo_path(repo, GRAPH))
    expected = {
        "release_id": "ASK-OFFLINE-RC3.8A.1",
        "display_version": "RC3.8A.1",
        "engine_evolution": "SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8",
    }
    for field, value in expected.items():
        if policy.get(field) != value:
            raise GenomeError(f"offline evolution policy differs:{field}")
    if policy.get("release_graph_binding_mode") != GRAPH_BINDING_MODE:
        raise GenomeError("offline evolution graph binding mode differs")
    if graph.get("graph_id") != policy.get("expected_graph_id"):
        raise GenomeError("offline evolution graph identity differs")
    if len(graph.get("stages", [])) != policy.get("expected_graph_stage_count"):
        raise GenomeError("offline evolution graph stage count differs")
    if len(graph.get("targets", {})) != policy.get("expected_graph_target_count"):
        raise GenomeError("offline evolution graph target count differs")
    if capability.get("ratchet_id") != policy.get("expected_capability_ratchet_id") or capability.get("ratchet_epoch") != policy.get("expected_capability_ratchet_epoch"):
        raise GenomeError("offline capability ratchet binding differs")
    if debt.get("ratchet_id") != policy.get("expected_technical_debt_ratchet_id") or debt.get("ratchet_epoch") != policy.get("expected_technical_debt_ratchet_epoch"):
        raise GenomeError("offline technical-debt ratchet binding differs")
    return {"policy": policy, "genome": genome, "capability": capability, "debt": debt, "graph": graph}


def render_evolution_block(repo: Path, *, heading: str = "## Engine evolution binding") -> str:
    data = load_evolution(repo)
    p, g, c, d, graph = (data[k] for k in ("policy", "genome", "capability", "debt", "graph"))
    return "\n".join([
        EVOLUTION_START_MARKER,
        heading,
        "",
        f"This artifact is bound to **{p['display_version']}** (`{p['release_id']}`), the evidence-calibrated evolution that adds a deterministic Scenario Genome, true behavioral-policy diversity, a balanced operational scenario pack, stakeholder scorecards, a fail-closed treatment-admission pipeline, dual monotonic ratchets, differential documentation verification, and graph-receipt-bound scenario-evolution evidence.",
        "",
        f"- Engine evolution profile: `{p.get('engine_evolution')}`",
        f"- Scenario Genome: `{g.get('genome_id')}` (`{g.get('genome_sha256')}`)",
        f"- Capability ratchet: `{c.get('ratchet_id')}`, epoch `{c.get('ratchet_epoch')}` (`{c.get('ratchet_anchor_sha256')}`)",
        f"- Technical-debt ratchet: `{d.get('ratchet_id')}`, epoch `{d.get('ratchet_epoch')}` (`{d.get('ratchet_anchor_sha256')}`)",
        f"- Canonical release graph: `{graph.get('graph_id')}` with `{len(graph.get('stages', []))}` stages and `{len(graph.get('targets', {}))}` targets",
        "- Behavioral quality-diversity: the ratcheted archive preserves 107 unique structural behavior signatures across all 30 observed behavior cells; its integer quality vector selects scenario representatives only and never scores learners.",
        "- Behavioral policy diversity: 107 operational contexts are quotient-checked into four genuinely different decision-policy classes; wording, names, provenance, and seeds cannot claim novelty by themselves.",
        "- Operational scenario pack: 12 reviewed scenarios are balanced three-per-profile across direct handoff, communication relay, resource coordination, and dual-constraint coordination.",
        "- Four playable offline role-model teamwork challenges: the standalone file lets the user select and play direct handoff, communications relay, resource coordination, or the combined relay-and-resource route; added teamwork actions carry zero clinical points.",
        "- Source-conformance scorecard: four reference scorecards expose evidence by competency dimension, preserve a hard safety gate, and return INSUFFICIENT_EVIDENCE rather than fabricated precision; they are not psychometrically validated proficiency scores.",
        "- Treatment-admission pipeline: two treatment concepts remain DISCOVERED, zero are SIMULATION_ADMITTED, and zero active learner treatment choices are allowed until exact source spans, applicability, scope, and SME review are complete.",
        "- Plain-language release translation: every release must state what changed for learners, instructors, reviewers, and maintainers, plus what remains uncalibrated or prohibited.",
        "- Scenario-science telemetry: event traces are privacy-bounded, append-only, and hash-chained; they create calibration evidence without silently promoting exercise timing or learner scoring." ,
        f"- Release-identity DAG: `{GRAPH_BINDING_MODE}` contract `{release_graph_contract_sha256(graph)}`",
        "- Truth boundary: clinical authority `NOT_GRANTED`; operational calibration `NOT_CALIBRATED`; patient-care use `PROHIBITED`; human-team behavior `STRUCTURAL_ONLY_NOT_CALIBRATED`; patient dynamics `SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY`; quality-vector use `SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING`.",
        "",
        "- Canonical-writer rule: each governed artifact has one writer and at least one independently implemented read-only verifier.",
        "- Receipt rule: a committed `PASS` report is insufficient; final evidence must bind current graph, stage configuration, inputs, and output hashes.",
        "- Release-identity rule: the offline descriptor binds an acyclic semantic graph projection rather than the graph's raw file hash, while the graph independently locks the descriptor.",
        "- Route topology: the Scenario Genome admits only reachable, terminating, cycle-free routes with zero nonterminal dead ends.",
        "- Technical-debt rule: reviewed blocker classifications, evidence floors, and final receipt requirements cannot be silently weakened.",
        "- Regression rule: future epochs may raise demonstrated floors but cannot lower them without an explicit reviewed epoch change and renewed evidence.",
        "",
        "The Scenario Genome is a structural identity and provenance artifact. It does not establish clinical certification, empirical timing, human-behavior calibration, treatment effect, dynamic physiology, psychometric validity, or suitability for direct patient care.",
        EVOLUTION_END_MARKER,
    ]) + "\n"


def replace_marked_block(text: str, block: str, start: str = EVOLUTION_START_MARKER, end: str = "<!-- asklepios-offline-evolution:end -->") -> str:
    first = text.find(start)
    last = text.find(end)
    if first == -1 and last == -1:
        return text.rstrip() + "\n\n" + block
    if first == -1 or last == -1 or last < first or text.find(start, first + 1) != -1 or text.find(end, last + 1) != -1:
        raise GenomeError(f"documentation marker inventory differs:{start}:{end}")
    last += len(end)
    rendered = text[:first].rstrip() + "\n\n" + block.rstrip() + "\n" + text[last:].lstrip("\n")
    return rendered.rstrip("\n") + "\n"
