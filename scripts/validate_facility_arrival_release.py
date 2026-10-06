#!/usr/bin/env python3
"""Join independently produced Facility Arrival assurance evidence.

The runtime-only mode is intentionally not a publication certificate.  The final
mode additionally requires the Lean axiom audit and byte-for-byte build
reproducibility report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_MUTATION_IDS = {
    "early_hidden_findings",
    "score_inflation",
    "unauthorized_actor_knowledge",
    "wit_authority_escalation",
    "reordered_transitions",
    "removed_timeout_event",
    "source_point_forgery",
    "calibration_promotion",
    "claim_entailment_promotion",
    "command_id_collision",
    "premature_diagnostics_event",
    "surge_ack_before_notice",
    "authority_escalation",
    "operational_source_binding",
    "operational_score_delta",
    "unknown_source_action_binding",
    "post_terminal_transition",
    "manifest_path_traversal",
    "generated_spec_divergence",
    "registry_source_hash_forgery",
    "licensed_text_in_manifest",
    "duplicate_transition",
    "removed_diagnostics_event",
    "state_snapshot_mismatch",
    "source_scenario_id_forgery",
    "registry_root_forgery",
    "pass_threshold_calibration_promotion",
    "wit_process_flag_removed",
    "timeout_terminal_without_event",
    "readme_link_removed",
}


def load(root: Path, relative: str, errors: list[str]) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top-level JSON value is not an object")
        return value
    except Exception as exc:  # noqa: BLE001 - report every malformed input
        errors.append(f"missing or invalid assurance input:{relative}:{exc}")
        return {}


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_canonical_utf8_lf(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def attestation_valid(report: dict[str, Any]) -> bool:
    claimed = report.get("attestation_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        return False
    payload = dict(report)
    payload.pop("attestation_sha256", None)
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest() == claimed


def current_hash_matches(root: Path, relative: Any, expected: Any, mode: str = "raw_bytes_v1") -> bool:
    if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
        return False
    path = root / relative
    if not path.is_file():
        return False
    if mode == "raw_bytes_v1":
        observed = sha256_file(path)
    elif mode == "canonical_utf8_lf_v1":
        observed = sha256_canonical_utf8_lf(path)
    else:
        return False
    return observed == expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = args.repo.resolve()
    errors: list[str] = []

    spec = load(root, "reports/facility-arrival-spec-compiler.json", errors)
    bindings = load(root, "reports/facility-arrival-bindings.json", errors)
    python_check = load(root, "reports/facility-arrival-python-check.json", errors)
    node_check = load(root, "reports/facility-arrival-node-check.json", errors)
    mutations = load(root, "reports/facility-arrival-semantic-mutations.json", errors)
    sequence = load(root, "reports/facility-arrival-sequence-assurance.json", errors)
    exploration = load(root, "reports/facility-arrival-state-exploration.json", errors)
    static = load(root, "reports/facility-arrival-release-static.json", errors)
    generator_regression = load(root, "reports/facility-arrival-generator-regression.json", errors)
    typescript_syntax = load(root, "reports/facility-arrival-typescript-syntax.json", errors)
    module_resolution = load(root, "reports/facility-arrival-module-resolution.json", errors)
    runtime_resolution = load(root, "reports/facility-arrival-runtime-resolution.json", errors)
    attestation_lifecycle = load(root, "reports/facility-arrival-attestation-lifecycle.json", errors)
    artifact_boundary = load(root, "reports/facility-arrival-artifact-boundary.json", errors)
    cross_platform = load(root, "reports/facility-arrival-cross-platform.json", errors)
    example_attestation = load(root, "reports/facility-arrival-example-check.json", errors)
    manifest = load(root, "examples/facility-arrival/manifest.json", errors)

    require(spec.get("status") == "PASS" and spec.get("mode") == "check", "spec compiler gate not PASS in check mode", errors)
    require(spec.get("attestation_kind") == "verification", "spec compiler attestation is not verification-scoped", errors)
    require(attestation_valid(spec), "spec compiler attestation digest invalid", errors)
    require(current_hash_matches(root, spec.get("source"), spec.get("source_file_sha256")), "spec compiler source attestation is stale", errors)
    require(current_hash_matches(root, spec.get("target"), spec.get("target_file_sha256")), "spec compiler target attestation is stale", errors)
    require(spec.get("target_file_sha256") == spec.get("expected_target_sha256"), "generated specification differs from verified projection", errors)

    require(bindings.get("status") == "PASS" and bindings.get("mode") == "check", "source-binding gate not PASS in check mode", errors)
    require(bindings.get("attestation_kind") == "verification", "source-binding attestation is not verification-scoped", errors)
    require(bindings.get("scenario_source_hash_mode") == "canonical_utf8_lf_v1", "scenario-source hash canonicalization mode differs", errors)
    require(attestation_valid(bindings), "source-binding attestation digest invalid", errors)
    require(current_hash_matches(root, bindings.get("registry_path"), bindings.get("registry_file_sha256")), "content-registry binding attestation is stale", errors)
    require(current_hash_matches(root, bindings.get("scenario_source_path"), bindings.get("scenario_source_sha256"), str(bindings.get("scenario_source_hash_mode"))), "scenario-source binding attestation is stale", errors)
    require(current_hash_matches(root, bindings.get("target_path"), bindings.get("target_file_sha256")), "generated TypeScript binding attestation is stale", errors)
    require(current_hash_matches(root, bindings.get("binding_json_path"), bindings.get("binding_json_file_sha256")), "generated JSON binding attestation is stale", errors)
    require(python_check.get("status") == "PASS" and python_check.get("checks", 0) >= 371, "independent Python reconstruction insufficient", errors)
    require(node_check.get("status") == "PASS" and node_check.get("checks", 0) >= 447, "independent Node reconstruction insufficient", errors)
    require(static.get("status") == "PASS" and int(static.get("checks", 0) or 0) >= 80, "release static-policy gate not PASS", errors)
    require(generator_regression.get("status") == "PASS", "generator-source regression gate not PASS", errors)
    require(generator_regression.get("regression") == "rc3.3.5-ci-portability-and-canonical-artifact-boundary", "generator regression identity differs", errors)
    require(typescript_syntax.get("status") == "PASS", "TypeScript syntax parser gate not PASS", errors)
    require(int(typescript_syntax.get("files_checked", 0) or 0) >= 13, "too few TypeScript files syntax-checked", errors)
    require(not typescript_syntax.get("errors"), "TypeScript syntax errors present", errors)
    require(module_resolution.get("status") == "PASS", "tsx module-resolution gate not PASS", errors)
    require(module_resolution.get("tsconfig") == "tsconfig.app.json", "tsx module-resolution tsconfig differs", errors)
    require(int(module_resolution.get("files_checked", 0) or 0) >= 20, "too few runtime module files resolved", errors)
    require(int(module_resolution.get("module_edges_checked", 0) or 0) >= 20, "too few runtime module edges resolved", errors)
    require(not module_resolution.get("errors"), "tsx module-resolution errors present", errors)
    require(runtime_resolution.get("status") == "PASS", "live tsx runtime-resolution smoke not PASS", errors)
    require(runtime_resolution.get("tsconfig") == "tsconfig.app.json", "live tsx runtime-resolution tsconfig differs", errors)
    require(runtime_resolution.get("source_scenario_id") == "ASK-D-001", "live tsx runtime source differs", errors)
    require(runtime_resolution.get("local_checks") == "PASS" and runtime_resolution.get("independent_checks") == "PASS", "live tsx runtime checkers disagree", errors)
    require(not runtime_resolution.get("errors"), "live tsx runtime-resolution errors present", errors)

    require(example_attestation.get("status") == "PASS" and example_attestation.get("mode") == "check", "facility example attestation not PASS in check mode", errors)
    require(example_attestation.get("attestation_kind") == "verification", "facility example attestation is not verification-scoped", errors)
    require(attestation_valid(example_attestation), "facility example attestation digest invalid", errors)
    expected_example_files = {
        "examples/facility-arrival/README.md",
        "examples/facility-arrival/aar.json",
        "examples/facility-arrival/claim-ledger.json",
        "examples/facility-arrival/interaction.json",
        "examples/facility-arrival/manifest.json",
        "examples/facility-arrival/source-snapshot.json",
        "examples/facility-arrival/source-truth.json",
        "public/data/facility_arrival/reference-aar.json",
        "public/data/facility_arrival/reference-manifest.json",
        "public/data/facility_arrival/reference-session.json",
    }
    example_hashes = example_attestation.get("file_sha256", {}) if isinstance(example_attestation.get("file_sha256"), dict) else {}
    require(set(example_hashes) == expected_example_files, "facility example attestation file inventory differs", errors)
    require(example_attestation.get("files") == len(expected_example_files), "facility example attestation file count differs", errors)
    require(not example_attestation.get("mismatches"), "facility example attestation reports mismatches", errors)
    for relative in sorted(expected_example_files):
        require(current_hash_matches(root, relative, example_hashes.get(relative)), f"facility example attestation is stale:{relative}", errors)

    require(artifact_boundary.get("status") == "PASS", "canonical artifact-boundary gate not PASS", errors)
    require(not artifact_boundary.get("errors"), "canonical artifact-boundary report contains errors", errors)
    expected_artifact_pairs = {
        "public/data/facility_arrival/reference-session.json": "examples/facility-arrival/interaction.json",
        "public/data/facility_arrival/reference-aar.json": "examples/facility-arrival/aar.json",
        "public/data/facility_arrival/reference-manifest.json": "examples/facility-arrival/manifest.json",
    }
    public_dir = root / "public/data/facility_arrival"
    observed_public = {p.name for p in public_dir.iterdir() if p.is_file() and not p.is_symlink()} if public_dir.is_dir() else set()
    require(observed_public == {Path(p).name for p in expected_artifact_pairs}, "canonical public artifact inventory differs", errors)
    for public_rel, source_rel in expected_artifact_pairs.items():
        public_path, source_path = root / public_rel, root / source_rel
        require(public_path.is_file() and not public_path.is_symlink(), f"canonical public artifact invalid:{public_rel}", errors)
        require(source_path.is_file() and not source_path.is_symlink(), f"canonical source artifact invalid:{source_rel}", errors)
        if public_path.is_file() and source_path.is_file():
            require(sha256_file(public_path) == sha256_file(source_path), f"canonical public/source artifact mismatch:{public_rel}", errors)
    for forbidden_rel in [
        "public/data/facility_arrival/reference_session.json",
        "public/data/facility_arrival/reference_aar.json",
        "public/data/facility_arrival/manifest.json",
        "reports/facility-arrival-generation.json",
    ]:
        require(not (root / forbidden_rel).exists() and not (root / forbidden_rel).is_symlink(), f"forbidden legacy/transient artifact present:{forbidden_rel}", errors)

    require(attestation_lifecycle.get("status") == "PASS", "attestation lifecycle gate not PASS", errors)
    require(int(attestation_lifecycle.get("cases", 0) or 0) >= 8, "attestation lifecycle challenge inventory too small", errors)
    lifecycle_properties = attestation_lifecycle.get("properties", {}) if isinstance(attestation_lifecycle.get("properties"), dict) else {}
    require(bool(lifecycle_properties) and all(lifecycle_properties.values()), "attestation lifecycle property failed", errors)
    require(not attestation_lifecycle.get("failures"), "attestation lifecycle challenge failed", errors)
    require(cross_platform.get("status") == "PASS", "cross-platform source-identity gate not PASS", errors)
    require(cross_platform.get("hash_mode") == "canonical_utf8_lf_v1", "cross-platform source hash mode differs", errors)
    require(int(cross_platform.get("cases", 0) or 0) >= 5, "cross-platform challenge inventory too small", errors)
    require(not cross_platform.get("failures"), "cross-platform source-identity challenge failed", errors)
    require(all(isinstance(item, dict) and item.get("pass") is True for item in cross_platform.get("results", [])), "cross-platform result contains a non-pass case", errors)

    mutation_count = int(mutations.get("cases", mutations.get("attacks", 0)) or 0)
    rehashed_count = int(mutations.get("globally_rehashed_cases", mutations.get("globally_rehashed_attacks", 0)) or 0)
    rejected_both = int(mutations.get("rejected_by_both_independent_checkers", mutations.get("rejected_by_both", 0)) or 0)
    mutation_results = mutations.get("results", []) if isinstance(mutations.get("results"), list) else []
    mutation_ids = {str(item.get("case_id")) for item in mutation_results if isinstance(item, dict)}
    require(mutations.get("status") == "PASS", "semantic mutation gate not PASS", errors)
    require(mutation_count == len(EXPECTED_MUTATION_IDS), "semantic attack inventory count changed", errors)
    require(mutation_ids == EXPECTED_MUTATION_IDS, "semantic attack inventory differs", errors)
    require(rejected_both == mutation_count, "not every semantic attack rejected by both checkers", errors)
    require(rehashed_count >= 25, "insufficient globally rehashed semantic attacks", errors)
    require(int(mutations.get("node_checker_internal_errors", -1) or 0) == 0, "semantic suite counted a Node checker crash or malformed output", errors)
    require(all(isinstance(item, dict) and item.get("node_checker_healthy") is True for item in mutation_results), "semantic mutation used an unhealthy Node checker", errors)
    require(all(isinstance(item, dict) and item.get("pass") is True for item in mutation_results), "semantic mutation result contains a non-pass case", errors)

    required_pairs = int(sequence.get("required_ordered_pairs", 0) or 0)
    covered_pairs = int(sequence.get("covered_ordered_pairs", 0) or 0)
    required_triples = int(sequence.get("selected_ordered_triples", 0) or 0)
    covered_triples = int(sequence.get("covered_ordered_triples", 0) or 0)
    require(sequence.get("status") == "PASS", "ordered-sequence gate not PASS", errors)
    require(required_pairs >= 34 and covered_pairs == required_pairs, "ordered-pair coverage incomplete", errors)
    require(required_triples >= 7 and covered_triples == required_triples, "ordered-triple coverage incomplete", errors)
    require(sequence.get("pair_coverage_fraction") == 1.0, "ordered-pair coverage fraction is not 1.0", errors)
    require(sequence.get("triple_coverage_fraction") == 1.0, "ordered-triple coverage fraction is not 1.0", errors)

    require(exploration.get("status") == "PASS", "bounded exploration gate not PASS", errors)
    require(exploration.get("reachable_nonterminal_dead_ends") == 0, "reachable active dead end exists", errors)
    require(int(exploration.get("states_seen", 0) or 0) < int(exploration.get("state_limit", 0) or 0), "bounded exploration exhausted its state limit", errors)
    require(exploration.get("depth_bound") == 9, "bounded exploration depth differs", errors)
    require(int(exploration.get("differential_checks", 0) or 0) >= 250, "too few abstract/runtime differential checks", errors)
    require(not exploration.get("differential_failures"), "abstract/runtime differential failure present", errors)
    witnesses = exploration.get("terminal_witnesses", {}) if isinstance(exploration.get("terminal_witnesses"), dict) else {}
    require({"completed", "timeout", "failed_unsafe_discharge", "failed_unsafe_tourniquet"}.issubset(witnesses), "terminal witness inventory incomplete", errors)
    properties = exploration.get("properties", {})
    require(isinstance(properties, dict) and bool(properties) and all(properties.values()), "bounded exploration property failed", errors)

    require(manifest.get("browser_route") == "/examples/facility-arrival", "manifest browser route mismatch", errors)
    authority = manifest.get("authority", {}) if isinstance(manifest.get("authority"), dict) else {}
    require(authority.get("patient_care_use") == "PROHIBITED", "patient-care boundary escalated", errors)
    require(authority.get("automatic_clinical_rule_generation") is False, "automatic clinical rule generation enabled", errors)
    require(authority.get("clinical_content_mode") == "INHERITED_REPOSITORY_TEMPLATE", "clinical content mode changed", errors)

    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").is_file() else ""
    app = (root / "src/App.tsx").read_text(encoding="utf-8") if (root / "src/App.tsx").is_file() else ""
    require("examples/facility-arrival/README.md" in readme, "root README facility link missing", errors)
    require("/examples/facility-arrival" in readme, "root README facility route missing", errors)
    require(app.count('path="/examples/facility-arrival"') == 1, "application facility route missing or duplicated", errors)

    formal: dict[str, Any] = {}
    reproducibility: dict[str, Any] = {}
    if not args.runtime_only:
        formal = load(root, "reports/facility-arrival-axiom-check.json", errors)
        reproducibility = load(root, "reports/facility-arrival-build-reproducibility.json", errors)
        require(formal.get("status") == "PASS", "formal exact zero-axiom gate not PASS", errors)
        require(formal.get("theorems_expected") == 12 and formal.get("theorems_observed") == 12, "formal theorem inventory mismatch", errors)
        require(not formal.get("errors"), "formal dependency errors present", errors)
        require(reproducibility.get("status") == "PASS", "two-build reproducibility gate not PASS", errors)
        require(int(reproducibility.get("files_compared", 0) or 0) >= 1, "no build files compared", errors)

    scope = "runtime_only" if args.runtime_only else "complete_release"
    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not errors else "FAIL",
        "scope": scope,
        "release": "Facility Arrival Reliability RC3.3.5",
        "assurance": {
            "independent_python_checks": python_check.get("checks", 0),
            "independent_node_checks": node_check.get("checks", 0),
            "semantic_mutations": mutation_count,
            "semantic_mutation_ids": sorted(mutation_ids),
            "globally_rehashed_mutations": rehashed_count,
            "ordered_pairs": covered_pairs,
            "ordered_triples": covered_triples,
            "bounded_states": exploration.get("states_seen", 0),
            "bounded_transitions": exploration.get("transitions_explored", 0),
            "formal_theorems": formal.get("theorems_observed", 0) if formal else None,
            "build_files_compared": reproducibility.get("files_compared", 0) if reproducibility else None,
            "generator_regression_checks": generator_regression.get("checks", 0),
            "typescript_syntax_files": typescript_syntax.get("files_checked", 0),
            "runtime_module_files": module_resolution.get("files_checked", 0),
            "runtime_module_edges": module_resolution.get("module_edges_checked", 0),
            "live_runtime_resolution": runtime_resolution.get("status"),
            "attestation_lifecycle_cases": attestation_lifecycle.get("cases", 0),
            "canonical_artifact_boundary": artifact_boundary.get("status"),
            "example_attestation": example_attestation.get("status"),
            "cross_platform_source_identity": cross_platform.get("status"),
        },
        "authority": {
            "deployment_scope": authority.get("deployment_scope"),
            "patient_care_use": authority.get("patient_care_use"),
            "clinical_content_mode": authority.get("clinical_content_mode"),
        },
        "open_limits": [
            "Exercise timing values are not empirically calibrated distributions.",
            "The formal model is not yet an end-to-end refinement proof of the TypeScript and Python executables.",
            "Patient-care use remains prohibited.",
        ],
        "errors": sorted(set(errors)),
    }
    default_output = (
        "reports/facility-arrival-runtime-validation.json"
        if args.runtime_only
        else "reports/facility-arrival-release-validation.json"
    )
    output = root / (args.output or default_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
