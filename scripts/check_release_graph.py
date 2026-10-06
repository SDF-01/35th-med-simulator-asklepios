#!/usr/bin/env python3
"""Fail-closed structural validator for the canonical Asklepios release graph."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any, Iterable

from release_graph_core import (
    GRAPH_PATH,
    ReleaseGraphError,
    canonical_json,
    load_graph,
    plan_payload,
    read_json,
    resolve_command,
    stage_map,
    target_plan,
    target_stage_ids,
    verify_input_set,
    write_json,
)
from release_result import FAIL, PASS, exit_code
from release_source_closure import (
    CLOSURE_SCOPE,
    NODE_MODE,
    PYTHON_MODE,
    SCHEMA_VERSION as SOURCE_CLOSURE_SCHEMA_VERSION,
    build_dependency_index,
    transitive_closure_errors,
)

OUTPUT = Path("reports/release-graph-consistency.json")
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
JOB_LINE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
USES_LINE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
RUN_LINE = re.compile(r"^\s*run:\s*(.+?)\s*$")
TS_IMPORT_FROM = re.compile(r"\b(?:import|export)\b[^;\n]*?\bfrom\s*[\"\']([^\"\']+)[\"\']")
TS_IMPORT_SIDE_EFFECT = re.compile(r"^\s*import\s*[\"\']([^\"\']+)[\"\']", re.MULTILINE)
TS_IMPORT_DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*[\"\']([^\"\']+)[\"\']\s*\)")
TS_SOURCE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".json")
RELEASE_SCRIPT_SUFFIXES = (".py", ".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs")
RELEASE_SCRIPT_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./-])(scripts/[A-Za-z0-9_.\-/]+\.(?:py|ts|tsx|mts|cts|js|mjs|cjs))(?![A-Za-z0-9_.\-/])"
)
SCENARIO_IMPORT_CLOSURE_INSPECTION_ONLY = {"src/pages/ResearchScenarioLabPage.tsx"}
OFFLINE_GRAPH_BINDING_MODE = "ACYCLIC_SEMANTIC_PROJECTION_V1"
OFFLINE_POLICY_PATH = Path("config/release/OFFLINE_SCENARIO_RELEASE.json")
OFFLINE_DESCRIPTOR_PATH = Path("public/data/scenario_core/offline_scenario_release.json")
OFFLINE_ATTACK_CASE_FLOOR = 41
PRODUCTION_POLICY_EPOCH = 9
PRODUCTION_EVIDENCE_PROFILE = 'PRODUCTION_SIMULATION_EVIDENCE_JOIN_V9'
PRODUCTION_POLICY_ANCHOR = 'fb561dc97a4b78750871faab9f70a63b2b27dedce1c5530cda6a2161f4c5824c'
PRODUCTION_REQUIRED_REPORTS = ('reports/facility-decision-build-reproducibility.json',
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
PRODUCTION_REQUIRED_RECEIPTS = ('orchestration.graph-check',
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


def _python_module_constants(text: str) -> dict[str, object]:
    """Extract simple top-level constant assignments from Python source."""
    tree = ast.parse(text)
    constants: dict[str, object] = {}
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
            constants[target.id] = value.value
    return constants


def _python_function_literal_case_ids(text: str, function_name: str) -> list[str]:
    """Extract literal first tuple elements from a list returned by a function."""
    tree = ast.parse(text)
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    ]
    if len(functions) != 1:
        return []
    result: list[str] = []
    for node in ast.walk(functions[0]):
        if not isinstance(node, ast.Return) or not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        for item in node.value.elts:
            if not isinstance(item, ast.Tuple) or not item.elts:
                continue
            first = item.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                result.append(first.value)
    return result


def _typescript_specifiers(text: str) -> list[str]:
    return sorted(set(
        TS_IMPORT_FROM.findall(text)
        + TS_IMPORT_SIDE_EFFECT.findall(text)
        + TS_IMPORT_DYNAMIC.findall(text)
    ))


def _resolve_local_typescript_specifier(root: Path, source: str, specifier: str) -> str | None:
    if specifier.startswith("@/"):
        base = root / "src" / specifier[2:]
    elif specifier.startswith("."):
        base = (root / source).parent / specifier
    else:
        return None
    candidates: list[Path]
    if base.suffix in TS_SOURCE_SUFFIXES:
        candidates = [base]
    else:
        candidates = [Path(str(base) + suffix) for suffix in TS_SOURCE_SUFFIXES]
        candidates.extend(base / f"index{suffix}" for suffix in TS_SOURCE_SUFFIXES)
    root_resolved = root.resolve()
    for candidate in candidates:
        candidate = candidate.resolve()
        try:
            relative = candidate.relative_to(root_resolved)
        except ValueError:
            continue
        if candidate.is_file():
            return relative.as_posix()
    return f"UNRESOLVED:{specifier}"


def _typescript_local_dependencies(root: Path, locked_files: Iterable[str]) -> list[tuple[str, str, str]]:
    dependencies: list[tuple[str, str, str]] = []
    for source in sorted(locked_files):
        path = root / source
        if source in SCENARIO_IMPORT_CLOSURE_INSPECTION_ONLY:
            continue
        if path.suffix not in TS_SOURCE_SUFFIXES or not path.is_file():
            continue
        for specifier in _typescript_specifiers(path.read_text(encoding="utf-8")):
            target = _resolve_local_typescript_specifier(root, source, specifier)
            if target is not None:
                dependencies.append((source, specifier, target))
    return dependencies


def _job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    jobs_index = next((index for index, line in enumerate(lines) if line.rstrip() == "jobs:"), None)
    if jobs_index is None:
        return {}
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[jobs_index + 1:]:
        match = JOB_LINE.match(line)
        if match:
            current = match.group(1)
            result[current] = [line]
            continue
        if current is not None:
            if line and not line.startswith(" "):
                break
            result[current].append(line)
    return {key: "\n".join(value) for key, value in result.items()}


def _workflow_has_pull_request_trigger(text: str) -> bool:
    """Recognize pull-request triggers without relying on a YAML dependency.

    GitHub treats ``on`` as a top-level workflow key.  We support block,
    scalar, and inline-list forms and deliberately include
    ``pull_request_target`` in the governed inventory because it is an even
    more privileged pull-request execution path.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(?:on|['\"]on['\"]):\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(1).split("#", 1)[0].strip()
        if re.search(r"(?:^|[\s,\[])(?:pull_request|pull_request_target)(?:$|[\s,\]])", value):
            return True
        if value:
            return False
        for child in lines[index + 1:]:
            if child and not child.startswith((" ", "\t")):
                break
            child_without_comment = child.split("#", 1)[0]
            if re.match(r"^\s{2}(?:pull_request|pull_request_target):(?:\s|$)", child_without_comment):
                return True
        return False
    return False


def _workflow_paths(root: Path) -> list[Path]:
    workflow_root = root / ".github/workflows"
    return sorted({*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")})


def _plan_signature(root: Path, graph: dict[str, Any], target: str) -> str:
    # Exact means same stages, same dependency edges, same commands, and the same
    # fully resolved npm-script bodies—not merely aliases with similar names.
    return canonical_json(plan_payload(target_plan(root, graph, target)))


def _resolved_npm_bodies(resolved: dict[str, Any]) -> list[str]:
    bodies: list[str] = []
    npm = resolved.get("npm")
    if not isinstance(npm, dict):
        return bodies
    pending = [npm]
    while pending:
        item = pending.pop()
        body = item.get("body")
        if isinstance(body, str):
            bodies.append(body)
        dependencies = item.get("dependencies", [])
        if isinstance(dependencies, list):
            pending.extend(value for value in dependencies if isinstance(value, dict))
    return bodies


def _release_script_paths_from_text(text: str) -> list[str]:
    """Extract literal repository script entrypoints from a command body.

    The regular expression is the authority for paths embedded in npm shell
    bodies.  ``shlex`` is used as a second independent parsing surface for
    ordinary argv-style bodies so quoting drift cannot silently hide a path.
    """
    paths = set(RELEASE_SCRIPT_TOKEN.findall(text))
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = []
    for token in tokens:
        if token.startswith("scripts/") and token.endswith(RELEASE_SCRIPT_SUFFIXES):
            paths.add(token)
    return sorted(paths)


def _stage_release_script_entrypoints(
    stage: dict[str, Any],
    package_scripts: dict[str, str],
) -> list[str]:
    command = stage.get("command", [])
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        return []
    resolved = resolve_command(command, package_scripts)
    paths = {
        item
        for item in command
        if item.startswith("scripts/") and item.endswith(RELEASE_SCRIPT_SUFFIXES)
    }
    for body in _resolved_npm_bodies(resolved):
        paths.update(_release_script_paths_from_text(body))
    return sorted(paths)


def _output_paths(stage: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for value in stage.get("outputs", []):
        paths.append(value if isinstance(value, str) else value["path"])
    return paths


def _output_covers(stage: dict[str, Any], artifact: str) -> bool:
    return any(artifact == output or artifact.startswith(output.rstrip("/") + "/") for output in _output_paths(stage))


def _offline_graph_contract_projection(graph: dict[str, Any]) -> dict[str, Any]:
    input_sets: dict[str, Any] = {}
    for set_id, specification in sorted(graph.get("input_sets", {}).items()):
        input_sets[set_id] = {
            "include": specification.get("include", []),
            "exclude": specification.get("exclude", []),
            "file_paths": sorted(specification.get("files", {})),
        }
    return {
        "schema_version": graph.get("schema_version"),
        "graph_id": graph.get("graph_id"),
        "classifications": graph.get("classifications"),
        "managed_package_scripts": graph.get("managed_package_scripts"),
        "production_designation": graph.get("production_designation"),
        "release_candidate": graph.get("release_candidate"),
        "truth_boundaries": graph.get("truth_boundaries"),
        "input_sets": input_sets,
        "stages": graph.get("stages"),
        "targets": graph.get("targets"),
        "integrations": graph.get("integrations"),
    }


def _offline_graph_contract_sha256(graph: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_offline_graph_contract_projection(graph)).encode("utf-8")).hexdigest()


def _stage_depends_on(stages: dict[str, dict[str, Any]], stage_id: str, required: str) -> bool:
    pending = list(stages.get(stage_id, {}).get("needs", []))
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == required:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(stages.get(current, {}).get("needs", []))
    return False


def _stage_ancestor_ids(stages: dict[str, dict[str, Any]], stage_id: str) -> list[str]:
    pending = list(stages.get(stage_id, {}).get("needs", []))
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        pending.extend(stages.get(current, {}).get("needs", []))
    return sorted(visited)


def validate(root: Path, graph_path: Path = GRAPH_PATH) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        graph = load_graph(root, graph_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.0.0",
            "classification": FAIL,
            "status": FAIL,
            "checks": 1,
            "errors": [f"canonical release graph unavailable:{type(exc).__name__}:{exc}"],
        }

    package = read_json(root / "package.json")
    scripts = package.get("scripts", {})
    require(isinstance(scripts, dict), "package scripts missing")
    if not isinstance(scripts, dict):
        scripts = {}

    offline_policy = read_json(root / OFFLINE_POLICY_PATH)
    offline_descriptor = read_json(root / OFFLINE_DESCRIPTOR_PATH)
    require(
        offline_policy.get("release_graph_binding_mode") == OFFLINE_GRAPH_BINDING_MODE,
        "offline release graph binding mode differs",
    )
    artifact_records = offline_policy.get("artifact_inventory", [])
    artifact_names = [record.get("name") for record in artifact_records if isinstance(record, dict)]
    artifact_paths = [record.get("path") for record in artifact_records if isinstance(record, dict)]
    require("release_graph" not in artifact_names, "offline descriptor reintroduces raw release-graph artifact cycle")
    require(GRAPH_PATH.as_posix() not in artifact_paths, "offline descriptor hashes the raw release graph")
    graph_binding = offline_descriptor.get("release_graph", {}) if isinstance(offline_descriptor.get("release_graph"), dict) else {}
    require(graph_binding.get("binding_mode") == OFFLINE_GRAPH_BINDING_MODE, "offline descriptor graph binding mode differs")
    require("file_sha256" not in graph_binding, "offline descriptor raw graph hash creates an identity cycle")
    require(
        graph_binding.get("contract_sha256") == _offline_graph_contract_sha256(graph),
        "offline descriptor semantic graph contract differs",
    )

    documentation_contract = offline_policy.get("documentation_contract") if isinstance(offline_policy.get("documentation_contract"), dict) else {}
    writer_owned = documentation_contract.get("writer_owned_surfaces")
    verification_only = documentation_contract.get("verification_only_surfaces")
    require(writer_owned == ["root", "standalone"], "offline documentation writer-owned surface contract differs")
    require(verification_only == ["facility", "verified"], "offline documentation verification-only surface contract differs")
    ownership = list(writer_owned or []) + list(verification_only or [])
    require(len(ownership) == 4 and len(set(ownership)) == 4 and set(ownership) == {"root", "standalone", "facility", "verified"}, "offline documentation ownership partition differs")

    require(graph.get("production_designation") == "NOT_GRANTED", "static production designation is not fail-closed")
    truth = graph.get("truth_boundaries", {})
    require(truth.get("healthcare_simulation_training") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "healthcare simulation scope differs")
    require(truth.get("simulated_patient_care_workflows") == "PERMITTED_WITHIN_VALIDATED_SCOPE", "simulated patient-care workflow scope differs")
    require(truth.get("direct_patient_care") == "PROHIBITED", "direct patient-care boundary changed")
    require(truth.get("clinical_decision_support") == "PROHIBITED", "clinical decision-support boundary changed")
    require(truth.get("patient_care_use") == "PROHIBITED", "legacy patient-care boundary changed")
    require(truth.get("simulation_logical_timing") == "VALIDATED_FOR_DETERMINISTIC_SIMULATION", "simulation logical timing boundary differs")
    require(truth.get("clinical_operational_timing") == "NOT_CALIBRATED", "clinical operational timing was promoted")
    require(truth.get("clinical_timing_transferability") == "NOT_ESTABLISHED", "clinical timing transferability was promoted")
    require(truth.get("operational_timing") == "NOT_CALIBRATED", "legacy operational timing was promoted")
    require(truth.get("concrete_treatments_admitted") == 0, "concrete treatment was admitted")
    require(truth.get("production_ready") is False, "legacy clinical production-ready flag was promoted")

    managed = graph["managed_package_scripts"]
    require(set(managed).issubset(scripts), "managed package script inventory is incomplete")
    for name, expected in sorted(managed.items()):
        require(scripts.get(name) == expected, f"package script differs:{name}")

    # Every lock is checked from the actual applied repository state.
    for set_id, specification in sorted(graph["input_sets"].items()):
        lock_errors = verify_input_set(root, set_id, specification)
        checks += max(1, len(specification.get("files", {})))
        errors.extend(lock_errors)
        require(GRAPH_PATH.as_posix() not in specification.get("files", {}), f"release graph self-hash cycle:{set_id}")

    stages = stage_map(graph)
    surface_paths = {
        "root": documentation_contract.get("root_readme"),
        "standalone": documentation_contract.get("standalone_readme"),
        "facility": documentation_contract.get("facility_readme"),
        "verified": documentation_contract.get("verified_readme"),
    }
    offline_stage = stages.get("offline.release-generate")
    require(isinstance(offline_stage, dict), "offline release generation stage missing")
    if isinstance(offline_stage, dict):
        declared_outputs = set(offline_stage.get("outputs", []))
        expected_owned_outputs = {surface_paths.get(surface) for surface in (writer_owned or [])}
        expected_owned_outputs.update({offline_policy.get("output_path"), offline_policy.get("report_path")})
        expected_owned_outputs.discard(None)
        require(declared_outputs == expected_owned_outputs, "offline release generation output ownership differs")
        forbidden_outputs = {surface_paths.get(surface) for surface in (verification_only or [])}
        forbidden_outputs.discard(None)
        require(not (declared_outputs & forbidden_outputs), "offline release generation claims verification-only documentation")
    stage_ids = list(stages)
    require(len(stage_ids) == len(set(stage_ids)), "stage IDs are not unique")
    for stage_id, stage in stages.items():
        command = stage["command"]
        require(stage.get("failure_classification") == FAIL, f"stage failure classification differs:{stage_id}")
        require(command[0] in {"npm", "npm.cmd"}, f"stage bypasses managed command layer:{stage_id}")
        if len(command) >= 3 and command[1] == "run":
            require(command[2] in managed, f"stage references unmanaged npm script:{stage_id}:{command[2]}")
        else:
            require(False, f"stage command is not npm run:{stage_id}")
        if stage.get("read_only"):
            locked_paths: set[str] = set()
            for set_id in stage.get("input_sets", []):
                locked_paths.update(graph["input_sets"][set_id].get("files", {}))
            for output in _output_paths(stage):
                overlap = any(path == output or path.startswith(output.rstrip("/") + "/") for path in locked_paths)
                require(not overlap, f"read-only stage output overlaps locked input:{stage_id}:{output}")

    # Every repository-local checker/generator dependency reachable from a stage's
    # exact npm command must be authenticated by that stage's input-set union.
    # This closes the recurring class where a new shared helper is imported but
    # omitted from the release graph, allowing unreviewed bytes to influence a
    # supposedly content-addressed receipt.
    stage_entrypoint_map: dict[str, list[str]] = {}
    all_entrypoints: set[str] = set()
    for stage_id, stage in sorted(stages.items()):
        try:
            entrypoints = _stage_release_script_entrypoints(stage, scripts)
        except Exception as exc:  # noqa: BLE001 - checker must retain a structured verdict
            entrypoints = []
            errors.append(f"release stage command cannot be resolved:{stage_id}:{type(exc).__name__}:{exc}")
        stage_entrypoint_map[stage_id] = entrypoints
        all_entrypoints.update(entrypoints)

    dependency_index, dependency_index_errors = build_dependency_index(root, all_entrypoints)
    checks += max(1, len(dependency_index))
    errors.extend(f"release source closure index:{item}" for item in dependency_index_errors)

    closure_entrypoints = 0
    closure_dependencies = 0
    closure_generated_dependencies = 0
    closure_visited_sources: set[str] = set()
    closure_stage_count = 0
    for stage_id, stage in sorted(stages.items()):
        stage_locked_paths = {
            relative
            for set_id in stage.get("input_sets", [])
            for relative in graph.get("input_sets", {}).get(set_id, {}).get("files", {})
        }
        authenticated_generated_files = {
            output
            for ancestor_id in _stage_ancestor_ids(stages, stage_id)
            for output in _output_paths(stages[ancestor_id])
            if output.startswith(("scripts/", "src/", "server/", "api/", "config/"))
            and (root / output).is_file()
        }
        entrypoints = stage_entrypoint_map[stage_id]
        closure_stage_count += 1
        closure_entrypoints += len(entrypoints)
        for entrypoint in entrypoints:
            require((root / entrypoint).is_file(), f"release stage script entrypoint missing:{stage_id}:{entrypoint}")
        stage_errors, stage_dependencies, visited_sources = transitive_closure_errors(
            entrypoints,
            stage_locked_paths,
            dependency_index,
            scope=f"stage:{stage_id}",
            authenticated_generated_files=authenticated_generated_files,
        )
        checks += max(1, len(entrypoints) + len(stage_dependencies))
        errors.extend(stage_errors)
        closure_dependencies += len(stage_dependencies)
        closure_generated_dependencies += sum(
            1 for dependency in stage_dependencies if dependency.target in authenticated_generated_files
        )
        closure_visited_sources.update(visited_sources)

    source_closure_summary = {
        "schema_version": SOURCE_CLOSURE_SCHEMA_VERSION,
        "scope": CLOSURE_SCOPE,
        "python_mode": PYTHON_MODE,
        "node_mode": NODE_MODE,
        "stages_checked": closure_stage_count,
        "stage_entrypoints_checked": closure_entrypoints,
        "unique_entrypoints": len(all_entrypoints),
        "dependency_index_sources": len(dependency_index),
        "repository_local_dependencies_checked": closure_dependencies,
        "authenticated_generated_dependencies_checked": closure_generated_dependencies,
        "unique_sources_visited": len(closure_visited_sources),
        "index_errors": dependency_index_errors,
    }

    integrations = graph.get("integrations", {})
    require(isinstance(integrations, dict), "release graph integrations missing")

    source_closure = integrations.get("local_source_closure_contract", {}) if isinstance(integrations, dict) else {}
    expected_identity_membership = {
        "scripts/release_identity_common.py": [
            "orchestration",
            "release-policy-source",
            "scenario-source",
            "standalone-source",
        ],
        "scripts/engine_evolution_documentation_common.mjs": [
            "orchestration",
            "release-policy-source",
            "scenario-source",
            "standalone-source",
        ],
    }
    require(source_closure.get("schema_version") == SOURCE_CLOSURE_SCHEMA_VERSION, "local source-closure schema differs")
    require(source_closure.get("scope") == CLOSURE_SCOPE, "local source-closure scope differs")
    require(source_closure.get("python_mode") == PYTHON_MODE, "local Python source-closure mode differs")
    require(source_closure.get("node_mode") == NODE_MODE, "local Node source-closure mode differs")
    require(source_closure.get("stage_scope") == "ALL_CANONICAL_STAGES", "local source-closure stage scope differs")
    require(
        source_closure.get("dependency_index_mode") == "RECURSIVE_FROM_EXACT_STAGE_ENTRYPOINTS",
        "local source-closure dependency-index mode differs",
    )
    require(
        source_closure.get("generated_dependency_policy") == "TRANSITIVE_PREDECESSOR_OUTPUTS_ONLY",
        "local source-closure generated-dependency policy differs",
    )
    require(
        source_closure.get("focused_attack_script") == "scripts/test_release_source_closure.py",
        "local source-closure focused attack script differs",
    )
    require(
        source_closure.get("focused_attack_report") == "reports/release-source-closure-mutations.json",
        "local source-closure focused attack report differs",
    )
    require(
        source_closure.get("identity_critical_membership") == expected_identity_membership,
        "identity-critical source membership contract differs",
    )
    for relative, set_ids in expected_identity_membership.items():
        for set_id in set_ids:
            require(
                relative in graph.get("input_sets", {}).get(set_id, {}).get("files", {}),
                f"identity-critical source is not locked:{set_id}:{relative}",
            )
    graph_attack_outputs = set(_output_paths(stages.get("orchestration.graph-attacks-mutations", {})))
    require(
        "reports/release-source-closure-mutations.json" in graph_attack_outputs,
        "release graph mutation partition omits source-closure evidence",
    )

    offline_identity = integrations.get("offline_release_identity_contract", {}) if isinstance(integrations, dict) else {}
    require(offline_identity.get("schema_version") == "1.0.0", "offline release identity contract schema differs")
    require(offline_identity.get("descriptor_path") == OFFLINE_DESCRIPTOR_PATH.as_posix(), "offline release descriptor path differs")
    require(offline_identity.get("release_graph_path") == GRAPH_PATH.as_posix(), "offline release graph path differs")
    require(offline_identity.get("binding_mode") == OFFLINE_GRAPH_BINDING_MODE, "offline release identity contract mode differs")
    require(offline_identity.get("raw_release_graph_file_hash_forbidden") is True, "offline raw release-graph hash is not forbidden")
    require(offline_identity.get("canonical_graph_locks_descriptor") is True, "canonical graph does not lock offline descriptor")
    require(
        offline_identity.get("semantic_projection_excludes") == ["input_sets.*.files.*"],
        "offline semantic projection exclusion contract differs",
    )
    require(
        offline_identity.get("semantic_projection_preserves") == [
            "classifications",
            "graph_id",
            "input_set_path_inventory",
            "integrations",
            "managed_package_scripts",
            "production_designation",
            "release_candidate",
            "stages",
            "targets",
            "truth_boundaries",
        ],
        "offline semantic projection preservation contract differs",
    )
    require(
        OFFLINE_DESCRIPTOR_PATH.as_posix() in graph.get("input_sets", {}).get("standalone-source", {}).get("files", {}),
        "offline descriptor is not locked by the canonical graph",
    )
    required_order = integrations.get("facility_arrival_required_order", []) if isinstance(integrations, dict) else []
    try:
        arrival_plan = target_stage_ids(graph, "facility-arrival-runtime")
    except Exception as exc:  # noqa: BLE001
        arrival_plan = []
        errors.append(f"facility arrival target unavailable:{type(exc).__name__}:{exc}")
    for stage_id in required_order:
        require(stage_id in arrival_plan, f"runtime assurance omits stage:{stage_id}")
    positions = [arrival_plan.index(stage_id) for stage_id in required_order if stage_id in arrival_plan]
    require(positions == sorted(positions) and len(set(positions)) == len(positions), "facility-arrival required order differs")

    standalone_stage = stages.get("standalone.contracts", {})
    require(
        standalone_stage.get("command") == ["npm", "run", "verify:facility-arrival-standalone"],
        "standalone contracts do not use the attributed canonical runner",
    )
    for relative in (
        ".asklepios/facility-standalone/gate-report.json",
        "reports/facility-arrival-standalone.json",
        "reports/facility-arrival-standalone-mutations.json",
        "reports/facility-arrival-standalone-runtime.json",
        "reports/facility-arrival-standalone-ui.json",
    ):
        require(relative in _output_paths(standalone_stage), f"standalone gate output missing:{relative}")

    content_stage = stages.get("content.registry-source", {})
    require(
        content_stage.get("command") == ["npm", "run", "check:content-registry-runtime"],
        "content registry does not use the attributed canonical runner",
    )
    require(
        ".asklepios/content-registry/runtime-report.json" in _output_paths(content_stage),
        "content-registry attributed report output missing",
    )

    app_typecheck = stages.get("build.app-typecheck", {})
    require(app_typecheck.get("command") == ["npm", "run", "typecheck:app"], "application typecheck stage differs")
    require(app_typecheck.get("needs") == ["dependencies.npm-ci"], "application typecheck bypasses locked dependencies")
    require(
        stages.get("build.double-reproducibility", {}).get("needs") == ["build.app-typecheck"],
        "double build bypasses application typecheck",
    )

    research_generation = stages.get("scenario.research-generation", {})
    require(
        research_generation.get("read_only") is False,
        "research scenario generation must declare writes",
    )
    require(
        set(_output_paths(research_generation)) == {"public/data/research_sandbox/generated_scenario.json"},
        "research scenario generation output boundary differs",
    )

    scenario_stage_specs = {'offline.release-attacks': {'command': ['npm', 'run', 'test:offline-scenario-release'],
                                 'needs': ['offline.release-python', 'offline.release-node'],
                                 'outputs': {'reports/offline-scenario-release-mutations.json'},
                                 'read_only': True},
     'offline.release-generate': {'command': ['npm', 'run', 'generate:offline-scenario-release'],
                                  'needs': ['arrival.generate',
                                            'scenario.verified-artifacts-generate',
                                            'standalone.contracts'],
                                  'outputs': {'README.md',
                                              'docs/FACILITY_ARRIVAL_STANDALONE.md',
                                              'public/data/scenario_core/offline_scenario_release.json',
                                              'reports/offline-scenario-release.json'},
                                  'read_only': False},
     'offline.release-node': {'command': ['npm', 'run', 'check:offline-scenario-release-node'],
                              'needs': ['offline.release-generate'],
                              'outputs': {'reports/offline-scenario-release-node.json'},
                              'read_only': True},
     'offline.release-python': {'command': ['npm', 'run', 'check:offline-scenario-release'],
                                'needs': ['offline.release-generate'],
                                'outputs': {'reports/offline-scenario-release-check.json'},
                                'read_only': True},
     'scenario.behavior-archive-attacks': {'command': ['npm', 'run', 'test:scenario-behavior-archive'],
                                           'needs': ['scenario.behavior-archive-check'],
                                           'outputs': {'reports/scenario-behavior-archive-mutations.json'},
                                           'read_only': True},
     'scenario.behavior-archive-check': {'command': ['npm', 'run', 'check:scenario-behavior-archive'],
                                         'needs': ['scenario.contracts'],
                                         'outputs': {'reports/scenario-behavior-archive-check.json'},
                                         'read_only': True},
     'scenario.behavioral-policy': {'command': ['npm', 'run', 'check:scenario-behavioral-policy'],
                                    'needs': ['scenario.behavior-archive-attacks'],
                                    'outputs': {'reports/scenario-behavioral-equivalence-generation.json',
                                                'reports/scenario-behavioral-equivalence-python.json',
                                                'reports/scenario-behavioral-equivalence.json'},
                                    'read_only': False},
     'scenario.behavioral-policy-attacks': {'command': ['npm', 'run', 'test:scenario-behavioral-policy'],
                                            'needs': ['scenario.behavioral-policy'],
                                            'outputs': {'reports/scenario-behavioral-equivalence-mutations.json'},
                                            'read_only': True},
     'scenario.capability-ratchet': {'command': ['npm', 'run', 'check:scenario-capability-ratchet'],
                                     'needs': ['scenario.plain-language-summary-attacks'],
                                     'outputs': {'reports/scenario-capability-ratchet.json'},
                                     'read_only': True},
     'scenario.capability-ratchet-attacks': {'command': ['npm', 'run', 'test:scenario-capability-ratchet'],
                                             'needs': ['scenario.capability-ratchet'],
                                             'outputs': {'reports/scenario-capability-ratchet-mutations.json'},
                                             'read_only': True},
     'scenario.contracts': {'command': ['npm', 'run', 'check:scenario-contract-gate'],
                            'needs': ['scenario.verified-example-attacks',
                                      'scenario.genome-attacks',
                                      'offline.release-attacks',
                                      'scenario.node-checker-cli-attacks',
                                      'scenario.engine-evolution-doc-attacks'],
                            'outputs': {'reports/scenario-behavior-archive.json',
                                        'reports/scenario-contract-gate.json',
                                        'reports/scenario-experience-assurance.json'},
                            'read_only': True},
     'scenario.engine-evolution-doc-attacks': {'command': ['npm', 'run', 'test:engine-evolution-docs'],
                                               'needs': ['scenario.engine-evolution-docs-python',
                                                         'scenario.engine-evolution-docs-node'],
                                               'outputs': {'reports/scenario-engine-evolution-doc-attacks.json'},
                                               'read_only': True},
     'scenario.engine-evolution-docs-node': {'command': ['npm', 'run', 'check:engine-evolution-docs-node'],
                                             'needs': ['scenario.node-checker-cli-attacks'],
                                             'outputs': {'reports/scenario-engine-evolution-docs-node.json'},
                                             'read_only': True},
     'scenario.engine-evolution-docs-python': {'command': ['npm', 'run', 'check:engine-evolution-docs-python'],
                                               'needs': ['scenario.node-checker-cli-attacks'],
                                               'outputs': {'reports/scenario-engine-evolution-docs-python.json'},
                                               'read_only': True},
     'scenario.evolution-evidence': {'command': ['npm', 'run', 'join:scenario-evolution'],
                                     'needs': ['scenario.capability-ratchet-attacks'],
                                     'outputs': {'reports/scenario-evolution-evidence.json'},
                                     'read_only': True},
     'scenario.evolution-evidence-attacks': {'command': ['npm', 'run', 'test:scenario-evolution-evidence'],
                                             'needs': ['scenario.evolution-evidence'],
                                             'outputs': {'reports/scenario-evolution-evidence-mutations.json'},
                                             'read_only': True},
     'scenario.genome-attacks': {'command': ['npm', 'run', 'test:scenario-genome'],
                                 'needs': ['scenario.genome-node'],
                                 'outputs': {'reports/scenario-genome-mutations.json'},
                                 'read_only': True},
     'scenario.genome-node': {'command': ['npm', 'run', 'check:scenario-genome-node'],
                              'needs': ['scenario.genome-python'],
                              'outputs': {'reports/scenario-genome-node.json'},
                              'read_only': True},
     'scenario.genome-python': {'command': ['npm', 'run', 'check:scenario-genome-python'],
                                'needs': ['scenario.verified-artifacts-generate'],
                                'outputs': {'reports/scenario-genome-python-check.json'},
                                'read_only': True},
     'scenario.node-checker-cli-attacks': {'command': ['npm', 'run', 'test:node-checker-cli'],
                                           'needs': ['scenario.verified-example-node',
                                                     'scenario.genome-node',
                                                     'offline.release-node'],
                                           'outputs': {'reports/node-checker-cli-mutations.json'},
                                           'read_only': True},
     'scenario.plain-language-summary': {'command': ['npm', 'run', 'generate:plain-language-change-summary'],
                                         'needs': ['scenario.stakeholder-product-attacks'],
                                         'outputs': {'docs/RC3_8D_PLAIN_LANGUAGE_CHANGE_SUMMARY.md',
                                                     'reports/plain-language-change-summary-write.json'},
                                         'read_only': False},
     'scenario.plain-language-summary-attacks': {'command': ['npm', 'run', 'test:plain-language-change-summary'],
                                                 'needs': ['scenario.plain-language-summary-check'],
                                                 'outputs': {'reports/plain-language-change-summary-mutations.json'},
                                                 'read_only': True},
     'scenario.plain-language-summary-check': {'command': ['npm', 'run', 'check:plain-language-change-summary'],
                                               'needs': ['scenario.plain-language-summary'],
                                               'outputs': {'reports/plain-language-change-summary-node.json',
                                                           'reports/plain-language-change-summary.json'},
                                               'read_only': True},
     'scenario.science-foundation': {'command': ['npm', 'run', 'generate:scenario-science-telemetry'],
                                     'needs': ['scenario.behavioral-policy-attacks'],
                                     'outputs': {'examples/scenario-science/reference-telemetry.json',
                                                 'reports/scenario-science-telemetry-write.json'},
                                     'read_only': False},
     'scenario.science-foundation-attacks': {'command': ['npm', 'run', 'test:scenario-science-foundation'],
                                             'needs': ['scenario.science-foundation-check'],
                                             'outputs': {'reports/scenario-science-telemetry-mutations.json'},
                                             'read_only': True},
     'scenario.science-foundation-check': {'command': ['npm', 'run', 'check:scenario-science-telemetry'],
                                           'needs': ['scenario.science-foundation'],
                                           'outputs': {'reports/scenario-science-telemetry-node.json',
                                                       'reports/scenario-science-telemetry-python.json'},
                                           'read_only': True},
     'scenario.stakeholder-product': {'command': ['npm', 'run', 'generate:stakeholder-product-surface'],
                                      'needs': ['scenario.treatment-admission-attacks'],
                                      'outputs': {'public/data/scenario_library/operational-pack.json',
                                                  'public/data/scenario_library/stakeholder-dashboard.json',
                                                  'reports/operational-scenario-pack-write.json',
                                                  'reports/stakeholder-product-bundle-write.json'},
                                      'read_only': False},
     'scenario.stakeholder-product-attacks': {'command': ['npm', 'run', 'test:stakeholder-product-surface'],
                                              'needs': ['scenario.stakeholder-product-check'],
                                              'outputs': {'reports/operational-scenario-pack-mutations.json',
                                                          'reports/stakeholder-product-bundle-mutations.json'},
                                              'read_only': True},
     'scenario.stakeholder-product-check': {'command': ['npm', 'run', 'check:stakeholder-product-surface'],
                                            'needs': ['scenario.stakeholder-product'],
                                            'outputs': {'reports/operational-scenario-pack-generation.json',
                                                        'reports/operational-scenario-pack-node.json',
                                                        'reports/stakeholder-product-bundle-node.json',
                                                        'reports/stakeholder-product-bundle-python.json',
                                                        'reports/stakeholder-product-bundle.json'},
                                            'read_only': True},
     'scenario.treatment-admission': {'command': ['npm', 'run', 'generate:treatment-admission'],
                                      'needs': ['scenario.science-foundation-attacks'],
                                      'outputs': {'public/data/scenario_library/treatment-admission.json',
                                                  'reports/treatment-admission-registry-write.json'},
                                      'read_only': False},
     'scenario.treatment-admission-attacks': {'command': ['npm', 'run', 'test:treatment-admission'],
                                              'needs': ['scenario.treatment-admission-check'],
                                              'outputs': {'reports/treatment-admission-registry-mutations.json'},
                                              'read_only': True},
     'scenario.treatment-admission-check': {'command': ['npm', 'run', 'check:treatment-admission'],
                                            'needs': ['scenario.treatment-admission'],
                                            'outputs': {'reports/treatment-admission-registry-node.json',
                                                        'reports/treatment-admission-registry.json'},
                                            'read_only': True},
     'scenario.verified-artifacts-generate': {'command': ['npm', 'run', 'generate:verified-scenario'],
                                              'needs': ['dependencies.npm-ci', 'content.registry-source'],
                                              'outputs': {'examples/verified-scenario/README.md',
                                                          'examples/verified-scenario/manifest.json',
                                                          'public/data/scenario_core/verified_scenario.json',
                                                          'public/data/scenario_core/verified_scenario_genome.json',
                                                          'public/data/scenario_core/verified_scenario_package.json',
                                                          'reports/scenario-genome.json',
                                                          'reports/scenario-package-generation.json',
                                                          'reports/verified-example-generation.json'},
                                              'read_only': False},
     'scenario.verified-example-attacks': {'command': ['npm', 'run', 'test:verified-example'],
                                           'needs': ['scenario.verified-example-python', 'scenario.verified-example-node'],
                                           'outputs': {'reports/verified-example-mutations.json'},
                                           'read_only': True},
     'scenario.verified-example-generation-check': {'command': ['npm', 'run', 'check:verified-example-generated'],
                                                    'needs': ['scenario.verified-artifacts-generate'],
                                                    'outputs': {'reports/verified-example-generation-check.json'},
                                                    'read_only': True},
     'scenario.verified-example-node': {'command': ['npm', 'run', 'check:verified-example-node'],
                                        'needs': ['scenario.verified-example-generation-check'],
                                        'outputs': {'reports/verified-example-node.json'},
                                        'read_only': True},
     'scenario.verified-example-python': {'command': ['npm', 'run', 'check:verified-example-python'],
                                          'needs': ['scenario.verified-example-generation-check'],
                                          'outputs': {'reports/verified-example-python.json'},
                                          'read_only': True},
     'standalone.generate': {'command': ['npm', 'run', 'generate:facility-arrival-standalone'],
                             'needs': ['release.production-policy-attacks'],
                             'outputs': {'examples/facility-arrival/playable.html'},
                             'read_only': False}}
    for stage_id, expected in scenario_stage_specs.items():
        stage = stages.get(stage_id)
        require(isinstance(stage, dict), f"scenario evolution stage missing:{stage_id}")
        if not isinstance(stage, dict):
            continue
        require(stage.get("command") == expected["command"], f"scenario evolution command differs:{stage_id}")
        require(stage.get("needs") == expected["needs"], f"scenario evolution predecessors differ:{stage_id}")
        require(stage.get("read_only") is expected["read_only"], f"scenario evolution write boundary differs:{stage_id}")
        require(set(_output_paths(stage)) == expected["outputs"], f"scenario evolution outputs differ:{stage_id}")

    expected_evolution_boundary = ['standalone.generate',
     'scenario.verified-artifacts-generate',
     'scenario.verified-example-generation-check',
     'scenario.verified-example-python',
     'scenario.verified-example-node',
     'scenario.verified-example-attacks',
     'scenario.genome-python',
     'scenario.genome-node',
     'scenario.genome-attacks',
     'offline.release-generate',
     'offline.release-python',
     'offline.release-node',
     'offline.release-attacks',
     'scenario.node-checker-cli-attacks',
     'scenario.engine-evolution-docs-python',
     'scenario.engine-evolution-docs-node',
     'scenario.engine-evolution-doc-attacks',
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
     'scenario.plain-language-summary',
     'scenario.plain-language-summary-check',
     'scenario.plain-language-summary-attacks',
     'scenario.capability-ratchet',
     'scenario.capability-ratchet-attacks',
     'scenario.evolution-evidence',
     'scenario.evolution-evidence-attacks']
    require(
        integrations.get("required_scenario_evolution_stages") == expected_evolution_boundary,
        "required scenario evolution stage inventory differs",
    )
    require(
        "scenario.evolution-evidence-attacks" in integrations.get("critical_package_rehearsal_stages", []),
        "scenario receipt attack stage is not release-critical",
    )
    require(
        "scenario.behavior-archive-attacks" in integrations.get("critical_package_rehearsal_stages", []),
        "scenario behavior archive attack stage is not release-critical",
    )

    scenario_stage = stages.get("scenario.contracts", {})
    scenario_locked = graph.get("input_sets", {}).get("scenario-source", {}).get("files", {})
    for relative in (
        "config/scenario-genome/SCENARIO_GENOME_POLICY.json",
        "config/release/OFFLINE_SCENARIO_RELEASE.json",
        "scripts/build_offline_scenario_release.py",
        "scripts/build_scenario_genome.py",
        "scripts/check_engine_evolution_documentation.mjs",
        "scripts/check_engine_evolution_documentation.py",
        "scripts/check_offline_scenario_release.mjs",
        "scripts/engine_evolution_common.py",
        "scripts/engine_evolution_documentation_common.mjs",
        "scripts/node_checker_cli.mjs",
        "scripts/offline_scenario_release_common.py",
        "scripts/build_verified_example_scenario.py",
        "scripts/checkRepositoryVocabulary.ts",
        "scripts/check_scenario_genome.mjs",
        "scripts/check_scenario_behavior_archive.py",
        "scripts/check_verified_example_scenario.mjs",
        "scripts/check_verified_example_scenario.py",
        "scripts/join_scenario_evolution_evidence.py",
        "scripts/run_scenario_contract_gate.py",
        "scripts/run_scenario_contracts_hermetic.py",
        "scripts/runScenarioExperienceAssurance.ts",
        "scripts/scenario_genome_common.py",
        "scripts/test_engine_evolution_documentation.py",
        "scripts/test_node_checker_cli.mjs",
        "scripts/test_offline_scenario_release.py",
        "scripts/test_scenario_evolution_evidence.py",
        "scripts/test_scenario_genome.py",
        "scripts/test_scenario_behavior_archive.py",
        "scripts/test_verified_example_scenario.py",
        "scripts/testScenarioExperienceMutations.ts",
        "scripts/validateScenarioContractRelease.ts",
        "src/pages/ResearchScenarioLabPage.tsx",
        "src/scenario-core/experience.ts",
        "src/scenario-core/qualityDiversity.ts",
        "src/tests/scenarioCoreExperience.test.ts",
        "src/tests/scenarioCoreVocabularyIsolation.test.ts",
        "src/test-fixtures/researchBridge.fixture.ts",
    ):
        require(relative in scenario_locked, f"scenario transitive dependency is not locked:{relative}")
    for source, specifier, target in _typescript_local_dependencies(root, scenario_locked):
        require(not target.startswith("UNRESOLVED:"), f"scenario local import does not resolve:{source}:{specifier}")
        if not target.startswith("UNRESOLVED:"):
            require(target in scenario_locked, f"scenario transitive dependency is not locked:{target}:imported-by:{source}")

    experience_assurance_source = (root / "scripts/runScenarioExperienceAssurance.ts").read_text(encoding="utf-8")
    route_source = (root / "src/scenario-core/route.ts").read_text(encoding="utf-8")
    profile_route_test_source = (root / "src/tests/scenarioOperationalBehaviorProfiles.test.ts").read_text(encoding="utf-8")
    for marker in (
        "enumerateSuccessfulRouteWitnesses",
        "replayRouteWitness",
        "successful_route_witness_inventory_is_complete",
        "route_witness_replay_is_edge_order_independent",
        "every_successful_route_preserves_teamwork_requirements",
        "SCENARIO_OPERATIONAL_BEHAVIOR_PROFILES",
        "auditProfileRouteWitnesses",
        "for (const profile of SCENARIO_OPERATIONAL_BEHAVIOR_PROFILES)",
        "graph_derived_witnesses_preserve_requirements",
    ):
        require(marker in experience_assurance_source, f"scenario experience graph-derived route witness guard missing:{marker}")
    for marker in (
        "export function enumerateSuccessfulRouteWitnesses",
        "export function replayRouteWitness",
        "Route witness inventory exceeds the configured limit.",
        "Route witness encountered a cycle",
    ):
        require(marker in route_source, f"scenario route witness primitive missing:{marker}")
    for marker in (
        "enumerateSuccessfulRouteWitnesses",
        "replayRouteWitness(reversedEdgeRoute, witness)",
        "witness inventory depends on edge storage order",
        "profile.intermediate_handoff_steps",
    ):
        require(marker in profile_route_test_source, f"four-profile route witness regression missing:{marker}")
    hardcoded_experience_routes = (
        r"\[\s*['\"]start['\"]\s*,\s*['\"]arrive['\"]\s*,\s*['\"]facilitator_event['\"]\s*,\s*['\"]handoff_ready['\"]\s*,\s*['\"]close['\"]\s*\]",
        r"\[\s*['\"]start['\"]\s*,\s*['\"]arrive['\"]\s*,\s*['\"]handoff_ready['\"]\s*,\s*['\"]close['\"]\s*\]",
    )
    for pattern in hardcoded_experience_routes:
        require(re.search(pattern, experience_assurance_source) is None, "legacy fixed-length scenario route trigger sequence remains")

    quality_diversity_source = (root / "src/scenario-core/qualityDiversity.ts").read_text(encoding="utf-8")
    behavior_archive_checker_source = (root / "scripts/check_scenario_behavior_archive.py").read_text(encoding="utf-8")
    behavior_archive_attack_source = (root / "scripts/test_scenario_behavior_archive.py").read_text(encoding="utf-8")
    for marker in (
        "TOPIC_X_OBSERVED_FEASIBLE_OPERATIONAL_POLICY_SHAPE_V1",
        "feasibleOperationalPolicyShapes",
        "marginalCartesianCells",
        "infeasibleCartesianCellsExcluded",
        "possibleCells = topics * feasibleOperationalPolicyShapes",
    ):
        require(marker in quality_diversity_source, f"feasible behavior-cell domain guard missing:{marker}")
    require(
        re.search(r"const\s+possibleCells\s*=\s*topics\s*\*\s*communications", quality_diversity_source) is None,
        "quality-diversity archive restored infeasible marginal Cartesian cell count",
    )
    for marker in (
        "FEASIBILITY_PROFILE",
        "feasible_operational_policy_shapes",
        "marginal_cartesian_cells_in_observed_domain",
        "infeasible_cartesian_cells_excluded",
        "possible_cells = topics * feasible_operational_policy_shapes",
    ):
        require(marker in behavior_archive_checker_source, f"independent feasible behavior-cell reconstruction missing:{marker}")
    require(
        re.search(r"possible_cells\s*=\s*topics\s*\*\s*communications", behavior_archive_checker_source) is None,
        "independent behavior archive checker restored infeasible marginal Cartesian cell count",
    )
    for marker in (
        "feasible_cell_domain_profile_removed",
        "marginal_cartesian_overcount_rejected",
        "profile_route_witness_guard_removed",
    ):
        require(marker in behavior_archive_attack_source, f"behavior archive feasibility/witness regression case missing:{marker}")

    node_documentation_common = root / "scripts/engine_evolution_documentation_common.mjs"
    require(node_documentation_common.is_file(), "shared Node engine-evolution renderer missing")
    common_renderer_source = node_documentation_common.read_text(encoding="utf-8") if node_documentation_common.is_file() else ""
    for marker in (
        "export function graphContractProjection",
        "export function graphContractSha256",
        "export function renderEvolutionBlock",
        "export function renderRootSection",
        "export function renderStandaloneSection",
    ):
        require(common_renderer_source.count(marker) == 1, f"shared Node documentation renderer inventory differs:{marker}")
    for relative in (
        "scripts/check_offline_scenario_release.mjs",
        "scripts/check_engine_evolution_documentation.mjs",
        "scripts/generateFacilityArrivalArtifacts.ts",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        require(
            "./engine_evolution_documentation_common.mjs" in source,
            f"Node checker bypasses shared engine-evolution renderer:{relative}",
        )
        for forbidden in (
            "function graphContractProjection",
            "function graphContractSha256",
            "function renderEvolutionBlock",
            "function renderRootSection",
            "function renderStandaloneSection",
            "function expectedEvolutionBlock",
        ):
            require(forbidden not in source, f"duplicate Node documentation renderer authority:{relative}:{forbidden}")
        if relative == "scripts/generateFacilityArrivalArtifacts.ts":
            require("renderEvolutionBlock(evolutionContext" in source, "Facility Arrival parity checker omits shared evolution renderer")
            require("graphContractSha256(evolutionContext.graph)" in source, "Facility Arrival parity checker omits shared graph-contract identity")

    offline_attack_path = root / "scripts/test_offline_scenario_release.py"
    require(offline_attack_path.is_file(), "offline release adversarial harness missing")
    offline_attack_source = offline_attack_path.read_text(encoding="utf-8") if offline_attack_path.is_file() else ""
    try:
        offline_attack_constants = _python_module_constants(offline_attack_source)
        offline_attack_case_ids = _python_function_literal_case_ids(offline_attack_source, "cases")
    except SyntaxError as exc:
        offline_attack_constants = {}
        offline_attack_case_ids = []
        errors.append(f"offline release adversarial harness syntax invalid:{exc.msg}")
    require(
        offline_attack_constants.get("CASE_REGISTRY_PROFILE") == "UNIQUE_DETERMINISTIC_CASE_REGISTRY_V1",
        "offline release case registry contract missing",
    )
    require(
        offline_attack_constants.get("CASE_SCHEDULER_PROFILE") == "BOUNDED_PARALLEL_ISOLATED_FIXTURES_V1",
        "offline release bounded scheduler contract missing",
    )
    require(
        offline_attack_constants.get("SOURCE_GUARD_PROFILE") == "SOURCE_INVENTORY_PRESERVATION_RATCHET_V1",
        "offline release source preservation contract missing",
    )
    require(offline_attack_constants.get("DEFAULT_WORKERS") == 4, "offline release default worker count differs")
    require(offline_attack_constants.get("MAX_WORKERS") == 8, "offline release worker ceiling differs")
    require(
        len(offline_attack_case_ids) >= OFFLINE_ATTACK_CASE_FLOOR,
        "offline release attack case floor regressed",
    )
    require(
        len(offline_attack_case_ids) == len(set(offline_attack_case_ids)),
        "offline release attack case registry contains duplicates",
    )
    for case_id in offline_attack_case_ids:
        require(
            re.fullmatch(r"[a-z0-9][a-z0-9_-]*", case_id) is not None,
            f"offline release attack case ID is unsafe:{case_id}",
        )
    for marker in (
        "concurrent.futures.ThreadPoolExecutor",
        "def normalized_case_registry",
        "def source_inventory",
        "def source_mutations",
        "offline-release-case-registry-is-unique",
        "offline-release-adversarial-suite-preserves-source-tree",
        '"source_mutations": mutations',
    ):
        require(marker in offline_attack_source, f"offline release adversarial guard missing:{marker}")

    stabilizer_path = root / "scripts/stabilize_engine_evolution_release.py"
    require(stabilizer_path.is_file(), "engine-evolution stabilizer missing")
    stabilizer_source = stabilizer_path.read_text(encoding="utf-8") if stabilizer_path.is_file() else ""
    for marker in (
        'PROFILE = "BOUNDED_GRAPH_FIRST_CANONICAL_WRITER_CONVERGENCE_V2"',
        "MAX_ATTEMPTS = 3",
        "def _repository_file_paths",
        "repository_inventory_before",
        "comparison_paths = locked_paths_before | locked_paths_after",
        "canonical evolution writer modified unauthorized locked source",
        "scripts/lock_release_graph.py",
        "scripts/build_offline_scenario_release.py",
        "scripts/check_offline_scenario_release.mjs",
        "scripts/check_engine_evolution_documentation.mjs",
    ):
        require(marker in stabilizer_source, f"engine-evolution stabilizer contract missing:{marker}")
    require(
        scripts.get("check:scenario-behavior-archive")
        == "node scripts/run_python.mjs scripts/check_scenario_behavior_archive.py --repo . --json-output reports/scenario-behavior-archive-check.json",
        "scenario behavior archive checker package command differs",
    )
    require(
        scripts.get("test:scenario-behavior-archive")
        == "node scripts/run_python.mjs scripts/test_scenario_behavior_archive.py --repo . --json-output reports/scenario-behavior-archive-mutations.json",
        "scenario behavior archive attack package command differs",
    )
    require(
        scripts.get("verify:scenario-experience")
        == "npm run assure:scenario-experience && npm run check:scenario-behavior-archive && npm run test:scenario-experience && npm run test:scenario-behavior-archive",
        "scenario experience verification command differs",
    )

    require(
        scripts.get("stabilize:engine-evolution-source")
        == "node scripts/run_python.mjs scripts/stabilize_engine_evolution_release.py --repo . --json-output reports/engine-evolution-stabilization.json",
        "engine-evolution stabilizer package command differs",
    )
    require(
        scripts.get("check:engine-evolution-stabilization")
        == "node scripts/run_python.mjs scripts/stabilize_engine_evolution_release.py --repo . --check --json-output reports/engine-evolution-stabilization.json",
        "engine-evolution stabilizer check command differs",
    )
    for set_id in ("scenario-source", "orchestration", "standalone-source", "release-policy-source"):
        require(
            "scripts/stabilize_engine_evolution_release.py" in graph.get("input_sets", {}).get(set_id, {}).get("files", {}),
            f"engine-evolution stabilizer is not locked:{set_id}",
        )

    scenario_runner_source = (root / "scripts/run_scenario_contract_gate.py").read_text(encoding="utf-8")
    required_scenario_scripts = integrations.get("scenario_contract_required_scripts", [])
    required_scenario_outputs = integrations.get("scenario_contract_required_outputs", [])
    for name in required_scenario_scripts:
        require(f'"{name}"' in scenario_runner_source, f"scenario canonical subgate missing:{name}")
        require(name in managed, f"scenario canonical subgate is unmanaged:{name}")
    for relative in required_scenario_outputs:
        require(f'"{relative}"' in scenario_runner_source, f"scenario canonical output missing:{relative}")
    for marker in (
        "DETACHED_GIT_WORKTREE_WITH_LOCKED_OVERLAY_V2",
        "first_invalid_step",
        "transient_retry_used",
        "committed scenario output differs:",
        "copy_outputs",
    ):
        require(marker in scenario_runner_source, f"scenario gate assurance missing:{marker}")
    require(
        '    "generate:verified-scenario-package":' in scenario_runner_source,
        "scenario contract gate omits the core package rehearsal",
    )
    for duplicate_stage_script in (
        "generate:verified-scenario",
        "check:verified-example",
        "test:verified-example",
        "check:scenario-genome",
        "test:scenario-genome",
        "check:scenario-behavior-archive",
        "test:scenario-behavior-archive",
        "check:scenario-capability-ratchet",
        "test:scenario-capability-ratchet",
        "join:scenario-evolution",
        "test:scenario-evolution-evidence",
    ):
        require(
            f'    "{duplicate_stage_script}":' not in scenario_runner_source,
            f"scenario evolution has duplicate runner authority:{duplicate_stage_script}",
        )
    legacy_scenario_runner_source = (root / "scripts/run_scenario_contracts_hermetic.py").read_text(encoding="utf-8")
    require("from run_scenario_contract_gate import main" in legacy_scenario_runner_source, "legacy scenario entry point does not delegate to the canonical gate")
    require("translated_argv" in legacy_scenario_runner_source, "legacy scenario entry point lacks argument compatibility")
    for marker in ("def locked_overlay_paths", "overlay_locked_inputs", "def npm_invocation", 'suffix.lower() == ".py"'):
        require(marker in scenario_runner_source, f"scenario locked-overlay portability marker missing:{marker}")

    require(graph.get("targets", {}).get("ci-example-python", {}).get("terminal_stages") == ["scenario.verified-example-python"], "example Python CI target differs")
    require(graph.get("targets", {}).get("ci-example-node", {}).get("terminal_stages") == ["scenario.verified-example-node"], "example Node CI target differs")
    require(graph.get("targets", {}).get("ci-example-integrated", {}).get("terminal_stages") == ["scenario.evolution-evidence-attacks"], "example integrated CI target differs")
    require("scenario.release-validation" in target_stage_ids(graph, "ci-scenario"), "scenario CI target omits release validation")
    package_rehearsal_plan = set(target_stage_ids(graph, "package-rehearsal"))
    for stage_id in scenario_stage_specs:
        require(stage_id in package_rehearsal_plan, f"package rehearsal omits scenario evolution stage:{stage_id}")

    genome_policy_source = (root / "config/scenario-genome/SCENARIO_GENOME_POLICY.json").read_text(encoding="utf-8")
    for marker in (
        '"clinical_authority": "NOT_GRANTED"',
        '"human_team_behavior": "STRUCTURAL_ONLY_NOT_CALIBRATED"',
        '"operational_calibration": "NOT_CALIBRATED"',
        '"patient_care_use": "PROHIBITED"',
        '"scoring_behavior": "inherited_unchanged"',
        '"treatment_effect"',
        '"real_world_frequency"',
    ):
        require(marker in genome_policy_source, f"scenario genome truth boundary missing:{marker}")

    ratchet_source = (root / "scripts/check_scenario_capability_ratchet.py").read_text(encoding="utf-8")
    for marker in (
        "COMPILED_RATCHET_ANCHOR",
        "COMPILED_FLOORS",
        "scenario capability regressed:",
        "scenario ratchet anchor differs from compiled monotonic anchor",
        '"operational_calibration": "NOT_CALIBRATED"',
        '"scoring_behavior": "inherited_unchanged"',
    ):
        require(marker in ratchet_source, f"scenario capability ratchet guard missing:{marker}")

    build_runner_source = (root / "scripts/run_release_build_reproducibility.py").read_text(encoding="utf-8")
    for marker in (
        "TWO_ISOLATED_REVIEWED_SOURCE_SNAPSHOTS_V2",
        "GIT_TRACKED_PLUS_RELEASE_LOCKED_INPUTS_V1",
        "MINIMAL_ALLOWLISTED_REPRODUCIBLE_ENVIRONMENT_V1",
        '"build:generate"',
        '"build:typecheck"',
        '"build:bundle"',
        "primary_failure",
        "execution_command",
        "KNOWN_TOKEN_PATTERNS_AND_SECRET_ENV_VALUES_V1",
        "NOT_RUN_BUILD_FAILED",
        "DEFAULT_STEP_TIMEOUT_SECONDS",
        "DEFAULT_PROVENANCE_TIMEOUT_SECONDS",
        "def terminate_process_tree",
        "COMMAND TIMEOUT after",
        'if not errors and (root / "dist").is_dir()',
    ):
        require(marker in build_runner_source, f"build reproducibility diagnostics missing:{marker}")

    platform_source = (root / "scripts/release_graph_core.py").read_text(encoding="utf-8")
    for marker in ("def native_executable", "def native_command", "npm.cmd", "cmd.exe", "subprocess.list2cmdline"):
        require(marker in platform_source, f"cross-platform command policy missing:{marker}")
    require(
        stages.get("standalone.contracts", {}).get("command") == ["npm", "run", "verify:facility-arrival-standalone"],
        "standalone stage bypasses the platform-aware graph runner",
    )

    graph_attack_source = (root / "scripts/test_release_graph.py").read_text(encoding="utf-8")
    try:
        graph_attack_tree = ast.parse(graph_attack_source)
        graph_attack_constants = _python_module_constants(graph_attack_source)
    except SyntaxError as exc:
        graph_attack_tree = None
        graph_attack_constants = {}
        errors.append(f"release-graph adversarial harness syntax invalid:{exc.msg}")
    require(
        graph_attack_constants.get("SUITE_SOURCE_ISOLATION")
        == "STABLE_HERMETIC_SUITE_SOURCE_SNAPSHOT_WITH_PER_CASE_COPIES_V2",
        "release-graph suite source snapshot contract missing",
    )
    require(
        graph_attack_constants.get("SOURCE_SNAPSHOT_ISOLATION")
        == "STABLE_HERMETIC_SUITE_SOURCE_SNAPSHOT_WITH_PER_CASE_COPIES_V2",
        "release-graph partition source snapshot contract missing",
    )
    require(
        graph_attack_constants.get("PARTITION_ISOLATION")
        == "CHECKPOINTED_INDEPENDENT_MUTATION_AND_HEAVY_PARTITIONS_V2",
        "release-graph checkpointed partition contract missing",
    )
    require(
        graph_attack_constants.get("HEAVY_CASE_SOURCE_GUARD")
        == "PER_CASE_LOCKED_SOURCE_INVENTORY_GUARD_V1",
        "release-graph heavyweight source guard contract missing",
    )
    require(
        graph_attack_constants.get("BASELINE_FAIL_FAST")
        == "CANONICAL_BASELINE_FAILS_BEFORE_ADVERSARIAL_SCHEDULING_V1",
        "release-graph canonical baseline fail-fast contract missing",
    )
    require(
        graph_attack_constants.get("MUTATION_CASE_ISOLATION")
        == "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V1",
        "release-graph mutation process isolation contract missing",
    )
    require(
        graph_attack_constants.get("MUTATION_WORKER_EXECUTION")
        == "SEALED_PER_CASE_MUTATION_SNAPSHOT_EXECUTABLE_V1",
        "release-graph mutation worker execution boundary differs",
    )
    require(
        graph_attack_constants.get("MUTATION_WORKER_RESULT_BINDING")
        == "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1",
        "release-graph mutation worker result binding differs",
    )
    require(
        graph_attack_constants.get("MUTATION_CHECKPOINT_PROFILE")
        == "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1",
        "release-graph mutation checkpoint profile differs",
    )
    require(
        graph_attack_constants.get("HEAVY_CHECKPOINT_PROFILE")
        == "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1",
        "release-graph heavyweight checkpoint profile differs",
    )
    require(
        graph_attack_constants.get("DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS") == 60,
        "release-graph mutation validator timeout differs",
    )
    require(
        graph_attack_constants.get("DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS") == 90,
        "release-graph mutation case timeout differs",
    )
    require(
        graph_attack_constants.get("HEAVY_RESOURCE_SCHEDULER")
        == "RESOURCE_CLASS_AWARE_EXCLUSIVE_FANOUT_V1",
        "release-graph heavyweight resource scheduler contract missing",
    )
    require(
        graph_attack_constants.get("HEAVY_WORKER_EXECUTION")
        == "SEALED_PER_CASE_SOURCE_SNAPSHOT_EXECUTABLE_V1",
        "release-graph heavyweight worker execution boundary differs",
    )
    require(
        graph_attack_constants.get("HEAVY_WORKER_RESULT_BINDING")
        == "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1",
        "release-graph heavyweight worker result binding differs",
    )
    require(
        graph_attack_constants.get("WORKSPACE_PATH_PROFILE")
        == "CONTENT_ADDRESSED_COMPACT_WORKSPACE_PATHS_V1",
        "release-graph portable workspace path profile differs",
    )
    require(
        isinstance(graph_attack_constants.get("WORKSPACE_COMPONENT_HASH_HEX"), int)
        and graph_attack_constants.get("WORKSPACE_COMPONENT_HASH_HEX") >= 16,
        "release-graph compact workspace hash floor differs",
    )
    require(
        graph_attack_constants.get("PORTABLE_WINDOWS_PATH_BUDGET") == 240,
        "release-graph Windows path budget differs",
    )
    require(
        graph_attack_constants.get("PORTABLE_TEMP_PREFIX") == "arg-",
        "release-graph compact temporary prefix differs",
    )
    require(
        graph_attack_constants.get("DEFAULT_HEAVY_CASE_WORKERS") == 1,
        "release-graph heavyweight default worker floor differs",
    )
    require(
        'FIXTURE_COPY_POLICY = "HERMETIC_METADATA_PRESERVING_COPY_V1"' in graph_attack_source,
        "release-graph mutation fixture copy policy missing",
    )
    require("os.link(" not in graph_attack_source, "release-graph mutation fixtures use unsafe hard links")
    require(
        '"reports", "__pycache__"' in graph_attack_source,
        "release-graph mutation fixture transient-output exclusion missing",
    )
    for marker in (
        'HEAVY_CASE_ISOLATION = "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V2"',
        'MUTATION_CASE_ISOLATION = "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V1"',
        'MUTATION_WORKER_EXECUTION = "SEALED_PER_CASE_MUTATION_SNAPSHOT_EXECUTABLE_V1"',
        'MUTATION_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"',
        'MUTATION_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"',
        'DEFAULT_MUTATION_CHECKPOINT_ROOT = Path(".asklepios/release-graph-mutation-checkpoints")',
        'HEAVY_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"',
        'DEFAULT_HEAVY_CHECKPOINT_ROOT = Path(".asklepios/release-graph-heavy-checkpoints")',
        "DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS = 60",
        "DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS = 90",
        'PARTITION_ISOLATION = "CHECKPOINTED_INDEPENDENT_MUTATION_AND_HEAVY_PARTITIONS_V2"',
        'HEAVY_RESOURCE_SCHEDULER = "RESOURCE_CLASS_AWARE_EXCLUSIVE_FANOUT_V1"',
        'HEAVY_WORKER_EXECUTION = "SEALED_PER_CASE_SOURCE_SNAPSHOT_EXECUTABLE_V1"',
        'HEAVY_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"',
        'WORKSPACE_PATH_PROFILE = "CONTENT_ADDRESSED_COMPACT_WORKSPACE_PATHS_V1"',
        "WORKSPACE_COMPONENT_HASH_HEX = 20",
        "PORTABLE_WINDOWS_PATH_BUDGET = 240",
        'PORTABLE_TEMP_PREFIX = "arg-"',
        "def _compact_workspace_component",
        "def _portable_workspace_path_probe",
        "portable-workspace-path-budget-is-enforced",
        'worker_root = root / _compact_workspace_component("m", case_id)',
        'worker_root = root / _compact_workspace_component("h", case_id)',
        'prefix=PORTABLE_TEMP_PREFIX',
        'mutation_root = root / "m"',
        'heavy_root = root / "h"',
        '"failed_case_details": [',
        "DEFAULT_HEAVY_CASE_WORKERS = 1",
        "EXCLUSIVE_HEAVY_CASES = frozenset({",
        "exclusive fan-out",
        "def acquire_stable_source_snapshot",
        "stable-source-snapshot-acquisition",
        "source-drift-attribution-distinguishes-external-edit-from-suite-mutation",
        "canonical-baseline-failure-stops-before-adversarial-scheduling",
        "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures",
        "per-case-source-mutation-guard-is-contained-and-attributed",
        "if not baseline_ok:",
        "source_mutation_attribution",
        "def _mutation_checkpoint_envelope",
        "def _load_mutation_checkpoint",
        "def _write_mutation_checkpoint",
        "def _safe_mutation_checkpoint_root",
        "def _mutation_checkpoint_context",
        "REUSE_MUTATION_CASE",
        "INVALIDATE_MUTATION_CHECKPOINT",
        "mutation-checkpoint-root",
        "no-mutation-checkpoint-reuse",
        "clear-mutation-checkpoints",
        "mutation-checkpoint-reuse-and-invalidation",
        "heavy-checkpoint-reuse-and-invalidation",
        '"tool_versions": collect_tool_versions(["python"])',
        "def _heavy_checkpoint_envelope",
        "def _load_heavy_checkpoint",
        "def _write_heavy_checkpoint",
        "def _safe_heavy_checkpoint_root",
        "def _heavy_checkpoint_context",
        "REUSE_HEAVY_CASE",
        "INVALIDATE_HEAVY_CHECKPOINT",
        "heavy-checkpoint-root",
        "no-heavy-checkpoint-reuse",
        "clear-heavy-checkpoints",
        "def run_mutation_case_isolated",
        "def _mutation_worker_command",
        'worker_script = candidate / "scripts/test_release_graph.py"',
        "mutation worker execution boundary differs",
        "mutation worker result-binding boundary differs",
        "mutation worker script hash differs",
        "mutation case timeout after",
        "mutation worker exited without a durable result",
        "def _validated_mutation_case_result",
        "mutation worker case ID differs",
        "START_MUTATION_CASE",
        "END_MUTATION_CASE",
        "def run_heavy_case_isolated",
        "def _heavy_worker_command",
        'worker_script = case_source / "scripts/test_release_graph.py"',
        "heavyweight worker execution boundary differs",
        "heavyweight worker result-binding boundary differs",
        "heavyweight worker script hash differs",
        "heavyweight-worker-executes-sealed-source-snapshot",
        "subprocess.Popen",
        "start_new_session",
        "taskkill",
        "os.killpg",
        "def _terminate_subprocess_tree",
        "heavyweight case timeout after",
        "worker exited without a durable result",
        "def _validated_heavy_case_result",
        "heavyweight worker case ID differs",
        "heavyweight-result-case-id-mismatch-is-rejected",
        "heavyweight-process-tree-timeout-is-bounded",
        "mutation-worker-process-tree-timeout-is-bounded",
        "release-graph-mutation-checkpoint-profile-weakened",
        "release-graph-heavy-checkpoint-profile-weakened",
        "release-graph-mutation-process-isolation-weakened",
        "release-graph-mutation-worker-execution-boundary-weakened",
        "release-graph-mutation-worker-result-binding-weakened",
        "release-graph-mutation-worker-live-script-regression",
        "release-graph-mutation-case-timeout-weakened",
        "release-graph-mutation-validator-timeout-weakened",
        "release-graph-heavy-default-worker-floor-widened",
        "release-graph-heavy-worker-execution-boundary-weakened",
        "release-graph-heavy-worker-result-binding-weakened",
        "release-graph-heavy-worker-live-script-regression",
        "release-graph-workspace-path-profile-weakened",
        "release-graph-mutation-workspace-full-case-id-regression",
        "release-graph-heavy-workspace-full-case-id-regression",
        "release-graph-failed-case-diagnostics-removed",
        'mini / "tool-bin/npm.cmd"',
        'mini / "tool-bin/fake_npm.py"',
        "unregistered-pull-request-workflow-rejected",
        "scenario-behavior-archive-output-removed",
        "scenario-behavior-archive-check-stage-removed",
        "scenario-behavior-archive-attacks-detached",
        "scenario-behavior-archive-checker-lock-removed",
        "scenario-capability-ratchet-stage-removed",
        "scenario-evolution-evidence-bypassed",
        "scenario-evolution-receipt-attacks-removed",
        "scenario-genome-artifact-contract-removed",
        "scenario-evolution-duplicate-runner-rejected",
        "example-workflow-target-drift",
        "--skip-mutations",
        "--skip-heavy",
        "release-graph-partition-checkpoint-boundary-removed",
        "release-graph-mutation-partition-stage-removed",
        "release-graph-heavy-partition-stage-removed",
        "release-graph-partition-join-bypassed",
        "release-graph-partition-join-attacks-output-removed",
        "python-cache-ignore-boundary-removed",
        "release-receipt-ignore-boundary-removed",
        "mutation-checkpoint-ignore-boundary-removed",
        "heavy-checkpoint-ignore-boundary-removed",
        "artifact-authority-coverage-removed",
        "artifact-authority-broad-directory-output",
        "artifact-authority-unclaimed-output",
        "artifact-authority-second-writer",
        "generated-binding-authority-contract-removed",
    ):
        require(marker in graph_attack_source, f"release-graph heavyweight fault containment missing:{marker}")
    mutation_worker_command_source = ""
    mutation_worker_command_function = None
    if graph_attack_tree is not None:
        mutation_worker_command_function = next(
            (
                node for node in graph_attack_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_mutation_worker_command"
            ),
            None,
        )
        if mutation_worker_command_function is not None:
            mutation_worker_command_source = ast.get_source_segment(graph_attack_source, mutation_worker_command_function) or ""
    require(bool(mutation_worker_command_source), "release-graph mutation worker command function missing")
    mutation_worker_assignment_is_sealed = False
    if mutation_worker_command_function is not None:
        for node in ast.walk(mutation_worker_command_function):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
            if not isinstance(target, ast.Name) or target.id != "worker_script":
                continue
            mutation_worker_assignment_is_sealed = (
                isinstance(value, ast.BinOp)
                and isinstance(value.op, ast.Div)
                and isinstance(value.left, ast.Name)
                and value.left.id == "candidate"
                and isinstance(value.right, ast.Constant)
                and value.right.value == "scripts/test_release_graph.py"
            )
            break
    require(
        mutation_worker_assignment_is_sealed,
        "release-graph mutation worker is not bound to the sealed candidate snapshot",
    )
    require(
        mutation_worker_command_function is not None
        and not any(
            isinstance(node, ast.Name) and node.id == "__file__"
            for node in ast.walk(mutation_worker_command_function)
        ),
        "release-graph mutation worker executes the live working-tree script",
    )
    require(
        "str(worker_script.resolve(strict=True))" in mutation_worker_command_source,
        "release-graph mutation worker executable resolution differs",
    )

    heavy_worker_command_source = ""
    heavy_worker_command_function = None
    if graph_attack_tree is not None:
        heavy_worker_command_function = next(
            (
                node for node in graph_attack_tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_heavy_worker_command"
            ),
            None,
        )
        if heavy_worker_command_function is not None:
            heavy_worker_command_source = ast.get_source_segment(graph_attack_source, heavy_worker_command_function) or ""
    require(bool(heavy_worker_command_source), "release-graph heavyweight worker command function missing")
    worker_assignment_is_sealed = False
    if heavy_worker_command_function is not None:
        for node in ast.walk(heavy_worker_command_function):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
            if not isinstance(target, ast.Name) or target.id != "worker_script":
                continue
            worker_assignment_is_sealed = (
                isinstance(value, ast.BinOp)
                and isinstance(value.op, ast.Div)
                and isinstance(value.left, ast.Name)
                and value.left.id == "case_source"
                and isinstance(value.right, ast.Constant)
                and value.right.value == "scripts/test_release_graph.py"
            )
            break
    require(
        worker_assignment_is_sealed,
        "release-graph heavyweight worker is not bound to the sealed case snapshot",
    )
    require(
        heavy_worker_command_function is not None
        and not any(
            isinstance(node, ast.Name) and node.id == "__file__"
            for node in ast.walk(heavy_worker_command_function)
        ),
        "release-graph heavyweight worker executes the live working-tree script",
    )
    require(
        "str(worker_script.resolve(strict=True))" in heavy_worker_command_source,
        "release-graph heavyweight worker executable resolution differs",
    )

    def _function_source(name: str) -> str:
        if graph_attack_tree is None:
            return ""
        node = next(
            (
                item for item in graph_attack_tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == name
            ),
            None,
        )
        return ast.get_source_segment(graph_attack_source, node) if node is not None else ""

    mutation_isolated_source = _function_source("run_mutation_case_isolated") or ""
    heavy_isolated_source = _function_source("run_heavy_case_isolated") or ""
    emit_suite_source = _function_source("emit_suite_report") or ""
    require(
        'worker_root = root / _compact_workspace_component("m", case_id)'
        in mutation_isolated_source,
        "release-graph mutation workspace uses unbounded case IDs",
    )
    require(
        'worker_root = root / _compact_workspace_component("h", case_id)'
        in heavy_isolated_source,
        "release-graph heavyweight workspace uses unbounded case IDs",
    )
    require(
        'result["worker_log_tail"] = _bounded_worker_log_tail(worker_log)'
        in mutation_isolated_source
        and 'result["worker_log_tail"] = _bounded_worker_log_tail(worker_log)'
        in heavy_isolated_source,
        "release-graph worker failure diagnostics are not retained",
    )
    require(
        '"failed_case_details": [' in emit_suite_source,
        "release-graph visible failed-case diagnostics are missing",
    )

    mutation_partition_stage = stages.get("orchestration.graph-attacks-mutations", {})
    heavy_partition_stage = stages.get("orchestration.graph-attacks-heavy", {})
    graph_attack_join_stage = stages.get("orchestration.graph-attacks", {})
    expected_graph_attack_input_sets = ["orchestration", "release-policy-source", "hub-source"]
    require(
        mutation_partition_stage.get("command") == ["npm", "run", "test:release-graph-mutations"],
        "release graph mutation partition command differs",
    )
    require(
        mutation_partition_stage.get("needs") == ["orchestration.graph-check"],
        "release graph mutation partition is detached",
    )
    require(
        mutation_partition_stage.get("input_sets") == expected_graph_attack_input_sets,
        "release graph mutation partition input sets differ",
    )
    require(mutation_partition_stage.get("read_only") is True, "release graph mutation partition is not read-only")
    require(
        set(_output_paths(mutation_partition_stage)) == {
            "reports/release-graph-mutation-partition.json",
            "reports/release-source-closure-mutations.json",
        },
        "release graph mutation partition output inventory differs",
    )
    require(
        heavy_partition_stage.get("command") == ["npm", "run", "test:release-graph-heavy"],
        "release graph heavyweight partition command differs",
    )
    require(
        heavy_partition_stage.get("needs") == ["orchestration.graph-check"],
        "release graph heavyweight partition is detached",
    )
    require(
        heavy_partition_stage.get("input_sets") == expected_graph_attack_input_sets,
        "release graph heavyweight partition input sets differ",
    )
    require(heavy_partition_stage.get("read_only") is True, "release graph heavyweight partition is not read-only")
    require(
        set(_output_paths(heavy_partition_stage)) == {"reports/release-graph-heavy-partition.json"},
        "release graph heavyweight partition output inventory differs",
    )
    require(
        graph_attack_join_stage.get("command") == ["npm", "run", "join:release-graph-attacks"],
        "release graph attack join command differs",
    )
    require(
        graph_attack_join_stage.get("needs") == [
            "orchestration.graph-attacks-mutations",
            "orchestration.graph-attacks-heavy",
        ],
        "release graph attack join does not authenticate both partitions",
    )
    require(
        graph_attack_join_stage.get("input_sets") == expected_graph_attack_input_sets,
        "release graph attack join input sets differ",
    )
    require(graph_attack_join_stage.get("read_only") is True, "release graph attack join is not read-only")
    require(
        set(_output_paths(graph_attack_join_stage)) == {
            "reports/release-graph-partition-join-mutations.json",
            "reports/release-graph-mutations.json",
        },
        "release graph attack join output inventory differs",
    )

    graph_attack_join_source = (root / "scripts/join_release_graph_attack_partitions.py").read_text(encoding="utf-8")
    for marker in (
        "AUTHENTICATED_RELEASE_GRAPH_ATTACK_PARTITION_JOIN_V2",
        "MUTATIONS_ONLY",
        "HEAVY_ONLY",
        "partition repository inventory roots differ",
        "partition common-case evidence differs",
        "source-closure attack was accepted",
        "case inventory hash differs",
        "mutation process isolation differs",
        "mutation worker execution boundary differs",
        "mutation worker result binding differs",
        "mutation validator timeout differs",
        "mutation case timeout differs",
        "mutation worker script hash differs",
        "mutation worker executable differs",
        "mutation checkpoint profile differs",
        "mutation checkpoint digest is malformed",
        "mutation checkpoint path is malformed",
        "mutation checkpoint reuse is disabled",
        "heavyweight checkpoint profile differs",
        "heavyweight checkpoint digest is malformed",
        "heavyweight checkpoint path is malformed",
        "heavyweight checkpoint reuse is disabled",
        "heavyweight scheduler differs",
        "heavyweight worker execution boundary differs",
        "heavyweight worker result binding differs",
        "heavy worker script hash differs",
        "heavy worker executable differs",
        "exclusive heavyweight inventory differs",
        "heavyweight worker floor differs",
        "heavyweight timeout differs",
    ):
        require(marker in graph_attack_join_source, f"release graph partition join guard missing:{marker}")
    graph_attack_join_test_source = (root / "scripts/test_release_graph_attack_partition_join.py").read_text(encoding="utf-8")
    for marker in (
        "baseline_partition_join",
        "mutation_case_removed_and_rehashed",
        "common_case_evidence_disagrees",
        "accepted_mutation_attack_rejected",
        "partition_source_drift_rejected",
        "source_closure_accepted_attack_rejected",
        "mutation_checkpoint_profile_weakened",
        "mutation_checkpoint_reuse_disabled",
        "mutation_checkpoint_digest_forged",
        "mutation_checkpoint_path_forged",
        "heavy_checkpoint_profile_weakened",
        "heavy_checkpoint_reuse_disabled",
        "heavy_checkpoint_digest_forged",
        "heavy_checkpoint_path_forged",
        "mutation_isolation_weakened",
        "mutation_worker_execution_weakened",
        "mutation_worker_result_binding_weakened",
        "mutation_timeout_weakened",
        "mutation_worker_script_hash_forged",
        "mutation_worker_executable_forged",
        "heavy_scheduler_weakened",
        "heavy_worker_floor_widened",
        "exclusive_heavy_inventory_reduced",
        "heavy_worker_execution_weakened",
        "heavy_worker_result_binding_weakened",
        "heavy_worker_script_hash_forged",
        "heavy_worker_executable_forged",
        "symlinked_partition_report_rejected",
    ):
        require(marker in graph_attack_join_test_source, f"release graph partition join attack missing:{marker}")

    gitignore_source = (root / ".gitignore").read_text(encoding="utf-8")
    for marker in (
        "__pycache__/",
        "*.py[cod]",
        "*.tsbuildinfo",
        ".asklepios/release-receipts/",
        ".asklepios/release-stage-logs/",
        ".asklepios/release-graph-mutation-checkpoints/",
        ".asklepios/release-graph-heavy-checkpoints/",
        ".asklepios/build-reproducibility/",
        ".asklepios/scenario-contracts/",
    ):
        require(marker in gitignore_source.splitlines(), f"transient release artifact ignore boundary missing:{marker}")

    scenario_evidence_join_source = (root / "scripts/join_scenario_evolution_evidence.py").read_text(encoding="utf-8")
    for marker in (
        "GRAPH_RECEIPTS_REQUIRED",
        "receipt_valid",
        "output_root_sha256",
        "stage_config_sha256",
        "current_inventory",
    ):
        require(marker in scenario_evidence_join_source, f"scenario evolution receipt binding missing:{marker}")

    scenario_evidence_attack_source = (root / "scripts/test_scenario_evolution_evidence.py").read_text(encoding="utf-8")
    for marker in (
        "missing_genome_receipt_rejected",
        "forged_receipt_digest_rejected",
        "stale_genome_report_rejected",
        "wrong_graph_identity_rejected",
        "failed_receipt_rejected_even_when_rehashed",
        "stage_configuration_forgery_rejected",
    ):
        require(marker in scenario_evidence_attack_source, f"scenario evolution receipt attack missing:{marker}")

    scenario_genome_writer_source = (root / "scripts/build_scenario_genome.py").read_text(encoding="utf-8")
    scenario_genome_checker_source = (root / "scripts/check_scenario_genome.mjs").read_text(encoding="utf-8")
    scenario_genome_attack_source = (root / "scripts/test_scenario_genome.py").read_text(encoding="utf-8")
    for marker in (
        "REACHABLE_TERMINATING_DAG_V1",
        "scenario genome route has unreachable nodes:",
        "scenario genome route has nonterminal dead end:",
        "scenario genome route contains cycle",
    ):
        require(marker in scenario_genome_writer_source, f"scenario genome route topology writer guard missing:{marker}")
    for marker in (
        "REACHABLE_TERMINATING_DAG_V1",
        "scenario genome route has unreachable nodes:",
        "scenario genome route has nonterminal dead end:",
        "scenario genome route contains cycle",
    ):
        require(marker in scenario_genome_checker_source, f"scenario genome route topology checker guard missing:{marker}")
    for marker in (
        "unreachable_route_node_rejected",
        "nonterminal_route_dead_end_rejected",
        "cyclic_route_rejected",
        "windows_style_path_escape_rejected",
    ):
        require(marker in scenario_genome_attack_source, f"scenario genome route/path attack missing:{marker}")

    runner_source = (root / "scripts/run_release_graph.py").read_text(encoding="utf-8")
    for marker in (
        "execute_with_diagnostics",
        "combined_log_sha256",
        "stage command exited:",
        "KNOWN_GITHUB_TOKEN_PATTERNS_V1",
        "--collect-independent-failures",
        "blocked by failed predecessor:",
        "safe_to_continue",
        "--summary-output",
    ):
        require(marker in runner_source, f"release-stage diagnostics missing:{marker}")

    source_attest = stages.get("arrival.source-attestations", {})
    require(source_attest.get("command") == ["npm", "run", "check:facility-arrival-source-attestations"], "runtime source-attestation stage differs")
    require("reports/facility-arrival-example-check.json" in _output_paths(source_attest), "complete example attestation output missing")
    require(stages.get("arrival.source-attestations", {}).get("needs") == ["arrival.artifact-boundary"], "runtime source attestations are not ordered after artifact boundary")
    require(stages.get("arrival.runtime-tests", {}).get("needs") == ["arrival.source-attestations"], "runtime tests bypass source attestations")
    require(stages.get("arrival.static-attacks", {}).get("needs") == ["arrival.static-validator"], "Facility Arrival static attacks bypass validator")
    require(stages.get("decision.static-attacks", {}).get("needs") == ["decision.static-validator"], "decision static attacks bypass validator")
    require(stages.get("release.debt-evidence", {}).get("needs") == ["final.decision-evidence"], "final technical-debt evidence is detached or too early")
    require(stages.get("final.graph-evidence", {}).get("needs") == ["release.debt-evidence"], "final graph evidence bypasses final technical-debt evidence")
    require(stages.get("release.production-simulation-designation", {}).get("needs") == ["final.graph-evidence"], "production simulation designation bypasses final graph evidence")
    final_arrival_needs = set(stages.get("final.arrival-evidence", {}).get("needs", []))
    for required in (
        "release.runtime-evidence-join",
        "content.registry-source",
        "standalone.contracts",
        "scenario.release-validation",
        "formal.exact-audit",
        "build.double-reproducibility",
        "hub.runtime-smoke",
        "simulation.timing-assurance",
    ):
        require(required in final_arrival_needs, f"final arrival evidence omits direct predecessor:{required}")

    required_policy_chain = [
        ("release.intended-use-policy", ["orchestration.graph-attacks"]),
        ("release.intended-use-attacks", ["release.intended-use-policy"]),
        ("release.simulation-quality", ["release.intended-use-attacks"]),
        ("release.simulation-quality-attacks", ["release.simulation-quality"]),
        ("simulation.timing-policy", ["release.simulation-quality-attacks"]),
        ("simulation.timing-attacks", ["simulation.timing-policy"]),
        ("hub.security-source", ["simulation.timing-attacks"]),
        ("hub.security-attacks", ["hub.security-source"]),
        ("release.debt-ratchet", ["hub.security-attacks"]),
        ("release.debt-ratchet-attacks", ["release.debt-ratchet"]),
        ("release.debt-policy", ["release.debt-ratchet-attacks"]),
        ("release.debt-attacks", ["release.debt-policy"]),
        ("release.production-policy-attacks", ["release.debt-attacks"]),
    ]
    for stage_id, expected_needs in required_policy_chain:
        require(stage_id in stages, f"simulation production policy stage missing:{stage_id}")
        require(stages.get(stage_id, {}).get("needs") == expected_needs, f"simulation production policy order differs:{stage_id}")

    require(stages.get("hub.runtime-smoke", {}).get("needs") == ["build.app-typecheck", "hub.security-attacks"], "hub runtime smoke bypasses typecheck or source security")
    require(stages.get("simulation.timing-runtime", {}).get("needs") == ["decision.artifact-attacks"], "simulation timing runtime bypasses decision runtime assurance")
    require(stages.get("simulation.timing-assurance", {}).get("needs") == ["simulation.timing-runtime"], "simulation timing assurance bypasses runtime evidence")
    require(stages.get("release.debt-evidence", {}).get("command") == ["npm", "run", "check:release-debt-evidence"], "final technical-debt evidence command differs")
    require(stages.get("release.production-simulation-designation", {}).get("command") == ["npm", "run", "evaluate:production-simulation"], "production simulation designation command differs")

    for target in ("package-rehearsal", "publisher-full", "ci-integrated"):
        ids = target_stage_ids(graph, target)
        require(graph.get("targets", {}).get(target, {}).get("terminal_stages") == ["release.production-simulation-designation"], f"full release target does not terminate at scoped production designation:{target}")
        for stage_id in integrations.get("critical_package_rehearsal_stages", []):
            require(stage_id in ids, f"critical CI gate omitted:{target}:{stage_id}")
        for stage_id in integrations.get("dual_static_stages", []):
            require(stage_id in ids, f"dual static boundary omitted:{target}:{stage_id}")
        require(integrations.get("final_evidence_join_stage") in ids, f"final evidence join omitted:{target}")

    for group in integrations.get("exact_plan_equivalence", []):
        signatures: dict[str, str] = {}
        for target in group:
            try:
                signatures[target] = _plan_signature(root, graph, target)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"release target plan unavailable:{target}:{type(exc).__name__}:{exc}")
        if signatures:
            first = next(iter(signatures.values()))
            for target, signature in signatures.items():
                require(signature == first, f"release command plan differs:{target}")

    expected_wrappers = {
        "verify:facility-arrival": "npm run release:graph -- --target facility-arrival-runtime",
        "verify:facility-arrival-runtime": "npm run release:graph -- --target facility-arrival-runtime",
        "verify:facility-decision": "npm run release:graph -- --target canonical-runtime",
        "verify:facility-decision-source": "npm run release:graph -- --target facility-decision-source",
        "verify:facility-decision-runtime": "npm run release:graph -- --target facility-decision-runtime",
        "finalize:facility-arrival-release": "npm run release:graph -- --target facility-arrival-final",
        "finalize:facility-decision-release": "npm run release:graph -- --target publisher-full",
        "rehearse:release-package": "npm run release:graph -- --target package-rehearsal --no-reuse --collect-independent-failures --summary-output reports/package-rehearsal-summary.json",
    }
    for name, value in expected_wrappers.items():
        require(scripts.get(name) == value, f"package script differs:{name}")

    workflow_config = integrations.get("workflows", {})
    require(isinstance(workflow_config, dict) and bool(workflow_config), "workflow integration inventory missing")
    configured_workflows = set(workflow_config) if isinstance(workflow_config, dict) else set()
    pull_request_workflows = {
        path.relative_to(root).as_posix()
        for path in _workflow_paths(root)
        if _workflow_has_pull_request_trigger(path.read_text(encoding="utf-8"))
    }
    require(
        pull_request_workflows == configured_workflows,
        "pull-request workflow inventory differs:configured="
        + ",".join(sorted(configured_workflows))
        + ":observed="
        + ",".join(sorted(pull_request_workflows)),
    )
    observed_workflow_jobs: dict[str, list[str]] = {}
    for relative, specification in sorted(workflow_config.items() if isinstance(workflow_config, dict) else []):
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"workflow missing:{relative}")
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        require(_workflow_has_pull_request_trigger(text), f"configured workflow lacks pull-request trigger:{relative}")
        jobs = _job_blocks(text)
        observed_workflow_jobs[relative] = sorted(jobs)
        expected_jobs = specification.get("jobs", {})
        require(set(jobs) == set(expected_jobs), f"workflow job inventory differs:{relative}")
        require(text.count("actions/checkout@") >= int(specification.get("minimum_checkouts", 0)), f"workflow checkout count reduced:{relative}")
        for uses in USES_LINE.findall(text):
            if uses.startswith("./"):
                continue
            require(bool(PINNED_ACTION.fullmatch(uses)), f"GitHub action is not pinned to a full SHA:{uses}")
        for job_id, target in expected_jobs.items():
            block = jobs.get(job_id, "")
            command = f"python scripts/run_release_graph.py --repo . --target {target} --no-reuse"
            require(command in block, f"workflow graph target differs:{relative}:{job_id}")
            require(block.count("scripts/run_release_graph.py") == 1, f"workflow duplicates release execution:{relative}:{job_id}")
            require("persist-credentials: false" in block, f"checkout credentials are persisted:{relative}:{job_id}")
            require("node-version: 22.22.0" in block, f"workflow Node version is not exact:{relative}:{job_id}")
            require("python-version: '3.12'" in block, f"workflow Python version is not exact:{relative}:{job_id}")
            if "runs-on: windows-latest" in block:
                require("shell: bash" not in block, f"Windows workflow forces a non-native Bash shell:{relative}:{job_id}")
            run_commands = [item for item in RUN_LINE.findall(block) if item and not item.startswith("|") and not item.startswith(">")]
            # One release command is permitted; environment setup belongs in actions/with fields.
            direct_gates = [item for item in run_commands if "run_release_graph.py" not in item]
            require(not direct_gates, f"workflow duplicates direct gate:{relative}:{job_id}:{direct_gates}")

    for workflow_path in _workflow_paths(root):
        workflow_text = workflow_path.read_text(encoding="utf-8")
        for uses in USES_LINE.findall(workflow_text):
            if uses.startswith("./"):
                continue
            require(
                bool(PINNED_ACTION.fullmatch(uses)),
                f"GitHub action is not pinned to a full SHA:{workflow_path.relative_to(root).as_posix()}:{uses}",
            )

    artifact_contracts = integrations.get("artifact_authority_contracts", {})
    require(isinstance(artifact_contracts, dict) and bool(artifact_contracts), "artifact authority contract inventory missing")
    required_artifact_contracts = {
        "facility-arrival-example-artifacts",
        "verified-scenario-example-artifacts",
        "verified-scenario-genome-artifact",
        "verified-scenario-package-artifacts",
        "facility-arrival-generated-specification",
        "facility-arrival-generated-bindings",
        "research-sandbox-generated-scenario",
    }
    require(
        required_artifact_contracts.issubset(set(artifact_contracts) if isinstance(artifact_contracts, dict) else set()),
        "required artifact authority contract missing",
    )
    claimed_artifacts: dict[str, str] = {}
    for contract_id, contract in sorted(artifact_contracts.items() if isinstance(artifact_contracts, dict) else []):
        require(isinstance(contract, dict), f"artifact authority contract invalid:{contract_id}")
        if not isinstance(contract, dict):
            continue
        require(
            contract.get("authority_model") == "SINGLE_CANONICAL_WRITER_INDEPENDENT_DIFFERENTIAL_CHECKER_V1",
            f"artifact authority model differs:{contract_id}",
        )
        writer = contract.get("canonical_writer") if isinstance(contract.get("canonical_writer"), dict) else {}
        writer_stage_id = str(writer.get("stage", ""))
        writer_script = str(writer.get("package_script", ""))
        writer_implementation = str(writer.get("implementation", ""))
        require(writer_stage_id in stages, f"artifact canonical writer stage missing:{contract_id}:{writer_stage_id}")
        writer_stage = stages.get(writer_stage_id, {})
        require(writer_stage.get("read_only") is False, f"artifact canonical writer stage is read-only:{contract_id}")
        require(writer_stage.get("command") == ["npm", "run", writer_script], f"artifact canonical writer command differs:{contract_id}")
        require(writer_script in managed, f"artifact canonical writer package script unmanaged:{contract_id}:{writer_script}")
        writer_inputs = {path for set_id in writer_stage.get("input_sets", []) for path in graph.get("input_sets", {}).get(set_id, {}).get("files", {})}
        require(writer_implementation in writer_inputs, f"artifact canonical writer implementation unlocked:{contract_id}:{writer_implementation}")
        artifacts = contract.get("artifacts") if isinstance(contract.get("artifacts"), list) else []
        require(bool(artifacts), f"artifact authority contract has no artifacts:{contract_id}")
        require(len(artifacts) == len(set(artifacts)), f"artifact authority contract duplicates artifacts:{contract_id}")
        for artifact in artifacts:
            require(isinstance(artifact, str) and artifact and not artifact.startswith("/") and ".." not in Path(artifact).parts, f"unsafe governed artifact path:{contract_id}:{artifact}")
            if not isinstance(artifact, str):
                continue
            require(_output_covers(writer_stage, artifact), f"canonical writer output boundary omits artifact:{contract_id}:{artifact}")
            prior = claimed_artifacts.setdefault(artifact, contract_id)
            require(prior == contract_id, f"generated artifact has multiple authority contracts:{artifact}:{prior}:{contract_id}")
        checkers = contract.get("independent_checkers") if isinstance(contract.get("independent_checkers"), list) else []
        require(bool(checkers), f"artifact authority contract lacks independent checker:{contract_id}")
        checker_implementations: set[str] = set()
        for index, checker in enumerate(checkers):
            require(isinstance(checker, dict), f"artifact checker descriptor invalid:{contract_id}:{index}")
            if not isinstance(checker, dict):
                continue
            checker_stage_id = str(checker.get("stage", ""))
            checker_script = str(checker.get("package_script", ""))
            checker_implementation = str(checker.get("implementation", ""))
            require(checker.get("mode") in {"READ_ONLY_BYTE_PARITY", "READ_ONLY_SEMANTIC_RECONSTRUCTION"}, f"artifact checker mode differs:{contract_id}:{index}")
            require(checker_stage_id in stages, f"artifact checker stage missing:{contract_id}:{checker_stage_id}")
            checker_stage = stages.get(checker_stage_id, {})
            require(checker_stage.get("read_only") is True, f"artifact checker stage can write locked sources:{contract_id}:{checker_stage_id}")
            require(_stage_depends_on(stages, checker_stage_id, writer_stage_id), f"artifact checker does not depend on canonical writer:{contract_id}:{checker_stage_id}")
            require(checker_script in managed, f"artifact checker package script unmanaged:{contract_id}:{checker_script}")
            stage_command_text = managed.get(checker_stage.get("command", [None, None, None])[-1], "") if checker_stage.get("command", [])[:2] == ["npm", "run"] else ""
            require(
                checker_script in str(stage_command_text) or checker_stage.get("command") == ["npm", "run", checker_script],
                f"artifact checker is not consumed by declared stage:{contract_id}:{checker_script}",
            )
            checker_inputs = {path for set_id in checker_stage.get("input_sets", []) for path in graph.get("input_sets", {}).get(set_id, {}).get("files", {})}
            require(checker_implementation in checker_inputs, f"artifact checker implementation unlocked:{contract_id}:{checker_implementation}")
            require(checker_implementation != writer_implementation, f"artifact checker is not implementation-independent:{contract_id}:{checker_implementation}")
            require(checker_implementation not in checker_implementations, f"artifact checker implementation duplicated:{contract_id}:{checker_implementation}")
            checker_implementations.add(checker_implementation)

    coverage = integrations.get("artifact_authority_coverage", {})
    require(isinstance(coverage, dict), "artifact authority coverage contract missing")
    require(
        isinstance(coverage, dict)
        and coverage.get("profile") == "EXACT_COMMITTED_GENERATED_OUTPUT_OWNERSHIP_V1",
        "artifact authority coverage profile differs",
    )
    require(coverage.get("directory_outputs_forbidden") is True, "artifact authority permits broad directory outputs")
    require(coverage.get("unclaimed_outputs_permitted") is False, "artifact authority permits unclaimed generated outputs")
    governed_prefixes = coverage.get("governed_prefixes") if isinstance(coverage.get("governed_prefixes"), list) else []
    excluded_prefixes = coverage.get("excluded_prefixes") if isinstance(coverage.get("excluded_prefixes"), list) else []
    require(
        governed_prefixes == ["README.md", "config/", "docs/", "examples/", "public/data/", "src/"],
        "artifact authority governed prefix inventory differs",
    )
    require(
        excluded_prefixes == ["reports/", ".asklepios/", "dist", "node_modules/"],
        "artifact authority excluded prefix inventory differs",
    )

    def _matches_prefix(relative: str, prefix: str) -> bool:
        return relative == prefix or (prefix.endswith("/") and relative.startswith(prefix))

    governed_writers: dict[str, list[str]] = {}
    for stage_id, stage in sorted(stages.items()):
        for output in _output_paths(stage):
            if any(_matches_prefix(output, prefix) for prefix in excluded_prefixes):
                continue
            if not any(_matches_prefix(output, prefix) for prefix in governed_prefixes):
                continue
            output_path = root / output
            require(
                not output.endswith("/") and not output_path.is_dir(),
                f"governed generated output uses a broad directory boundary:{stage_id}:{output}",
            )
            require(stage.get("read_only") is False, f"read-only stage declares governed generated output:{stage_id}:{output}")
            require(output in claimed_artifacts, f"governed generated output lacks artifact authority:{stage_id}:{output}")
            governed_writers.setdefault(output, []).append(stage_id)

    for artifact, contract_id in sorted(claimed_artifacts.items()):
        contract = artifact_contracts.get(contract_id, {}) if isinstance(artifact_contracts, dict) else {}
        writer = contract.get("canonical_writer") if isinstance(contract, dict) and isinstance(contract.get("canonical_writer"), dict) else {}
        writer_stage_id = str(writer.get("stage", ""))
        if any(_matches_prefix(artifact, prefix) for prefix in governed_prefixes):
            require(
                governed_writers.get(artifact) == [writer_stage_id],
                f"governed artifact writer ownership differs:{artifact}:{governed_writers.get(artifact, [])}:{writer_stage_id}",
            )

    contract_files = integrations.get("classification_contract_files", [])
    for relative in contract_files:
        path = root / relative
        require(path.is_file(), f"classification contract file missing:{relative}")
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            require("classification" in text or "release_result" in text, f"classification vocabulary missing:{relative}")
            require("EXPECTED_REJECTION" in text or "release_result" in text, f"expected-rejection vocabulary missing:{relative}")
            require("INTERNAL_ERROR" in text or "release_result" in text, f"internal-error vocabulary missing:{relative}")

    static_checker = (root / "scripts/check_facility_arrival_release_static.py").read_text(encoding="utf-8")
    for marker in [
        "calibration record missing:second_casualty_inbound",
        "calibration status changed:second_casualty_inbound",
        "event times disagree:second_casualty_inbound",
        "exercise-assumption note missing:second_casualty_inbound",
        "facility clock event trigger kind changed:second_casualty_inbound",
        "canonical release graph consistency failed",
    ]:
        require(marker in static_checker, f"cross-layer static diagnostic missing:{marker}")

    required_orchestration = {
        "scripts/check_facility_decision_axioms.py",
        "scripts/release_graph_core.py",
        "scripts/release_source_closure.py",
        "scripts/release_result.py",
        "scripts/check_release_graph.py",
        "scripts/lock_release_graph.py",
        "scripts/run_python.mjs",
        "scripts/run_release_graph.py",
        "scripts/run_scenario_contract_gate.py",
        "scripts/test_release_graph.py",
        "scripts/join_release_graph_evidence.py",
        "scripts/run_release_formal_gate.py",
        "scripts/run_release_build_reproducibility.py",
        "scripts/test_release_build_reproducibility.py",
        "scripts/test_release_platform_identity.py",
    }
    orchestration_files = set(graph["input_sets"]["orchestration"].get("files", {}))
    for relative in sorted(required_orchestration):
        require(relative in orchestration_files, f"orchestration file is not content-locked:{relative}")

    # RC3.8A.1 replaced the raw release-graph file hash with an acyclic
    # semantic projection that excludes per-input-set file digests while
    # preserving graph structure, commands, policies, paths, and truth
    # boundaries. The generated descriptor may therefore be content-locked in
    # exactly one source set without creating a graph/descriptor hash cycle.
    offline_descriptor = "public/data/scenario_core/offline_scenario_release.json"
    descriptor_input_sets = []
    for input_set_name, input_set in sorted(graph.get("input_sets", {}).items()):
        locked_paths = set(input_set.get("files", {})) | set(input_set.get("include", []))
        if offline_descriptor in locked_paths:
            descriptor_input_sets.append(input_set_name)
    require(
        descriptor_input_sets == ["standalone-source"],
        "offline descriptor must be locked exactly once by standalone-source",
    )

    standalone_files = set(graph["input_sets"].get("standalone-source", {}).get("files", {}))
    for relative in (
        "scripts/run_facility_arrival_standalone_gate.py",
        "scripts/build_facility_arrival_standalone.py",
        "scripts/check_facility_arrival_standalone.py",
        "scripts/test_facility_arrival_standalone_runtime.mjs",
        "examples/facility-arrival/playable.html",
    ):
        require(relative in standalone_files, f"standalone transitive dependency is not locked:{relative}")

    content_files = set(graph["input_sets"].get("content-registry-source", {}).get("files", {}))
    for relative in (
        "scripts/run_content_registry_runtime_gate.py",
        "scripts/audit_content_registry.py",
        "scripts/check_content_registry.mjs",
        "public/data/content_registry/content_registry.json",
    ):
        require(relative in content_files, f"content-registry transitive dependency is not locked:{relative}")

    policy_files = set(graph["input_sets"].get("release-policy-source", {}).get("files", {}))
    for relative in (
        "config/release/SIMULATION_INTENDED_USE.json",
        "config/release/SIMULATION_QUALITY_PROFILE.json",
        "config/release/SIMULATION_TIMING_POLICY.json",
        "config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json",
        "config/release/TECHNICAL_DEBT_REGISTER.json",
        "config/release/TECHNICAL_DEBT_RATCHET.json",
        "config/release/PRODUCTION_SIMULATION_POLICY.json",
        "config/release/SCENARIO_CAPABILITY_RATCHET.json",
        "docs/SCENARIO_GENOME_AND_CAPABILITY_RATCHET.md",
        "docs/TECHNICAL_DEBT_RATCHET.md",
        "scripts/check_scenario_capability_ratchet.py",
        "scripts/test_scenario_capability_ratchet.py",
        "scripts/check_technical_debt_ratchet.py",
        "scripts/test_technical_debt_ratchet.py",
        "scripts/join_scenario_evolution_evidence.py",
        "scripts/release_policy_common.py",
        "scripts/release_intended_use.py",
        "scripts/release_simulation_quality.py",
        "scripts/release_simulation_timing.py",
        "scripts/release_technical_debt.py",
        "scripts/release_production_designation.py",
        "scripts/test_release_production_designation.py",
    ):
        require(relative in policy_files, f"release policy dependency is not content-locked:{relative}")

    hub_files = set(graph["input_sets"].get("hub-source", {}).get("files", {}))
    for relative in (
        "server/index.ts",
        "server/hubSecurity.ts",
        "src/services/networkHub.ts",
        "src/utils/lobbyCapability.ts",
        "src/pages/WitDashboardPage.tsx",
        "src/pages/CommandRoomPage.tsx",
        "scripts/check_hub_security.py",
        "scripts/test_hub_security.py",
        "scripts/testHubRuntimeSmoke.ts",
    ):
        require(relative in hub_files, f"hub security dependency is not content-locked:{relative}")

    production_policy = read_json(root / "config/release/PRODUCTION_SIMULATION_POLICY.json")
    policy_payload = dict(production_policy)
    policy_payload.pop("policy_anchor_sha256", None)
    observed_policy_anchor = hashlib.sha256(canonical_json(policy_payload).encode("utf-8")).hexdigest()
    require(production_policy.get("schema_version") == "1.1.0", "production policy schema differs")
    require(production_policy.get("policy_epoch") == PRODUCTION_POLICY_EPOCH, "production policy epoch differs")
    require(production_policy.get("evidence_profile") == PRODUCTION_EVIDENCE_PROFILE, "production policy evidence profile differs")
    require(production_policy.get("policy_anchor_sha256") == observed_policy_anchor, "production policy self-anchor differs")
    require(observed_policy_anchor == PRODUCTION_POLICY_ANCHOR, "production policy differs from compiled graph-validator floor")
    required_reports = production_policy.get("required_reports", [])
    require(
        required_reports == [{"classification": "PASS", "path": path} for path in PRODUCTION_REQUIRED_REPORTS],
        "production policy report inventory differs from compiled graph-validator floor",
    )
    require(all(not descriptor.get("evaluated_after_designation", False) for descriptor in required_reports if isinstance(descriptor, dict)), "production policy contains an after-designation evidence cycle")
    required_receipts = production_policy.get("required_stage_receipts", [])
    require(required_receipts == list(PRODUCTION_REQUIRED_RECEIPTS), "production policy receipt inventory differs from compiled graph-validator floor")
    for stage_id in PRODUCTION_REQUIRED_RECEIPTS:
        require(stage_id in stages, f"production policy references absent stage:{stage_id}")

    scenario_evolution_source = (root / "scripts/join_scenario_evolution_evidence.py").read_text(encoding="utf-8")
    production_designation_source = (root / "scripts/release_production_designation.py").read_text(encoding="utf-8")
    require(
        'REQUIRED_RECEIPT_STAGES = tuple(sorted(set(REPORT_STAGE_MAP.values()) | set(ARTIFACT_STAGE_MAP.values())))' in scenario_evolution_source,
        "scenario evolution receipt inventory is not derived from report-and-artifact producer union",
    )
    require(
        '"required_receipts": len(REQUIRED_RECEIPT_STAGES)' in scenario_evolution_source,
        "scenario evolution required receipt count is not union-derived",
    )
    require(
        'observed_receipt_stages == REQUIRED_RECEIPT_STAGES' in scenario_evolution_source,
        "scenario evolution receipt completeness self-check missing",
    )
    require(
        'behavioral_summary = behavioral_policy_summary(behavioral)' in production_designation_source,
        "production designation does not consume the canonical behavioral archive summary",
    )
    require(
        'behavioral.get("policy_equivalence_classes")' not in production_designation_source,
        "production designation regressed to obsolete top-level behavioral metrics",
    )
    require(
        'SCENARIO_EVOLUTION_EVIDENCE_PROFILE' in production_designation_source
        and 'SCENARIO_EVOLUTION_REQUIRED_RECEIPT_STAGES' in production_designation_source,
        "production designation duplicates scenario-evolution profile or receipt authority",
    )


    classification = PASS if not errors else FAIL
    return {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "graph_id": graph.get("graph_id"),
        "release_candidate": graph.get("release_candidate"),
        "production_designation": graph.get("production_designation"),
        "checks": checks,
        "stages": len(graph.get("stages", [])),
        "targets": sorted(graph.get("targets", {})),
        "workflow_jobs": observed_workflow_jobs,
        "source_closure": source_closure_summary,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = validate(args.repo.resolve(), args.graph)
    write_json(args.repo.resolve() / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
