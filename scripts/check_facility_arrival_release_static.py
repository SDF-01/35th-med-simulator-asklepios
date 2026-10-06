#!/usr/bin/env python3
"""Cheap, dependency-free release-policy checks for Facility Arrival RC3.3.5."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_release_graph import validate as validate_release_graph
from release_graph_core import load_graph, stage_map, target_stage_ids


SHA_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")


class WorkflowSyntaxError(ValueError):
    """Raised when the reviewed workflow leaves the supported YAML subset."""


def _parse_scalar_list(value: str, *, label: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("[") and value.endswith("]"):
        items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
    else:
        items = [value]
    for item in items:
        if re.fullmatch(r"[A-Za-z0-9_-]+", item) is None:
            raise WorkflowSyntaxError(f"invalid {label} item:{item}")
    return items


def parse_reviewed_workflow(text: str) -> dict[str, Any]:
    """Parse only the small, reviewed YAML subset used by this workflow.

    This intentionally avoids an undeclared PyYAML dependency and fails closed
    on anchors, aliases, tabs, duplicate jobs, malformed indentation, or
    unsupported multi-line scalar syntax.  It is not a general YAML parser.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\t" in normalized:
        raise WorkflowSyntaxError("tabs are forbidden in workflow YAML")
    if re.search(r"(^|[ \[])[&*][A-Za-z0-9_-]+", normalized, flags=re.M) or "<<:" in normalized:
        raise WorkflowSyntaxError("YAML anchors, aliases, and merge keys are forbidden")
    lines = normalized.split("\n")
    jobs_line = None
    for index, line in enumerate(lines):
        if line == "jobs:":
            if jobs_line is not None:
                raise WorkflowSyntaxError("duplicate jobs mapping")
            jobs_line = index
    if jobs_line is None:
        raise WorkflowSyntaxError("jobs mapping missing")

    jobs: dict[str, dict[str, Any]] = {}
    current_job: str | None = None
    current_step: dict[str, Any] | None = None
    in_needs_list = False
    in_with = False

    for raw in lines[jobs_line + 1:]:
        if not raw or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            break
        job_match = re.fullmatch(r"  ([A-Za-z0-9_-]+):", raw)
        if job_match:
            job_id = job_match.group(1)
            if job_id in jobs:
                raise WorkflowSyntaxError(f"duplicate workflow job:{job_id}")
            jobs[job_id] = {"needs": [], "steps": []}
            current_job = job_id
            current_step = None
            in_needs_list = False
            in_with = False
            continue
        if current_job is None:
            raise WorkflowSyntaxError(f"unexpected content before first job:{stripped}")
        if indent == 4 and stripped.startswith("needs:"):
            tail = stripped.partition(":")[2]
            jobs[current_job]["needs"] = _parse_scalar_list(tail, label="needs")
            in_needs_list = not tail.strip()
            current_step = None
            in_with = False
            continue
        if in_needs_list and indent == 6 and stripped.startswith("- "):
            item = stripped[2:].strip()
            jobs[current_job]["needs"].extend(_parse_scalar_list(item, label="needs"))
            continue
        if indent <= 4:
            in_needs_list = False
        uses_match = re.fullmatch(r"- uses:\s*(\S+)", stripped)
        if indent == 6 and uses_match:
            current_step = {"uses": uses_match.group(1), "with": {}}
            jobs[current_job]["steps"].append(current_step)
            in_with = False
            continue
        if indent == 8 and stripped == "with:":
            if current_step is None:
                raise WorkflowSyntaxError("with block does not belong to a uses step")
            in_with = True
            continue
        if in_with and indent == 10 and ":" in stripped:
            key, value = (part.strip() for part in stripped.split(":", 1))
            if not key or key in current_step["with"]:
                raise WorkflowSyntaxError(f"invalid or duplicate action input:{key}")
            if value == "false":
                parsed: Any = False
            elif value == "true":
                parsed = True
            else:
                parsed = value.strip("'\"")
            current_step["with"][key] = parsed
            continue
        if indent <= 8:
            in_with = False
        # Other reviewed job/step fields are intentionally ignored, but their
        # indentation still has to be spaces and their text must not use YAML
        # features rejected above.

    if not jobs:
        raise WorkflowSyntaxError("workflow job inventory empty")
    return {"jobs": jobs}
