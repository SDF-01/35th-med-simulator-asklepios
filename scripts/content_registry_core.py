#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

SAFE_INTEGER = 9_007_199_254_740_991
FORBIDDEN_CAPABILITIES = {
    "define_new_clinical_rule",
    "define_scoring_truth",
    "define_physiology",
    "define_medication_dose",
    "define_provider_scope",
}
RESEARCH_CAPABILITIES = {"catalog_display", "citation_reference", "aar_discussion"}
HASH_FIELDS = {
    "assets": "record_sha256",
    "relations": "relation_sha256",
    "agents": "record_sha256",
    "activities": "record_sha256",
    "evidence_attestations": "attestation_sha256",
    "claim_candidates": "claim_sha256",
    "compatibility_profiles": "profile_sha256",
}
COLLECTION_DOMAINS = {
    "assets": "asklepios.content-registry.assets.v1",
    "relations": "asklepios.content-registry.relations.v1",
    "agents": "asklepios.content-registry.agents.v1",
    "activities": "asklepios.content-registry.activities.v1",
    "evidence_attestations": "asklepios.content-registry.evidence-attestations.v1",
    "claim_candidates": "asklepios.content-registry.claim-candidates.v1",
    "compatibility_profiles": "asklepios.content-registry.compatibility-profiles.v1",
}
ID_FIELDS = {
    "assets": "asset_id",
    "relations": "relation_id",
    "agents": "agent_id",
    "activities": "activity_id",
    "evidence_attestations": "attestation_id",
    "claim_candidates": "claim_id",
    "compatibility_profiles": "profile_id",
}
FORBIDDEN_PUBLIC_KEYS = {
    "licensed_text", "full_text", "raw_text", "article_text", "xml_body",
    "institutional_token", "api_key", "embedding_vector", "private_prompt",
}


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise ValueError(f"integer outside cross-language safe range:{value}")
        return value
    if isinstance(value, float):
        raise ValueError("floating-point values are forbidden in committed registry hashes")
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("all JSON object keys must be strings")
        return {key: _normalize(value[key]) for key in sorted(value)}
    raise ValueError(f"unsupported canonical value:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_hash(record: dict[str, Any], hash_field: str) -> str:
    candidate = copy.deepcopy(record)
    candidate.pop(hash_field, None)
    return sha256_json(candidate)


def collection_root(domain: str, hashes: list[str]) -> str:
    return sha256_json({"domain": domain, "hashes": sorted(hashes)})


def compute_registry_roots(registry: dict[str, Any]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for name, hash_field in HASH_FIELDS.items():
        hashes = [record_hash(record, hash_field) for record in registry.get(name, [])]
        roots[f"{name}_merkle_root"] = collection_root(COLLECTION_DOMAINS[name], hashes)
    roots["registry_merkle_root"] = sha256_json({
        "domain": "asklepios.content-registry.v1",
        "source_manifest_sha256": registry["source_snapshot"]["source_manifest_sha256"],
        "authority_model_sha256": sha256_json(registry["authority_model"]),
        "release_boundary_sha256": sha256_json(registry["release_boundary"]),
        "component_roots": {key: roots[key] for key in sorted(roots)},
    })
    return roots


def refresh_registry_hashes(registry: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(registry)
    for name, hash_field in HASH_FIELDS.items():
        for record in result.get(name, []):
            record[hash_field] = record_hash(record, hash_field)
    result["roots"] = compute_registry_roots(result)
    return result


def _scan_forbidden_keys(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in FORBIDDEN_PUBLIC_KEYS:
                errors.append(f"forbidden public field:{path}.{key}")
            _scan_forbidden_keys(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_keys(child, f"{path}[{index}]", errors)


def validate_registry(registry: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks = 0

    try:
        canonical_bytes(registry)
        checks += 1
    except Exception as exc:
        errors.append(f"canonical-domain error:{exc}")
        return {"status": "FAIL", "checks": checks, "errors": errors, "warnings": warnings}

    if registry.get("schema_version") != "1.1.0":
        errors.append("unsupported registry schema")
    checks += 1

    source_files = registry.get("source_snapshot", {}).get("source_files", [])
    normalized_sources: list[dict[str, Any]] = []
    for item in source_files:
        rel = item.get("path", "")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            errors.append(f"unsafe source path:{rel}")
            continue
        path = repo_root / rel
        if not path.is_file():
            errors.append(f"source file missing:{rel}")
            continue
        observed = {"path": rel, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        normalized_sources.append(observed)
        if observed["bytes"] != item.get("bytes"):
            errors.append(f"source byte count mismatch:{rel}")
        if observed["sha256"] != item.get("sha256"):
            errors.append(f"source hash mismatch:{rel}")
        checks += 3
    expected_manifest = sha256_json({
        "domain": "asklepios.content-registry.source-manifest.v1",
        "files": sorted(normalized_sources, key=lambda row: row["path"]),
    })
    if expected_manifest != registry.get("source_snapshot", {}).get("source_manifest_sha256"):
        errors.append("source manifest hash mismatch")
    checks += 1

    known_ids: set[str] = set()
    ids_by_collection: dict[str, set[str]] = {}
    for name, hash_field in HASH_FIELDS.items():
        records = registry.get(name)
        if not isinstance(records, list):
            errors.append(f"collection missing:{name}")
            continue
        id_field = ID_FIELDS[name]
        seen: set[str] = set()
        for record in records:
            identifier = record.get(id_field)
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"invalid identifier:{name}")
                continue
            if identifier in seen:
                errors.append(f"duplicate identifier:{identifier}")
            seen.add(identifier)
            if record.get(hash_field) != record_hash(record, hash_field):
                errors.append(f"record hash mismatch:{identifier}")
            checks += 2
        ids_by_collection[name] = seen
        known_ids.update(seen)

    computed_roots = compute_registry_roots(registry)
    for key, value in computed_roots.items():
        if registry.get("roots", {}).get(key) != value:
            errors.append(f"registry root mismatch:{key}")
        checks += 1

    counts = registry.get("counts", {})
    for name in HASH_FIELDS:
        if counts.get(name) != len(registry.get(name, [])):
            errors.append(f"count mismatch:{name}")
        checks += 1

    assets = registry.get("assets", [])
    assets_by_id = {item.get("asset_id"): item for item in assets}
    protected = [item for item in assets if item.get("kind") == "protected_template"]
    if len(protected) != 2:
        errors.append("protected template inventory mismatch")
    for asset in assets:
        aid = asset.get("asset_id", "")
        capabilities = set(asset.get("capabilities", []))
        if capabilities & FORBIDDEN_CAPABILITIES:
            errors.append(f"forbidden capability:{aid}")
        source = asset.get("source", {})
        rel = source.get("path", "")
        source_entry = next((row for row in source_files if row.get("path") == rel), None)
        if source_entry is None or source.get("file_sha256") != source_entry.get("sha256"):
            errors.append(f"asset source binding mismatch:{aid}")
        kind = asset.get("kind")
        if kind == "research_evidence_reference":
            if not capabilities <= RESEARCH_CAPABILITIES:
                errors.append(f"research capability ceiling exceeded:{aid}")
            if asset.get("status") != "reference_only_entailment_not_adjudicated":
                errors.append(f"research evidence status escalation:{aid}")
        if kind == "scenario_seed" and asset.get("status") != "seed_only_not_deployable":
            errors.append(f"seed incorrectly deployable:{aid}")
        if kind == "protected_template":
            metadata = asset.get("metadata", {})
            if metadata.get("clinical_certification") != "NOT_GRANTED":
                errors.append(f"template authority escalation:{aid}")
        checks += 4

    claim_ids = ids_by_collection.get("claim_candidates", set())
    agent_ids = ids_by_collection.get("agents", set())
    activity_ids = ids_by_collection.get("activities", set())
    endpoint_ids = set(assets_by_id) | claim_ids | agent_ids | activity_ids
    for relation in registry.get("relations", []):
        rid = relation.get("relation_id", "")
        if relation.get("subject_id") not in endpoint_ids:
            errors.append(f"unknown relation subject:{rid}")
        if relation.get("object_id") not in endpoint_ids:
            errors.append(f"unknown relation object:{rid}")
        activity = relation.get("activity_id")
        if activity is not None and activity not in activity_ids:
            errors.append(f"unknown relation activity:{rid}")
        checks += 3

    attested_evidence_ids: set[str] = set()
    for attestation in registry.get("evidence_attestations", []):
        att_id = attestation.get("attestation_id", "")
        evidence_id = attestation.get("evidence_asset_id")
        if evidence_id in attested_evidence_ids:
            errors.append(f"duplicate evidence attestation:{evidence_id}")
        attested_evidence_ids.add(evidence_id)
        evidence = assets_by_id.get(evidence_id)
        source = assets_by_id.get(attestation.get("source_asset_id"))
        if not evidence or evidence.get("kind") != "research_evidence_reference":
            errors.append(f"attestation evidence target invalid:{att_id}")
        if not source or source.get("kind") != "research_source":
            errors.append(f"attestation source target invalid:{att_id}")
        expected = {
            "relation": "REFERENCE_ONLY",
            "identity_verification": "PASS",
            "entailment_status": "NOT_ADJUDICATED",
            "contradiction_status": "NOT_SEARCHED",
            "human_review_status": "NOT_REVIEWED",
            "clinical_authority": "NOT_GRANTED",
            "authority_tier": 3,
        }
        for key, value in expected.items():
            if attestation.get(key) != value:
                errors.append(f"evidence self-certification or escalation:{att_id}:{key}")
        if attestation.get("independent_verifiers") != []:
            errors.append(f"unreviewed verifier asserted:{att_id}")
        checks += 10

    research_evidence_ids = {
        asset_id for asset_id, asset in assets_by_id.items()
        if asset.get("kind") == "research_evidence_reference"
    }
    missing_attestations = sorted(research_evidence_ids - attested_evidence_ids)
    extra_attestations = sorted(attested_evidence_ids - research_evidence_ids)
    if missing_attestations:
        errors.append("evidence attestations missing:" + ",".join(missing_attestations))
    if extra_attestations:
        errors.append("evidence attestations target unknown evidence:" + ",".join(extra_attestations))
    checks += 2

    for claim in registry.get("claim_candidates", []):
        cid = claim.get("claim_id", "")
        if claim.get("support_bit") is not False or claim.get("refute_bit") is not False:
            errors.append(f"unadjudicated claim truth bit asserted:{cid}")
        if claim.get("relation") != "UNRESOLVED":
            errors.append(f"unadjudicated claim relation asserted:{cid}")
        if claim.get("admission_status") != "BLOCKED_FOR_SUPPORT_CLAIM":
            errors.append(f"claim admitted without review:{cid}")
        for evidence_id in claim.get("evidence_asset_ids", []):
            evidence = assets_by_id.get(evidence_id)
            if not evidence or evidence.get("kind") != "research_evidence_reference":
                errors.append(f"claim references unknown evidence:{cid}:{evidence_id}")
        checks += 4

    for profile in registry.get("compatibility_profiles", []):
        pid = profile.get("profile_id", "")
        exercise = assets_by_id.get(profile.get("exercise_asset_id"))
        if not exercise or exercise.get("kind") != "exercise_catalog_entry":
            errors.append(f"compatibility profile target invalid:{pid}")
        status = profile.get("activation_status")
        if status not in {"ACTIVATION_CANDIDATE", "BLOCKED_PENDING_ENGINE_PROFILE"}:
            errors.append(f"automatic activation forbidden:{pid}")
        if status == "ACTIVATION_CANDIDATE" and profile.get("blockers"):
            errors.append(f"candidate profile has blockers:{pid}")
        if status == "BLOCKED_PENDING_ENGINE_PROFILE" and not profile.get("blockers"):
            errors.append(f"blocked profile lacks blocker:{pid}")
        checks += 4

    boundary = registry.get("release_boundary", {})
    expected_boundary = {
        "clinical_authority": "NOT_GRANTED",
        "evidence_authority": "supporting_only",
        "deployment_scope": "research_sandbox_only",
        "generated_scope": "operational_world_only",
        "contains_licensed_source_text": False,
        "migration_is_additive": True,
        "legacy_modules_retained": True,
    }
    for key, value in expected_boundary.items():
        if boundary.get(key) != value:
            errors.append(f"release boundary changed:{key}")
        checks += 1

    _scan_forbidden_keys(registry, "registry", errors)
    checks += 1

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "checks": checks,
        "registry_merkle_root": registry.get("roots", {}).get("registry_merkle_root"),
        "errors": sorted(set(errors)),
        "warnings": warnings,
        "authority": {
            "clinical_authority": boundary.get("clinical_authority"),
            "evidence_authority": boundary.get("evidence_authority"),
            "automatic_activation": False,
        },
    }
