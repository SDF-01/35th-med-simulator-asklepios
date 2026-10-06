#!/usr/bin/env python3
"""Bounded state exploration with an independently implemented abstract reducer."""
from __future__ import annotations

import argparse
import collections
import copy
import json
from pathlib import Path
from typing import Any

from build_facility_arrival_example import (
    BINDING_PATH,
    SPEC_PATH,
    apply_action as concrete_apply_action,
    build_claim_ledger,
    build_session,
    process_events as concrete_process_events,
    reconstruct_source_snapshot,
)
from facility_arrival_verifier import ACTOR_IDS, diagnostics_due_at, initial_state, normalize_state, required_source_ids

REPORT = Path("reports/facility-arrival-state-exploration.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def semantic_key(state: dict[str, Any]) -> str:
    """Quotient representation-only history while retaining every future-relevant guard.

    Action and source completion timestamps other than the two diagnostic order
    times do not influence any current transition rule. Actor knowledge and alert
    text are deterministic projections of the completed actions/events and are
    checked independently by the concrete replay verifiers, so they are not part
    of this reachability quotient.
    """
    value = normalize_state(state)
    projection = {
        "elapsed_seconds": value["elapsed_seconds"],
        "phase": value["phase"],
        "terminal_status": value["terminal_status"],
        "completed_action_ids": value["completed_action_ids"],
        "completed_source_action_ids": value["completed_source_action_ids"],
        "unsafe_source_action_ids": value["unsafe_source_action_ids"],
        "fired_system_events": value["fired_system_events"],
        "revealed_hidden_findings": value["revealed_hidden_findings"],
        "score_points": value["score_points"],
        "imaging_completed_at": value["action_completed_at"].get("order_imaging"),
        "labs_completed_at": value["action_completed_at"].get("order_labs"),
    }
    return json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def source_map(source: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {value["id"]: value for value in source["source_actions"]}


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


def duration(state: dict[str, Any], action: dict[str, Any], spec: dict[str, Any]) -> int | None:
    if action["duration_mode"] == "fixed":
        return int(action["duration_seconds"])
    due = diagnostics_due_at(state, spec)
    return None if due is None else max(0, due - int(state["elapsed_seconds"]))


def enabled_actions(state: dict[str, Any], spec: dict[str, Any], source: dict[str, Any]) -> list[str]:
    if state["terminal_status"] != "active":
        return []
    source_actions = source_map(source)
    timeout = int(spec["parameters"]["timeout_seconds"]["value"])
    enabled: list[str] = []
    for action in spec["actions"]:
        action_id = action["action_id"]
        current_duration = duration(state, action, spec)
        conditions = [
            action["repeatable"] or action_id not in state["completed_action_ids"],
            all(value in state["completed_action_ids"] for value in action["prerequisites"]),
            all(value in state["fired_system_events"] for value in action.get("required_event_ids", [])),
            (
                action["origin"] == "operational_workflow" and action["source_action_id"] is None
            ) or (
                action["origin"] == "source_template" and action["source_action_id"] in source_actions
            ),
            current_duration is not None,
            current_duration is not None and (
                int(state["elapsed_seconds"]) + current_duration <= timeout or action_id == "wait_60"
            ),
            action_id != "complete_handoff" or completion_met(state, spec, source),
        ]
        if all(conditions):
            enabled.append(action_id)
    return sorted(enabled)


def grant(state: dict[str, Any], grants: dict[str, Any]) -> None:
    for actor in ACTOR_IDS:
        state["actor_knowledge"][actor].extend(grants.get(actor, []))


def abstract_event(state: dict[str, Any], event: dict[str, Any], source: dict[str, Any], event_time: int | None = None) -> dict[str, Any]:
    after = copy.deepcopy(normalize_state(state))
    if event_time is not None:
        after["elapsed_seconds"] = event_time
    after["revision"] += 1
    after["fired_system_events"].append(event["event_id"])
    grant(after, event.get("knowledge_grants", {}))
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
    return normalize_state(after)


def process_abstract_events(
    state: dict[str, Any], spec: dict[str, Any], source: dict[str, Any], just_action: str | None
) -> dict[str, Any]:
    current = normalize_state(state)
    for event in spec["events"]:
        if event["event_id"] in current["fired_system_events"]:
            continue
        trigger = event["trigger"]
        should_fire = False
        if trigger["kind"] == "initial":
            should_fire = current["revision"] == 0
        elif trigger["kind"] == "after_action":
            should_fire = just_action == trigger["action_id"]
        elif trigger["kind"] == "elapsed_time_due":
            should_fire = current["elapsed_seconds"] >= trigger["at_elapsed_seconds"]
        elif trigger["kind"] == "diagnostics_due":
            due = diagnostics_due_at(current, spec)
            should_fire = due is not None and current["elapsed_seconds"] >= due
        elif trigger["kind"] == "timeout_due":
            should_fire = current["elapsed_seconds"] >= spec["parameters"]["timeout_seconds"]["value"] and current["terminal_status"] == "active"
        if should_fire:
            current = abstract_event(current, event, source)
    return current


def abstract_step(state: dict[str, Any], action_id: str, spec: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    action = next(value for value in spec["actions"] if value["action_id"] == action_id)
    before = normalize_state(state)
    current_duration = duration(before, action, spec)
    if current_duration is None:
        raise ValueError("duration unavailable")
    timeout = int(spec["parameters"]["timeout_seconds"]["value"])
    if before["elapsed_seconds"] + current_duration > timeout:
        event = next(value for value in spec["events"] if value["event_id"] == "timeout_reached")
        return abstract_event(before, event, source, timeout)
    after = copy.deepcopy(before)
    after["revision"] += 1
    after["elapsed_seconds"] += current_duration
    after["completed_action_ids"].append(action_id)
    after["action_completed_at"][action_id] = after["elapsed_seconds"]
    if action.get("phase_after") is not None:
        after["phase"] = action["phase_after"]
    grant(after, action.get("knowledge_grants", {}))
    if action.get("source_action_id"):
        record = source_map(source)[action["source_action_id"]]
        after["score_points"] += int(record["points"])
        after["completed_source_action_ids"].append(record["id"])
        after["source_action_completed_at"][record["id"]] = after["elapsed_seconds"]
        if record["priority"] == "unsafe":
            after["unsafe_source_action_ids"].append(record["id"])
    if action_id == "review_diagnostics":
        after["alerts"].append("Diagnostic results reviewed and casualty reassessed.")
    if action_id == "pain_management":
        after["alerts"].append("Source-defined pain-management objective addressed without generating a drug, dose, or route.")
    if action.get("terminal_effect"):
        after["terminal_status"] = action["terminal_effect"]
        after["phase"] = "complete"
        after["outcome"] = (
            "Closed-loop receiving handoff completed."
            if action["terminal_effect"] == "completed"
            else f"Unsafe source action selected: {action['label']}"
        )
    return process_abstract_events(normalize_state(after), spec, source, action_id)


def concrete_step(state: dict[str, Any], action_id: str, spec: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    action = next(value for value in spec["actions"] if value["action_id"] == action_id)
    transitions: list[dict[str, Any]] = []
    command = {"command_id": f"differential-{state['revision']}-{action_id}", "action_id": action_id, "expected_revision": state["revision"]}
    current = concrete_apply_action(state, action, command, spec, source, transitions)
    if current["terminal_status"] == "active":
        current = concrete_process_events(current, spec, source, transitions, action_id)
    return current


def terminal_witnesses(spec: dict[str, Any], source: dict[str, Any], binding: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    cases = {
        "completed": spec["canonical_command_sequence"],
        "failed_unsafe_discharge": ["receive_handoff", "discharge_without_workup"],
        "failed_unsafe_tourniquet": ["receive_handoff", "remove_tourniquet"],
        "timeout": ["wait_60"] * 20,
    }
    witnesses: dict[str, Any] = {}
    for name, sequence in cases.items():
        session = build_session(spec, source, binding, ledger, list(sequence), f"witness-{name}")
        witnesses[name] = {
            "terminal_status": session["final_state"]["terminal_status"],
            "elapsed_seconds": session["final_state"]["elapsed_seconds"],
            "transitions": len(session["transitions"]),
            "session_sha256": session["certificate"]["session_sha256"],
        }
    return witnesses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--max-depth", type=int, default=9)
    parser.add_argument("--max-states", type=int, default=100_000)
    parser.add_argument("--differential-limit", type=int, default=500)
    parser.add_argument("--output", default=str(REPORT))
    args = parser.parse_args()
    repo = args.repo.resolve()
    spec = load(repo / SPEC_PATH)
    binding = load(repo / BINDING_PATH)
    source = reconstruct_source_snapshot(repo)
    ledger = build_claim_ledger(spec)

    root = process_abstract_events(initial_state(spec, source), spec, source, None)
    queue = collections.deque([(root, 0)])
    seen = {semantic_key(root)}
    transitions_explored = 0
    terminal_counts = collections.Counter()
    active_dead_ends: list[dict[str, Any]] = []
    active_frontier = 0
    differential_checks = 0
    differential_failures: list[str] = []
    max_depth_seen = 0

    while queue:
        state, depth = queue.popleft()
        max_depth_seen = max(max_depth_seen, depth)
        if state["terminal_status"] != "active":
            terminal_counts[state["terminal_status"]] += 1
            continue
        enabled = enabled_actions(state, spec, source)
        if not enabled:
            active_dead_ends.append({"depth": depth, "state": json.loads(semantic_key(state))})
            continue
        if depth >= args.max_depth:
            active_frontier += 1
            continue
        for action_id in enabled:
            abstract_after = abstract_step(state, action_id, spec, source)
            transitions_explored += 1
            if differential_checks < args.differential_limit:
                concrete_after = concrete_step(state, action_id, spec, source)
                differential_checks += 1
                if semantic_key(abstract_after) != semantic_key(concrete_after):
                    differential_failures.append(f"differential mismatch:depth={depth}:action={action_id}")
            key = semantic_key(abstract_after)
            if key not in seen:
                if len(seen) >= args.max_states:
                    raise RuntimeError(f"state limit reached:{args.max_states}")
                seen.add(key)
                queue.append((abstract_after, depth + 1))

    witnesses = terminal_witnesses(spec, source, binding, ledger)
    properties = {
        "every_explored_active_state_has_continuation_or_frontier_witness": len(active_dead_ends) == 0,
        "completed_terminal_witness_exists": witnesses["completed"]["terminal_status"] == "completed",
        "timeout_terminal_witness_exists": witnesses["timeout"]["terminal_status"] == "timeout",
        "unsafe_discharge_terminal_witness_exists": witnesses["failed_unsafe_discharge"]["terminal_status"] == "failed",
        "unsafe_tourniquet_terminal_witness_exists": witnesses["failed_unsafe_tourniquet"]["terminal_status"] == "failed",
        "abstract_and_concrete_reducers_agree_on_sampled_edges": not differential_failures and differential_checks >= 50,
    }
    errors = [name for name, passed in properties.items() if not passed]
    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not errors else "FAIL",
        "exploration_model": "semantic-state breadth-first exploration with command identifiers and revision counters quotiented out of the state key",
        "depth_bound": args.max_depth,
        "state_limit": args.max_states,
        "states_seen": len(seen),
        "transitions_explored": transitions_explored,
        "maximum_depth_seen": max_depth_seen,
        "bounded_frontier_active_states": active_frontier,
        "reachable_nonterminal_dead_ends": len(active_dead_ends),
        "active_dead_end_samples": active_dead_ends[:5],
        "terminal_state_counts_within_bound": dict(sorted(terminal_counts.items())),
        "terminal_witnesses": witnesses,
        "differential_checks": differential_checks,
        "differential_failures": differential_failures,
        "properties": properties,
        "errors": errors,
        "limitations": [
            "The breadth-first proof is bounded by semantic action depth.",
            "Repeatable delay behavior beyond the bound is represented by a separately replayed source-timeout witness.",
            "The abstraction retains all fields used by current action admission and transition semantics but is not an unbounded liveness proof.",
        ],
    }
    output = repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_keys = [
        "schema_version", "status", "states_seen", "transitions_explored", "maximum_depth_seen",
        "bounded_frontier_active_states", "reachable_nonterminal_dead_ends", "differential_checks",
        "differential_failures", "terminal_witnesses", "properties", "errors",
    ]
    print(json.dumps({key: report[key] for key in summary_keys}, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