REQUIRED_JOBS = {
    "facility-static-and-python",
    "facility-runtime-linux",
    "facility-runtime-windows",
    "facility-formal",
    "facility-reproducibility",
    "integrated-facility-gate",
}
REQUIRED_NEEDS = REQUIRED_JOBS - {"integrated-facility-gate"}
REQUIRED_SCRIPT_NAMES = {
    "compile:facility-arrival",
    "bind:facility-arrival",
    "check:facility-arrival-generator-parity",
    "check:facility-arrival-source-attestations",
    "generate:facility-arrival",
    "verify:facility-arrival-runtime",
    "verify:facility-arrival",
    "finalize:facility-arrival-release",
}



def _script_closure_contains(scripts: dict[str, Any], root_script: str, target_script: str) -> bool:
    """Resolve local ``npm run`` edges without executing shell text.

    The release contract cares whether the application build *transitively*
    invokes Facility Arrival generation.  Requiring the leaf name to appear in
    the top-level ``build`` string would reject safe script factoring and would
    create another independently maintained command graph.
    """
    pending = [root_script]
    visited: set[str] = set()
    pattern = re.compile(r"(?:^|[&|;]\s*)npm\s+run\s+([A-Za-z0-9:_-]+)")
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == target_script:
            return True
        command = scripts.get(current)
        if not isinstance(command, str):
            continue
        for dependency in pattern.findall(command):
            if dependency == target_script:
                return True
            if dependency not in visited:
                pending.append(dependency)
    return False


