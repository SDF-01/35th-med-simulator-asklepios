#!/usr/bin/env python3
"""Semantic attacks against the standalone no-server scenario artifact."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

TARGET = Path("examples/facility-arrival/playable.html")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_checker(repo: Path):
    path = repo / "scripts/check_facility_arrival_standalone.py"
    spec = importlib.util.spec_from_file_location("asklepios_standalone_checker", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("standalone checker could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract(html: str, tag_id: str) -> tuple[re.Match[str], str]:
    pattern = re.compile(rf'(<script\b[^>]*\bid=["\']{re.escape(tag_id)}["\'][^>]*>)(.*?)(</script>)', re.I | re.S)
    match = pattern.search(html)
    if not match:
        raise ValueError(f"script missing:{tag_id}")
    return match, match.group(2)


def replace_script(html: str, tag_id: str, content: str) -> str:
    match, _ = extract(html, tag_id)
    return html[: match.start()] + match.group(1) + content + match.group(3) + html[match.end() :]


def load_payload(html: str) -> dict[str, Any]:
    _, raw = extract(html, "asklepios-scenario-data")
    value = json.loads(raw.replace("<\\/script>", "</script>"))
    if not isinstance(value, dict):
        raise ValueError("payload is not an object")
    return value


def write_payload(html: str, payload: dict[str, Any]) -> str:
    copy = json.loads(json.dumps(payload))
    copy.get("provenance", {}).pop("payload_sha256", None)
    payload["provenance"]["payload_sha256"] = hashlib.sha256(canonical(copy)).hexdigest()
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).replace("</script>", "<\\/script>")
    return replace_script(html, "asklepios-scenario-data", raw)


def mutate_payload(html: str, operation: Callable[[dict[str, Any]], None]) -> str:
    payload = load_payload(html)
    operation(payload)
    return write_payload(html, payload)


def rehash_role_models(payload: dict[str, Any]) -> None:
    profiles = payload.get("role_model_profiles")
    if isinstance(profiles, list):
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            body = dict(profile)
            body.pop("profile_sha256", None)
            profile["profile_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        payload["provenance"]["role_model_profiles_root_sha256"] = hashlib.sha256(canonical(profiles)).hexdigest()
    contract = payload.get("role_model_profile_contract")
    if isinstance(contract, dict):
        body = dict(contract)
        body.pop("contract_sha256", None)
        contract["contract_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
        payload["provenance"]["role_model_contract_sha256"] = contract["contract_sha256"]


def mutate_role_models(html: str, operation: Callable[[dict[str, Any]], None]) -> str:
    payload = load_payload(html)
    operation(payload)
    rehash_role_models(payload)
    return write_payload(html, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("reports/facility-arrival-standalone-mutations.json"))
    args = parser.parse_args()
    repo = args.repo.resolve()
    checker = load_checker(repo)
    baseline = (repo / TARGET).read_text(encoding="utf-8")

    cases: list[tuple[str, Callable[[str], str], bool]] = []
    cases.append(("baseline", lambda value: value, True))
    cases.append(("external_script_rejected", lambda value: value.replace("</head>", '<script src="https://example.invalid/remote.js"></script></head>'), False))
    cases.append(("network_fetch_rejected", lambda value: replace_script(value, "asklepios-ui", extract(value, "asklepios-ui")[1] + "\nfetch('https://example.invalid');"), False))
    cases.append(("weakened_csp_rejected", lambda value: value.replace("connect-src 'none'", "connect-src *"), False))
    cases.append(("patient_care_escalation_rehashed", lambda value: mutate_payload(value, lambda payload: payload["authority"].__setitem__("patient_care_use", "GRANTED")), False))
    cases.append(("automatic_rule_generation_rehashed", lambda value: mutate_payload(value, lambda payload: payload["authority"].__setitem__("automatic_clinical_rule_generation", True)), False))
    cases.append(("unsafe_discharge_neutralized_rehashed", lambda value: mutate_payload(value, lambda payload: next(item for item in payload["spec"]["actions"] if item["action_id"] == "discharge_without_workup").__setitem__("terminal_effect", None)), False))
    cases.append(("source_points_forged_rehashed", lambda value: mutate_payload(value, lambda payload: next(item for item in payload["source_snapshot"]["source_actions"] if item["id"] == "order_imaging").__setitem__("points", 999)), False))
    cases.append(("canonical_sequence_weakened_rehashed", lambda value: mutate_payload(value, lambda payload: payload["spec"].__setitem__("canonical_command_sequence", [item for item in payload["spec"]["canonical_command_sequence"] if item != "escalation"])), False))
    cases.append(("source_binding_forged_rehashed", lambda value: mutate_payload(value, lambda payload: payload["source_snapshot"].__setitem__("source_scenario_id", "ASK-FORGED")), False))
    cases.append(("release_graph_binding_mode_forged_rehashed", lambda value: mutate_payload(value, lambda payload: payload["scenario_evolution"]["release_graph"].__setitem__("binding_mode", "RAW_FILE_SHA256_V0")), False))
    cases.append(("release_graph_contract_hash_forged_rehashed", lambda value: mutate_payload(value, lambda payload: payload["scenario_evolution"]["release_graph"].__setitem__("contract_sha256", "0" * 64)), False))

    cases.append((
        "playable_role_model_removed_rehashed",
        lambda value: mutate_role_models(value, lambda payload: payload["role_model_profiles"].pop(1)),
        False,
    ))
    cases.append((
        "playable_role_model_duplicated_rehashed",
        lambda value: mutate_role_models(value, lambda payload: payload["role_model_profiles"].append(json.loads(json.dumps(payload["role_model_profiles"][0])))),
        False,
    ))

    def relabel_without_route(payload: dict[str, Any]) -> None:
        profile = next(item for item in payload["role_model_profiles"] if item["profile_id"] == "COMMUNICATION_RELAY_REQUIRED")
        profile["required_operational_actions"] = []
        profile["intermediate_handoff_steps"] = 0

    cases.append(("role_model_relabel_without_route_rehashed", lambda value: mutate_role_models(value, relabel_without_route), False))

    def promote_teamwork_score(payload: dict[str, Any]) -> None:
        profile = next(item for item in payload["role_model_profiles"] if item["profile_id"] == "RESOURCE_COORDINATION_REQUIRED")
        profile["scoring_effect"] = "CLINICAL_POINTS_GRANTED"

    cases.append(("role_model_clinical_score_promotion_rehashed", lambda value: mutate_role_models(value, promote_teamwork_score), False))

    def forge_role_model_policy_path(payload: dict[str, Any]) -> None:
        payload["role_model_profile_contract"]["source_policy_path"] = "config/scenario-science/FORGED.json"
        payload["provenance"]["role_model_policy_path"] = "config/scenario-science/FORGED.json"

    cases.append(("role_model_policy_path_forged_rehashed", lambda value: mutate_role_models(value, forge_role_model_policy_path), False))

    def remove_timeout_engine(value: str) -> str:
        match, engine = extract(value, "asklepios-engine")
        changed = engine.replace("if (state.elapsed_seconds >= timeout && state.terminal_status === \"active\")", "if (false)")
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        result = replace_script(value, "asklepios-engine", changed)
        return write_payload(result, payload)

    cases.append(("timeout_semantics_removed_rehashed", remove_timeout_engine, False))

    def remove_elapsed_clock_engine(value: str) -> str:
        match, engine = extract(value, "asklepios-engine")
        changed = engine.replace(
            'event.trigger.kind === "elapsed_time_due"',
            'event.trigger.kind === "elapsed_time_disabled"',
            1,
        )
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        result = replace_script(value, "asklepios-engine", changed)
        return write_payload(result, payload)

    cases.append(("elapsed_clock_runtime_removed_rehashed", remove_elapsed_clock_engine, False))

    def regress_clock_to_action_alert(value: str) -> str:
        match, engine = extract(value, "asklepios-engine")
        changed = engine.replace(
            'if (event.trigger.kind === "elapsed_time_due"\n          && state.elapsed_seconds >= Number(event.trigger.at_elapsed_seconds)) {',
            'if (event.trigger.kind === "elapsed_time_due" && afterActionId === "order_imaging") {',
            1,
        )
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        result = replace_script(value, "asklepios-engine", changed)
        return write_payload(result, payload)

    cases.append(("clock_regressed_to_action_trigger_rehashed", regress_clock_to_action_alert, False))

    def expose_hidden_early(value: str) -> str:
        match, engine = extract(value, "asklepios-engine")
        changed = engine.replace("visible_findings: [],", "visible_findings: copy(data.source_snapshot.patient.hidden_findings),")
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        result = replace_script(value, "asklepios-engine", changed)
        return write_payload(result, payload)

    cases.append(("hidden_findings_exposed_early_rehashed", expose_hidden_early, False))

    def remove_profile_route_builder(value: str) -> str:
        _, engine = extract(value, "asklepios-engine")
        changed = engine.replace(
            'if (required.includes("establish_communications_relay")) {',
            'if (false) {',
            1,
        )
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        return write_payload(replace_script(value, "asklepios-engine", changed), payload)

    cases.append(("communications_relay_route_removed_rehashed", remove_profile_route_builder, False))

    def remove_handoff_profile_binding(value: str) -> str:
        _, engine = extract(value, "asklepios-engine")
        changed = engine.replace(
            'handoff.prerequisites = unique([...(handoff.prerequisites || []), ...required]);',
            'handoff.prerequisites = unique([...(handoff.prerequisites || [])]);',
            1,
        )
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        return write_payload(replace_script(value, "asklepios-engine", changed), payload)

    cases.append(("profile_handoff_guard_removed_rehashed", remove_handoff_profile_binding, False))

    def promote_operational_action_to_source_scored(value: str) -> str:
        _, engine = extract(value, "asklepios-engine")
        marker = 'action_id: "establish_communications_relay",'
        start = engine.find(marker)
        if start < 0:
            raise ValueError("relay action definition missing")
        end = engine.find('},\n      coordinate_constrained_resource:', start)
        block = engine[start:end]
        changed_block = block.replace('source_action_id: null', 'source_action_id: "receive_handoff"', 1)
        changed = engine[:start] + changed_block + engine[end:]
        payload = load_payload(value)
        payload["provenance"]["engine_sha256"] = sha(changed)
        return write_payload(replace_script(value, "asklepios-engine", changed), payload)

    cases.append(("role_model_action_source_scored_rehashed", promote_operational_action_to_source_scored, False))

    def remove_profile_selector(value: str) -> str:
        return value.replace('id="profile-selector"', 'id="profile-selector-removed"', 1)

    cases.append(("playable_profile_selector_removed", remove_profile_selector, False))

    def remove_profile_ui_binding(value: str) -> str:
        _, ui = extract(value, "asklepios-ui")
        changed = ui.replace('for (const button of document.querySelectorAll("[data-profile]")) {', 'for (const button of []) {', 1)
        payload = load_payload(value)
        payload["provenance"]["ui_sha256"] = sha(changed)
        return write_payload(replace_script(value, "asklepios-ui", changed), payload)

    cases.append(("playable_profile_click_binding_removed_rehashed", remove_profile_ui_binding, False))

    results = []
    errors = []
    with tempfile.TemporaryDirectory(prefix="asklepios-standalone-mutations-") as temporary:
        root = Path(temporary)
        for case_id, operation, expected_pass in cases:
            artifact = root / f"{case_id}.html"
            artifact.write_text(operation(baseline), encoding="utf-8", newline="\n")
            report = checker.validate_artifact(repo, artifact, require_generated_identity=False)
            observed_pass = report.get("status") == "PASS"
            passed = observed_pass == expected_pass
            if not passed:
                errors.append(f"mutation expectation mismatch:{case_id}")
            results.append({
                "case_id": case_id,
                "pass": passed,
                "expected_artifact_pass": expected_pass,
                "observed_artifact_pass": observed_pass,
                "checker_errors": report.get("errors", [])[:8],
            })

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "cases": len(results),
        "attacks": len(results) - 1,
        "rehashed_semantic_attacks": sum(1 for case_id, _, _ in cases if "rehashed" in case_id),
        "results": results,
        "errors": errors,
    }
    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
