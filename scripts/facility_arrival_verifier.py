#!/usr/bin/env python3
"""Independent file-level verifier for the facility-arrival reference scenario.

This implementation deliberately does not import or execute the TypeScript runtime.
It reconstructs the state machine from the committed JSON specification and source
snapshot, then validates every transition, command receipt, certificate, AAR, and
manifest binding.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

ACTOR_IDS = (
    "receiving_provider",
    "clinic_nurse",
    "diagnostics_tech",
    "wit_observer",
)

FORBIDDEN_PUBLIC_KEYS = {
    "licensed_text",
    "full_text",
    "article_text",
    "raw_xml",
    "api_key",
    "institutional_token",
    "credential",
    "secret",
}

DEMONSTRATED_GATES = {
    "source_scenario_block_binding",
    "source_action_only_clinical_scoring",
    "deterministic_event_sourced_replay",
    "per_transition_state_binding",
    "explicit_actor_knowledge_updates",
    "hidden_findings_withheld_until_diagnostics",
    "timeout_as_authenticated_system_event",
    "duplicate_action_and_command_rejection",
    "score_clamped_to_closed_basis_point_range",
    "wit_process_observation_separated_from_clinical_scoring",
    "exercise_assumptions_disclosed_as_uncalibrated",
}

OPEN_GATES = {
    "claim_level_clinical_entailment",
    "real_world_frequency_calibration",
    "human_team_policy_calibration",
    "facility_specific_workflow_calibration",
    "continuous_physiology_model",
    "concurrent_multi_casualty_resource_contention",
    "causal_identification_for_counterfactual_aar",
    "executable_to_lean_refinement",
    "independent_proof_kernel_acceptance",
    "formal_vva_for_specific_wing_intended_use",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_canonical(value: Any) -> str:
    return sha256_text(canonical_json(value))


def sha256_canonical_utf8_lf(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"UTF-8 BOM forbidden:{path}")
    text = raw.decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def merkle_root(hashes: Iterable[str]) -> str:
    level = sorted(hashes)
    if not level:
        return sha256_text("")
    while len(level) > 1:
        next_level: list[str] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(sha256_text(f"{left}:{right}"))
        level = next_level
    return level[0]


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(state)
    for key in (
        "completed_action_ids",
        "completed_source_action_ids",
        "unsafe_source_action_ids",
        "fired_system_events",
        "revealed_hidden_findings",
        "alerts",
    ):
        value[key] = unique_sorted(value.get(key, []))
    value["actor_knowledge"] = {
        actor: unique_sorted(value.get("actor_knowledge", {}).get(actor, []))
        for actor in ACTOR_IDS
    }
    value["source_action_completed_at"] = dict(sorted(value.get("source_action_completed_at", {}).items()))
    value["action_completed_at"] = dict(sorted(value.get("action_completed_at", {}).items()))
    return value


def state_hash(state: dict[str, Any]) -> str:
    return sha256_canonical(normalize_state(state))


def scan_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in FORBIDDEN_PUBLIC_KEYS:
                errors.append(f"forbidden public field:{path}.{key}")
            errors.extend(scan_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(scan_forbidden_keys(child, f"{path}[{index}]"))
    return errors


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))



def _balanced_slice(text: str, start: int, opening: str = "{", closing: str = "}") -> str:
    if start < 0 or start >= len(text) or text[start] != opening:
        raise ValueError("balanced slice start is invalid")
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unterminated balanced source block")


def _property_string(text: str, name: str) -> str:
    import re
    match = re.search(rf"\b{re.escape(name)}\s*:\s*'([^']*)'", text, flags=re.S)
    if not match:
        raise ValueError(f"source property missing:{name}")
    return match.group(1)


def _property_number(text: str, name: str) -> int | float:
    import re
    match = re.search(rf"\b{re.escape(name)}\s*:\s*(-?\d+(?:\.\d+)?)", text)
    if not match:
        raise ValueError(f"source numeric property missing:{name}")
    raw = match.group(1)
    return float(raw) if "." in raw else int(raw)


def _property_array_strings(text: str, name: str) -> list[str]:
    import re
    marker = re.search(rf"\b{re.escape(name)}\s*:\s*\[", text)
    if not marker:
        raise ValueError(f"source array property missing:{name}")
    start = text.find("[", marker.start())
    block = _balanced_slice(text, start, "[", "]")
    return re.findall(r"'([^']*)'", block)


def _property_object(text: str, name: str) -> str:
    import re
    marker = re.search(rf"\b{re.escape(name)}\s*:\s*\{{", text)
    if not marker:
        raise ValueError(f"source object property missing:{name}")
    start = text.find("{", marker.start())
    return _balanced_slice(text, start)


def _extract_object_entries(array_block: str) -> list[str]:
    entries: list[str] = []
    index = 0
    while True:
        start = array_block.find("{", index)
        if start < 0:
            return entries
        block = _balanced_slice(array_block, start)
        entries.append(block)
        index = start + len(block)


def reconstruct_source_snapshot(repo: Path) -> dict[str, Any]:
    """Reconstruct the released ASK-D-001 fields directly from scenarios.ts.

    This is intentionally a small, fail-closed parser for the reviewed repository
    syntax. Any structural rewrite of the source block causes the release to stop
    instead of being guessed or silently normalized.
    """
    import re
    source_path = repo / "src" / "content" / "scenarios.ts"
    text = source_path.read_text(encoding="utf-8")
    marker = text.find("const askD001: Scenario =")
    if marker < 0:
        raise ValueError("ASK-D-001 source declaration missing")
    start = text.find("{", marker)
    block = _balanced_slice(text, start)
    patient_array_marker = re.search(r"\bpatients\s*:\s*\[", block)
    if not patient_array_marker:
        raise ValueError("ASK-D-001 patient array missing")
    patient_array_start = block.find("[", patient_array_marker.start())
    patient_array = _balanced_slice(block, patient_array_start, "[", "]")
    patient_objects = _extract_object_entries(patient_array)
    if len(patient_objects) != 1:
        raise ValueError("ASK-D-001 expected exactly one patient")
    patient = patient_objects[0]
    vitals = _property_object(patient, "initial_vitals")
    expected_actions = _property_object(block, "expected_actions")
    action_records: list[dict[str, Any]] = []
    for priority in ("critical", "important", "optional", "unsafe"):
        marker_match = re.search(rf"\b{priority}\s*:\s*\[", expected_actions)
        if not marker_match:
            raise ValueError(f"ASK-D-001 action group missing:{priority}")
        arr_start = expected_actions.find("[", marker_match.start())
        arr = _balanced_slice(expected_actions, arr_start, "[", "]")
        for action in _extract_object_entries(arr):
            action_records.append({
                "id": _property_string(action, "id"),
                "label": _property_string(action, "label"),
                "priority": priority,
                "points": int(_property_number(action, "points")),
            })
    end_conditions = _property_object(block, "end_conditions")
    return {
        "scenario_id": _property_string(block, "scenario_id"),
        "title": _property_string(block, "title"),
        "version": _property_string(block, "version"),
        "patient": {
            "initial_presentation": _property_string(patient, "initial_presentation"),
            "initial_vitals": {
                "hr": _property_number(vitals, "hr"),
                "bp_systolic": _property_number(vitals, "bp_systolic"),
                "bp_diastolic": _property_number(vitals, "bp_diastolic"),
                "rr": _property_number(vitals, "rr"),
                "spo2": _property_number(vitals, "spo2"),
                "temp_c": _property_number(vitals, "temp_c"),
                "gcs": _property_number(vitals, "gcs"),
            },
            "hidden_findings": _property_array_strings(patient, "hidden_findings"),
        },
        "source_actions": sorted(action_records, key=lambda value: value["id"]),
        "end_conditions": {
            "success": _property_array_strings(end_conditions, "success"),
            "failure": _property_array_strings(end_conditions, "failure"),
            "timeout_minutes": int(_property_number(end_conditions, "timeout_minutes")),
        },
        "source_file_sha256": sha256_canonical_utf8_lf(source_path),
    }


def verify_registry_source_binding(repo: Path, source: dict[str, Any], errors: list[str]) -> None:
    registry = load_json(repo / "public" / "data" / "content_registry" / "content_registry.json")
    assets = [asset for asset in registry.get("assets", []) if asset.get("asset_id") == "template:ASK-D-001"]
    if len(assets) != 1:
        errors.append("content registry ASK-D-001 template count mismatch")
        return
    asset = assets[0]
    without_hash = {key: value for key, value in asset.items() if key != "record_sha256"}
    if asset.get("record_sha256") != sha256_canonical(without_hash):
        errors.append("content registry template record hash mismatch")
    if asset.get("record_sha256") != source.get("template_record_sha256"):
        errors.append("source snapshot template record mismatch")
    if asset.get("source", {}).get("path") != source.get("source_file_path"):
        errors.append("source snapshot path differs from registry")
    actual_file_hash = sha256_canonical_utf8_lf(repo / source["source_file_path"])
    if asset.get("source", {}).get("file_sha256") != actual_file_hash:
        errors.append("content registry source file hash mismatch")
    if registry.get("roots", {}).get("registry_merkle_root") != source.get("content_registry_merkle_root"):
        errors.append("source snapshot registry root mismatch")


def initial_state(spec: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    max_points = sum(max(0, int(action["points"])) for action in source["source_actions"])
    actors = {actor["actor_id"]: actor for actor in spec["actors"]}
    return normalize_state({
        "revision": 0,
        "elapsed_seconds": 0,
        "phase": "pre_arrival",
        "terminal_status": "active",
        "outcome": None,
        "completed_action_ids": [],
        "completed_source_action_ids": [],
        "unsafe_source_action_ids": [],
        "fired_system_events": [],
        "source_action_completed_at": {},
        "action_completed_at": {},
        "revealed_hidden_findings": [],
        "actor_knowledge": {
            actor_id: list(actors.get(actor_id, {}).get("initial_knowledge", []))
            for actor_id in ACTOR_IDS
        },
        "alerts": [],
        "score_points": 0,
        "max_positive_points": max_points,
    })


def grant(state: dict[str, Any], grants: dict[str, Any]) -> None:
    for actor in ACTOR_IDS:
        state["actor_knowledge"][actor].extend(grants.get(actor, []))


def diagnostics_due_at(state: dict[str, Any], spec: dict[str, Any]) -> int | None:
    imaging = state["action_completed_at"].get("order_imaging")
    labs = state["action_completed_at"].get("order_labs")
    if imaging is None or labs is None:
        return None
    return max(int(imaging), int(labs)) + int(spec["parameters"]["diagnostic_delay_seconds"]["value"])


def action_duration(state: dict[str, Any], action: dict[str, Any], spec: dict[str, Any]) -> int:
    if action["duration_mode"] == "fixed":
        return int(action["duration_seconds"])
    if action["duration_mode"] != "until_diagnostics":
        raise ValueError(f"unknown duration mode:{action['duration_mode']}")
    due = diagnostics_due_at(state, spec)
    if due is None:
        raise ValueError("diagnostic wait started before both diagnostic orders")
    return max(0, due - int(state["elapsed_seconds"]))


def source_action_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["id"]: record for record in source["source_actions"]}


def required_source_ids(spec: dict[str, Any], source: dict[str, Any]) -> list[str]:
    priorities = set(spec["completion"]["required_source_action_priorities"])
    return sorted(record["id"] for record in source["source_actions"] if record["priority"] in priorities)


def completion_requirements_met(state: dict[str, Any], spec: dict[str, Any], source: dict[str, Any]) -> bool:
    required_source = required_source_ids(spec, source)
    required_operational = [
        action_id
        for action_id in spec["completion"]["required_operational_actions"]
        if action_id != "complete_handoff"
    ]
    return (
        all(action_id in state["completed_source_action_ids"] for action_id in required_source)
        and all(action_id in state["completed_action_ids"] for action_id in required_operational)
        and all(event_id in state["fired_system_events"] for event_id in spec["completion"]["required_event_ids"])
        and not state["unsafe_source_action_ids"]
    )


def expected_event_trigger(
    state: dict[str, Any],
    event: dict[str, Any],
    transition: dict[str, Any],
    previous: dict[str, Any] | None,
    spec: dict[str, Any],
) -> bool:
    trigger = event["trigger"]
    kind = trigger["kind"]
    if kind == "initial":
        return transition["sequence"] == 1 and state["revision"] == 0
    if kind == "after_action":
        return previous is not None and previous.get("action_id") == trigger["action_id"]
    if kind == "elapsed_time_due":
        return (
            int(state["elapsed_seconds"]) >= int(trigger["at_elapsed_seconds"])
            and int(transition["completed_at_seconds"]) >= int(trigger["at_elapsed_seconds"])
        )
    if kind == "diagnostics_due":
        due = diagnostics_due_at(state, spec)
        return due is not None and int(transition["completed_at_seconds"]) >= due
    if kind == "timeout_due":
        return int(transition["completed_at_seconds"]) == int(spec["parameters"]["timeout_seconds"]["value"])
    return False


def apply_action(
    state: dict[str, Any],
    transition: dict[str, Any],
    action: dict[str, Any],
    spec: dict[str, Any],
    source: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    action_id = action["action_id"]
    before = normalize_state(state)
    if before["terminal_status"] != "active":
        errors.append(f"action after terminal state:{transition['sequence']}")
    if action_id in before["completed_action_ids"] and not action["repeatable"]:
        errors.append(f"duplicate nonrepeatable action:{action_id}")
    for prerequisite in action["prerequisites"]:
        if prerequisite not in before["completed_action_ids"]:
            errors.append(f"missing prerequisite:{action_id}:{prerequisite}")
    for event_id in action.get("required_event_ids", []):
        if event_id not in before["fired_system_events"]:
            errors.append(f"missing required event:{action_id}:{event_id}")
    if action_id == "complete_handoff" and not completion_requirements_met(before, spec, source):
        errors.append("completion admitted before requirements")

    expected_duration = action_duration(before, action, spec)
    if int(transition["started_at_seconds"]) != int(before["elapsed_seconds"]):
        errors.append(f"action start mismatch:{action_id}")
    if int(transition["completed_at_seconds"]) != int(before["elapsed_seconds"]) + expected_duration:
        errors.append(f"action duration mismatch:{action_id}")
    if int(transition["completed_at_seconds"]) > int(spec["parameters"]["timeout_seconds"]["value"]):
        errors.append(f"action exceeded timeout without timeout event:{action_id}")

    after = copy.deepcopy(before)
    after["revision"] += 1
    after["elapsed_seconds"] += expected_duration
    after["completed_action_ids"].append(action_id)
    after["action_completed_at"][action_id] = after["elapsed_seconds"]
    if action.get("phase_after") is not None:
        after["phase"] = action["phase_after"]
    grant(after, action.get("knowledge_grants", {}))

    source_actions = source_action_map(source)
    score_delta = 0
    source_action_id = action.get("source_action_id")
    if action["origin"] == "operational_workflow":
        if source_action_id is not None:
            errors.append(f"operational action has source binding:{action_id}")
    elif action["origin"] == "source_template":
        source_record = source_actions.get(source_action_id)
        if not source_record:
            errors.append(f"invalid source action binding:{action_id}")
        else:
            score_delta = int(source_record["points"])
            after["score_points"] += score_delta
            after["completed_source_action_ids"].append(source_record["id"])
            after["source_action_completed_at"][source_record["id"]] = after["elapsed_seconds"]
            if source_record["priority"] == "unsafe":
                after["unsafe_source_action_ids"].append(source_record["id"])
    else:
        errors.append(f"unknown action origin:{action_id}:{action['origin']}")

    if int(transition["score_delta"]) != score_delta:
        errors.append(f"score delta mismatch:{action_id}")
    if action_id == "review_diagnostics":
        after["alerts"].append("Diagnostic results reviewed and casualty reassessed.")
    if action_id == "pain_management":
        after["alerts"].append(
            "Source-defined pain-management objective addressed without generating a drug, dose, or route."
        )
        if action.get("clinical_detail_policy") != "NO_GENERATED_DRUG_DOSE_OR_ROUTE":
            errors.append("pain-management detail policy missing")
    terminal_effect = action.get("terminal_effect")
    if terminal_effect:
        after["terminal_status"] = terminal_effect
        after["phase"] = "complete"
        after["outcome"] = (
            "Closed-loop receiving handoff completed."
            if terminal_effect == "completed"
            else f"Unsafe source action selected: {action['label']}"
        )
    return normalize_state(after)


def apply_event(
    state: dict[str, Any],
    transition: dict[str, Any],
    event: dict[str, Any],
    previous: dict[str, Any] | None,
    spec: dict[str, Any],
    source: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    event_id = event["event_id"]
    before = normalize_state(state)
    if event_id in before["fired_system_events"]:
        errors.append(f"duplicate system event:{event_id}")
    if not expected_event_trigger(before, event, transition, previous, spec):
        errors.append(f"event trigger mismatch:{event_id}")
    if int(transition["started_at_seconds"]) != int(before["elapsed_seconds"]):
        errors.append(f"event start mismatch:{event_id}")
    if int(transition["completed_at_seconds"]) < int(before["elapsed_seconds"]):
        errors.append(f"event time regressed:{event_id}")

    after = copy.deepcopy(before)
    after["elapsed_seconds"] = int(transition["completed_at_seconds"])
    after["revision"] += 1
    after["fired_system_events"].append(event_id)
    grant(after, event.get("knowledge_grants", {}))
    if event.get("reveal_source_hidden_findings"):
        after["revealed_hidden_findings"].extend(source["patient"]["hidden_findings"])
    alerts = {
        "prearrival_notice": "Pre-arrival notification received. Prepare for post-field-care reception.",
        "second_casualty_inbound": "Second casualty inbound. Preserve continuity while resources remain constrained.",
        "diagnostics_ready": "Ordered imaging and laboratory results are available for review.",
    }
    if event_id in alerts:
        after["alerts"].append(alerts[event_id])
    terminal_effect = event.get("terminal_effect")
    if terminal_effect:
        after["terminal_status"] = terminal_effect
        after["phase"] = "complete"
        after["outcome"] = (
            "Exercise ended at the source-bound timeout before closed-loop receiving handoff."
            if terminal_effect == "timeout"
            else f"Exercise ended: {terminal_effect}"
        )
    return normalize_state(after)


def expected_transition_id(transition: dict[str, Any]) -> str:
    core = {key: value for key, value in transition.items() if key != "transition_id"}
    return f"FAT-{int(transition['sequence']):03d}-{sha256_canonical(core)[:12]}"


def normalized_score_bps(state: dict[str, Any]) -> int:
    maximum = int(state["max_positive_points"])
    if maximum <= 0:
        return 0
    # All current source scores make the ratio exact; round-half-up is used here
    # to match JavaScript Math.round for future non-integral values.
    raw = (int(state["score_points"]) * 10_000 + maximum // 2) // maximum
    return min(10_000, max(0, raw))



def expected_generated_spec_text(spec: dict[str, Any]) -> str:
    digest = sha256_canonical(spec)
    pretty = json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True)
    text = (
        "/* AUTO-GENERATED by scripts/compile_facility_arrival_spec.py. DO NOT EDIT. */\n"
        "import type { FacilityArrivalSpec } from './types';\n\n"
        f"export const FACILITY_ARRIVAL_SPEC_SHA256 = '{digest}' as const;\n"
        "export const FACILITY_ARRIVAL_SPEC = " + pretty + " as FacilityArrivalSpec;\n"
    )
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def verify_spec_contract(repo: Path, spec: dict[str, Any], errors: list[str]) -> int:
    checks = 0
    expected_authority = {
        "deployment_scope": "production_training_reference",
        "patient_care_use": "PROHIBITED",
        "clinical_content_mode": "INHERITED_REPOSITORY_TEMPLATE",
        "operational_content_mode": "DETERMINISTIC_EXERCISE_ORCHESTRATION",
        "evidence_mode": "IDENTITY_AND_SCOPE_ONLY",
        "automatic_clinical_rule_generation": False,
    }
    if spec.get("authority") != expected_authority:
        errors.append("spec authority boundary mismatch")
    checks += 1
    parameters = spec.get("parameters", {})
    expected_parameters = {"diagnostic_delay_seconds", "pass_threshold_bps", "timeout_seconds"}
    if set(parameters) != expected_parameters:
        errors.append("spec parameter inventory mismatch")
    else:
        if parameters["diagnostic_delay_seconds"].get("calibration_status") != "NOT_CALIBRATED":
            errors.append("diagnostic delay calibration promoted")
        if parameters["pass_threshold_bps"].get("calibration_status") != "NOT_CALIBRATED":
            errors.append("pass threshold calibration promoted")
        if parameters["timeout_seconds"].get("calibration_status") != "SOURCE_BOUND":
            errors.append("timeout source binding weakened")
        if not (0 <= int(parameters["pass_threshold_bps"].get("value", -1)) <= 10_000):
            errors.append("pass threshold outside closed range")
    checks += 4
    action_ids: set[str] = set()
    for action in spec.get("actions", []):
        action_id = action.get("action_id")
        if not isinstance(action_id, str) or action_id in action_ids:
            errors.append(f"spec duplicate or invalid action:{action_id}")
        action_ids.add(action_id)
        if action.get("origin") == "operational_workflow" and action.get("source_action_id") is not None:
            errors.append(f"operational action has source binding:{action_id}")
        if action.get("origin") == "source_template" and not isinstance(action.get("source_action_id"), str):
            errors.append(f"source action lacks binding:{action_id}")
        if action_id == "pain_management" and action.get("clinical_detail_policy") != "NO_GENERATED_DRUG_DOSE_OR_ROUTE":
            errors.append("pain-management detail policy weakened")
    checks += max(1, len(action_ids) * 2)
    event_ids = [item.get("event_id") for item in spec.get("events", [])]
    if set(event_ids) != {"prearrival_notice", "second_casualty_inbound", "diagnostics_ready", "timeout_reached"}:
        errors.append("spec event inventory mismatch")
    timeout = next((item for item in spec.get("events", []) if item.get("event_id") == "timeout_reached"), None)
    if not timeout or timeout.get("trigger") != {"kind": "timeout_due"} or timeout.get("terminal_effect") != "timeout":
        errors.append("timeout event contract mismatch")
    diagnostics = [item.get("event_id") for item in spec.get("events", []) if item.get("reveal_source_hidden_findings")]
    if diagnostics != ["diagnostics_ready"]:
        errors.append("hidden-finding release event mismatch")
    checks += 3
    generated = repo / "src" / "facility-arrival" / "specification.generated.ts"
    if not generated.is_file() or generated.read_text(encoding="utf-8") != expected_generated_spec_text(spec):
        errors.append("generated TypeScript specification diverges from JSON source")
    checks += 1
    return checks

def verify_claim_ledger(ledger: dict[str, Any], spec: dict[str, Any], errors: list[str]) -> None:
    records = ledger.get("records", [])
    record_ids: set[str] = set()
    for record in records:
        record_id = record.get("claim_id")
        if record_id in record_ids:
            errors.append(f"duplicate claim record:{record_id}")
        record_ids.add(record_id)
        without_hash = {key: value for key, value in record.items() if key != "record_sha256"}
        if record.get("record_sha256") != sha256_canonical(without_hash):
            errors.append(f"claim record hash mismatch:{record_id}")
        if record.get("origin_class") == "exercise_assumption":
            if record.get("relation") != "ASSUMPTION":
                errors.append(f"exercise assumption promoted:{record_id}")
            if record.get("evidence_entailment") != "NOT_ADJUDICATED":
                errors.append(f"exercise assumption falsely adjudicated:{record_id}")
            if record.get("clinical_authority") != "NOT_GRANTED":
                errors.append(f"exercise assumption authority escalated:{record_id}")
        if record.get("origin_class") == "scope_reference":
            if record.get("relation") != "SCOPE_AND_PROCESS_REFERENCE":
                errors.append(f"scope reference relation escalated:{record_id}")
            if record.get("clinical_authority") != "NOT_GRANTED":
                errors.append(f"scope reference authority escalated:{record_id}")
        if record.get("origin_class") == "inherited_source_template":
            if record.get("clinical_authority") != "INHERITED_ONLY":
                errors.append(f"inherited source authority mismatch:{record_id}")
    payload = {"schema_version": ledger.get("schema_version"), "example_id": ledger.get("example_id"), "records": records}
    if ledger.get("ledger_sha256") != sha256_canonical(payload):
        errors.append("claim ledger root mismatch")
    expected_assumption_fields = {
        f"spec.parameters.{name}"
        for name, parameter in spec["parameters"].items()
        if parameter["origin"] in {"exercise_assumption", "exercise_policy"}
    }
    observed_assumptions = {
        record["field_path"] for record in records if record.get("origin_class") == "exercise_assumption"
    }
    if observed_assumptions != expected_assumption_fields:
        errors.append("exercise assumption claim coverage mismatch")


def verify_source_truth(source_truth: dict[str, Any], errors: list[str]) -> None:
    records = source_truth.get("records", [])
    for record in records:
        without_hash = {key: value for key, value in record.items() if key != "source_record_sha256"}
        if record.get("source_record_sha256") != sha256_canonical(without_hash):
            errors.append(f"source truth record hash mismatch:{record.get('source_id')}")
        if record.get("relation") != "SCOPE_AND_PROCESS_REFERENCE":
            errors.append(f"source truth relation escalated:{record.get('source_id')}")
        if record.get("clinical_rule_entailment") != "NOT_USED":
            errors.append(f"scope reference used as clinical rule:{record.get('source_id')}")
    payload = {key: value for key, value in source_truth.items() if key != "source_truth_root_sha256"}
    if source_truth.get("source_truth_root_sha256") != sha256_canonical(payload):
        errors.append("source truth root mismatch")


def verify_session(
    session: dict[str, Any],
    spec: dict[str, Any],
    source: dict[str, Any],
    ledger: dict[str, Any],
) -> tuple[list[str], int]:
    errors: list[str] = []
    checks = 0

    expected_authority = {
        "deployment_scope": "production_training_reference",
        "patient_care_use": "PROHIBITED",
        "clinical_content_mode": "INHERITED_REPOSITORY_TEMPLATE",
        "operational_content_mode": "DETERMINISTIC_EXERCISE_ORCHESTRATION",
        "evidence_mode": "IDENTITY_AND_SCOPE_ONLY",
        "automatic_clinical_rule_generation": False,
    }
    if session.get("authority") != expected_authority:
        errors.append("authority boundary mismatch")
    checks += 1
    if session.get("source_binding", {}).get("source_scenario_id") != source.get("source_scenario_id"):
        errors.append("source scenario ID mismatch")
    if session.get("source_binding", {}).get("source_scenario_sha256") != source.get("source_scenario_sha256"):
        errors.append("source scenario hash mismatch")
    if session.get("source_binding", {}).get("source_action_ids") != sorted(r["id"] for r in source["source_actions"]):
        errors.append("source action inventory mismatch")
    for key in ("source_file_path", "template_asset_id", "template_record_sha256", "content_registry_merkle_root"):
        if session.get("source_binding", {}).get(key) != source.get(key):
            errors.append(f"source binding mismatch:{key}")
    checks += 6
    if session.get("spec_sha256") != sha256_canonical(spec):
        errors.append("spec hash mismatch")
    checks += 1

    state = initial_state(spec, source)
    if normalize_state(session.get("initial_state", {})) != state:
        errors.append("initial state mismatch")
    checks += 1
    actions = {record["action_id"]: record for record in spec["actions"]}
    events = {record["event_id"]: record for record in spec["events"]}
    previous: dict[str, Any] | None = None
    transitions = session.get("transitions", [])
    if not transitions:
        errors.append("transition history empty")
    for index, transition in enumerate(transitions, 1):
        checks += 10
        if transition.get("sequence") != index:
            errors.append(f"transition sequence mismatch:{index}")
        if transition.get("before_state_sha256") != state_hash(state):
            errors.append(f"before state hash mismatch:{index}")
        if transition.get("transition_id") != expected_transition_id(transition):
            errors.append(f"transition ID mismatch:{index}")
        if transition.get("kind") == "learner_action":
            action = actions.get(transition.get("action_id"))
            if not action:
                errors.append(f"unknown learner action:{transition.get('action_id')}")
                expected = state
            else:
                expected = apply_action(state, transition, action, spec, source, errors)
            if transition.get("actor_id") != "receiving_provider":
                errors.append(f"learner transition actor mismatch:{index}")
            if transition.get("event_id") is not None:
                errors.append(f"learner transition carries event:{index}")
        elif transition.get("kind") == "system_event":
            event = events.get(transition.get("event_id"))
            if not event:
                errors.append(f"unknown system event:{transition.get('event_id')}")
                expected = state
            else:
                expected = apply_event(state, transition, event, previous, spec, source, errors)
            if transition.get("actor_id") != "system":
                errors.append(f"system transition actor mismatch:{index}")
            if int(transition.get("score_delta", 0)) != 0:
                errors.append(f"system event changed clinical score:{index}")
        else:
            errors.append(f"unknown transition kind:{index}")
            expected = state
        wit = transition.get("wit_observation", {})
        if wit.get("process_only") is not True or wit.get("clinical_directive") is not None:
            errors.append(f"WIT observation exceeded process-only scope:{index}")
        if transition.get("after_state_sha256") != state_hash(expected):
            errors.append(f"after state hash mismatch:{index}")
        if normalize_state(transition.get("state_after", {})) != expected:
            errors.append(f"state snapshot mismatch:{index}")
        state = expected
        previous = transition

    if normalize_state(session.get("final_state", {})) != state:
        errors.append("final state mismatch")
    checks += 1
    expected_score = normalized_score_bps(state)
    if session.get("normalized_score_bps") != expected_score:
        errors.append("normalized score mismatch")
    if not 0 <= expected_score <= 10_000:
        errors.append("normalized score outside closed range")
    checks += 2
    if state["revealed_hidden_findings"] and "diagnostics_ready" not in state["fired_system_events"]:
        errors.append("hidden findings disclosed before diagnostics")
    if state["terminal_status"] == "completed" and transitions[-1].get("action_id") != "complete_handoff":
        errors.append("completed session lacks terminal handoff")
    if state["terminal_status"] == "timeout" and transitions[-1].get("event_id") != "timeout_reached":
        errors.append("timeout is not an explicit terminal event")
    if state["terminal_status"] == "failed" and not state["unsafe_source_action_ids"]:
        errors.append("failed unsafe branch has no unsafe source action")
    checks += 4

    certificate = session.get("certificate", {})
    if certificate.get("source_binding_sha256") != sha256_canonical(session["source_binding"]):
        errors.append("source binding certificate mismatch")
    if certificate.get("spec_sha256") != sha256_canonical(spec):
        errors.append("certificate spec hash mismatch")
    if certificate.get("initial_state_sha256") != state_hash(session["initial_state"]):
        errors.append("certificate initial state mismatch")
    if certificate.get("final_state_sha256") != state_hash(session["final_state"]):
        errors.append("certificate final state mismatch")
    transition_root = merkle_root(transition["after_state_sha256"] for transition in transitions)
    if certificate.get("transition_root_sha256") != transition_root:
        errors.append("transition Merkle root mismatch")
    replay_payload = {
        "initial_state": session["initial_state"],
        "transitions": [
            {
                "transition_id": transition["transition_id"],
                "before_state_sha256": transition["before_state_sha256"],
                "after_state_sha256": transition["after_state_sha256"],
            }
            for transition in transitions
        ],
        "final_state": session["final_state"],
    }
    if certificate.get("replay_root_sha256") != sha256_canonical(replay_payload):
        errors.append("replay root mismatch")
    if certificate.get("claim_ledger_sha256") != ledger.get("ledger_sha256"):
        errors.append("certificate claim ledger mismatch")
    without_certificate = {key: value for key, value in session.items() if key != "certificate"}
    if certificate.get("session_sha256") != sha256_canonical(without_certificate):
        errors.append("session certificate hash mismatch")
    checks += 8

    certificate_checks = certificate.get("checks", {})
    required_check_keys = {
        "source_binding_matches",
        "source_action_subset_preserved",
        "required_source_actions_complete",
        "unsafe_source_actions_fail_closed",
        "diagnostics_precede_hidden_findings",
        "terminal_handoff_reached",
        "patient_care_use_prohibited",
        "wit_observations_process_only",
        "replay_chain_complete",
        "timeout_is_event_sourced",
        "transition_states_bound",
        "score_within_bounds",
        "actor_knowledge_authorized",
        "uncalibrated_parameters_disclosed",
    }
    if set(certificate_checks) != required_check_keys:
        errors.append("certificate check inventory mismatch")
    if not all(certificate_checks.get(key) is True for key in required_check_keys):
        errors.append("certificate reports a failed check")
    checks += 2

    # Independently derive actor knowledge ceiling from the spec.
    allowed: dict[str, set[str]] = {
        actor["actor_id"]: set(actor.get("initial_knowledge", [])) for actor in spec["actors"]
    }
    for record in [*spec["actions"], *spec["events"]]:
        for actor, tokens in record.get("knowledge_grants", {}).items():
            allowed.setdefault(actor, set()).update(tokens)
    for actor, tokens in state["actor_knowledge"].items():
        unknown = set(tokens) - allowed.get(actor, set())
        if unknown:
            errors.append(f"unauthorized actor knowledge:{actor}:{','.join(sorted(unknown))}")
    checks += len(ACTOR_IDS)

    # Command receipt semantics: each learner command has exactly one learner transition;
    # its receipt range may include immediately triggered system events.
    receipts = session.get("command_receipts", [])
    if len(receipts) != len([t for t in transitions if t["kind"] == "learner_action"]):
        errors.append("command receipt count mismatch")
    receipt_ids: set[str] = set()
    for receipt_index, receipt in enumerate(receipts):
        command_id = receipt.get("command_id")
        if command_id in receipt_ids:
            errors.append(f"duplicate command receipt:{command_id}")
        receipt_ids.add(command_id)
        first = receipt.get("first_transition_sequence")
        final = receipt.get("final_transition_sequence")
        if not isinstance(first, int) or not isinstance(final, int) or not (1 <= first <= final <= len(transitions)):
            errors.append(f"invalid command receipt range:{command_id}")
            continue
        first_transition = transitions[first - 1]
        if first_transition.get("kind") != "learner_action" or first_transition.get("command_id") != command_id:
            errors.append(f"receipt does not begin at learner action:{command_id}")
        if first_transition.get("action_id") != receipt.get("action_id"):
            errors.append(f"receipt action mismatch:{command_id}")
        next_first = receipts[receipt_index + 1].get("first_transition_sequence") if receipt_index + 1 < len(receipts) else len(transitions) + 1
        if final != next_first - 1:
            errors.append(f"receipt range is not contiguous:{command_id}")
        before_revision = session["initial_state"]["revision"] if first == 1 else transitions[first - 2]["state_after"]["revision"]
        expected_command = {
            "command_id": command_id,
            "action_id": receipt.get("action_id"),
            "expected_revision": before_revision,
        }
        if receipt.get("command_sha256") != sha256_canonical(expected_command):
            errors.append(f"command receipt hash mismatch:{command_id}")
    checks += max(1, len(receipts) * 5)

    return sorted(set(errors)), checks


def verify_repository(repo: Path) -> dict[str, Any]:
    base = repo / "examples" / "facility-arrival"
    spec = load_json(repo / "config" / "facility-arrival" / "ASK-D-001.json")
    session = load_json(base / "interaction.json")
    aar = load_json(base / "aar.json")
    ledger = load_json(base / "claim-ledger.json")
    source = load_json(base / "source-snapshot.json")
    source_truth = load_json(base / "source-truth.json")
    manifest = load_json(base / "manifest.json")
    errors: list[str] = []
    checks = 0

    # Public-boundary scan.
    for name, payload in {
        "spec": spec,
        "session": session,
        "aar": aar,
        "claim-ledger": ledger,
        "source-snapshot": source,
        "source-truth": source_truth,
        "manifest": manifest,
    }.items():
        errors.extend(f"{name}:{error}" for error in scan_forbidden_keys(payload))
        checks += 1

    checks += verify_spec_contract(repo, spec, errors)
    verify_claim_ledger(ledger, spec, errors)
    verify_source_truth(source_truth, errors)
    checks += len(ledger.get("records", [])) * 3 + len(source_truth.get("records", [])) * 3

    source_without_hash = {key: value for key, value in source.items() if key != "snapshot_sha256"}
    if source.get("snapshot_sha256") != sha256_canonical(source_without_hash):
        errors.append("source snapshot hash mismatch")
    checks += 1
    try:
        reconstructed = reconstruct_source_snapshot(repo)
        if reconstructed["scenario_id"] != source.get("source_scenario_id"):
            errors.append("source-code scenario ID mismatch")
        if reconstructed["patient"] != source.get("patient"):
            errors.append("source-code patient snapshot mismatch")
        if reconstructed["source_actions"] != source.get("source_actions"):
            errors.append("source-code action inventory mismatch")
        if reconstructed["end_conditions"] != source.get("end_conditions"):
            errors.append("source-code end-condition mismatch")
        verify_registry_source_binding(repo, source, errors)
        checks += 12
    except Exception as exc:
        errors.append(f"source reconstruction failed:{exc}")

    session_errors, session_checks = verify_session(session, spec, source, ledger)
    errors.extend(session_errors)
    checks += session_checks

    # AAR binding and non-causal language.
    aar_without_hash = {key: value for key, value in aar.items() if key != "aar_sha256"}
    if aar.get("aar_sha256") != sha256_canonical(aar_without_hash):
        errors.append("AAR hash mismatch")
    if aar.get("session_sha256") != session["certificate"]["session_sha256"]:
        errors.append("AAR session binding mismatch")
    if aar.get("counterfactual_boundaries", {}).get("causal_claims_allowed") is not False:
        errors.append("AAR improperly claims causal identification")
    if set(aar.get("validity_ledger", {}).get("demonstrated", [])) != DEMONSTRATED_GATES:
        errors.append("demonstrated validity ledger mismatch")
    if set(aar.get("validity_ledger", {}).get("open", [])) != OPEN_GATES:
        errors.append("open validity ledger mismatch")
    checks += 5

    # Manifest path and file binding.
    allowed_files = {
        "interaction": "interaction.json",
        "aar": "aar.json",
        "claim_ledger": "claim-ledger.json",
        "source_snapshot": "source-snapshot.json",
        "source_truth": "source-truth.json",
        "documentation": "README.md",
    }
    if manifest.get("files") != allowed_files:
        errors.append("manifest file map mismatch")
    for value in manifest.get("files", {}).values():
        if Path(value).is_absolute() or ".." in Path(value).parts or Path(value).name != value:
            errors.append(f"unsafe manifest path:{value}")
    hash_fields = {
        "interaction_sha256": "interaction.json",
        "aar_sha256": "aar.json",
        "claim_ledger_sha256": "claim-ledger.json",
        "source_snapshot_sha256": "source-snapshot.json",
        "source_truth_sha256": "source-truth.json",
        "documentation_sha256": "README.md",
    }
    for field, file_name in hash_fields.items():
        expected = hashlib.sha256((base / file_name).read_bytes()).hexdigest()
        if manifest.get("hashes", {}).get(field) != expected:
            errors.append(f"manifest file hash mismatch:{field}")
    if manifest.get("certificate") != session.get("certificate"):
        errors.append("manifest certificate mismatch")
    if manifest.get("source_binding") != session.get("source_binding"):
        errors.append("manifest source binding mismatch")
    expected_counts = {
        "transitions": len(session["transitions"]),
        "learner_actions": sum(t["kind"] == "learner_action" for t in session["transitions"]),
        "system_events": sum(t["kind"] == "system_event" for t in session["transitions"]),
        "wit_observations": len(session["transitions"]),
        "claim_records": len(ledger["records"]),
        "demonstrated_gates": len(DEMONSTRATED_GATES),
        "open_gates": len(OPEN_GATES),
    }
    if manifest.get("counts") != expected_counts:
        errors.append("manifest count mismatch")
    if manifest.get("generated_from", {}).get("spec_sha256") != sha256_canonical(spec):
        errors.append("manifest spec binding mismatch")
    if manifest.get("generated_from", {}).get("source_snapshot_sha256") != source.get("snapshot_sha256"):
        errors.append("manifest source snapshot binding mismatch")
    manifest_without_hash = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != sha256_canonical(manifest_without_hash):
        errors.append("manifest root hash mismatch")
    checks += 6 + len(hash_fields)

    root_readme = (repo / "README.md").read_text(encoding="utf-8")
    example_readme = (base / "README.md").read_text(encoding="utf-8")
    if "examples/facility-arrival/README.md" not in root_readme:
        errors.append("root README facility example link missing")
    if "/examples/facility-arrival" not in root_readme:
        errors.append("root README browser route missing")
    if session["certificate"]["session_sha256"] not in example_readme:
        errors.append("example documentation session hash missing")
    if source["source_scenario_id"] not in example_readme:
        errors.append("example documentation source ID missing")
    if "NOT_CALIBRATED" not in example_readme:
        errors.append("example documentation calibration disclosure missing")
    checks += 5

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "example_id": session.get("example_id"),
        "session_sha256": session.get("certificate", {}).get("session_sha256"),
        "transitions": len(session.get("transitions", [])),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    report = verify_repository(args.repo.resolve())
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text, encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
