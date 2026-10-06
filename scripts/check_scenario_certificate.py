#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import deque
from pathlib import Path
from typing import Any

HASH_LENGTH = 64


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        if value == 0:
            return "0"
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(str(key), ensure_ascii=False) + ":" + canonical(value[key])
            for key in sorted(value)
        ) + "}"
    raise TypeError(f"unsupported type: {type(value).__name__}")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return digest_text("")
    level = sorted(hashes)
    while len(level) > 1:
        next_level: list[str] = []
        for index in range(0, len(level), 2):
            left = level[index]
            right = level[index + 1] if index + 1 < len(level) else left
            next_level.append(digest_text(f"{left}:{right}"))
        level = next_level
    return level[0]


def protected_projection(scenario: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "training_objectives", "target_section", "target_role", "skill_level",
        "difficulty", "threat_type", "casualty_count", "patients",
        "expected_actions", "end_conditions", "aar_teaching_points",
    )
    return {key: scenario[key] for key in keys}


def diff_paths(left: Any, right: Any, prefix: str = "") -> list[str]:
    if canonical(left) == canonical(right):
        return []
    if not isinstance(left, dict) or not isinstance(right, dict):
        return [prefix]
    output: list[str] = []
    for key in sorted(set(left) | set(right)):
        child = f"{prefix}.{key}" if prefix else key
        output.extend(diff_paths(left.get(key), right.get(key), child))
    return output


