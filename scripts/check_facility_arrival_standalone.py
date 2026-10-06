#!/usr/bin/env python3
"""Independent verifier for the one-file, no-server Facility Arrival demo."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

TARGET = Path("examples/facility-arrival/playable.html")
SPEC = Path("config/facility-arrival/ASK-D-001.json")
SNAPSHOT = Path("examples/facility-arrival/source-snapshot.json")
TRUTH = Path("examples/facility-arrival/source-truth.json")
MANIFEST = Path("examples/facility-arrival/manifest.json")
ROOT_README = Path("README.md")
EXAMPLE_README = Path("examples/facility-arrival/README.md")
OFFLINE_POLICY = Path("config/release/OFFLINE_SCENARIO_RELEASE.json")
SCENARIO_GENOME = Path("public/data/scenario_core/verified_scenario_genome.json")
CAPABILITY_RATCHET = Path("config/release/SCENARIO_CAPABILITY_RATCHET.json")
TECHNICAL_DEBT_RATCHET = Path("config/release/TECHNICAL_DEBT_RATCHET.json")
RELEASE_GRAPH = Path("config/release/RELEASE_GRAPH.json")
ROLE_MODEL_POLICY = Path("config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json")
ROLE_MODEL_PROFILE_IDS = (
    "DIRECT_HANDOFF_BASELINE",
    "COMMUNICATION_RELAY_REQUIRED",
    "RESOURCE_COORDINATION_REQUIRED",
    "DUAL_CONSTRAINT_RELAY_AND_COORDINATION",
)
ROLE_MODEL_ACTION_IDS = ("establish_communications_relay", "coordinate_constrained_resource")
GRAPH_BINDING_MODE = "ACYCLIC_SEMANTIC_PROJECTION_V1"

EXPECTED_TOP_LEVEL = {
    "schema_version",
    "release_id",
    "standalone_mode",
    "scenario_evolution",
    "role_model_profile_contract",
    "default_role_model_profile_id",
    "role_model_profiles",
    "authority",
    "spec",
    "source_snapshot",
    "source_truth",
    "example_manifest",
    "open_validity_obligations",
    "provenance",
}

NETWORK_PATTERNS = {
    "external script": re.compile(r"<script\b[^>]*\bsrc\s*=", re.I),
    "external stylesheet": re.compile(r"<link\b[^>]*\bhref\s*=", re.I),
    "fetch API": re.compile(r"\bfetch\s*\(", re.I),
    "XMLHttpRequest": re.compile(r"\bXMLHttpRequest\b"),
    "WebSocket": re.compile(r"\bWebSocket\b"),
    "EventSource": re.compile(r"\bEventSource\b"),
    "sendBeacon": re.compile(r"\bsendBeacon\b"),
    "remote iframe": re.compile(r"<iframe\b", re.I),
    "form action": re.compile(r"<form\b", re.I),
}

REQUIRED_ENGINE_MARKERS = (
    "function roleModelProfiles(data)",
    "function createProfiledData(baseData, profileId)",
    "function profileAction(actionId, prerequisites)",
    'if (required.includes("establish_communications_relay")) {',
    'if (required.includes("coordinate_constrained_resource")) {',
    "function createSession(data)",
    "function evaluateAction(state, actionId, data)",
    "function applyAction(previous, actionId, data, commandId)",
    "function processDueEvents(state, data, afterActionId)",
    "function runCanonical(data)",
    "function runUnsafe(actionId, data)",
    "function runTimeout(data)",
    "state.visible_findings = copy(data.source_snapshot.patient.hidden_findings)",
    "establish_communications_relay",
    "coordinate_constrained_resource",
    "teamwork_actions_award_clinical_points: false",
    "clinical_directive: null",
)

REQUIRED_UI_MARKERS = (
    "No Vercel. No API. No installation.",
    "Watch autoplay",
    "Unsafe discharge branch",
    "Unsafe tourniquet branch",
    "Save run report",
    "Learner view",
    "WIT process view",
    "Provenance view",
    "Scenario Genome",
    "Capability epoch",
    "Debt epoch",
    "Choose a role-model teamwork challenge",
    "Direct handoff baseline",
    "Communications relay",
    "Resource coordination",
    "Relay and resource coordination",
    'id="profile-selector"',
    'for (const button of document.querySelectorAll("[data-profile]")) {',
    "data-profile",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")




def graph_contract_projection(graph: dict[str, Any]) -> dict[str, Any]:
    raw_sets = graph.get("input_sets")
    if not isinstance(raw_sets, dict):
        raise ValueError("release graph input-set inventory malformed")
    input_sets: dict[str, Any] = {}
    for set_id in sorted(raw_sets):
        specification = raw_sets[set_id]
        if not isinstance(specification, dict):
            raise ValueError(f"release graph input set malformed:{set_id}")
        files = specification.get("files")
        include = specification.get("include", [])
        exclude = specification.get("exclude", [])
        if not isinstance(files, dict) or not isinstance(include, list) or not isinstance(exclude, list):
            raise ValueError(f"release graph input contract malformed:{set_id}")
        input_sets[str(set_id)] = {
            "include": include,
            "exclude": exclude,
            "file_paths": sorted(str(path) for path in files),
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


def graph_contract_sha256(graph: dict[str, Any]) -> str:
    return sha256_bytes(canonical(graph_contract_projection(graph)))


def extract_tag(html: str, tag_id: str) -> str:
    pattern = re.compile(
        rf'<script\b[^>]*\bid=["\']{re.escape(tag_id)}["\'][^>]*>(.*?)</script>',
        re.I | re.S,
    )
    match = pattern.search(html)
    if not match:
        raise ValueError(f"script tag missing:{tag_id}")
    return match.group(1)


def extract_style(html: str) -> str:
    match = re.search(r'<style\b[^>]*\bid=["\']asklepios-style["\'][^>]*>(.*?)</style>', html, re.I | re.S)
    if not match:
        raise ValueError("standalone style tag missing")
    return match.group(1)


def load_generator(repo: Path):
    path = repo / "scripts/build_facility_arrival_standalone.py"
    spec = importlib.util.spec_from_file_location("asklepios_standalone_builder", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("standalone generator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_artifact(repo: Path, artifact: Path, *, require_generated_identity: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    checks = 0
    try:
        html = artifact.read_text(encoding="utf-8")
    except Exception as exc:
        return {"status": "FAIL", "checks": 0, "errors": [f"standalone HTML unreadable:{exc}"]}

    checks += 1
    if len(html.encode("utf-8")) > 750_000:
        errors.append("standalone HTML exceeds 750 KiB budget")
    if "\r" in html:
        errors.append("standalone HTML contains carriage returns")
    if not html.endswith("\n"):
        errors.append("standalone HTML lacks final newline")

    csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"
    checks += 1
    if csp not in html:
        errors.append("strict offline CSP differs")

    for label, pattern in NETWORK_PATTERNS.items():
        checks += 1
        if pattern.search(html):
            errors.append(f"network/server dependency forbidden:{label}")

    try:
        data_text = extract_tag(html, "asklepios-scenario-data")
        engine = extract_tag(html, "asklepios-engine")
        ui = extract_tag(html, "asklepios-ui")
        css = extract_style(html)
        payload = json.loads(data_text.replace("<\\/script>", "</script>"))
    except Exception as exc:
        return {"status": "FAIL", "checks": checks, "errors": errors + [f"standalone structure invalid:{exc}"]}

    checks += 1
    if set(payload) != EXPECTED_TOP_LEVEL:
        errors.append("standalone payload top-level field set differs")
    if payload.get("schema_version") != "1.2.0":
        errors.append("standalone payload schema differs")
    if payload.get("standalone_mode") != "single_file_no_network":
        errors.append("standalone mode differs")
    try:
        policy = json.loads((repo / OFFLINE_POLICY).read_text(encoding="utf-8"))
        genome = json.loads((repo / SCENARIO_GENOME).read_text(encoding="utf-8"))
        ratchet = json.loads((repo / CAPABILITY_RATCHET).read_text(encoding="utf-8"))
        debt_ratchet = json.loads((repo / TECHNICAL_DEBT_RATCHET).read_text(encoding="utf-8"))
        graph = json.loads((repo / RELEASE_GRAPH).read_text(encoding="utf-8"))
        checks += 1
        if payload.get("release_id") != policy.get("release_id"):
            errors.append("standalone release identity differs")
        expected_evolution = {
            "release_id": policy["release_id"],
            "display_version": policy["display_version"],
            "engine_evolution": policy["engine_evolution"],
            "scenario_genome": {
                "genome_id": genome["genome_id"],
                "genome_sha256": genome["genome_sha256"],
            },
            "capability_ratchet": {
                "ratchet_id": ratchet["ratchet_id"],
                "ratchet_epoch": ratchet["ratchet_epoch"],
                "ratchet_anchor_sha256": ratchet["ratchet_anchor_sha256"],
            },
            "technical_debt_ratchet": {
                "ratchet_id": debt_ratchet["ratchet_id"],
                "ratchet_epoch": debt_ratchet["ratchet_epoch"],
                "ratchet_anchor_sha256": debt_ratchet["ratchet_anchor_sha256"],
            },
            "release_graph": {
                "graph_id": graph["graph_id"],
                "stage_count": len(graph["stages"]),
                "target_count": len(graph["targets"]),
                "binding_mode": GRAPH_BINDING_MODE,
                "contract_sha256": graph_contract_sha256(graph),
            },
            "capability_floor": {
                "scenario_experience": ratchet["hard_floors"]["scenario_experience"],
                "scenario_contract": ratchet["hard_floors"]["scenario_contract"],
            },
            "offline_guarantees": policy["offline_guarantees"],
            "truth_boundary": policy["truth_boundary"],
        }
        checks += 1
        if payload.get("scenario_evolution") != expected_evolution:
            errors.append("standalone scenario evolution binding differs")
    except Exception as exc:
        errors.append(f"standalone evolution source unavailable:{type(exc).__name__}:{exc}")
        expected_evolution = None

    # Independently reconstruct the playable role-model contract. These profiles
    # change only operational coordination routes; they never grant clinical authority
    # or clinical score points.
    try:
        role_policy = json.loads((repo / ROLE_MODEL_POLICY).read_text(encoding="utf-8"))
    except Exception as exc:
        role_policy = {}
        errors.append(f"role-model policy unreadable:{type(exc).__name__}:{exc}")
    role_contract = payload.get("role_model_profile_contract")
    profiles = payload.get("role_model_profiles")
    checks += 1
    if not isinstance(role_contract, dict):
        errors.append("playable role-model contract missing")
        role_contract = {}
    if not isinstance(profiles, list):
        errors.append("playable role-model profile inventory missing")
        profiles = []
    observed_profile_ids = [item.get("profile_id") for item in profiles if isinstance(item, dict)]
    checks += 1
    if observed_profile_ids != list(ROLE_MODEL_PROFILE_IDS):
        errors.append("playable role-model profile inventory differs")
    if len(profiles) != 4 or len(set(observed_profile_ids)) != 4:
        errors.append("exactly four unique playable role-model profiles are required")
    if role_policy.get("required_operational_profiles") != list(ROLE_MODEL_PROFILE_IDS):
        errors.append("behavioral-diversity policy role-model profile inventory differs")
    checks += 1
    if payload.get("default_role_model_profile_id") != "DIRECT_HANDOFF_BASELINE":
        errors.append("default playable role-model profile differs")
    expected_requirements = {
        "DIRECT_HANDOFF_BASELINE": [],
        "COMMUNICATION_RELAY_REQUIRED": ["establish_communications_relay"],
        "RESOURCE_COORDINATION_REQUIRED": ["coordinate_constrained_resource"],
        "DUAL_CONSTRAINT_RELAY_AND_COORDINATION": [
            "establish_communications_relay",
            "coordinate_constrained_resource",
        ],
    }
    for profile in profiles:
        checks += 1
        if not isinstance(profile, dict):
            errors.append("role-model profile is not an object")
            continue
        profile_id = profile.get("profile_id")
        expected_actions = expected_requirements.get(profile_id)
        if expected_actions is None:
            errors.append(f"unknown role-model profile:{profile_id}")
            continue
        if profile.get("required_operational_actions") != expected_actions:
            errors.append(f"role-model operational route differs:{profile_id}")
        if profile.get("intermediate_handoff_steps") != len(expected_actions):
            errors.append(f"role-model handoff-step count differs:{profile_id}")
        if profile.get("clinical_authority") != "NOT_GRANTED":
            errors.append(f"role-model clinical authority promoted:{profile_id}")
        if profile.get("human_behavior_calibration") != "STRUCTURAL_ONLY_NOT_CALIBRATED":
            errors.append(f"role-model human behavior calibration promoted:{profile_id}")
        if profile.get("scoring_effect") != "ZERO_CLINICAL_POINTS":
            errors.append(f"role-model clinical score effect differs:{profile_id}")
        hashed = dict(profile)
        observed_hash = hashed.pop("profile_sha256", None)
        if observed_hash != sha256_bytes(canonical(hashed)):
            errors.append(f"role-model profile digest differs:{profile_id}")
    expected_contract = {
        "schema_version": "1.0.0",
        "profile_family": "REVIEWED_NONCLINICAL_OPERATIONAL_ROUTE_FAMILY_V1",
        "selection_profile": "LEARNER_SELECTABLE_OFFLINE_ROLE_MODELS_V1",
        "playable_profile_count": 4,
        "default_profile_id": "DIRECT_HANDOFF_BASELINE",
        "required_profile_ids": list(ROLE_MODEL_PROFILE_IDS),
        "source_policy_path": ROLE_MODEL_POLICY.as_posix(),
        "source_policy_sha256": sha256_file(repo / ROLE_MODEL_POLICY) if (repo / ROLE_MODEL_POLICY).is_file() else None,
        "clinical_authority": "NOT_GRANTED",
        "operational_timing": "NOT_CALIBRATED",
        "scoring_state": "SOURCE_CONFORMANCE_ONLY",
    }
    expected_contract["contract_sha256"] = sha256_bytes(canonical(expected_contract))
    checks += 1
    if role_contract != expected_contract:
        errors.append("playable role-model contract differs")

    authority = payload.get("authority")
    checks += 1
    if not isinstance(authority, dict):
        errors.append("authority object missing")
    else:
        expected_authority = {
            "deployment_scope": "production_training_reference",
            "patient_care_use": "PROHIBITED",
            "clinical_content_mode": "INHERITED_REPOSITORY_TEMPLATE",
            "operational_content_mode": "DETERMINISTIC_EXERCISE_ORCHESTRATION",
            "evidence_mode": "IDENTITY_AND_SCOPE_ONLY",
            "automatic_clinical_rule_generation": False,
        }
        if authority != expected_authority:
            errors.append("authority boundary differs")

    source_inputs = {
        "spec": SPEC,
        "source_snapshot": SNAPSHOT,
        "source_truth": TRUTH,
        "example_manifest": MANIFEST,
    }
    for field, relative in source_inputs.items():
        checks += 1
        try:
            expected = json.loads((repo / relative).read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"source input unreadable:{relative}:{exc}")
            continue
        if payload.get(field) != expected:
            errors.append(f"embedded source differs:{field}")

    provenance = payload.get("provenance")
    checks += 1
    if not isinstance(provenance, dict):
        errors.append("provenance object missing")
        provenance = {}
    expected_hashes = {
        "spec_file_sha256": sha256_file(repo / SPEC),
        "snapshot_file_sha256": sha256_file(repo / SNAPSHOT),
        "source_truth_file_sha256": sha256_file(repo / TRUTH),
        "example_manifest_file_sha256": sha256_file(repo / MANIFEST),
        "engine_sha256": sha256_bytes(engine.encode("utf-8")),
        "ui_sha256": sha256_bytes(ui.encode("utf-8")),
        "css_sha256": sha256_bytes(css.encode("utf-8")),
        "role_model_policy_sha256": sha256_file(repo / ROLE_MODEL_POLICY),
        "role_model_contract_sha256": role_contract.get("contract_sha256"),
        "role_model_profiles_root_sha256": sha256_bytes(canonical(profiles)),
    }
    for field, expected in expected_hashes.items():
        checks += 1
        if provenance.get(field) != expected:
            errors.append(f"provenance hash differs:{field}")
    checks += 1
    if provenance.get("role_model_policy_path") != ROLE_MODEL_POLICY.as_posix():
        errors.append("role-model policy path differs")
    if role_contract.get("source_policy_sha256") != provenance.get("role_model_policy_sha256"):
        errors.append("role-model policy hash cross-binding differs")

    payload_without_hash = json.loads(json.dumps(payload))
    payload_without_hash.get("provenance", {}).pop("payload_sha256", None)
    checks += 1
    if provenance.get("payload_sha256") != sha256_bytes(canonical(payload_without_hash)):
        errors.append("payload digest differs")

    spec_value = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    actions = spec_value.get("actions") if isinstance(spec_value.get("actions"), list) else []
    events = spec_value.get("events") if isinstance(spec_value.get("events"), list) else []
    action_ids = [item.get("action_id") for item in actions if isinstance(item, dict)]
    checks += 1
    if len(actions) != 16 or len(set(action_ids)) != 16:
        errors.append("standalone action inventory differs")
    required_actions = {
        "receive_handoff", "primary_assessment", "monitor_vitals", "differential",
        "order_imaging", "order_labs", "pain_management", "confirm_surge_roles",
        "documentation", "wait_for_diagnostics", "review_diagnostics", "escalation",
        "complete_handoff", "wait_60", "discharge_without_workup", "remove_tourniquet",
    }
    if set(action_ids) != required_actions:
        errors.append("standalone action IDs differ")
    checks += 1
    if {event.get("event_id") for event in events if isinstance(event, dict)} != {
        "prearrival_notice", "second_casualty_inbound", "diagnostics_ready", "timeout_reached"
    }:
        errors.append("standalone event inventory differs")
    event_by_id = {item.get("event_id"): item for item in events if isinstance(item, dict)}
    checks += 1
    second_trigger = event_by_id.get("second_casualty_inbound", {}).get("trigger")
    if second_trigger != {"kind": "elapsed_time_due", "at_elapsed_seconds": 240}:
        errors.append("standalone second-casualty event is not clock-driven at 240 seconds")
    action_by_id = {item.get("action_id"): item for item in actions if isinstance(item, dict)}
    checks += 1
    if action_by_id.get("discharge_without_workup", {}).get("terminal_effect") != "failed":
        errors.append("unsafe discharge no longer fails closed")
    if action_by_id.get("remove_tourniquet", {}).get("terminal_effect") != "failed":
        errors.append("unsafe tourniquet action no longer fails closed")
    if action_by_id.get("complete_handoff", {}).get("terminal_effect") != "completed":
        errors.append("final handoff no longer completes")

    for marker in REQUIRED_ENGINE_MARKERS:
        checks += 1
        if marker not in engine:
            errors.append(f"engine invariant missing:{marker}")
    for marker in REQUIRED_UI_MARKERS:
        checks += 1
        if marker not in html:
            errors.append(f"UI capability missing:{marker}")

    checks += 1
    if "data.source_snapshot.patient.hidden_findings" not in engine:
        errors.append("hidden finding release is not source-bound")
    if "state.visible_findings = []" not in engine and "visible_findings: []" not in engine:
        errors.append("initial hidden findings boundary missing")
    if "state.elapsed_seconds >= timeout" not in engine:
        errors.append("timeout transition missing")
    if 'event.trigger.kind === "elapsed_time_due"' not in engine or "state.elapsed_seconds >= Number(event.trigger.at_elapsed_seconds)" not in engine:
        errors.append("elapsed-time event transition missing")
    if 'actionId === "order_imaging"' in engine and "Second casualty notification received" in engine:
        errors.append("second-casualty event regressed to action-triggered alert")
    if "action.source_action_id ?" not in engine:
        errors.append("source-action score isolation missing")
    checks += 1
    if 'source_action_id: null' not in engine or 'origin: "operational_workflow"' not in engine:
        errors.append("role-model operational actions are not isolated from clinical scoring")
    if 'required.includes("establish_communications_relay")' not in engine:
        errors.append("communications-relay profile route missing")
    if 'required.includes("coordinate_constrained_resource")' not in engine:
        errors.append("resource-coordination profile route missing")
    if 'prereqs = required.includes("establish_communications_relay")' not in engine:
        errors.append("dual-constraint role-model ordering missing")
    if engine.count('source_action_id: null') < 2:
        errors.append("role-model actions no longer have two zero-clinical-source bindings")
    if engine.count('duration_seconds: 45') < 2:
        errors.append("role-model action timing inventory differs")
    if 'handoff.prerequisites = unique([...(handoff.prerequisites || []), ...required])' not in engine:
        errors.append("profile-specific handoff prerequisite binding missing")
    if '...required,\n      ...baseSequence.slice(handoffIndex)' not in engine:
        errors.append("profile-specific canonical route insertion missing")

    evolution = payload.get("scenario_evolution") if isinstance(payload.get("scenario_evolution"), dict) else {}
    checks += 1
    if not isinstance(evolution.get("scenario_genome"), dict):
        errors.append("standalone Scenario Genome identity missing")
    if not isinstance(evolution.get("capability_ratchet"), dict):
        errors.append("standalone capability ratchet identity missing")
    if not isinstance(evolution.get("technical_debt_ratchet"), dict):
        errors.append("standalone technical-debt ratchet identity missing")
    release_graph_identity = evolution.get("release_graph")
    if not isinstance(release_graph_identity, dict):
        errors.append("standalone release graph identity missing")
    else:
        if release_graph_identity.get("binding_mode") != GRAPH_BINDING_MODE:
            errors.append("standalone release graph binding mode differs")
        if not re.fullmatch(r"[0-9a-f]{64}", str(release_graph_identity.get("contract_sha256", ""))):
            errors.append("standalone release graph contract hash malformed")
    if evolution.get("truth_boundary", {}).get("patient_care_use") != "PROHIBITED":
        errors.append("standalone evolution patient-care boundary differs")
    if evolution.get("truth_boundary", {}).get("operational_calibration") != "NOT_CALIBRATED":
        errors.append("standalone evolution timing boundary differs")
    if evolution.get("offline_guarantees", {}).get("network_requests") is not False:
        errors.append("standalone evolution network boundary differs")

    checks += 1
    root_readme = (repo / ROOT_README).read_text(encoding="utf-8") if (repo / ROOT_README).is_file() else ""
    example_readme = (repo / EXAMPLE_README).read_text(encoding="utf-8") if (repo / EXAMPLE_README).is_file() else ""
    if "examples/facility-arrival/playable.html" not in root_readme:
        errors.append("root README does not link standalone demo")
    if "playable.html" not in example_readme:
        errors.append("facility README does not link standalone demo")
    role_model_doc_markers = (
        "Four playable offline role-model teamwork challenges",
        "Direct handoff baseline",
        "Communications relay",
        "Resource coordination",
        "Relay and resource coordination",
    )
    for marker in role_model_doc_markers:
        checks += 1
        if marker not in root_readme:
            errors.append(f"root README role-model documentation missing:{marker}")
        if marker not in example_readme:
            errors.append(f"facility README role-model documentation missing:{marker}")

    if require_generated_identity:
        checks += 1
        try:
            expected = load_generator(repo).build(repo)
            if html != expected:
                errors.append("standalone HTML differs from deterministic generator")
        except Exception as exc:
            errors.append(f"standalone generator identity unavailable:{exc}")

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "artifact": artifact.relative_to(repo).as_posix() if artifact.is_relative_to(repo) else str(artifact),
        "artifact_sha256": sha256_file(artifact),
        "offline_mode": "single_file_no_network",
        "release_id": payload.get("release_id"),
        "genome_id": (payload.get("scenario_evolution") or {}).get("scenario_genome", {}).get("genome_id"),
        "ratchet_epoch": (payload.get("scenario_evolution") or {}).get("capability_ratchet", {}).get("ratchet_epoch"),
        "technical_debt_ratchet_epoch": (payload.get("scenario_evolution") or {}).get("technical_debt_ratchet", {}).get("ratchet_epoch"),
        "release_graph_id": (payload.get("scenario_evolution") or {}).get("release_graph", {}).get("graph_id"),
        "playable_role_model_profiles": len(profiles),
        "role_model_profile_ids": observed_profile_ids,
        "role_model_contract_sha256": role_contract.get("contract_sha256"),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--semantic-only", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/facility-arrival-standalone.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    artifact = (args.artifact if args.artifact else repo / TARGET).resolve()
    report = validate_artifact(repo, artifact, require_generated_identity=not args.semantic_only)
    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
