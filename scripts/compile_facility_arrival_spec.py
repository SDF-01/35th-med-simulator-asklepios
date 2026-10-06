#!/usr/bin/env python3
"""Validate and deterministically compile the facility-arrival JSON specification.

The JSON file is the sole editable operational specification.  The generated
TypeScript module is a byte-for-byte projection of the validated JSON and must
never be edited independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SOURCE = Path("config/facility-arrival/ASK-D-001.json")
TARGET = Path("src/facility-arrival/specification.generated.ts")
REPORT = Path("reports/facility-arrival-spec-compiler.json")
SAFE_INTEGER = 9_007_199_254_740_991
ACTORS = {"receiving_provider", "clinic_nurse", "diagnostics_tech", "wit_observer"}
TERMINALS = {None, "completed", "failed", "timeout"}
PHASES = {None, "pre_arrival", "reception", "assessment", "diagnostics_pending", "results_review", "disposition", "complete"}

class SpecError(ValueError):
    pass

def canonical(value: Any) -> str:
    def validate(item: Any, path: str = "$") -> None:
        if item is None or isinstance(item, (str, bool)):
            return
        if isinstance(item, int) and not isinstance(item, bool):
            if abs(item) > SAFE_INTEGER:
                raise SpecError(f"unsafe integer at {path}")
            return
        if isinstance(item, float):
            raise SpecError(f"floating-point value forbidden at {path}")
        if isinstance(item, list):
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise SpecError(f"non-string key at {path}")
                validate(child, f"{path}.{key}")
            return
        raise SpecError(f"unsupported JSON value at {path}: {type(item).__name__}")
    validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition: bool, message: str) -> None:
    if not condition:
        raise SpecError(message)

def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    require(set(value) == expected, f"{label} keys differ:{sorted(set(value) ^ expected)}")

def validate_spec(spec: dict[str, Any]) -> None:
    _exact_keys(spec, {
        "schema_version", "profile_id", "example_id", "title", "source_scenario_id",
        "care_continuum_phase", "authority", "parameters", "actors", "actions", "events",
        "completion", "canonical_command_sequence", "sequence_assurance",
    }, "top-level")
    require(spec["schema_version"] == "1.1.0", "unsupported schema")
    require(spec["source_scenario_id"] == "ASK-D-001", "source scenario must be ASK-D-001")
    require(spec["example_id"] == "ASK-FACILITY-ARRIVAL-RC3-3", "example ID mismatch")
    require(spec["care_continuum_phase"] == "post_cuf_tfc_facility_reception", "care phase mismatch")
    require(spec["authority"] == {
        "deployment_scope": "production_training_reference",
        "patient_care_use": "PROHIBITED",
        "clinical_content_mode": "INHERITED_REPOSITORY_TEMPLATE",
        "operational_content_mode": "DETERMINISTIC_EXERCISE_ORCHESTRATION",
        "evidence_mode": "IDENTITY_AND_SCOPE_ONLY",
        "automatic_clinical_rule_generation": False,
    }, "authority boundary differs")

    parameters = spec["parameters"]
    require(set(parameters) == {"diagnostic_delay_seconds", "pass_threshold_bps", "timeout_seconds"}, "parameter inventory differs")
    for name, parameter in parameters.items():
        _exact_keys(parameter, {"value", "unit", "origin", "calibration_status", "note"}, f"parameter:{name}")
        require(isinstance(parameter["value"], int), f"parameter must be integer:{name}")
        require(parameter["value"] >= 0, f"parameter negative:{name}")
        require(parameter["calibration_status"] in {"NOT_CALIBRATED", "SOURCE_BOUND"}, f"calibration status invalid:{name}")
        require(parameter["origin"] in {"exercise_assumption", "exercise_policy", "source_template"}, f"parameter origin invalid:{name}")
    require(parameters["diagnostic_delay_seconds"]["calibration_status"] == "NOT_CALIBRATED", "diagnostic delay may not claim calibration")
    require(parameters["pass_threshold_bps"]["calibration_status"] == "NOT_CALIBRATED", "pass threshold may not claim calibration")
    require(parameters["timeout_seconds"]["calibration_status"] == "SOURCE_BOUND", "timeout must remain source-bound")
    require(0 <= parameters["pass_threshold_bps"]["value"] <= 10_000, "pass threshold out of bounds")
    require(parameters["timeout_seconds"]["value"] > parameters["diagnostic_delay_seconds"]["value"], "timeout must exceed diagnostic delay")

    actors = spec["actors"]
    require(isinstance(actors, list) and len(actors) == len(ACTORS), "actor count differs")
    actor_ids: set[str] = set()
    for actor in actors:
        _exact_keys(actor, {"actor_id", "role", "initial_knowledge"}, "actor")
        actor_id = actor["actor_id"]
        require(actor_id in ACTORS, f"unknown actor:{actor_id}")
        require(actor_id not in actor_ids, f"duplicate actor:{actor_id}")
        actor_ids.add(actor_id)
        require(isinstance(actor["initial_knowledge"], list) and all(isinstance(x, str) for x in actor["initial_knowledge"]), f"invalid actor knowledge:{actor_id}")
    require(actor_ids == ACTORS, "actor inventory differs")

    actions = spec["actions"]
    require(isinstance(actions, list) and len(actions) >= 15, "action inventory too small")
    action_ids: set[str] = set()
    for action in actions:
        _exact_keys(action, {
            "action_id", "label", "origin", "source_action_id", "duration_mode", "duration_seconds",
            "repeatable", "prerequisites", "required_event_ids", "phase_after", "knowledge_grants",
            "wit_category", "terminal_effect", "clinical_detail_policy",
        }, f"action:{action.get('action_id')}")
        action_id = action["action_id"]
        require(re.fullmatch(r"[a-z0-9_]+", action_id) is not None, f"invalid action ID:{action_id}")
        require(action_id not in action_ids, f"duplicate action:{action_id}")
        action_ids.add(action_id)
        require(action["origin"] in {"source_template", "operational_workflow"}, f"unknown origin:{action_id}")
        if action["origin"] == "operational_workflow":
            require(action["source_action_id"] is None, f"operational action has source binding:{action_id}")
        else:
            require(isinstance(action["source_action_id"], str) and action["source_action_id"], f"source action lacks binding:{action_id}")
        require(action["duration_mode"] in {"fixed", "until_diagnostics"}, f"unknown duration mode:{action_id}")
        require(isinstance(action["duration_seconds"], int) and action["duration_seconds"] >= 0, f"invalid duration:{action_id}")
        if action["duration_mode"] == "until_diagnostics":
            require(action["duration_seconds"] == 0, f"until_diagnostics must not add an independent duration:{action_id}")
        require(action["phase_after"] in PHASES, f"unknown phase:{action_id}")
        require(action["terminal_effect"] in TERMINALS, f"unknown terminal effect:{action_id}")
        require(set(action["knowledge_grants"]).issubset(ACTORS), f"unknown knowledge-grant actor:{action_id}")
        require(all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in action["knowledge_grants"].values()), f"invalid grants:{action_id}")
        if action_id == "pain_management":
            require(action["clinical_detail_policy"] == "NO_GENERATED_DRUG_DOSE_OR_ROUTE", "pain-management boundary missing")
        else:
            require(action["clinical_detail_policy"] is None, f"unexpected clinical detail policy:{action_id}")

    for action in actions:
        require(set(action["prerequisites"]).issubset(action_ids), f"unknown prerequisite:{action['action_id']}")
        require(action["action_id"] not in action["prerequisites"], f"self prerequisite:{action['action_id']}")

    events = spec["events"]
    event_ids: set[str] = set()
    for event in events:
        _exact_keys(event, {"event_id", "label", "trigger", "knowledge_grants", "reveal_source_hidden_findings", "terminal_effect", "wit_category"}, f"event:{event.get('event_id')}")
        event_id = event["event_id"]
        require(event_id not in event_ids, f"duplicate event:{event_id}")
        event_ids.add(event_id)
        require(event["terminal_effect"] in TERMINALS, f"invalid event terminal:{event_id}")
        require(set(event["knowledge_grants"]).issubset(ACTORS), f"unknown event-grant actor:{event_id}")
        trigger = event["trigger"]
        require(trigger.get("kind") in {"initial", "after_action", "elapsed_time_due", "diagnostics_due", "timeout_due"}, f"unknown trigger:{event_id}")
        if trigger["kind"] == "after_action":
            require(set(trigger) == {"kind", "action_id"} and trigger["action_id"] in action_ids, f"invalid after_action trigger:{event_id}")
        elif trigger["kind"] == "elapsed_time_due":
            require(set(trigger) == {"kind", "at_elapsed_seconds"}, f"unexpected elapsed_time_due fields:{event_id}")
            require(isinstance(trigger["at_elapsed_seconds"], int) and not isinstance(trigger["at_elapsed_seconds"], bool), f"invalid elapsed_time_due time:{event_id}")
            require(0 <= trigger["at_elapsed_seconds"] <= spec["parameters"]["timeout_seconds"]["value"], f"elapsed_time_due outside scenario clock:{event_id}")
        else:
            require(set(trigger) == {"kind"}, f"unexpected trigger fields:{event_id}")
    require(event_ids == {"prearrival_notice", "second_casualty_inbound", "diagnostics_ready", "timeout_reached"}, "event inventory differs")
    second_casualty_event = next(e for e in events if e["event_id"] == "second_casualty_inbound")
    require(second_casualty_event["trigger"] == {"kind": "elapsed_time_due", "at_elapsed_seconds": 240}, "second-casualty event must remain clock-driven and uncalibrated at the reviewed exercise time")
    hidden_events = [e["event_id"] for e in events if e["reveal_source_hidden_findings"]]
    require(hidden_events == ["diagnostics_ready"], "only diagnostics_ready may reveal source hidden findings")
    timeout_event = next(e for e in events if e["event_id"] == "timeout_reached")
    require(timeout_event["terminal_effect"] == "timeout" and timeout_event["trigger"] == {"kind": "timeout_due"}, "timeout event not fail-closed")

    completion = spec["completion"]
    _exact_keys(completion, {"required_source_action_priorities", "required_operational_actions", "required_event_ids"}, "completion")
    require(completion["required_source_action_priorities"] == ["critical", "important"], "required source priorities differ")
    require(set(completion["required_operational_actions"]).issubset(action_ids), "unknown completion action")
    require(set(completion["required_event_ids"]).issubset(event_ids), "unknown completion event")
    require("complete_handoff" in completion["required_operational_actions"], "handoff not required")

    canonical_sequence = spec["canonical_command_sequence"]
    require(canonical_sequence and canonical_sequence[-1] == "complete_handoff", "canonical path must end with handoff")
    require(set(canonical_sequence).issubset(action_ids), "canonical path references unknown action")
    require(len(canonical_sequence) == len(set(canonical_sequence)), "canonical path duplicates a nonrepeatable action")
    require({"pain_management", "documentation", "confirm_surge_roles"}.issubset(canonical_sequence), "canonical ideal path omits reviewed objectives")

    triples = spec["sequence_assurance"]["selected_three_event_sequences"]
    require(isinstance(triples, list) and len(triples) >= 7, "selected sequence triples missing")
    require(all(isinstance(item, list) and len(item) == 3 and all(isinstance(x, str) for x in item) for item in triples), "invalid selected sequence triple")
    canonical(spec)

def render(spec: dict[str, Any]) -> tuple[str, str]:
    digest = sha256(canonical(spec))
    pretty = json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=True)
    text = (
        "/* AUTO-GENERATED by scripts/compile_facility_arrival_spec.py. DO NOT EDIT. */\n"
        "import type { FacilityArrivalSpec } from './types';\n\n"
        f"export const FACILITY_ARRIVAL_SPEC_SHA256 = '{digest}' as const;\n"
        "export const FACILITY_ARRIVAL_SPEC = " + pretty + " as FacilityArrivalSpec;\n"
    )
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n", digest

def compile_spec(repo: Path, check: bool) -> dict[str, Any]:
    source = repo / SOURCE
    target = repo / TARGET
    spec = json.loads(source.read_text(encoding="utf-8"))
    require(isinstance(spec, dict), "specification must be an object")
    validate_spec(spec)
    expected, digest = render(spec)
    mismatches: list[str] = []
    if check:
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            mismatches.append(str(TARGET))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8", newline="\n")
    source_file_sha256 = sha256_file(source)
    expected_target_sha256 = sha256(expected)
    target_file_sha256 = sha256_file(target) if target.is_file() else None
    report = {
        "schema_version": "1.2.0",
        "status": "PASS" if not mismatches else "FAIL",
        "mode": "check" if check else "write",
        "attestation_kind": "verification" if check else "generation",
        "source": str(SOURCE),
        "target": str(TARGET),
        "source_file_sha256": source_file_sha256,
        "spec_sha256": digest,
        "expected_target_sha256": expected_target_sha256,
        "target_file_sha256": target_file_sha256,
        "actors": len(spec["actors"]),
        "actions": len(spec["actions"]),
        "events": len(spec["events"]),
        "selected_sequence_triples": len(spec["sequence_assurance"]["selected_three_event_sequences"]),
        "mismatches": mismatches,
    }
    attested = dict(report)
    report["attestation_sha256"] = sha256(canonical(attested))
    # Only check mode emits the durable verification attestation. Generation
    # may run repeatedly during builds and must never overwrite evidence that
    # a later release join relies on.
    if check:
        report_path = repo / REPORT
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = compile_spec(args.repo.resolve(), args.check)
    except (OSError, json.JSONDecodeError, SpecError, KeyError, TypeError) as exc:
        report = {
            "schema_version": "1.2.0",
            "status": "FAIL",
            "mode": "check" if args.check else "write",
            "attestation_kind": "verification" if args.check else "generation",
            "errors": [str(exc)],
        }
        if args.check:
            output = args.repo.resolve() / REPORT
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