def route_valid(route: dict[str, Any]) -> bool:
    node_ids = [node["node_id"] for node in route["nodes"]]
    nodes = set(node_ids)
    if len(nodes) != len(node_ids) or route["start_node_id"] not in nodes:
        return False
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    trigger_keys: set[str] = set()
    for edge in route["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            return False
        key = f'{edge["from"]}:{edge["trigger"]}:{edge["priority"]}'
        if key in trigger_keys:
            return False
        trigger_keys.add(key)
        outgoing[edge["from"]].append(edge["to"])
    for node in route["nodes"]:
        if not node["terminal"] and not outgoing[node["node_id"]]:
            return False
    reached: set[str] = set()
    queue: deque[str] = deque([route["start_node_id"]])
    while queue:
        current = queue.popleft()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(outgoing[current])
    return len(reached) == len(nodes) and any(
        node["terminal"] and node["node_id"] in reached for node in route["nodes"]
    )


def normalized_bridge(bridge: dict[str, Any]) -> dict[str, Any]:
    output = dict(bridge)
    output["sources"] = sorted(bridge["sources"], key=lambda item: item["source_index"])
    output["evidence_refs"] = sorted(bridge["evidence_refs"], key=lambda item: item["evidence_id"])
    output["prototypes"] = sorted(bridge["prototypes"], key=lambda item: item["prototype_id"])
    return output


def stage_payload(stage_id: str, package: dict[str, Any]) -> Any:
    certificate = package["certificate"]
    if stage_id == "source":
        return {
            "build": package["build"],
            "base_scenario_sha256": certificate["base_scenario_sha256"],
            "blueprint_sha256": certificate["blueprint_sha256"],
            "evidence_ids": [item["evidence_id"] for item in package["evidence"]],
        }
    if stage_id == "setting":
        scenario = package["scenario"]
        context = scenario["operational_context"]
        return {
            "scenario_id": scenario["scenario_id"],
            "title": scenario["title"],
            "version": scenario["version"],
            "fictionalization_notice": scenario["fictionalization_notice"],
            "location_type": context["location_type"],
            "weather": context["weather"],
            "visibility": context["visibility"],
            "comms_status": context["comms_status"],
            "resource_status": context["resource_status"],
        }
    if stage_id == "pressure":
        atom = next((item for item in package["atoms"] if item["atom_id"] == "atom-resource-event"), None)
        return {
            "narrative": package["scenario"]["operational_context"]["narrative"],
            "resource_event_atom_sha256": atom["atom_sha256"] if atom else "",
        }
    if stage_id == "route":
        return package["route"]
    if stage_id == "final":
        return {
            "scenario": package["scenario"],
            "route_sha256": certificate["route_sha256"],
            "evidence_sha256": certificate["evidence_sha256"],
        }
    raise ValueError(f"unknown stage {stage_id}")


def check(package: dict[str, Any], snapshot: dict[str, Any], bridge: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    base = snapshot["scenario"]
    certificate = package["certificate"]

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(package.get("schema_version") == "2.1.0", "unsupported package schema")
    require(package["build"].get("mode") == "template_locked", "unsupported build mode")
    require(package["authority"] == {
        "clinical_authority": "NOT_GRANTED",
        "deployment_scope": "research_sandbox_only",
        "source_template_status": "repository_template_not_clinically_certified",
        "clinical_rule_source": "inherited_template",
        "evidence_authority": "supporting_only",
        "evidence_effect_scope": "citation_support_only",
        "scoring_behavior": "inherited_unchanged",
    }, "authority boundary changed")

    require(digest(base) == snapshot["source_scenario_sha256"], "source snapshot hash mismatch")
    require(digest(protected_projection(base)) == snapshot["protected_projection_sha256"], "source projection hash mismatch")
    require(digest(base) == certificate["base_scenario_sha256"], "base scenario binding mismatch")
    require(digest(protected_projection(base)) == certificate["base_protected_sha256"], "base protected binding mismatch")
    require(digest(protected_projection(package["scenario"])) == certificate["output_protected_sha256"], "output protected hash mismatch")
    require(certificate["base_protected_sha256"] == certificate["output_protected_sha256"], "protected fields changed")

    changed = [f"scenario.{path}" for path in diff_paths(base, package["scenario"]) if path]
    allowed = package["blueprint"]["mutable_paths"]
    require(all(any(path == item or path.startswith(item + ".") for item in allowed) for path in changed), "change outside blueprint allowlist")

    require(digest(package["blueprint"]) == certificate["blueprint_sha256"], "blueprint hash mismatch")
    require(digest(normalized_bridge(bridge)) == package["build"]["source_bridge_sha256"], "bridge hash mismatch")
    require(bridge["retrieval_release"]["database_sha256"] == package["build"]["source_database_sha256"], "database binding mismatch")
    prototype = next((item for item in bridge["prototypes"] if item["prototype_id"] == package["build"]["source_prototype_id"]), None)
    require(prototype is not None, "prototype not found")
    if prototype is not None:
        require(prototype["prototype_sha256"] == package["build"]["source_prototype_sha256"], "prototype declared hash mismatch")
        require(digest(prototype) == package["build"]["source_prototype_record_sha256"], "prototype record hash mismatch")

    evidence_ids = [item["evidence_id"] for item in package["evidence"]]
    require(0 < len(evidence_ids) <= 6 and len(set(evidence_ids)) == len(evidence_ids), "evidence cardinality or uniqueness failure")
    require(digest(package["evidence"]) == certificate["evidence_sha256"], "evidence hash mismatch")

    for atom in package["atoms"]:
        atom_without_hash = {key: value for key, value in atom.items() if key != "atom_sha256"}
        require(digest(atom_without_hash) == atom["atom_sha256"], f'atom hash mismatch:{atom["atom_id"]}')
        require(all(item in evidence_ids for item in atom["evidence_ids"]), f'unknown atom evidence:{atom["atom_id"]}')
        if atom["authority"] == "supporting_only":
            require(bool(atom["evidence_ids"]), f'supporting atom lacks evidence:{atom["atom_id"]}')
        if atom["authority"] == "nonclinical":
            require(not atom["evidence_ids"], f'nonclinical atom claims evidence:{atom["atom_id"]}')
    require(merkle_root([item["atom_sha256"] for item in package["atoms"]]) == certificate["atom_root_sha256"], "atom root mismatch")

    previous = None
    for stage in package["stages"]:
        if previous is not None:
            require(stage["input_sha256"] == previous, f'stage input mismatch:{stage["stage_id"]}')
        require(stage["formula_version"] == "1.0.0", f'stage formula mismatch:{stage["stage_id"]}')
        require(digest(stage_payload(stage["stage_id"], package)) == stage["payload_sha256"], f'stage payload mismatch:{stage["stage_id"]}')
        stage_without_output = {key: value for key, value in stage.items() if key != "output_sha256"}
        require(digest(stage_without_output) == stage["output_sha256"], f'stage output mismatch:{stage["stage_id"]}')
        previous = stage["output_sha256"]
    require(digest(package["stages"]) == certificate["stage_chain_sha256"], "stage chain hash mismatch")

    require(route_valid(package["route"]), "route graph invalid")
    require(digest(package["route"]) == certificate["route_sha256"], "route hash mismatch")

    origins = {item["field_path"]: item for item in package["field_origins"]}
    atom_ids = {item["atom_id"] for item in package["atoms"]}
    for path in changed + ["route"]:
        require(path in origins, f'missing field origin:{path}')
        if path in origins:
            require(all(item in atom_ids for item in origins[path]["atom_ids"]), f'unknown origin atom:{path}')
            require(all(item in evidence_ids for item in origins[path]["evidence_ids"]), f'unknown origin evidence:{path}')
    require(digest(package["field_origins"]) == certificate["field_origin_sha256"], "field origin hash mismatch")

    certificate_without_package = {key: value for key, value in certificate.items() if key != "package_sha256"}
    package_without_certificate = {key: value for key, value in package.items() if key != "certificate"}
    expected_package_hash = digest({**package_without_certificate, "certificate": certificate_without_package})
    require(expected_package_hash == certificate["package_sha256"], "package hash mismatch")
    require(all(certificate["checks"].values()), "certificate contains failed check")

    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "checks": 32 + len(package["atoms"]) + len(package["stages"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--source-snapshot", required=True)
    parser.add_argument("--bridge", required=True)
    args = parser.parse_args()
    package = json.loads(Path(args.package).read_text(encoding="utf-8"))
    snapshot = json.loads(Path(args.source_snapshot).read_text(encoding="utf-8"))
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8"))
    report = check(package, snapshot, bridge)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
