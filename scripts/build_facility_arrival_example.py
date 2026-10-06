#!/usr/bin/env python3
"""Deterministically build the facility-arrival reference artifacts.

This builder is intentionally independent of the TypeScript runtime.  It consumes
only the committed JSON specification, the committed source binding, the
repository source scenario, and the content registry.  The TypeScript generator
must produce byte-identical files in CI.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from engine_evolution_common import render_evolution_block
from facility_arrival_verifier import (
    ACTOR_IDS,
    DEMONSTRATED_GATES,
    OPEN_GATES,
    canonical_json,
    diagnostics_due_at,
    initial_state,
    merkle_root,
    normalize_state,
    normalized_score_bps,
    reconstruct_source_snapshot,
    required_source_ids,
    sha256_canonical,
    sha256_text,
    state_hash,
)

EXAMPLE_DIR = Path("examples/facility-arrival")
PUBLIC_DIR = Path("public/data/facility_arrival")
GENERATION_REPORT = Path("reports/facility-arrival-python-build.json")
VERIFICATION_REPORT = Path("reports/facility-arrival-example-check.json")
SPEC_PATH = Path("config/facility-arrival/ASK-D-001.json")
BINDING_PATH = Path("config/facility-arrival/source-binding.generated.json")


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def file_sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def grant_knowledge(state: dict[str, Any], grants: dict[str, Any]) -> None:
    for actor in ACTOR_IDS:
        state["actor_knowledge"][actor].extend(grants.get(actor, []))


def source_action_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {record["id"]: record for record in source["source_actions"]}


def action_duration(state: dict[str, Any], action: dict[str, Any], spec: dict[str, Any]) -> int:
    if action["duration_mode"] == "fixed":
        return int(action["duration_seconds"])
    if action["duration_mode"] != "until_diagnostics":
        raise ValueError(f"unsupported duration mode:{action['duration_mode']}")
    due = diagnostics_due_at(state, spec)
    if due is None:
        raise ValueError("diagnostic wait requested before both orders")
    return max(0, due - int(state["elapsed_seconds"]))


def transition_id(core: dict[str, Any], sequence: int) -> str:
    return f"FAT-{sequence:03d}-{sha256_canonical(core)[:12]}"


def append_transition(
    transitions: list[dict[str, Any]],
    before: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    sequence = len(transitions) + 1
    after = normalize_state(payload["state_after"])
    core = {
        **payload,
        "sequence": sequence,
        "state_after": after,
        "before_state_sha256": state_hash(before),
        "after_state_sha256": state_hash(after),
    }
    record = {**core, "transition_id": transition_id(core, sequence)}
    transitions.append(record)
    return record


def wit_observation(category: str, statement: str) -> dict[str, Any]:
    return {
        "category": category,
        "statement": statement,
        "process_only": True,
        "clinical_directive": None,
    }


def event_triggered(
    event: dict[str, Any],
    state: dict[str, Any],
    spec: dict[str, Any],
    just_completed_action: str | None,
) -> bool:
    if event["event_id"] in state["fired_system_events"]:
        return False
    trigger = event["trigger"]
    if trigger["kind"] == "initial":
        return int(state["revision"]) == 0
    if trigger["kind"] == "after_action":
        return just_completed_action == trigger["action_id"]
    if trigger["kind"] == "elapsed_time_due":
        return int(state["elapsed_seconds"]) >= int(trigger["at_elapsed_seconds"])
    if trigger["kind"] == "diagnostics_due":
        due = diagnostics_due_at(state, spec)
        return due is not None and int(state["elapsed_seconds"]) >= due
    if trigger["kind"] == "timeout_due":
        return (
            int(state["elapsed_seconds"]) >= int(spec["parameters"]["timeout_seconds"]["value"])
            and state["terminal_status"] == "active"
        )
    raise ValueError(f"unsupported event trigger:{trigger}")


def apply_event(
    state: dict[str, Any],
    event: dict[str, Any],
    source: dict[str, Any],
    transitions: list[dict[str, Any]],
    *,
    event_time: int | None = None,
    command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before = normalize_state(state)
    after = copy.deepcopy(before)
    if event_time is not None:
        after["elapsed_seconds"] = int(event_time)
    after["revision"] += 1
    after["fired_system_events"].append(event["event_id"])
    grant_knowledge(after, event.get("knowledge_grants", {}))
    if event.get("reveal_source_hidden_findings"):
        after["revealed_hidden_findings"].extend(source["patient"]["hidden_findings"])
    alerts = {
        "prearrival_notice": "Pre-arrival notification received. Prepare for post-field-care reception.",
        "second_casualty_inbound": "Second casualty inbound. Preserve continuity while resources remain constrained.",
        "diagnostics_ready": "Ordered imaging and laboratory results are available for review.",
    }
    if event["event_id"] in alerts:
        after["alerts"].append(alerts[event["event_id"]])
    if event.get("terminal_effect"):
        after["terminal_status"] = event["terminal_effect"]
        after["phase"] = "complete"
        after["outcome"] = (
            "Exercise ended at the source-bound timeout before closed-loop receiving handoff."
            if event["terminal_effect"] == "timeout"
            else f"Exercise ended: {event['terminal_effect']}"
        )
    after = normalize_state(after)
    append_transition(
        transitions,
        before,
        {
            "kind": "system_event",
            "actor_id": "system",
            "command_id": command["command_id"] if command else None,
            "action_id": command["action_id"] if command else None,
            "event_id": event["event_id"],
            "label": event["label"],
            "source_action_id": None,
            "origin": "system_event",
            "started_at_seconds": before["elapsed_seconds"],
            "completed_at_seconds": after["elapsed_seconds"],
            "score_delta": 0,
            "state_after": after,
            "wit_observation": wit_observation(event["wit_category"], event["label"]),
        },
    )
    return after


def process_events(
    state: dict[str, Any],
    spec: dict[str, Any],
    source: dict[str, Any],
    transitions: list[dict[str, Any]],
    just_completed_action: str | None,
) -> dict[str, Any]:
    current = normalize_state(state)
    for event in spec["events"]:
        if event_triggered(event, current, spec, just_completed_action):
            current = apply_event(current, event, source, transitions)
    return current


def completion_met(state: dict[str, Any], spec: dict[str, Any], source: dict[str, Any]) -> bool:
    required_source = required_source_ids(spec, source)
    required_operational = [
        value for value in spec["completion"]["required_operational_actions"] if value != "complete_handoff"
    ]
    return (
        all(value in state["completed_source_action_ids"] for value in required_source)
        and all(value in state["completed_action_ids"] for value in required_operational)
        and all(value in state["fired_system_events"] for value in spec["completion"]["required_event_ids"])
        and not state["unsafe_source_action_ids"]
    )


def apply_action(
    state: dict[str, Any],
    action: dict[str, Any],
    command: dict[str, Any],
    spec: dict[str, Any],
    source: dict[str, Any],
    transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    before = normalize_state(state)
    if before["terminal_status"] != "active":
        raise ValueError("action after terminal state")
    if action["action_id"] in before["completed_action_ids"] and not action["repeatable"]:
        raise ValueError(f"duplicate nonrepeatable action:{action['action_id']}")
    if int(command["expected_revision"]) != int(before["revision"]):
        raise ValueError("stale expected revision")
    if any(value not in before["completed_action_ids"] for value in action["prerequisites"]):
        raise ValueError(f"missing action prerequisite:{action['action_id']}")
    if any(value not in before["fired_system_events"] for value in action.get("required_event_ids", [])):
        raise ValueError(f"missing event prerequisite:{action['action_id']}")
    if action["action_id"] == "complete_handoff" and not completion_met(before, spec, source):
        raise ValueError("handoff before completion requirements")
    duration = action_duration(before, action, spec)
    timeout = int(spec["parameters"]["timeout_seconds"]["value"])
    if int(before["elapsed_seconds"]) + duration > timeout:
        timeout_event = next(event for event in spec["events"] if event["event_id"] == "timeout_reached")
        return apply_event(before, timeout_event, source, transitions, event_time=timeout, command=command)

    after = copy.deepcopy(before)
    after["revision"] += 1
    after["elapsed_seconds"] += duration
    after["completed_action_ids"].append(action["action_id"])
    after["action_completed_at"][action["action_id"]] = after["elapsed_seconds"]
    if action.get("phase_after") is not None:
        after["phase"] = action["phase_after"]
    grant_knowledge(after, action.get("knowledge_grants", {}))

    points = 0
    if action.get("source_action_id") is not None:
        source_record = source_action_map(source).get(action["source_action_id"])
        if source_record is None:
            raise ValueError(f"unknown source action:{action['source_action_id']}")
        points = int(source_record["points"])
        after["score_points"] += points
        after["completed_source_action_ids"].append(source_record["id"])
        after["source_action_completed_at"][source_record["id"]] = after["elapsed_seconds"]
        if source_record["priority"] == "unsafe":
            after["unsafe_source_action_ids"].append(source_record["id"])
    elif action["origin"] != "operational_workflow":
        raise ValueError(f"source-template action has no binding:{action['action_id']}")

    if action["action_id"] == "review_diagnostics":
        after["alerts"].append("Diagnostic results reviewed and casualty reassessed.")
    if action["action_id"] == "pain_management":
        after["alerts"].append(
            "Source-defined pain-management objective addressed without generating a drug, dose, or route."
        )
    if action.get("terminal_effect"):
        after["terminal_status"] = action["terminal_effect"]
        after["phase"] = "complete"
        after["outcome"] = (
            "Closed-loop receiving handoff completed."
            if action["terminal_effect"] == "completed"
            else f"Unsafe source action selected: {action['label']}"
        )
    after = normalize_state(after)
    append_transition(
        transitions,
        before,
        {
            "kind": "learner_action",
            "actor_id": "receiving_provider",
            "command_id": command["command_id"],
            "action_id": action["action_id"],
            "event_id": None,
            "label": action["label"],
            "source_action_id": action.get("source_action_id"),
            "origin": action["origin"],
            "started_at_seconds": before["elapsed_seconds"],
            "completed_at_seconds": after["elapsed_seconds"],
            "score_delta": points,
            "state_after": after,
            "wit_observation": wit_observation(action["wit_category"], f"{action['label']} observed."),
        },
    )
    return after


def source_binding(source: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_scenario_id": source["scenario_id"],
        "source_scenario_sha256": binding["source_scenario_projection_sha256"],
        "source_action_ids": sorted(record["id"] for record in source["source_actions"]),
        "source_file_path": binding["scenario_source_path"],
        "template_asset_id": binding["template_asset_id"],
        "template_record_sha256": binding["template_record_sha256"],
        "content_registry_merkle_root": binding["content_registry_merkle_root"],
    }


def build_claim_ledger(spec: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    def add(record: dict[str, Any]) -> None:
        records.append({**record, "record_sha256": sha256_canonical(record)})

    add({
        "claim_id": "claim-source-template-ASK-D-001",
        "field_path": "source_binding.source_scenario_id",
        "atomic_claim": "Clinical actions, points, patient presentation, hidden findings, unsafe actions, and timeout are inherited from ASK-D-001.",
        "origin_class": "inherited_source_template",
        "relation": "INHERITED",
        "evidence_entailment": "NOT_APPLICABLE",
        "contradiction_status": "NOT_APPLICABLE",
        "clinical_authority": "INHERITED_ONLY",
        "source_pointer": "src/content/scenarios.ts#ASK-D-001",
    })
    for name, parameter in spec["parameters"].items():
        if parameter["origin"] in {"exercise_assumption", "exercise_policy"}:
            add({
                "claim_id": f"claim-parameter-{name}",
                "field_path": f"spec.parameters.{name}",
                "atomic_claim": f"{name} is a declared exercise parameter, not an empirically calibrated real-world frequency.",
                "origin_class": "exercise_assumption",
                "relation": "ASSUMPTION",
                "evidence_entailment": "NOT_ADJUDICATED",
                "contradiction_status": "NOT_SEARCHED",
                "clinical_authority": "NOT_GRANTED",
                "source_pointer": "config/facility-arrival/ASK-D-001.json",
            })
    for source_id in (
        "JTS-CPG-INDEX-2026-07-28",
        "JTS-PI-2026-04-02",
        "JTS-DCOT-2026-04-03",
        "USAF-WIT-CRE-2026",
    ):
        add({
            "claim_id": f"claim-scope-{source_id}",
            "field_path": f"source_truth.records.{source_id}",
            "atomic_claim": f"{source_id} is used only to frame care-continuum, performance-improvement, or inspection process scope.",
            "origin_class": "scope_reference",
            "relation": "SCOPE_AND_PROCESS_REFERENCE",
            "evidence_entailment": "NOT_ADJUDICATED",
            "contradiction_status": "NOT_SEARCHED",
            "clinical_authority": "NOT_GRANTED",
            "source_pointer": f"examples/facility-arrival/source-truth.json#{source_id}",
        })
    records.sort(key=lambda record: record["claim_id"])
    payload = {"schema_version": "1.0.0", "example_id": spec["example_id"], "records": records}
    return {**payload, "ledger_sha256": sha256_canonical(payload)}


def build_source_truth() -> dict[str, Any]:
    base_records = [
        {
            "source_id": "JTS-CPG-INDEX-2026-07-28",
            "title": "Joint Trauma System Clinical Practice Guidelines",
            "url": "https://jts.health.mil/index.cfm/CPGs/cpgs",
            "locator": "Primary goals; Blood; Documentation; Radiology; Tactical Combat Casualty Care Guidelines; Transport",
            "relation": "SCOPE_AND_PROCESS_REFERENCE",
            "clinical_rule_entailment": "NOT_USED",
            "supported_scope_claim": "JTS publishes current casualty-care standards and lists relevant resuscitation, documentation, imaging, TCCC, and transport resources.",
            "retrieved_at_utc": "2026-07-29T00:00:00Z",
        },
        {
            "source_id": "JTS-PI-2026-04-02",
            "title": "Joint Trauma System Performance Improvement",
            "url": "https://jts.health.mil/index.cfm/pi",
            "locator": "Performance Improvement overview",
            "relation": "SCOPE_AND_PROCESS_REFERENCE",
            "clinical_rule_entailment": "NOT_USED",
            "supported_scope_claim": "JTS performance improvement spans the continuum of care and evaluates transitions between phases of care.",
            "retrieved_at_utc": "2026-07-29T00:00:00Z",
        },
        {
            "source_id": "JTS-DCOT-2026-04-03",
            "title": "Defense Committees on Trauma",
            "url": "https://jts.health.mil/index.cfm/committees/dcot",
            "locator": "Mission and component committees",
            "relation": "SCOPE_AND_PROCESS_REFERENCE",
            "clinical_rule_entailment": "NOT_USED",
            "supported_scope_claim": "DoD combat-casualty governance spans tactical, en route, and surgical care through separate expert committees.",
            "retrieved_at_utc": "2026-07-29T00:00:00Z",
        },
        {
            "source_id": "USAF-WIT-CRE-2026",
            "title": "Wing Inspection Team supports readiness during Combat Readiness Exercise 2026",
            "url": "https://www.18af.amc.af.mil/News/Article-Display/Article/4388635/wing-inspection-team-supports-readiness-during-combat-readiness-exercise-2026-a/",
            "locator": "WIT roles in observation, evaluation, trend identification, and corrective-action validation",
            "relation": "SCOPE_AND_PROCESS_REFERENCE",
            "clinical_rule_entailment": "NOT_USED",
            "supported_scope_claim": "Wing Inspection Team members observe operations, evaluate processes, and identify strengths and gaps during readiness exercises.",
            "retrieved_at_utc": "2026-07-29T00:00:00Z",
        },
    ]
    records = [{**record, "source_record_sha256": sha256_canonical(record)} for record in base_records]
    payload = {
        "schema_version": "1.1.0",
        "purpose": "Identity-only scope and process references for post-field-care facility reception and Wing Inspection Team framing.",
        "clinical_rule_source": "ASK-D-001 inherited repository template only",
        "records": records,
    }
    return {**payload, "source_truth_root_sha256": sha256_canonical(payload)}


def build_source_snapshot(source: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "source_scenario_id": source["scenario_id"],
        "source_scenario_sha256": binding["source_scenario_projection_sha256"],
        "source_action_ids": sorted(record["id"] for record in source["source_actions"]),
        "source_file_path": binding["scenario_source_path"],
        "template_asset_id": binding["template_asset_id"],
        "template_record_sha256": binding["template_record_sha256"],
        "content_registry_merkle_root": binding["content_registry_merkle_root"],
        "patient": source["patient"],
        "source_actions": source["source_actions"],
        "end_conditions": source["end_conditions"],
    }
    return {**payload, "snapshot_sha256": sha256_canonical(payload)}


def certificate_checks(session: dict[str, Any], spec: dict[str, Any], source: dict[str, Any], ledger: dict[str, Any]) -> dict[str, bool]:
    transitions = session["transitions"]
    required = required_source_ids(spec, source)
    diagnostics_sequence = next((t["sequence"] for t in transitions if t.get("event_id") == "diagnostics_ready"), None)
    handoff = next((t for t in transitions if t.get("action_id") == "complete_handoff"), None)
    allowed = {actor["actor_id"]: set(actor.get("initial_knowledge", [])) for actor in spec["actors"]}
    for record in [*spec["actions"], *spec["events"]]:
        for actor, tokens in record.get("knowledge_grants", {}).items():
            allowed.setdefault(actor, set()).update(tokens)
    actor_ok = all(set(session["final_state"]["actor_knowledge"][actor]) <= allowed.get(actor, set()) for actor in ACTOR_IDS)
    chain_ok = True
    previous = state_hash(session["initial_state"])
    for transition in transitions:
        if transition["before_state_sha256"] != previous or transition["after_state_sha256"] != state_hash(transition["state_after"]):
            chain_ok = False
        previous = transition["after_state_sha256"]
    chain_ok = chain_ok and previous == state_hash(session["final_state"])
    hidden_ok = True
    for transition in transitions:
        if transition["state_after"]["revealed_hidden_findings"] and (diagnostics_sequence is None or transition["sequence"] < diagnostics_sequence):
            hidden_ok = False
    timeout_ok = session["final_state"]["terminal_status"] != "timeout" or (
        transitions[-1]["kind"] == "system_event"
        and transitions[-1]["event_id"] == "timeout_reached"
        and transitions[-1]["state_after"]["terminal_status"] == "timeout"
    )
    return {
        "source_binding_matches": session["source_binding"]["source_scenario_id"] == source["scenario_id"],
        "source_action_subset_preserved": set(session["final_state"]["completed_source_action_ids"]) <= set(session["source_binding"]["source_action_ids"]),
        "required_source_actions_complete": session["final_state"]["terminal_status"] != "completed" or all(value in session["final_state"]["completed_source_action_ids"] for value in required),
        "unsafe_source_actions_fail_closed": not session["final_state"]["unsafe_source_action_ids"] or session["final_state"]["terminal_status"] == "failed",
        "diagnostics_precede_hidden_findings": hidden_ok,
        "terminal_handoff_reached": session["final_state"]["terminal_status"] != "completed" or bool(handoff and diagnostics_sequence is not None and handoff["sequence"] > diagnostics_sequence),
        "patient_care_use_prohibited": session["authority"]["patient_care_use"] == "PROHIBITED",
        "wit_observations_process_only": all(t["wit_observation"]["process_only"] is True and t["wit_observation"]["clinical_directive"] is None for t in transitions),
        "replay_chain_complete": chain_ok and transitions[-1]["state_after"] == session["final_state"],
        "timeout_is_event_sourced": timeout_ok,
        "transition_states_bound": chain_ok,
        "score_within_bounds": 0 <= session["normalized_score_bps"] <= 10_000,
        "actor_knowledge_authorized": actor_ok,
        "uncalibrated_parameters_disclosed": all(p["calibration_status"] in {"NOT_CALIBRATED", "SOURCE_BOUND"} for p in spec["parameters"].values()) and any(r["origin_class"] == "exercise_assumption" for r in ledger["records"]),
    }


def build_session(
    spec: dict[str, Any],
    source: dict[str, Any],
    binding: dict[str, Any],
    ledger: dict[str, Any],
    command_sequence: list[str] | None = None,
    command_prefix: str = 'canonical',
) -> dict[str, Any]:
    initial = initial_state(spec, source)
    transitions: list[dict[str, Any]] = []
    current = process_events(initial, spec, source, transitions, None)
    actions = {record["action_id"]: record for record in spec["actions"]}
    receipts: list[dict[str, Any]] = []
    sequence = command_sequence if command_sequence is not None else list(spec["canonical_command_sequence"])
    for index, action_id in enumerate(sequence, start=1):
        command = {
            "command_id": f"{command_prefix}-{index:02d}-{action_id}",
            "action_id": action_id,
            "expected_revision": current["revision"],
        }
        first = len(transitions) + 1
        current = apply_action(current, actions[action_id], command, spec, source, transitions)
        if current["terminal_status"] == "active":
            current = process_events(current, spec, source, transitions, action_id)
        final = len(transitions)
        receipts.append({
            "command_id": command["command_id"],
            "action_id": action_id,
            "command_sha256": sha256_canonical(command),
            "first_transition_sequence": first if first <= final else None,
            "final_transition_sequence": final if first <= final else None,
        })
    receipts.sort(key=lambda record: record["command_id"])
    base = {
        "schema_version": "1.1.0",
        "example_id": spec["example_id"],
        "title": "Post-CUF/TFC blast casualty reception at a constrained base clinic",
        "facility_profile": spec["profile_id"],
        "care_continuum_phase": spec["care_continuum_phase"],
        "authority": spec["authority"],
        "source_binding": source_binding(source, binding),
        "spec_sha256": sha256_canonical(spec),
        "initial_patient_snapshot": {
            "presentation": source["patient"]["initial_presentation"],
            "vitals": source["patient"]["initial_vitals"],
            "hidden_findings_count": len(source["patient"]["hidden_findings"]),
        },
        "initial_state": initial,
        "transitions": transitions,
        "command_receipts": receipts,
        "final_state": current,
        "normalized_score_bps": normalized_score_bps(current),
    }
    provisional = {**base, "certificate": {}}
    checks = certificate_checks(provisional, spec, source, ledger)
    certificate = {
        "certificate_version": "1.0.0",
        "source_binding_sha256": sha256_canonical(base["source_binding"]),
        "spec_sha256": sha256_canonical(spec),
        "initial_state_sha256": state_hash(initial),
        "final_state_sha256": state_hash(current),
        "transition_root_sha256": merkle_root(t["after_state_sha256"] for t in transitions),
        "replay_root_sha256": sha256_canonical({
            "initial_state": initial,
            "transitions": [{
                "transition_id": t["transition_id"],
                "before_state_sha256": t["before_state_sha256"],
                "after_state_sha256": t["after_state_sha256"],
            } for t in transitions],
            "final_state": current,
        }),
        "claim_ledger_sha256": ledger["ledger_sha256"],
        "checks": checks,
        "session_sha256": sha256_canonical(base),
    }
    return {**base, "certificate": certificate}


def build_aar(session: dict[str, Any], spec: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    required = required_source_ids(spec, source)
    optional = sorted(record["id"] for record in source["source_actions"] if record["priority"] == "optional")
    required_done = [value for value in required if value in session["final_state"]["completed_source_action_ids"]]
    optional_done = [value for value in optional if value in session["final_state"]["completed_source_action_ids"]]
    required_missing = [value for value in required if value not in required_done]
    optional_missing = [value for value in optional if value not in optional_done]
    strengths: list[str] = []
    improvements: list[str] = []
    if not required_missing:
        strengths.append("All required source-template actions were completed.")
    else:
        improvements.append(f"Complete missing required source actions: {', '.join(required_missing)}.")
    if not session["final_state"]["unsafe_source_action_ids"]:
        strengths.append("No source-defined unsafe action was selected.")
    else:
        improvements.append(f"Avoid unsafe source actions: {', '.join(session['final_state']['unsafe_source_action_ids'])}.")
    if "diagnostics_ready" in session["final_state"]["fired_system_events"]:
        strengths.append("Diagnostic results were processed through an explicit system event before disclosure.")
    if session["final_state"]["terminal_status"] != "completed":
        improvements.append("Reach a closed-loop receiving handoff before timeout or failure.")
    if optional_missing:
        improvements.append(f"Optional source objectives not exercised: {', '.join(optional_missing)}.")
    payload = {
        "schema_version": "1.1.0",
        "example_id": session["example_id"],
        "session_sha256": session["certificate"]["session_sha256"],
        "terminal_status": session["final_state"]["terminal_status"],
        "normalized_score_bps": session["normalized_score_bps"],
        "passed": session["final_state"]["terminal_status"] == "completed" and session["normalized_score_bps"] >= int(spec["parameters"]["pass_threshold_bps"]["value"]),
        "pass_threshold_bps": int(spec["parameters"]["pass_threshold_bps"]["value"]),
        "source_action_coverage": {
            "required_completed": required_done,
            "required_missing": required_missing,
            "optional_completed": optional_done,
            "optional_not_exercised": optional_missing,
        },
        "strengths": strengths,
        "improvement_opportunities": improvements,
        "wit_observation_summary": [transition["wit_observation"] for transition in session["transitions"]],
        "counterfactual_boundaries": {
            "available_branches": ["unsafe_discharge", "unsafe_tourniquet_removal", "source_bound_timeout"],
            "causal_claims_allowed": False,
            "note": "Alternative branches are deterministic replay comparisons. They are not identified causal effects.",
        },
        "validity_ledger": {
            "demonstrated": [
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
            ],
            "open": [
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
            ],
        },
    }
    return {**payload, "aar_sha256": sha256_canonical(payload)}


def build_readme(repo: Path, session: dict[str, Any], aar: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {t['sequence']} | {t['completed_at_seconds']}s | {t['kind']} | {str(t['label']).replace('|', r'\|')} |"
        for t in session["transitions"]
    )
    open_items = "\n".join(f"- {value}" for value in aar["validity_ledger"]["open"])
    return (
        "# Facility-arrival canonical interactive scenario\n\n"
        "[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request.\n\n"
        "## Four playable offline role-model teamwork challenges\n\n"
        "The single offline file includes four selectable, fully playable role-model examples. Each profile keeps the same source-bound clinical template and changes only the operational teamwork route:\n\n"
        "- **Direct handoff baseline** — complete the normal closed-loop receiving workflow.\n"
        "- **Communications relay** — establish an intermediate relay and confirm receipt before the final handoff.\n"
        "- **Resource coordination** — coordinate a constrained resource and confirm ownership before the final handoff.\n"
        "- **Relay and resource coordination** — establish the relay first, then coordinate the constrained resource, then close the handoff.\n\n"
        "Open `playable.html`, choose a challenge at the top, and use manual actions, **Watch autoplay**, or **Complete canonical replay**. Relay and resource actions carry zero clinical points. They are structural training behaviors, not clinically calibrated timing or treatment authority.\n\n"
        "This is the current start-to-finish Project Asklepios example for the **post-CUF/TFC receiving phase**. "
        "It begins when a field-stabilized casualty arrives at a constrained base clinic and ends with a closed-loop transfer to the next level of care.\n\n"
        f"- Browser route: [`/examples/facility-arrival`](/examples/facility-arrival)\n"
        f"- Source template: `{session['source_binding']['source_scenario_id']}`\n"
        f"- Facility profile: `{session['facility_profile']}`\n"
        f"- Terminal status: `{session['final_state']['terminal_status']}`\n"
        f"- Score: `{session['normalized_score_bps'] / 100:.2f}%`\n"
        f"- Session SHA-256: `{session['certificate']['session_sha256']}`\n"
        f"- Content-registry root: `{session['source_binding']['content_registry_merkle_root']}`\n\n"
        f"{render_evolution_block(repo)}\n"
        "## Complete simulated learner interaction\n\n"
        "| Seq | Time | Type | Interaction |\n|---:|---:|---|---|\n"
        f"{rows}\n\n"
        "## Alternate branches\n\n"
        "The interactive page can also produce an explicit source-bound timeout, unsafe discharge failure, and unsafe tourniquet-action failure. Each branch is event-sourced and independently replayable.\n\n"
        "## WIT and learner separation\n\n"
        "WIT observations remain process-only and carry no clinical directive or clinical points. Hidden source findings remain unavailable to the learner until the authenticated diagnostics-ready event occurs.\n\n"
        "## Evidence and calibration boundary\n\n"
        "Clinical actions and points come only from the inherited ASK-D-001 repository template. The JTS and USAF records in `source-truth.json` frame continuum-of-care and inspection-process scope; they are not used as a hidden clinical-rule generator. Diagnostic timing and the pass threshold are explicitly marked `NOT_CALIBRATED` exercise-design values.\n\n"
        "## Rebuild and verify\n\n"
        "```bash\n"
        "npm run generate:facility-arrival\n"
        "npm run verify:facility-arrival\n"
        "python3 scripts/check_facility_arrival_example.py --repo .\n"
        "node scripts/check_facility_arrival_example.mjs --repo .\n"
        "```\n\n"
        "## Open validity obligations\n\n"
        f"{open_items}\n"
    )


def generate(repo: Path) -> dict[str, str]:
    spec = json.loads((repo / SPEC_PATH).read_text(encoding="utf-8"))
    binding = json.loads((repo / BINDING_PATH).read_text(encoding="utf-8"))
    source = reconstruct_source_snapshot(repo)
    ledger = build_claim_ledger(spec)
    truth = build_source_truth()
    snapshot = build_source_snapshot(source, binding)
    session = build_session(spec, source, binding, ledger)
    aar = build_aar(session, spec, source)
    readme = build_readme(repo, session, aar)

    generated = {
        "interaction.json": pretty_json(session),
        "aar.json": pretty_json(aar),
        "claim-ledger.json": pretty_json(ledger),
        "source-snapshot.json": pretty_json(snapshot),
        "source-truth.json": pretty_json(truth),
        "README.md": readme.rstrip() + "\n",
    }
    hashes = {name: file_sha256_bytes(content.encode("utf-8")) for name, content in generated.items()}
    manifest_payload = {
        "schema_version": "1.1.0",
        "example_id": session["example_id"],
        "title": session["title"],
        "browser_route": "/examples/facility-arrival",
        "care_continuum_phase": session["care_continuum_phase"],
        "authority": session["authority"],
        "source_binding": session["source_binding"],
        "certificate": session["certificate"],
        "counts": {
            "transitions": len(session["transitions"]),
            "learner_actions": sum(t["kind"] == "learner_action" for t in session["transitions"]),
            "system_events": sum(t["kind"] == "system_event" for t in session["transitions"]),
            "wit_observations": len(session["transitions"]),
            "claim_records": len(ledger["records"]),
            "demonstrated_gates": len(aar["validity_ledger"]["demonstrated"]),
            "open_gates": len(aar["validity_ledger"]["open"]),
        },
        "files": {
            "interaction": "interaction.json",
            "aar": "aar.json",
            "claim_ledger": "claim-ledger.json",
            "source_snapshot": "source-snapshot.json",
            "source_truth": "source-truth.json",
            "documentation": "README.md",
        },
        "hashes": {
            "interaction_sha256": hashes["interaction.json"],
            "aar_sha256": hashes["aar.json"],
            "claim_ledger_sha256": hashes["claim-ledger.json"],
            "source_snapshot_sha256": hashes["source-snapshot.json"],
            "source_truth_sha256": hashes["source-truth.json"],
            "documentation_sha256": hashes["README.md"],
        },
        "generated_from": {
            "spec_path": str(SPEC_PATH),
            "spec_sha256": sha256_canonical(spec),
            "source_path": binding["scenario_source_path"],
            "source_snapshot_sha256": snapshot["snapshot_sha256"],
            "content_registry_root": binding["content_registry_merkle_root"],
        },
    }
    manifest = {**manifest_payload, "manifest_sha256": sha256_canonical(manifest_payload)}
    generated["manifest.json"] = pretty_json(manifest)
    return generated


def write_or_check(repo: Path, generated: dict[str, str], check: bool) -> list[str]:
    mismatches: list[str] = []
    example = repo / EXAMPLE_DIR
    public = repo / PUBLIC_DIR
    if not check:
        example.mkdir(parents=True, exist_ok=True)
        public.mkdir(parents=True, exist_ok=True)
    for name, content in generated.items():
        destination = example / name
        if check:
            if not destination.exists() or destination.read_text(encoding="utf-8") != content:
                mismatches.append(str(destination.relative_to(repo)))
        else:
            destination.write_bytes(content.encode("utf-8"))
    public_map = {
        "reference-session.json": generated["interaction.json"],
        "reference-aar.json": generated["aar.json"],
        "reference-manifest.json": generated["manifest.json"],
    }
    for name, content in public_map.items():
        destination = public / name
        if check:
            if not destination.exists() or destination.read_text(encoding="utf-8") != content:
                mismatches.append(str(destination.relative_to(repo)))
        else:
            destination.write_bytes(content.encode("utf-8"))
    return sorted(mismatches)


def _attestation_sha256(report: dict[str, Any]) -> str:
    payload = dict(report)
    payload.pop("attestation_sha256", None)
    return sha256_canonical(payload)


def _artifact_inventory(repo: Path, generated: dict[str, str]) -> dict[str, str]:
    expected: dict[str, str] = {}
    for name, content in generated.items():
        expected[(EXAMPLE_DIR / name).as_posix()] = sha256_text(content)
    expected[(PUBLIC_DIR / "reference-session.json").as_posix()] = sha256_text(generated["interaction.json"])
    expected[(PUBLIC_DIR / "reference-aar.json").as_posix()] = sha256_text(generated["aar.json"])
    expected[(PUBLIC_DIR / "reference-manifest.json").as_posix()] = sha256_text(generated["manifest.json"])
    return dict(sorted(expected.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    repo = args.repo.resolve()
    generated = generate(repo)
    mismatches = write_or_check(repo, generated, args.check)
    inventory = _artifact_inventory(repo, generated)
    for relative, expected_hash in inventory.items():
        path = repo / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            if relative not in mismatches:
                mismatches.append(relative)
    mismatches = sorted(set(mismatches))
    report: dict[str, Any] = {
        "schema_version": "1.1.0",
        "status": "PASS" if not mismatches else "FAIL",
        "mode": "check" if args.check else "write",
        "attestation_kind": "verification" if args.check else "generation",
        "files": len(inventory),
        "file_sha256": inventory,
        "mismatches": mismatches,
        "example_id": json.loads(generated["manifest.json"])["example_id"],
        "session_sha256": json.loads(generated["interaction.json"])["certificate"]["session_sha256"],
    }
    report["attestation_sha256"] = _attestation_sha256(report)
    default_output = VERIFICATION_REPORT if args.check else GENERATION_REPORT
    output = repo / (args.output or default_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pretty_json(report).encode("utf-8"))
    print(pretty_json(report), end="")
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
