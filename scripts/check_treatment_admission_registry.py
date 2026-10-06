#!/usr/bin/env python3
"""Validate and, when requested, materialize the treatment-admission projection.

The registry is intentionally fail-closed.  A treatment is never learner-active
unless every admission state has been reached, the source profile agrees, and no
missing requirement remains.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
EXPECTED_STATE_ORDER = [
    "DISCOVERED",
    "SOURCE_BYTES_VERIFIED",
    "EVIDENCE_SPAN_BOUND",
    "APPLICABILITY_REVIEWED",
    "CONTRAINDICATION_MODEL_REVIEWED",
    "ROLE_SCOPE_BOUND",
    "SIMULATED_EFFECT_ADJUDICATED",
    "INDEPENDENTLY_ATTESTED",
    "SIMULATION_ADMITTED",
]
COMPILED_BOUNDARIES = {
    "healthcare_simulation": "PERMITTED_WITHIN_VALIDATED_SCOPE",
    "direct_patient_care": "PROHIBITED",
    "clinical_decision_support": "PROHIBITED",
    "patient_care_authority": "NONE",
    "automatic_treatment_activation": False,
    "unadjudicated_treatment_visible_as_active_choice": False,
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def safe_repo_path(root: Path, value: str, label: str, *, allow_missing: bool = True) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ValueError(f"unsafe repository path:{label}")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} or ":" in part or part.endswith((" ", ".")) for part in path.parts):
        raise ValueError(f"unsafe repository path:{label}")
    candidate = root.joinpath(*path.parts)
    current = root
    for part in path.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"symlinked repository parent:{label}")
    resolved_root = root.resolve()
    resolved_parent = candidate.parent.resolve()
    if resolved_parent != resolved_root and resolved_root not in resolved_parent.parents:
        raise ValueError(f"repository path escapes root:{label}")
    if candidate.exists() and candidate.is_symlink():
        raise ValueError(f"symlinked repository file:{label}")
    if not allow_missing and not candidate.is_file():
        raise ValueError(f"required repository file missing:{label}")
    return candidate


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or (path.exists() and path.is_symlink()):
        raise ValueError(f"unsafe output path:{path}")
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def build_projection(registry: dict[str, Any], source_profile: dict[str, Any]) -> dict[str, Any]:
    source_treatments = {
        item.get("treatment_id"): item
        for item in source_profile.get("treatment_policies", [])
        if isinstance(item, dict)
    }
    entries: list[dict[str, Any]] = []
    for entry in registry["entries"]:
        source = source_treatments.get(entry["treatment_id"], {})
        admitted = entry["current_state"] == "SIMULATION_ADMITTED" and entry["simulation_admitted"] is True
        entries.append({
            "treatment_id": entry["treatment_id"],
            "display_name": entry["display_name"],
            "facility_action_id": entry["facility_action_id"],
            "admission_state": entry["current_state"],
            "simulation_admitted": admitted,
            "learner_choice_status": "AVAILABLE" if admitted else "BLOCKED_PENDING_ADJUDICATION",
            "governing_rule_status": entry["governing_rule_status"],
            "effect_model_status": entry["effect_model_status"],
            "missing_requirements": list(entry["missing_requirements"]),
            "source_profile_activation_state": source.get("activation_state", "MISSING"),
            "plain_language_limitation": (
                "This treatment is not yet an active learner choice because its governing evidence, applicability, scope, "
                "contraindications, simulated effect, and independent clinical review have not all been admitted."
                if not admitted else
                "This treatment is admitted only for the declared healthcare-simulation scope and does not authorize real-patient care."
            ),
        })
    entries.sort(key=lambda item: item["treatment_id"])
    without_hash = {
        "schema_version": SCHEMA_VERSION,
        "classification": "PASS",
        "status": "PASS",
        "registry_id": registry["registry_id"],
        "registry_epoch": registry["registry_epoch"],
        "registry_sha256": registry["registry_sha256"],
        "admission_profile": registry["admission_profile"],
        "state_order": list(registry["state_order"]),
        "entry_count": len(entries),
        "simulation_admitted_count": sum(1 for entry in entries if entry["simulation_admitted"]),
        "active_learner_choice_count": sum(1 for entry in entries if entry["learner_choice_status"] == "AVAILABLE"),
        "entries": entries,
        "boundaries": dict(registry["boundaries"]),
        "truth_boundary": (
            "A discovered or source-mentioned treatment is not an active simulation choice. Activation requires exact source bytes, "
            "a bound evidence span, applicability and contraindication review, role/scope binding, an adjudicated simulated effect, "
            "and independent attestation. Direct patient care and clinical decision support remain prohibited."
        ),
    }
    return {**without_hash, "projection_sha256": sha256(without_hash)}


def validate_registry(registry: dict[str, Any], source_profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append("treatment registry schema version differs")
    if registry.get("state_order") != EXPECTED_STATE_ORDER:
        errors.append("treatment admission state order differs")
    if registry.get("boundaries") != COMPILED_BOUNDARIES:
        errors.append("treatment admission authority boundaries differ")
    body = dict(registry)
    observed_hash = body.pop("registry_sha256", None)
    expected_hash = sha256(body)
    if observed_hash != expected_hash or not isinstance(observed_hash, str) or not HEX64.fullmatch(observed_hash):
        errors.append("treatment registry self hash differs")
    entries = registry.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("treatment registry entries missing")
        return errors
    source_treatments = {
        item.get("treatment_id"): item
        for item in source_profile.get("treatment_policies", [])
        if isinstance(item, dict)
    }
    ids: set[str] = set()
    actions: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("treatment registry entry is not an object")
            continue
        treatment_id = entry.get("treatment_id")
        action_id = entry.get("facility_action_id")
        if not isinstance(treatment_id, str) or not treatment_id:
            errors.append("treatment registry entry ID missing")
            continue
        if treatment_id in ids:
            errors.append(f"treatment registry ID duplicated:{treatment_id}")
        ids.add(treatment_id)
        if not isinstance(action_id, str) or not action_id:
            errors.append(f"facility action ID missing:{treatment_id}")
        elif action_id in actions:
            errors.append(f"facility action ID duplicated:{action_id}")
        else:
            actions.add(action_id)
        source = source_treatments.get(treatment_id)
        if not source:
            errors.append(f"source treatment policy missing:{treatment_id}")
            continue
        if source.get("facility_action_id") != action_id:
            errors.append(f"source facility action differs:{treatment_id}")
        state = entry.get("current_state")
        if state not in EXPECTED_STATE_ORDER:
            errors.append(f"unrecognized treatment admission state:{treatment_id}")
            continue
        missing = entry.get("missing_requirements")
        if not isinstance(missing, list) or any(not isinstance(item, str) or not item for item in missing):
            errors.append(f"treatment missing-requirements inventory invalid:{treatment_id}")
            missing = []
        if len(set(missing)) != len(missing):
            errors.append(f"treatment missing-requirements inventory duplicated:{treatment_id}")
        admitted = state == "SIMULATION_ADMITTED"
        if bool(entry.get("simulation_admitted")) != admitted:
            errors.append(f"treatment admitted flag differs from state:{treatment_id}")
        if bool(entry.get("concrete_treatment_allowed")) != admitted:
            errors.append(f"concrete treatment permission differs from state:{treatment_id}")
        if admitted:
            if missing:
                errors.append(f"admitted treatment retains missing requirements:{treatment_id}")
            if entry.get("governing_rule_status") != "ADJUDICATED":
                errors.append(f"admitted treatment lacks adjudicated governing rule:{treatment_id}")
            if entry.get("effect_model_status") != "ADJUDICATED_FOR_SIMULATION":
                errors.append(f"admitted treatment lacks adjudicated simulation effect:{treatment_id}")
            if source.get("concrete_treatment_allowed") is not True:
                errors.append(f"source profile does not admit concrete treatment:{treatment_id}")
        else:
            if not missing:
                errors.append(f"blocked treatment has no explicit missing requirement:{treatment_id}")
            if entry.get("effect_model_status") != "BLOCKED":
                errors.append(f"blocked treatment effect model is not blocked:{treatment_id}")
            if entry.get("governing_rule_status") == "ADJUDICATED":
                errors.append(f"blocked treatment claims adjudicated governing rule:{treatment_id}")
            if source.get("concrete_treatment_allowed") is not False:
                errors.append(f"source profile unexpectedly admits concrete treatment:{treatment_id}")
    if set(source_treatments) != ids:
        errors.append("treatment registry and source-profile inventories differ")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=("write", "check"), default="check")
    parser.add_argument("--json-output", default="reports/treatment-admission-registry.json")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    errors: list[str] = []
    projection: dict[str, Any] | None = None
    try:
        registry_path = safe_repo_path(root, "config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json", "registry", allow_missing=False)
        registry = read_json(registry_path)
        source_path = safe_repo_path(root, registry.get("source_profile_path", ""), "source_profile", allow_missing=False)
        source_profile = read_json(source_path)
        errors.extend(validate_registry(registry, source_profile))
        if not errors:
            projection = build_projection(registry, source_profile)
            projection_path = safe_repo_path(root, registry["public_projection_path"], "public_projection")
            if args.mode == "write":
                write_json_atomic(projection_path, projection)
            elif not projection_path.is_file():
                errors.append("treatment admission public projection missing")
            else:
                observed = read_json(projection_path)
                if canonical_bytes(observed) != canonical_bytes(projection):
                    errors.append("treatment admission public projection differs")
    except Exception as exc:  # structured fail-closed result
        errors.append(str(exc))
    result = {
        "schema_version": SCHEMA_VERSION,
        "classification": "FAIL" if errors else "PASS",
        "status": "FAIL" if errors else "PASS",
        "mode": args.mode,
        "registry_id": projection.get("registry_id") if projection else None,
        "entry_count": projection.get("entry_count") if projection else 0,
        "simulation_admitted_count": projection.get("simulation_admitted_count") if projection else 0,
        "active_learner_choice_count": projection.get("active_learner_choice_count") if projection else 0,
        "projection_sha256": projection.get("projection_sha256") if projection else None,
        "errors": errors,
    }
    try:
        output = safe_repo_path(root, args.json_output, "json_output")
        write_json_atomic(output, result)
    except Exception as exc:
        result["classification"] = result["status"] = "FAIL"
        result["errors"].append(str(exc))
    print(json.dumps(result, indent=2))
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
