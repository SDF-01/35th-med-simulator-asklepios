#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SAFE_INTEGER = 9_007_199_254_740_991
MANIFEST_PATH = Path("examples/verified-scenario/manifest.json")
DOC_PATH = Path("examples/verified-scenario/README.md")
README_PATH = Path("README.md")
EXPECTED_TOP_LEVEL = {
    "schema_version",
    "example_id",
    "purpose",
    "source_bindings",
    "authority",
    "protected_template",
    "scenario",
    "route_summary",
    "certificate",
    "citations",
    "validity_ledger",
    "claim_language",
    "documentation",
    "hashing",
    "example_manifest_sha256",
}
REQUIRED_AUTHORITY = {
    "clinical_authority": "NOT_GRANTED",
    "deployment_scope": "research_sandbox_only",
    "source_template_status": "repository_template_not_clinically_certified",
    "clinical_rule_source": "inherited_template",
    "evidence_authority": "supporting_only",
    "evidence_effect_scope": "citation_support_only",
    "scoring_behavior": "inherited_unchanged",
}
REQUIRED_OPEN_GATES = {
    "clinical_template_certification",
    "claim_level_evidence_entailment",
    "contradiction_search",
    "real_world_operational_calibration",
    "human_policy_calibration",
    "executable_to_formal_refinement",
    "independent_proof_kernel",
    "multi_template_clinical_breadth",
    "training_effectiveness_validation",
}
REQUIRED_DEMONSTRATED_GATES = {
    "source_template_binding",
    "protected_projection_preservation",
    "deterministic_package_certificate",
    "citation_identity_provenance",
    "authority_non_escalation",
}
FORBIDDEN_PUBLIC_KEYS = {
    "licensed_text",
    "full_text",
    "raw_text",
    "article_text",
    "xml_body",
    "institutional_token",
    "api_key",
    "embedding_vector",
    "private_prompt",
}
README_START = "<!-- asklepios-verified-example:start -->"
README_END = "<!-- asklepios-verified-example:end -->"
README_LINK = "[Open the canonical verified example](examples/verified-scenario/README.md)"
OFFLINE_POLICY_PATH = Path("config/release/OFFLINE_SCENARIO_RELEASE.json")
GENOME_PATH = Path("public/data/scenario_core/verified_scenario_genome.json")
CAPABILITY_RATCHET_PATH = Path("config/release/SCENARIO_CAPABILITY_RATCHET.json")
DEBT_RATCHET_PATH = Path("config/release/TECHNICAL_DEBT_RATCHET.json")
RELEASE_GRAPH_PATH = Path("config/release/RELEASE_GRAPH.json")
EXPECTED_OFFLINE_RELEASE = "ASK-OFFLINE-RC3.8A.1"
EXPECTED_GRAPH_ID = "asklepios-rc3.8a.1-scenario-science-stakeholder-graph"
MINIMUM_GRAPH_STAGE_COUNT = 118
MINIMUM_GRAPH_TARGET_COUNT = 26
EXPECTED_DEBT_RATCHET_ID = "asklepios-technical-debt-ratchet-v1"
EXPECTED_DEBT_RATCHET_EPOCH = 8
EXPECTED_DEBT_RATCHET_ANCHOR = "84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91"


def check_text_hygiene(path: Path, label: str, errors: list[str]) -> int:
    if not path.is_file():
        errors.append(f"missing:{path}")
        return 1
    raw = path.read_bytes()
    if b"\r" in raw:
        errors.append(f"carriage return forbidden:{label}")
    text = raw.decode("utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            errors.append(f"trailing whitespace:{label}:{line_number}")
    if text and not text.endswith("\n"):
        errors.append(f"final newline missing:{label}")
    return 1


def normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise ValueError(f"integer outside cross-language safe range:{value}")
        return value
    if isinstance(value, float):
        raise ValueError("floating-point values forbidden")
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("non-string object key")
        return {key: normalize(value[key]) for key in sorted(value)}
    raise ValueError(f"unsupported type:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected object:{path}")
    return value



def stable_public_value(value: Any) -> Any:
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, list):
        return [stable_public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: stable_public_value(child) for key, child in value.items()}
    return value


def scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in FORBIDDEN_PUBLIC_KEYS:
                errors.append(f"forbidden public field:{path}.{key}")
            scan_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scan_forbidden(child, f"{path}[{index}]", errors)


def check(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    checks = 0

    manifest_file = repo / MANIFEST_PATH
    doc_file = repo / DOC_PATH
    readme_file = repo / README_PATH
    if not manifest_file.is_file():
        return {"schema_version": "1.0.0", "status": "FAIL", "checks": checks, "errors": [f"missing:{MANIFEST_PATH}"]}
    checks += check_text_hygiene(doc_file, str(DOC_PATH), errors)
    checks += check_text_hygiene(readme_file, str(README_PATH), errors)
    try:
        manifest = load_json(manifest_file)
    except Exception as exc:
        return {"schema_version": "1.0.0", "status": "FAIL", "checks": checks, "errors": [str(exc)]}

    if set(manifest) != EXPECTED_TOP_LEVEL:
        errors.append("manifest top-level field set differs from reviewed schema")
    checks += 1
    if manifest.get("schema_version") != "1.0.0":
        errors.append("unsupported example schema")
    if manifest.get("example_id") != "ASK-EXAMPLE-RC3-2":
        errors.append("unexpected example ID")
    checks += 2

    candidate = copy.deepcopy(manifest)
    observed_manifest_hash = candidate.pop("example_manifest_sha256", None)
    try:
        expected_manifest_hash = sha256_json(candidate)
    except Exception as exc:
        errors.append(f"canonicalization failed:{exc}")
        expected_manifest_hash = ""
    if observed_manifest_hash != expected_manifest_hash:
        errors.append("example manifest hash mismatch")
    checks += 1

    scan_forbidden(manifest, "$manifest", errors)
    checks += 1

    source = manifest.get("source_bindings", {})
    scenario_rel = source.get("scenario_package_path")
    registry_rel = source.get("content_registry_path")
    for rel, label in ((scenario_rel, "scenario package"), (registry_rel, "content registry")):
        if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in Path(rel).parts:
            errors.append(f"unsafe {label} path")
    if errors and (not isinstance(scenario_rel, str) or not isinstance(registry_rel, str)):
        return {"schema_version": "1.0.0", "status": "FAIL", "checks": checks, "errors": sorted(set(errors))}

    scenario_file = repo / str(scenario_rel)
    registry_file = repo / str(registry_rel)
    if not scenario_file.is_file():
        errors.append("source scenario package missing")
    if not registry_file.is_file():
        errors.append("source content registry missing")
    if errors and (not scenario_file.is_file() or not registry_file.is_file()):
        return {"schema_version": "1.0.0", "status": "FAIL", "checks": checks, "errors": sorted(set(errors))}

    package = load_json(scenario_file)
    registry = load_json(registry_file)
    scan_forbidden(package, "$package", errors)
    scan_forbidden(registry, "$registry", errors)
    checks += 2

    if source.get("scenario_package_file_sha256") != sha256_file(scenario_file):
        errors.append("scenario package file hash mismatch")
    if source.get("content_registry_file_sha256") != sha256_file(registry_file):
        errors.append("content registry file hash mismatch")
    if source.get("content_registry_merkle_root") != registry.get("roots", {}).get("registry_merkle_root"):
        errors.append("content registry root mismatch")
    if source.get("scenario_package_sha256") != package.get("certificate", {}).get("package_sha256"):
        errors.append("scenario certificate package hash mismatch")
    if source.get("source_database_sha256") != package.get("build", {}).get("source_database_sha256"):
        errors.append("source database binding mismatch")
    if source.get("source_bridge_sha256") != package.get("build", {}).get("source_bridge_sha256"):
        errors.append("source bridge binding mismatch")
    checks += 6

    if manifest.get("authority") != REQUIRED_AUTHORITY:
        errors.append("example authority boundary mismatch")
    if package.get("authority") != REQUIRED_AUTHORITY:
        errors.append("source package authority boundary mismatch")
    checks += 2

    scenario = manifest.get("scenario", {})
    package_scenario = package.get("scenario", {})
    package_build = package.get("build", {})
    field_pairs = [
        ("scenario_id", package_scenario.get("scenario_id")),
        ("source_scenario_id", package_build.get("source_scenario_id")),
        ("title", package_scenario.get("title")),
        ("topic_id", package_build.get("topic_id")),
        ("seed", package_build.get("seed")),
        ("mode", package_build.get("mode")),
    ]
    for field, expected in field_pairs:
        if scenario.get(field) != expected:
            errors.append(f"scenario binding mismatch:{field}")
        checks += 1

    package_context = package_scenario.get("operational_context", {})
    for field in ("location_type", "weather", "visibility", "comms_status", "resource_status"):
        if scenario.get("operational_context", {}).get(field) != package_context.get(field):
            errors.append(f"operational context mismatch:{field}")
        checks += 1

    package_patient = (package_scenario.get("patients") or [{}])[0]
    for field in ("patient_id", "role_context", "mechanism_of_injury", "initial_presentation", "initial_vitals"):
        if scenario.get("patient_summary", {}).get(field) != stable_public_value(package_patient.get(field)):
            errors.append(f"patient summary mismatch:{field}")
        checks += 1

    assets = {item.get("asset_id"): item for item in registry.get("assets", [])}
    attestations = {
        item.get("evidence_asset_id", "").removeprefix("evidence:"): item
        for item in registry.get("evidence_attestations", [])
    }
    template = manifest.get("protected_template", {})
    template_asset = assets.get(template.get("asset_id"))
    if not template_asset:
        errors.append("protected template registry asset missing")
    else:
        expected_template_id = f"template:{package_build.get('source_scenario_id')}"
        if template.get("asset_id") != expected_template_id:
            errors.append("protected template ID mismatch")
        if template_asset.get("kind") != "protected_template":
            errors.append("protected template asset kind mismatch")
        if template.get("record_sha256") != template_asset.get("record_sha256"):
            errors.append("protected template record hash mismatch")
        if template.get("source_path") != template_asset.get("source", {}).get("path"):
            errors.append("protected template source path mismatch")
        if template.get("source_file_sha256") != template_asset.get("source", {}).get("file_sha256"):
            errors.append("protected template source hash mismatch")
        if template.get("clinical_certification") != "NOT_GRANTED":
            errors.append("example claims clinical certification")
        checks += 6

    route = manifest.get("route_summary", {})
    package_route = package.get("route", {})
    nodes = package_route.get("nodes", [])
    edges = package_route.get("edges", [])
    expected_terminals = [node.get("node_id") for node in nodes if node.get("terminal") is True]
    route_expected = {
        "route_id": package_route.get("route_id"),
        "start_node_id": package_route.get("start_node_id"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "terminal_node_ids": expected_terminals,
        "nodes": [
            {key: node.get(key) for key in ("node_id", "node_kind", "label", "terminal")}
            for node in nodes
        ],
        "edges": [
            {key: edge.get(key) for key in ("edge_id", "from", "to", "trigger", "priority")}
            for edge in edges
        ],
    }
    if route != route_expected:
        errors.append("route summary differs from source package")
    checks += 1

    certificate = manifest.get("certificate", {})
    package_certificate = package.get("certificate", {})
    certificate_fields = (
        "certificate_version",
        "checker_profile",
        "base_scenario_sha256",
        "base_protected_sha256",
        "output_protected_sha256",
        "route_sha256",
        "field_origin_sha256",
        "evidence_sha256",
        "package_sha256",
        "checks",
    )
    for field in certificate_fields:
        if certificate.get(field) != package_certificate.get(field):
            errors.append(f"certificate mismatch:{field}")
        checks += 1
    if certificate.get("base_protected_sha256") != certificate.get("output_protected_sha256"):
        errors.append("protected projection changed")
    if not certificate.get("checks") or not all(value is True for value in certificate.get("checks", {}).values()):
        errors.append("certificate includes a failed check")
    checks += 2

    source_evidence = package.get("evidence", [])
    citations = manifest.get("citations")
    if not isinstance(citations, list):
        errors.append("citations are not a list")
        citations = []
    if len(citations) != len(source_evidence):
        errors.append("citation count mismatch")
    seen: set[str] = set()
    for index, evidence in enumerate(source_evidence):
        if index >= len(citations):
            break
        citation = citations[index]
        evidence_id = evidence.get("evidence_id")
        if citation.get("order") != index + 1:
            errors.append(f"citation order mismatch:{evidence_id}")
        if citation.get("evidence_id") != evidence_id:
            errors.append(f"citation evidence ID mismatch:{index}")
        if evidence_id in seen:
            errors.append(f"duplicate evidence ID:{evidence_id}")
        seen.add(evidence_id)
        for field in ("title", "journal", "doi", "locator", "chunk_sha256", "source_file_sha256"):
            if citation.get(field) != evidence.get(field):
                errors.append(f"citation/source mismatch:{evidence_id}:{field}")
        evidence_asset_id = f"evidence:{evidence_id}"
        evidence_asset = assets.get(evidence_asset_id)
        if evidence_asset is None:
            errors.append(f"registry evidence asset missing:{evidence_id}")
            continue
        source_asset_id = evidence_asset.get("metadata", {}).get("source_asset_id")
        source_asset = assets.get(source_asset_id)
        attestation = attestations.get(evidence_id)
        if source_asset is None:
            errors.append(f"registry source asset missing:{evidence_id}")
            continue
        if attestation is None:
            errors.append(f"identity attestation missing:{evidence_id}")
            continue
        for field in ("doi", "locator", "chunk_sha256", "source_file_sha256"):
            if evidence_asset.get("metadata", {}).get(field) != evidence.get(field):
                errors.append(f"registry evidence mismatch:{evidence_id}:{field}")
        for field in ("title", "journal", "doi", "source_file_sha256"):
            if source_asset.get("metadata", {}).get(field) != evidence.get(field):
                errors.append(f"registry source mismatch:{evidence_id}:{field}")
        expected_citation = {
            "evidence_asset_id": evidence_asset_id,
            "evidence_asset_record_sha256": evidence_asset.get("record_sha256"),
            "source_asset_id": source_asset_id,
            "source_asset_record_sha256": source_asset.get("record_sha256"),
            "attestation_id": attestation.get("attestation_id"),
            "attestation_sha256": attestation.get("attestation_sha256"),
            "relation": "REFERENCE_ONLY",
            "identity_verification": "PASS",
            "entailment_status": "NOT_ADJUDICATED",
            "contradiction_status": "NOT_SEARCHED",
            "human_review_status": "NOT_REVIEWED",
            "clinical_authority": "NOT_GRANTED",
            "authority_tier": 3,
        }
        for field, expected in expected_citation.items():
            if citation.get(field) != expected:
                errors.append(f"citation attestation mismatch:{evidence_id}:{field}")
        if attestation.get("relation") != "REFERENCE_ONLY" or attestation.get("entailment_status") != "NOT_ADJUDICATED":
            errors.append(f"registry attestation improperly promoted:{evidence_id}")
        if attestation.get("contradiction_status") != "NOT_SEARCHED" or attestation.get("human_review_status") != "NOT_REVIEWED":
            errors.append(f"registry attestation review state differs:{evidence_id}")
        if attestation.get("clinical_authority") != "NOT_GRANTED" or attestation.get("authority_tier") != 3:
            errors.append(f"registry attestation authority escalation:{evidence_id}")
        if attestation.get("independent_verifiers") != []:
            errors.append(f"unreviewed evidence claims independent verification:{evidence_id}")
        checks += 26

    ledger = manifest.get("validity_ledger")
    if not isinstance(ledger, list):
        errors.append("validity ledger is not a list")
        ledger = []
    gate_ids = [item.get("gate_id") for item in ledger if isinstance(item, dict)]
    if len(gate_ids) != len(set(gate_ids)):
        errors.append("duplicate validity gate")
    gate_map = {item.get("gate_id"): item for item in ledger if isinstance(item, dict)}
    for gate_id in REQUIRED_DEMONSTRATED_GATES:
        gate = gate_map.get(gate_id)
        if not gate or gate.get("status") != "DEMONSTRATED" or not gate.get("evidence_paths"):
            errors.append(f"demonstrated gate missing evidence:{gate_id}")
    for gate_id in REQUIRED_OPEN_GATES:
        gate = gate_map.get(gate_id)
        if not gate or gate.get("status") != "OPEN" or gate.get("evidence_paths") != []:
            errors.append(f"open gate incorrectly closed or evidenced:{gate_id}")
    unexpected = set(gate_map) - REQUIRED_DEMONSTRATED_GATES - REQUIRED_OPEN_GATES
    if unexpected:
        errors.append("unexpected validity gates:" + ",".join(sorted(unexpected)))
    checks += len(REQUIRED_DEMONSTRATED_GATES) + len(REQUIRED_OPEN_GATES) + 2

    prohibited = set(manifest.get("claim_language", {}).get("prohibited_claims", []))
    if prohibited != {
        "clinically certified",
        "real-world validated",
        "citation entailment verified",
        "authoritative treatment guidance",
    }:
        errors.append("prohibited claim inventory changed")
    checks += 1

    evolution_paths = (OFFLINE_POLICY_PATH, GENOME_PATH, CAPABILITY_RATCHET_PATH, DEBT_RATCHET_PATH, RELEASE_GRAPH_PATH)
    evolution: dict[str, dict[str, Any]] = {}
    for relative in evolution_paths:
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"engine evolution input missing:{relative}")
            continue
        try:
            evolution[relative.as_posix()] = load_json(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"engine evolution input invalid:{relative}:{exc}")
    checks += len(evolution_paths)

    policy = evolution.get(OFFLINE_POLICY_PATH.as_posix(), {})
    genome = evolution.get(GENOME_PATH.as_posix(), {})
    capability = evolution.get(CAPABILITY_RATCHET_PATH.as_posix(), {})
    debt = evolution.get(DEBT_RATCHET_PATH.as_posix(), {})
    graph = evolution.get(RELEASE_GRAPH_PATH.as_posix(), {})
    if policy.get("release_id") != EXPECTED_OFFLINE_RELEASE or policy.get("display_version") != "RC3.8A.1":
        errors.append("offline engine-evolution policy identity differs")
    if policy.get("engine_evolution") != "SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8":
        errors.append("offline engine-evolution profile differs")
    if graph.get("graph_id") != EXPECTED_GRAPH_ID:
        errors.append("engine-evolution release graph identity differs")
    expected_stage_count = policy.get("expected_graph_stage_count")
    expected_target_count = policy.get("expected_graph_target_count")
    observed_stage_count = len(graph.get("stages", []))
    observed_target_count = len(graph.get("targets", {}))
    if type(expected_stage_count) is not int or expected_stage_count < MINIMUM_GRAPH_STAGE_COUNT:
        errors.append("engine-evolution release graph stage floor regressed")
    if observed_stage_count != expected_stage_count:
        errors.append("engine-evolution release graph stage count differs")
    if type(expected_target_count) is not int or expected_target_count < MINIMUM_GRAPH_TARGET_COUNT:
        errors.append("engine-evolution release graph target floor regressed")
    if observed_target_count != expected_target_count:
        errors.append("engine-evolution release graph target count differs")
    if capability.get("ratchet_id") != "asklepios-scenario-capability-ratchet-v1" or capability.get("ratchet_epoch") != 5:
        errors.append("scenario capability ratchet identity differs")
    if capability.get("authority_boundary", {}).get("quality_vector_use") != "SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING":
        errors.append("scenario capability quality-vector boundary differs")
    if (
        debt.get("ratchet_id") != EXPECTED_DEBT_RATCHET_ID
        or debt.get("ratchet_epoch") != EXPECTED_DEBT_RATCHET_EPOCH
        or debt.get("ratchet_anchor_sha256") != EXPECTED_DEBT_RATCHET_ANCHOR
    ):
        errors.append("technical-debt ratchet identity differs")
    if genome:
        identity_candidate = copy.deepcopy(genome)
        identity_candidate.pop("genome_id", None)
        identity_candidate.pop("genome_sha256", None)
        expected_identity_digest = sha256_json(identity_candidate)
        expected_genome_id = f"ASK-GENOME-{expected_identity_digest[:16].upper()}"
        if genome.get("genome_id") != expected_genome_id:
            errors.append("scenario genome identity mismatch")

        hash_candidate = copy.deepcopy(genome)
        observed_genome_sha = hash_candidate.pop("genome_sha256", None)
        expected_genome_sha = sha256_json(hash_candidate)
        if observed_genome_sha != expected_genome_sha:
            errors.append("scenario genome hash mismatch")
        descriptor = genome.get("behavior_descriptor") if isinstance(genome.get("behavior_descriptor"), dict) else {}
        if descriptor.get("cycle_free") is not True:
            errors.append("scenario genome route is not cycle-free")
        if descriptor.get("reachable_nonterminal_dead_ends") not in (0, None):
            errors.append("scenario genome contains reachable nonterminal dead ends")
    checks += 8


    if not doc_file.is_file():
        errors.append("human-readable example missing")
    else:
        doc = doc_file.read_text(encoding="utf-8")
        required_doc_fragments = [
            f"`{manifest.get('example_manifest_sha256')}`",
            f"`{scenario.get('scenario_id')}`",
            "Clinical authority is NOT GRANTED",
            "entailment `NOT_ADJUDICATED`",
            "## Open validity gates",
            "python3 scripts/check_verified_example_scenario.py --repo .",
            "## Engine evolution binding",
            "Behavioral quality-diversity",
            EXPECTED_OFFLINE_RELEASE,
            str(genome.get("genome_id", "")),
            EXPECTED_GRAPH_ID,
            "NOT_CALIBRATED",
            "PROHIBITED",
        ]
        for fragment in required_doc_fragments:
            if fragment not in doc:
                errors.append(f"example documentation missing fragment:{fragment}")
        checks += len(required_doc_fragments)


    if not readme_file.is_file():
        errors.append("root README missing")
    else:
        readme = readme_file.read_text(encoding="utf-8")
        if readme.count(README_START) != 1 or readme.count(README_END) != 1:
            errors.append("root README example marker count invalid")
        if README_LINK not in readme:
            errors.append("root README canonical example link missing")
        if "Clinical authority remains NOT_GRANTED" not in readme:
            errors.append("root README authority warning missing")
        if EXPECTED_OFFLINE_RELEASE not in readme or EXPECTED_GRAPH_ID not in readme:
            errors.append("root README engine-evolution binding missing")
        if "Psychometric validity:   ESTABLISHED" in readme:
            errors.append("unsupported psychometric validity claim")
        checks += 5

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "example_id": manifest.get("example_id"),
        "scenario_id": scenario.get("scenario_id"),
        "citation_count": len(citations),
        "registry_merkle_root": source.get("content_registry_merkle_root"),
        "example_manifest_sha256": observed_manifest_hash,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        result = check(repo)
    except Exception as exc:
        result = {"schema_version": "1.0.0", "status": "FAIL", "checks": 0, "errors": [str(exc)]}
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.report:
        path = Path(args.report)
        if not path.is_absolute():
            path = repo / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if result.get("status") == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
