#!/usr/bin/env python3
"""Build or verify the deterministic Asklepios Scenario Genome v1.

The genome is deliberately structural.  It identifies the exact evidence-bound
scenario package and describes the executable route topology without inventing
clinical truth, calibrated human behavior, patient physiology, causal effects,
or real-world frequency claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections import deque
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
    normalize,
    safe_repo_path,
)

sys.dont_write_bytecode = True

POLICY_PATH = Path("config/scenario-genome/SCENARIO_GENOME_POLICY.json")
COMPILED_AUTHORITY_BOUNDARY = {
    "clinical_authority": "NOT_GRANTED",
    "deployment_scope": "research_sandbox_only",
    "evidence_authority": "supporting_only",
    "human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED",
    "operational_calibration": "NOT_CALIBRATED",
    "patient_care_use": "PROHIBITED",
    "patient_dynamics": "SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY",
    "scoring_behavior": "inherited_unchanged",
}
COMPILED_POLICY_ID = "asklepios-scenario-genome-policy-v1"
COMPILED_GENOME_SCHEMA = "1.0.0"
COMPILED_DESCRIPTOR_PROFILE = "INTERPRETABLE_STRUCTURAL_BEHAVIOR_DESCRIPTOR_V1"
COMPILED_ROUTE_TOPOLOGY_PROFILE = "REACHABLE_TERMINATING_DAG_V1"
COMPILED_REQUIRED_DIMENSIONS = {
    "atom_count",
    "branching_nodes",
    "cycle_free",
    "evidence_references",
    "expected_action_counts",
    "field_origin_records",
    "maximum_out_degree",
    "node_kind_counts",
    "nonterminal_dead_ends",
    "operational_factor_count",
    "reachable_nodes",
    "route_edges",
    "route_maximum_steps",
    "route_nodes",
    "stage_count",
    "terminal_nodes",
    "unreachable_nodes",
    "unsafe_action_count",
}
COMPILED_FORBIDDEN_FIELDS = {
    "action_probability",
    "clinical_effect_probability",
    "compliance_probability",
    "empirical_distribution",
    "patient_outcome_probability",
    "physiology_transition_probability",
    "real_world_frequency",
    "treatment_effect",
    "treatment_recommendation",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GenomeError(message)


def _scan_forbidden(value: Any, forbidden: set[str], path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in forbidden:
                findings.append(f"{path}.{key}")
            findings.extend(_scan_forbidden(child, forbidden, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden(child, forbidden, f"{path}[{index}]"))
    return findings


def _policy(repo: Path) -> tuple[dict[str, Any], Path]:
    path = safe_repo_path(repo, POLICY_PATH.as_posix())
    policy = load_object(path)
    _require(policy.get("schema_version") == "1.0.0", "scenario genome policy schema differs")
    _require(policy.get("policy_id") == COMPILED_POLICY_ID, "scenario genome policy ID differs")
    _require(policy.get("genome_schema_version") == COMPILED_GENOME_SCHEMA, "scenario genome schema differs")
    _require(policy.get("behavior_descriptor_profile") == COMPILED_DESCRIPTOR_PROFILE, "scenario genome descriptor profile differs")
    _require(policy.get("route_topology_profile") == COMPILED_ROUTE_TOPOLOGY_PROFILE, "scenario genome route topology profile differs")
    _require(policy.get("authority_boundary") == COMPILED_AUTHORITY_BOUNDARY, "scenario genome authority boundary differs")
    _require(set(policy.get("required_behavior_dimensions", [])) == COMPILED_REQUIRED_DIMENSIONS, "scenario genome behavior dimension inventory differs")
    _require(set(policy.get("forbidden_genome_fields", [])) == COMPILED_FORBIDDEN_FIELDS, "scenario genome forbidden-field inventory differs")
    requirements = policy.get("provenance_requirements")
    _require(isinstance(requirements, dict) and requirements and all(value is True for value in requirements.values()), "scenario genome provenance requirements differ")
    source_paths = policy.get("source_paths")
    _require(isinstance(source_paths, dict), "scenario genome source paths missing")
    _require(set(source_paths) == {"content_registry", "independent_checker", "scenario_package", "writer"}, "scenario genome source path inventory differs")
    for relative in [*source_paths.values(), policy.get("output_path"), policy.get("report_path")]:
        _require(isinstance(relative, str) and bool(relative), "scenario genome path declaration malformed")
        safe_repo_path(repo, relative)
    return policy, path


def _route_metrics(route: dict[str, Any]) -> dict[str, Any]:
    nodes = route.get("nodes")
    edges = route.get("edges")
    start = route.get("start_node_id")
    _require(isinstance(nodes, list) and bool(nodes), "scenario genome route nodes missing")
    _require(isinstance(edges, list) and bool(edges), "scenario genome route edges missing")
    _require(isinstance(start, str) and bool(start), "scenario genome route start missing")

    node_map: dict[str, dict[str, Any]] = {}
    kind_counts: Counter[str] = Counter()
    terminal_ids: set[str] = set()
    for node in nodes:
        _require(isinstance(node, dict), "scenario genome route node malformed")
        node_id = node.get("node_id")
        kind = node.get("node_kind")
        _require(isinstance(node_id, str) and node_id, "scenario genome route node ID missing")
        _require(node_id not in node_map, f"scenario genome route node duplicated:{node_id}")
        _require(isinstance(kind, str) and kind, f"scenario genome route node kind missing:{node_id}")
        _require(isinstance(node.get("terminal"), bool), f"scenario genome route terminal flag malformed:{node_id}")
        node_map[node_id] = node
        kind_counts[kind] += 1
        if node["terminal"]:
            terminal_ids.add(node_id)
    _require(start in node_map, "scenario genome route start is unknown")
    _require(bool(terminal_ids), "scenario genome route has no terminal")

    adjacency: dict[str, list[str]] = defaultdict(list)
    edge_ids: set[str] = set()
    for edge in edges:
        _require(isinstance(edge, dict), "scenario genome route edge malformed")
        edge_id = edge.get("edge_id")
        source = edge.get("from")
        target = edge.get("to")
        _require(isinstance(edge_id, str) and edge_id, "scenario genome route edge ID missing")
        _require(edge_id not in edge_ids, f"scenario genome route edge duplicated:{edge_id}")
        edge_ids.add(edge_id)
        _require(source in node_map and target in node_map, f"scenario genome route edge endpoint unknown:{edge_id}")
        adjacency[source].append(target)
    for targets in adjacency.values():
        targets.sort()

    out_degrees = {node_id: len(adjacency.get(node_id, [])) for node_id in node_map}
    terminal_with_outgoing = sorted(node_id for node_id in terminal_ids if out_degrees[node_id] != 0)
    _require(not terminal_with_outgoing, "scenario genome terminal has outgoing edge:" + ",".join(terminal_with_outgoing))
    nonterminal_dead_ends = sorted(
        node_id for node_id in node_map if node_id not in terminal_ids and out_degrees[node_id] == 0
    )
    _require(not nonterminal_dead_ends, "scenario genome route has nonterminal dead end:" + ",".join(nonterminal_dead_ends))

    reachable: set[str] = set()
    pending = [start]
    while pending:
        node_id = pending.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        pending.extend(reversed(adjacency.get(node_id, [])))
    unreachable = sorted(set(node_map) - reachable)
    _require(not unreachable, "scenario genome route has unreachable nodes:" + ",".join(unreachable))

    indegree = {node_id: 0 for node_id in node_map}
    for targets in adjacency.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    topological_order: list[str] = []
    while queue:
        node_id = queue.popleft()
        topological_order.append(node_id)
        for target in adjacency.get(node_id, []):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
        if len(queue) > 1:
            queue = deque(sorted(queue))
    _require(len(topological_order) == len(node_map), "scenario genome route contains cycle")

    longest = {node_id: -1 for node_id in node_map}
    longest[start] = 0
    for node_id in topological_order:
        if longest[node_id] < 0:
            continue
        for target in adjacency.get(node_id, []):
            longest[target] = max(longest[target], longest[node_id] + 1)
    maximum_steps = max((longest[node_id] for node_id in terminal_ids), default=-1)
    _require(maximum_steps >= 0, "scenario genome route has no reachable terminal")
    return {
        "route_topology_profile": COMPILED_ROUTE_TOPOLOGY_PROFILE,
        "route_nodes": len(nodes),
        "route_edges": len(edges),
        "reachable_nodes": len(reachable),
        "unreachable_nodes": len(unreachable),
        "terminal_nodes": len(terminal_ids),
        "nonterminal_dead_ends": len(nonterminal_dead_ends),
        "cycle_free": True,
        "branching_nodes": sum(1 for value in out_degrees.values() if value > 1),
        "maximum_out_degree": max(out_degrees.values(), default=0),
        "route_maximum_steps": maximum_steps,
        "node_kind_counts": dict(sorted(kind_counts.items())),
    }


def _expected_action_counts(package: dict[str, Any]) -> dict[str, int]:
    actions = package.get("scenario", {}).get("expected_actions")
    _require(isinstance(actions, dict), "scenario genome expected-action catalog missing")
    expected_categories = {"critical", "important", "optional", "unsafe"}
    _require(set(actions) == expected_categories, "scenario genome expected-action category inventory differs")
    result: dict[str, int] = {}
    for category in sorted(expected_categories):
        records = actions.get(category)
        _require(isinstance(records, list), f"scenario genome expected-action category malformed:{category}")
        result[category] = len(records)
    return result


def _build(repo: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    policy, policy_path = _policy(repo)
    source_paths = policy["source_paths"]
    package_path = safe_repo_path(repo, source_paths["scenario_package"])
    registry_path = safe_repo_path(repo, source_paths["content_registry"])
    writer_path = safe_repo_path(repo, source_paths["writer"])
    checker_path = safe_repo_path(repo, source_paths["independent_checker"])
    output_path = safe_repo_path(repo, policy["output_path"])
    report_path = safe_repo_path(repo, policy["report_path"])

    for path, label in ((package_path, "scenario package"), (registry_path, "content registry"), (writer_path, "scenario genome writer"), (checker_path, "scenario genome checker")):
        _require(path.is_file() and not path.is_symlink(), f"required regular {label} missing")

    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise GenomeError(f"scenario genome source JSON unavailable:{type(exc).__name__}:{exc}") from exc
    _require(isinstance(package, dict), "scenario package is not an object")
    _require(isinstance(registry, dict), "content registry is not an object")
    authority = package.get("authority")
    _require(isinstance(authority, dict), "scenario package authority missing")
    _require(authority.get("clinical_authority") == "NOT_GRANTED", "scenario package clinical authority escalated")
    _require(authority.get("deployment_scope") == "research_sandbox_only", "scenario package deployment scope differs")
    _require(authority.get("evidence_authority") == "supporting_only", "scenario package evidence authority escalated")
    _require(authority.get("scoring_behavior") == "inherited_unchanged", "scenario package scoring behavior changed")
    certificate = package.get("certificate")
    _require(isinstance(certificate, dict), "scenario package certificate missing")
    _require(is_sha256(certificate.get("package_sha256")), "scenario package certificate hash malformed")
    checks = certificate.get("checks")
    _require(isinstance(checks, dict) and checks and all(value is True for value in checks.values()), "scenario package certificate contains failed check")
    _require(certificate.get("base_protected_sha256") == certificate.get("output_protected_sha256"), "scenario protected projection changed")
    registry_root = registry.get("roots", {}).get("registry_merkle_root")
    _require(is_sha256(registry_root), "content registry Merkle root malformed")

    build = package.get("build")
    scenario = package.get("scenario")
    blueprint = package.get("blueprint")
    route = package.get("route")
    evidence = package.get("evidence")
    atoms = package.get("atoms")
    stages = package.get("stages")
    field_origins = package.get("field_origins")
    for value, label in ((build, "build"), (scenario, "scenario"), (blueprint, "blueprint"), (route, "route")):
        _require(isinstance(value, dict), f"scenario package {label} missing")
    for value, label in ((evidence, "evidence"), (atoms, "atoms"), (stages, "stages"), (field_origins, "field origins")):
        _require(isinstance(value, list), f"scenario package {label} missing")

    operational_context = scenario.get("operational_context")
    _require(isinstance(operational_context, dict), "scenario operational context missing")
    factors = {
        key: value
        for key, value in operational_context.items()
        if key != "narrative"
    }
    _require(all(isinstance(value, str) and value for value in factors.values()), "scenario operational factors malformed")
    route_metrics = _route_metrics(route)
    action_counts = _expected_action_counts(package)
    behavior_descriptor = {
        "descriptor_profile": COMPILED_DESCRIPTOR_PROFILE,
        **route_metrics,
        "expected_action_counts": action_counts,
        "unsafe_action_count": action_counts["unsafe"],
        "evidence_references": len(evidence),
        "atom_count": len(atoms),
        "stage_count": len(stages),
        "field_origin_records": len(field_origins),
        "operational_factor_count": len(factors),
        "operational_context_sha256": canonical_sha256(factors),
        "route_sha256": canonical_sha256(route),
        "protected_projection_sha256": certificate.get("output_protected_sha256"),
    }
    missing_dimensions = COMPILED_REQUIRED_DIMENSIONS - behavior_descriptor.keys()
    _require(not missing_dimensions, "scenario genome behavior dimensions missing:" + ",".join(sorted(missing_dimensions)))

    evidence_records: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for item in evidence:
        _require(isinstance(item, dict), "scenario genome evidence record malformed")
        evidence_id = item.get("evidence_id")
        _require(isinstance(evidence_id, str) and evidence_id, "scenario genome evidence ID missing")
        _require(evidence_id not in seen_evidence, f"scenario genome evidence ID duplicated:{evidence_id}")
        seen_evidence.add(evidence_id)
        record = {
            "evidence_id": evidence_id,
            "source_id": item.get("source_id"),
            "doi": item.get("doi"),
            "locator": item.get("locator"),
            "chunk_sha256": item.get("chunk_sha256"),
            "source_file_sha256": item.get("source_file_sha256"),
            "evidence_record_sha256": canonical_sha256(item),
        }
        _require(is_sha256(record["chunk_sha256"]), f"scenario genome evidence chunk hash malformed:{evidence_id}")
        _require(is_sha256(record["source_file_sha256"]), f"scenario genome evidence source hash malformed:{evidence_id}")
        evidence_records.append(record)
    evidence_records.sort(key=lambda item: item["evidence_id"])

    identity = {
        "identity_domain": policy["genome_identity_domain"],
        "source_scenario_id": build.get("source_scenario_id"),
        "scenario_id": scenario.get("scenario_id"),
        "blueprint_id": build.get("blueprint_id"),
        "topic_id": build.get("topic_id"),
        "seed": build.get("seed"),
        "retriever_track": build.get("retriever_track"),
        "scenario_package_path": source_paths["scenario_package"],
        "scenario_package_file_sha256": file_sha256(package_path),
        "scenario_package_certificate_sha256": certificate.get("package_sha256"),
        "content_registry_path": source_paths["content_registry"],
        "content_registry_file_sha256": file_sha256(registry_path),
        "content_registry_merkle_root": registry_root,
        "policy_path": POLICY_PATH.as_posix(),
        "policy_file_sha256": file_sha256(policy_path),
        "writer_path": source_paths["writer"],
        "writer_file_sha256": file_sha256(writer_path),
        "independent_checker_path": source_paths["independent_checker"],
        "independent_checker_file_sha256": file_sha256(checker_path),
    }
    for field in ("source_scenario_id", "scenario_id", "blueprint_id", "topic_id", "retriever_track"):
        _require(isinstance(identity[field], str) and identity[field], f"scenario genome identity field missing:{field}")
    _require(isinstance(identity["seed"], int), "scenario genome seed malformed")

    genome: dict[str, Any] = {
        "schema_version": COMPILED_GENOME_SCHEMA,
        "genome_id": "PENDING",
        "genome_sha256": "PENDING",
        "identity": identity,
        "authority_boundary": COMPILED_AUTHORITY_BOUNDARY,
        "operational_factors": dict(sorted(factors.items())),
        "behavior_descriptor": behavior_descriptor,
        "evidence_records": evidence_records,
        "provenance_root_sha256": canonical_sha256({
            "identity": identity,
            "evidence_records": evidence_records,
        }),
        "limitations": [
            "No clinical authority is granted.",
            "Human and team behavior remains structural only and is not empirically calibrated.",
            "Operational timing remains not calibrated.",
            "Patient dynamics remain source-bound static observations only.",
            "Scoring behavior is inherited unchanged and is not a validated psychometric proficiency model.",
        ],
        "truth_boundary": policy["truth_boundary"],
    }
    forbidden_findings = _scan_forbidden(genome, COMPILED_FORBIDDEN_FIELDS)
    _require(not forbidden_findings, "forbidden scenario genome fields:" + ",".join(forbidden_findings))
    digest = hash_without(genome, "genome_id", "genome_sha256")
    genome["genome_id"] = f"ASK-GENOME-{digest[:16].upper()}"
    genome["genome_sha256"] = hash_without(genome, "genome_sha256")
    normalize(genome)

    report = {
        "schema_version": "1.0.0",
        "classification": "PASS",
        "status": "PASS",
        "mode": "write",
        "genome_id": genome["genome_id"],
        "genome_sha256": genome["genome_sha256"],
        "scenario_id": identity["scenario_id"],
        "source_scenario_id": identity["source_scenario_id"],
        "behavior_descriptor_profile": behavior_descriptor["descriptor_profile"],
        "behavior_dimensions": len(genome.get("behavior_descriptor", {})),
        "required_behavior_dimensions": len(COMPILED_REQUIRED_DIMENSIONS),
        "evidence_records": len(evidence_records),
        "authority_boundary": COMPILED_AUTHORITY_BOUNDARY,
        "output_path": policy["output_path"],
        "mismatches": [],
        "errors": [],
    }
    return genome, report, output_path, report_path


def _expected_text(value: dict[str, Any]) -> str:
    return json.dumps(normalize(value), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    report_path: Path | None = None
    try:
        genome, report, output_path, default_report_path = _build(repo)
        report_path = args.json_output if args.json_output and args.json_output.is_absolute() else repo / (args.json_output or default_report_path.relative_to(repo))
        if args.check:
            report["mode"] = "check"
            expected = _expected_text(genome)
            if output_path.is_symlink() or not output_path.is_file():
                report["mismatches"].append(output_path.relative_to(repo).as_posix())
            elif output_path.read_text(encoding="utf-8") != expected:
                report["mismatches"].append(output_path.relative_to(repo).as_posix())
            if report["mismatches"]:
                report["classification"] = report["status"] = "FAIL"
                report["errors"].append("committed scenario genome differs")
        else:
            atomic_write_json(output_path, genome)
        atomic_write_json(report_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["classification"] == "PASS" else 3
    except Exception as exc:  # noqa: BLE001 - convert to durable structured result
        report = {
            "schema_version": "1.0.0",
            "classification": "FAIL",
            "status": "FAIL",
            "mode": "check" if args.check else "write",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
        if report_path is None:
            report_path = args.json_output if args.json_output and args.json_output.is_absolute() else repo / (args.json_output or Path("reports/scenario-genome.json"))
        try:
            atomic_write_json(report_path, report)
        except Exception:
            pass
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