def _walk_steps(node: Any):
    if isinstance(node, dict):
        if "uses" in node:
            yield node
        for value in node.values():
            yield from _walk_steps(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_steps(value)


def validate(root: Path, *, validate_graph: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    if validate_graph:
        release_graph_report = validate_release_graph(root)
        require(release_graph_report.get("classification") == "PASS", "canonical release graph consistency failed")
    try:
        release_graph = load_graph(root)
        release_stages = stage_map(release_graph)
        runtime_stage_ids = target_stage_ids(release_graph, "facility-arrival-runtime")
        managed_scripts = release_graph.get("managed_package_scripts", {})
        for name in sorted(REQUIRED_SCRIPT_NAMES):
            require(name in managed_scripts, f"canonical release graph omits package script:{name}")
            require(scripts.get(name) == managed_scripts.get(name), f"package script differs:{name}")
        generate_command = str(managed_scripts.get("generate:facility-arrival", ""))
        parity_command = str(managed_scripts.get("check:facility-arrival-generator-parity", ""))
        attestation_command = str(managed_scripts.get("check:facility-arrival-source-attestations", ""))
        require("build_facility_arrival_example.py --repo ." in generate_command, "canonical Facility Arrival generation does not use the Python writer")
        require("npm run check:facility-arrival-generator-parity" in generate_command, "canonical Facility Arrival generation omits independent parity verification")
        require("generateFacilityArrivalArtifacts.ts --check" in parity_command, "independent Facility Arrival parity command differs")
        require("--json-output reports/facility-arrival-generator-parity.json" in parity_command, "independent Facility Arrival parity evidence is not durable")
        require("build_facility_arrival_example.py --repo . --check" in attestation_command, "source attestations omit canonical example verification")
        require("npm run check:facility-arrival-generator-parity" in attestation_command, "source attestations omit independent generator parity")
    except Exception as exc:  # noqa: BLE001 - report a static contract failure
        errors.append(f"canonical release graph unavailable:{type(exc).__name__}:{exc}")
        release_graph = {}
        release_stages = {}
        runtime_stage_ids = []
    compiler_source = (root / "scripts/compile_facility_arrival_spec.py").read_text(encoding="utf-8")
    binding_source = (root / "scripts/build_facility_arrival_bindings.py").read_text(encoding="utf-8")
    example_builder_source = (root / "scripts/build_facility_arrival_example.py").read_text(encoding="utf-8")
    facility_spec = json.loads((root / "config/facility-arrival/ASK-D-001.json").read_text(encoding="utf-8"))
    facility_types = (root / "src/facility-arrival/types.ts").read_text(encoding="utf-8")
    facility_runtime = (root / "src/facility-arrival/engine.ts").read_text(encoding="utf-8")
    facility_checker = (root / "src/facility-arrival-checker/verify.ts").read_text(encoding="utf-8")
    facility_python_checker = (root / "scripts/facility_arrival_verifier.py").read_text(encoding="utf-8")
    attributes_text = (root / ".gitattributes").read_text(encoding="utf-8") if (root / ".gitattributes").is_file() else ""
    require("if check:" in compiler_source and "report_path.write_text" in compiler_source, "spec compiler does not persist check-scoped evidence")
    require("if args.check:" in binding_source and "output.write_text" in binding_source, "binding compiler does not persist check-scoped evidence")
    require("if check:\n        report_path" in compiler_source, "spec generation can overwrite verification evidence")
    require("if args.check:\n        output" in binding_source, "binding generation can overwrite verification evidence")
    require("VERIFICATION_REPORT = Path(\"reports/facility-arrival-example-check.json\")" in example_builder_source, "facility example verification report path missing")
    require("default_output = VERIFICATION_REPORT if args.check else GENERATION_REPORT" in example_builder_source, "facility example generation/check evidence is not separated")
    require("attestation_kind" in example_builder_source and "file_sha256" in example_builder_source, "facility example check lacks authenticated file inventory")
    require("canonical_utf8_lf_v1" in binding_source, "scenario-source hash canonicalization mode missing")
    require("source_digest = sha256_canonical_text(repo / SCENARIO_SOURCE)" in binding_source, "scenario-source binding still hashes platform-dependent raw text bytes")
    second_event = next((item for item in facility_spec.get("events", []) if item.get("event_id") == "second_casualty_inbound"), None)
    require(second_event is not None, "facility clock event missing:second_casualty_inbound")
    facility_trigger = second_event.get("trigger", {}) if isinstance(second_event, dict) else {}
    require(facility_trigger.get("kind") == "elapsed_time_due", "facility clock event trigger kind changed:second_casualty_inbound")
    facility_time = facility_trigger.get("at_elapsed_seconds")
    require(facility_time == 240, f"facility clock event time changed:second_casualty_inbound:{facility_time}")

    decision_spec = json.loads((root / "config/facility-decision/ASK-D-001.json").read_text(encoding="utf-8"))
    decision_events = decision_spec.get("operational_model", {}).get("world_events", [])
    calibration_record = next((item for item in decision_events if isinstance(item, dict) and item.get("event_id") == "second_casualty_inbound"), None)
    require(calibration_record is not None, "calibration record missing:second_casualty_inbound")
    decision_time = calibration_record.get("at_elapsed_seconds") if isinstance(calibration_record, dict) else None
    calibration_status = calibration_record.get("calibration_status") if isinstance(calibration_record, dict) else None
    calibration_note = calibration_record.get("note") if isinstance(calibration_record, dict) else None
    require(calibration_status == "NOT_CALIBRATED", f"calibration status changed:second_casualty_inbound:{calibration_status}")
    require(facility_time == decision_time, f"event times disagree:second_casualty_inbound:facility={facility_time}:decision={decision_time}")
    note_text = calibration_note.casefold() if isinstance(calibration_note, str) else ""
    require("exercise-design" in note_text and "independent" in note_text, "exercise-assumption note missing:second_casualty_inbound")
    require("| { kind: 'elapsed_time_due'; at_elapsed_seconds: number }" in facility_types, "elapsed-time event trigger type missing")
    require("case 'elapsed_time_due':" in facility_runtime and "state.elapsed_seconds >= event.trigger.at_elapsed_seconds" in facility_runtime, "elapsed-time event runtime missing")
    require("elapsed_time_due outside scenario clock" in compiler_source, "elapsed-time event compiler bounds missing")
    require("case 'elapsed_time_due'" in facility_checker, "independent TypeScript checker omits elapsed-time event")
    require('kind == "elapsed_time_due"' in facility_python_checker, "independent Python checker omits elapsed-time event")
    require("): number | null" in facility_runtime and "return dueAt === null ? null" in facility_runtime, "total dynamic-duration resolver missing")
    require("duration_resolvable" in facility_runtime, "availability contract omits duration_resolvable")
    require("Facility action duration was unresolved after admission." in facility_runtime, "execution-time unresolved-duration guard missing")
    for attribute in ["src/content/scenarios.ts text eol=lf", "config/facility-arrival/*.json text eol=lf", "src/facility-arrival/*.ts text eol=lf", "examples/facility-arrival/* text eol=lf", ".github/workflows/facility-arrival-ci.yml text eol=lf"]:
        require(attribute in attributes_text, f"cross-platform LF attribute missing:{attribute}")
    validator_source = (root / "scripts/validate_facility_arrival_release.py").read_text(encoding="utf-8")
    require('require(attestation_valid(spec), "spec compiler attestation digest invalid", errors)' in validator_source, "final validator does not authenticate spec attestation")
    require('require(attestation_valid(bindings), "source-binding attestation digest invalid", errors)' in validator_source, "final validator does not authenticate binding attestation")
    require('require(current_hash_matches(root, spec.get("source"), spec.get("source_file_sha256")), "spec compiler source attestation is stale", errors)' in validator_source, "final validator omits spec freshness check")
    require('require(current_hash_matches(root, bindings.get("scenario_source_path"), bindings.get("scenario_source_sha256"), str(bindings.get("scenario_source_hash_mode"))), "scenario-source binding attestation is stale", errors)' in validator_source, "final validator omits canonical binding freshness check")
    require('example_attestation = load(root, "reports/facility-arrival-example-check.json", errors)' in validator_source, "final validator omits facility example verification attestation")
    require('require(attestation_valid(example_attestation), "facility example attestation digest invalid", errors)' in validator_source, "final validator does not authenticate the facility example attestation")
    require(_script_closure_contains(scripts, "build", "generate:facility-arrival"), "application build omits facility generation")
    assurance = scripts.get("assure:facility-arrival", "")
    require("--max-depth 9" in assurance, "bounded exploration depth is not explicitly 9")
    require("--differential-limit 250" in assurance, "differential exploration sample is not explicitly 250")
    required_runtime_stages = [
        "arrival.generator-source",
        "arrival.typescript-syntax",
        "arrival.module-resolution",
        "arrival.runtime-resolution",
        "arrival.generate",
        "arrival.artifact-boundary",
        "arrival.source-attestations",
        "arrival.runtime-tests",
        "arrival.python-check",
        "arrival.node-check",
        "arrival.semantic-attacks",
        "arrival.sequence-assurance",
        "arrival.state-exploration",
        "arrival.attestation-lifecycle-attacks",
        "arrival.artifact-boundary-attacks",
        "arrival.cross-platform-attacks",
        "arrival.static-validator",
        "arrival.runtime-evidence-join",
    ]
    for stage_id in required_runtime_stages:
        require(stage_id in runtime_stage_ids, f"runtime assurance omits stage:{stage_id}")
    source_stage = release_stages.get("arrival.source-attestations", {})
    require(source_stage.get("command") == ["npm", "run", "check:facility-arrival-source-attestations"], "runtime source-attestation stage differs")
    require(source_stage.get("needs") == ["arrival.artifact-boundary"], "runtime source attestations are not ordered after artifact boundary")


    readme = (root / "README.md").read_text(encoding="utf-8")
    facility_readme = (root / "examples/facility-arrival/README.md").read_text(encoding="utf-8")
    offline_policy = json.loads((root / "config/release/OFFLINE_SCENARIO_RELEASE.json").read_text(encoding="utf-8"))
    documentation_contract = offline_policy.get("documentation_contract", {}) if isinstance(offline_policy, dict) else {}
    root_start_marker = documentation_contract.get("root_start_marker")
    root_end_marker = documentation_contract.get("root_end_marker")
    display_version = offline_policy.get("display_version") if isinstance(offline_policy, dict) else None
    require(isinstance(root_start_marker, str) and readme.count(root_start_marker) == 1, "facility README start marker missing or duplicated")
    require(isinstance(root_end_marker, str) and readme.count(root_end_marker) == 1, "facility README end marker missing or duplicated")
    require("examples/facility-arrival/README.md" in readme, "facility walkthrough not linked from root README")
    require("/examples/facility-arrival" in readme, "facility browser route not linked from root README")
    require(
        isinstance(display_version, str)
        and f"## Current canonical offline scenario and engine evolution ({display_version})" in readme,
        "current policy-bound canonical facility heading missing",
    )
    require(facility_readme.startswith("# Facility-arrival canonical interactive scenario\n"), "facility example canonical heading missing")
    require("<!-- asklepios-verified-example:start -->" in readme, "foundational verified-example marker was removed")
    require("Research scenario generation\n\nThe `/research-sandbox` route" in readme, "research-sandbox README heading is malformed")

    generator = (root / "scripts/generateFacilityArrivalArtifacts.ts").read_text(encoding="utf-8")
    canonical_example_builder = (root / "scripts/build_facility_arrival_example.py").read_text(encoding="utf-8")
    escaped_calibration = "\\`NOT_CALIBRATED\\`"
    require(escaped_calibration in generator, "facility Markdown generator does not escape NOT_CALIBRATED inline-code delimiters")
    require("marked `NOT_CALIBRATED` exercise-design values" not in generator, "unescaped Markdown backticks break the TypeScript generator")
    require("resolve(publicBase, 'reference-session.json')" in generator, "canonical public session output missing")
    require("resolve(publicBase, 'reference-aar.json')" in generator, "canonical public AAR output missing")
    require("resolve(publicBase, 'reference-manifest.json')" in generator, "canonical public manifest output missing")
    offline_route = "[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request."
    require(offline_route in generator, "TypeScript generator omits offline standalone route")
    require(offline_route in canonical_example_builder, "Python canonical generator omits offline standalone route")
    require("generator_role: 'INDEPENDENT_TYPESCRIPT_CHECKER'" in generator, "TypeScript generator parity role marker missing")
    require("canonical_writer: 'PYTHON_BUILD_FACILITY_ARRIVAL_EXAMPLE'" in generator, "canonical generator identity marker missing")
    require("./engine_evolution_documentation_common.mjs" in generator, "TypeScript parity checker bypasses shared evolution renderer")
    require("renderEvolutionBlock(evolutionContext" in generator, "TypeScript parity checker shared evolution renderer invocation missing")
    require(r"`${evolutionBlock}\n\n` +" in generator, "TypeScript parity checker omits engine-evolution block")
    require("graphContractSha256(evolutionContext.graph)" in generator, "TypeScript parity checker omits shared graph-contract identity")
    require("function renderEvolutionBlock" not in generator, "TypeScript parity checker duplicates evolution renderer authority")
    require("function graphContractProjection" not in generator and "function graphContractSha256" not in generator, "TypeScript parity checker duplicates graph-contract authority")

    module_resolution_source = (root / "scripts/check_facility_arrival_module_resolution.py").read_text(encoding="utf-8")
    module_resolution_attacks = (root / "scripts/test_facility_arrival_module_resolution.py").read_text(encoding="utf-8")
    evolution_node_renderer = (root / "scripts/engine_evolution_documentation_common.mjs").read_text(encoding="utf-8")
    require(
        'NODE_BUILTIN_CAPABILITY_PROFILE = "EXACT_SOURCE_SCOPED_NODE_BUILTINS_V1"' in module_resolution_source,
        "Facility Arrival Node builtin capability profile differs",
    )
    require("ALLOWED_NODE_BUILTINS =" not in module_resolution_source, "Facility Arrival Node builtin capability policy is globally scoped")
    require(
        '"scripts/engine_evolution_documentation_common.mjs": frozenset({"node:crypto"})' in module_resolution_source,
        "engine-evolution renderer Node crypto capability differs",
    )
    require(
        '"scripts/generateFacilityArrivalArtifacts.ts": frozenset({"node:fs", "node:path"})' in module_resolution_source,
        "Facility Arrival generator Node builtin capabilities differ",
    )
    require(
        '"scripts/checkFacilityArrivalRuntimeResolution.ts": frozenset({"node:fs", "node:path"})' in module_resolution_source,
        "Facility Arrival runtime-resolution Node builtin capabilities differ",
    )
    require("declared Node builtin capability unused" in module_resolution_source, "unused Node builtin capability rejection missing")
    require("import crypto from 'node:crypto';" in evolution_node_renderer, "engine-evolution renderer reviewed crypto import missing")
    for case_id in [
        "reviewed_crypto_capability_wrong_source_rejected",
        "reviewed_crypto_capability_substitution_rejected",
        "unused_reviewed_crypto_capability_rejected",
    ]:
        require(case_id in module_resolution_attacks, f"Facility Arrival Node capability regression missing:{case_id}")

    require("TypeScript Facility Arrival generation is verification-only" in generator, "TypeScript generator is not verification-only")
    require("writeFileSync(path, content" not in generator, "TypeScript parity checker can overwrite generated artifacts")
    for script_name, command in scripts.items():
        if isinstance(command, str) and "generateFacilityArrivalArtifacts.ts" in command:
            require(script_name == "check:facility-arrival-generator-parity" and "--check" in command, f"TypeScript generator invoked outside parity check:{script_name}")
    require("--json-output" in generator and "facility-arrival-generator-parity.json" in scripts.get("check:facility-arrival-generator-parity", ""), "generator parity report is not durable")
    require("resolve(publicBase, 'reference_session.json')" not in generator, "legacy underscore session output forbidden")
    require("resolve(publicBase, 'reference_aar.json')" not in generator, "legacy underscore AAR output forbidden")
    require("resolve(publicBase, 'manifest.json')" not in generator, "generic public manifest output forbidden")
    require("reports/facility-arrival-generation.json" not in generator, "transient generation report must not mutate repository")
    require("rc3.3.5-ci-portability-and-canonical-artifact-boundary" in validator_source, "final validator expects stale generator regression identity")

    app = (root / "src/App.tsx").read_text(encoding="utf-8")
    require(app.count("import { FacilityArrivalExamplePage }") == 1, "facility page import missing or duplicated")
    require(app.count('path="/examples/facility-arrival"') == 1, "facility browser route missing or duplicated")

    formal_root = (root / "formal/ScenarioContracts.lean").read_text(encoding="utf-8")
    imports, _, declarations = formal_root.partition("set_option")
    require("import ScenarioContracts.FacilityArrival" in imports, "facility import absent from Lean import block")
    require("import ScenarioContracts.FacilityArrival" not in declarations, "facility import appears after Lean declarations")

    checker_source = (root / "scripts/check_facility_arrival_release_static.py").read_text(encoding="utf-8")
    require(re.search(r"^\s*(?:import\s+yaml|from\s+yaml\s+import)", checker_source, flags=re.M) is None, "undeclared PyYAML dependency forbidden")

    workflow_path = root / ".github/workflows/facility-arrival-ci.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    try:
        workflow = parse_reviewed_workflow(workflow_text)
    except WorkflowSyntaxError as exc:
        errors.append(f"workflow syntax rejected:{exc}")
        workflow = {"jobs": {}}
    jobs = workflow.get("jobs", {}) if isinstance(workflow, dict) else {}
    require(set(jobs) == REQUIRED_JOBS, "workflow job inventory differs")
    integrated = jobs.get("integrated-facility-gate", {})
    needs = integrated.get("needs", []) if isinstance(integrated, dict) else []
    require(set(needs) == REQUIRED_NEEDS, "integrated gate dependencies differ")
    require("continue-on-error" not in workflow_text, "workflow contains continue-on-error")
    require("|| true" not in workflow_text, "workflow suppresses a command failure")
    require("--target ci-integrated" in workflow_text, "integrated gate omits graph-owned final evidence join")
    require("--target ci-source" in workflow_text, "workflow source lane is not graph-owned")
    require(workflow_text.count("--target ci-runtime") >= 2, "Linux/Windows runtime lanes do not share the canonical graph target")
    require("--target ci-formal" in workflow_text, "workflow formal lane is not graph-owned")
    require("--target ci-reproducibility" in workflow_text, "workflow reproducibility lane is not graph-owned")
    require("python -m compileall" not in workflow_text, "workflow writes Python bytecode into the source tree")
    require("facility-runtime-windows" in workflow_text, "Windows runtime lane missing")
    require("patient_care" not in workflow_text.casefold(), "workflow should not carry clinical payload values")
    for step in _walk_steps(workflow):
        uses = step.get("uses")
        require(isinstance(uses, str) and SHA_ACTION.fullmatch(uses) is not None, f"GitHub action is not pinned to a full SHA:{uses}")
        with_block = step.get("with", {})
        if isinstance(uses, str) and uses.startswith("actions/checkout@"):
            require(isinstance(with_block, dict) and with_block.get("persist-credentials") is False, "checkout credentials are persisted")

    required_files = [
        "config/facility-arrival/ASK-D-001.json",
        "config/facility-arrival/source-binding.generated.json",
        "examples/facility-arrival/manifest.json",
        "formal/ScenarioContracts/FacilityArrival.lean",
        "formal/FacilityArrivalAxiomAudit.lean",
        "formal/FACILITY_ARRIVAL_TRUST_MANIFEST.json",
        "src/facility-arrival/engine.ts",
        "src/facility-arrival-checker/verify.ts",
        "src/pages/FacilityArrivalExamplePage.tsx",
        "scripts/check_facility_arrival_axioms.py",
        "scripts/check_facility_arrival_generator_regression.py",
        "scripts/check_facility_arrival_typescript_syntax.mjs",
        "scripts/check_facility_arrival_module_resolution.py",
        "scripts/test_facility_arrival_module_resolution.py",
        "scripts/test_facility_arrival_attestation_lifecycle.py",
        "scripts/check_facility_arrival_artifact_boundary.py",
        "scripts/test_facility_arrival_artifact_boundary.py",
        "scripts/test_facility_arrival_cross_platform.py",
        ".gitattributes",
        "scripts/checkFacilityArrivalRuntimeResolution.ts",
        "scripts/test_facility_arrival_mutations.py",
        "scripts/explore_facility_arrival_states.py",
        "scripts/run_python.mjs",
    ]
    for relative in required_files:
        require((root / relative).is_file() and (root / relative).stat().st_size > 0, f"required facility file missing:{relative}")

    return {
        "schema_version": "1.1.0",
        "classification": "PASS" if not errors else "FAIL",
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "workflow_jobs": sorted(jobs),
        "workflow_parser": "strict-stdlib-yaml-subset-v1",
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default="reports/facility-arrival-release-static.json")
    args = parser.parse_args()
    root = args.repo.resolve()
    report = validate(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
