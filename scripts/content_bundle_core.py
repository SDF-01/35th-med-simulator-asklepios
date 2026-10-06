#!/usr/bin/env python3
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from content_registry_core import (
    FORBIDDEN_CAPABILITIES,
    canonical_bytes,
    collection_root,
    record_hash,
    sha256_json,
)

SOURCE_CAPABILITY_CEILINGS = {
    "evidence_identity": {"catalog_display", "citation_reference", "aar_discussion"},
    "repository_content": {
        "catalog_display",
        "preserve_existing_content",
        "operational_context",
        "routing",
        "learner_prompt",
    },
    "operational_calibration_candidate": {
        "catalog_display",
        "operational_context",
        "aar_discussion",
    },
    "human_performance_candidate": {
        "catalog_display",
        "operational_context",
        "aar_discussion",
    },
    "reviewed_template_candidate": {"catalog_display", "preserve_existing_content"},
}
COLLECTIONS = (
    ("assets", "asset_id", "record_sha256"),
    ("relations", "relation_id", "relation_sha256"),
    ("evidence_attestations", "attestation_id", "attestation_sha256"),
    ("claim_candidates", "claim_id", "claim_sha256"),
    ("compatibility_hints", "profile_id", "profile_sha256"),
)
NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_BUNDLE_KEYS = {
    "licensed_text",
    "full_text",
    "raw_text",
    "article_text",
    "xml_body",
    "institutional_token",
    "api_key",
    "embedding_vector",
    "private_prompt",
    "script",
    "command",
    "executable",
    "module_source",
}


def _scan_bundle(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            folded = key.casefold()
            if folded in FORBIDDEN_BUNDLE_KEYS:
                errors.append(f"forbidden bundle field:{path}.{key}")
            if folded.endswith("path") and isinstance(child, str):
                parts = Path(child).parts
                if child.startswith("/") or ".." in parts or child.startswith("data/private"):
                    errors.append(f"unsafe bundle path:{path}.{key}")
            _scan_bundle(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_bundle(child, f"{path}[{index}]", errors)


def seal_bundle(raw: dict[str, Any]) -> dict[str, Any]:
    bundle = copy.deepcopy(raw)
    bundle.pop("bundle_sha256", None)
    bundle.pop("roots", None)
    for name, _id_field, hash_field in COLLECTIONS:
        bundle.setdefault(name, [])
        for record in bundle[name]:
            record[hash_field] = record_hash(record, hash_field)
    roots = {
        f"{name}_merkle_root": collection_root(
            f"asklepios.content-bundle.{name}.v1",
            [record[hash_field] for record in bundle[name]],
        )
        for name, _id_field, hash_field in COLLECTIONS
    }
    bundle["roots"] = roots
    bundle["bundle_sha256"] = sha256_json(
        {"domain": "asklepios.content-bundle.v1", "bundle": bundle}
    )
    return bundle


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        canonical_bytes(bundle)
    except Exception as exc:
        return [f"canonical-domain error:{exc}"]

    if bundle.get("schema_version") != "1.0.0":
        errors.append("unsupported bundle schema")
    namespace = bundle.get("namespace", "")
    if not isinstance(namespace, str) or not NAMESPACE.fullmatch(namespace):
        errors.append("invalid namespace")
    bundle_id = bundle.get("bundle_id", "")
    if not isinstance(bundle_id, str) or not NAMESPACE.fullmatch(bundle_id):
        errors.append("invalid bundle id")
    source_kind = bundle.get("source_kind")
    ceiling = SOURCE_CAPABILITY_CEILINGS.get(source_kind)
    if ceiling is None:
        errors.append("unsupported source kind")
        ceiling = set()
    source_manifest = bundle.get("source_manifest_sha256")
    if not isinstance(source_manifest, str) or not HEX64.fullmatch(source_manifest):
        errors.append("invalid source manifest hash")
    if bundle.get("activation_status") != "STAGED_NOT_ACTIVE":
        errors.append("bundle must be staging-only")

    expected = seal_bundle(bundle)
    if bundle.get("bundle_sha256") != expected.get("bundle_sha256"):
        errors.append("bundle hash mismatch")
    if bundle.get("roots") != expected.get("roots"):
        errors.append("bundle roots mismatch")

    local_ids: set[str] = set()
    for name, id_field, _hash_field in COLLECTIONS:
        records = bundle.get(name)
        if not isinstance(records, list):
            errors.append(f"bundle collection missing:{name}")
            continue
        for record in records:
            identifier = record.get(id_field)
            if not isinstance(identifier, str) or not identifier.startswith(
                f"extension:{namespace}:"
            ):
                errors.append(f"record namespace mismatch:{name}:{identifier}")
            if identifier in local_ids:
                errors.append(f"duplicate bundle identifier:{identifier}")
            if isinstance(identifier, str):
                local_ids.add(identifier)

    for asset in bundle.get("assets", []):
        asset_id = asset.get("asset_id")
        capabilities = set(asset.get("capabilities", []))
        if not capabilities <= ceiling:
            errors.append(f"capability ceiling exceeded:{asset_id}")
        if capabilities & FORBIDDEN_CAPABILITIES:
            errors.append(f"clinical capability forbidden:{asset_id}")

    for relation in bundle.get("relations", []):
        for key in ("subject_id", "object_id"):
            endpoint = relation.get(key)
            if not isinstance(endpoint, str) or not endpoint:
                errors.append(f"invalid relation endpoint:{relation.get('relation_id')}:{key}")

    for attestation in bundle.get("evidence_attestations", []):
        if (
            attestation.get("relation") != "REFERENCE_ONLY"
            or attestation.get("identity_verification") not in {None, "PASS"}
            or attestation.get("entailment_status") != "NOT_ADJUDICATED"
            or attestation.get("contradiction_status") not in {None, "NOT_SEARCHED"}
            or attestation.get("human_review_status") != "NOT_REVIEWED"
            or attestation.get("clinical_authority") not in {None, "NOT_GRANTED"}
            or attestation.get("independent_verifiers") not in (None, [])
        ):
            errors.append(
                f"evidence bundle self-certification:{attestation.get('attestation_id')}"
            )

    for claim in bundle.get("claim_candidates", []):
        if (
            claim.get("admission_status") != "BLOCKED_FOR_SUPPORT_CLAIM"
            or claim.get("support_bit") is not False
            or claim.get("refute_bit") is not False
            or claim.get("relation") not in {None, "UNRESOLVED"}
        ):
            errors.append(f"claim admitted during ingestion:{claim.get('claim_id')}")

    for hint in bundle.get("compatibility_hints", []):
        if hint.get("activation_status") not in {None, "PENDING_REVIEW"}:
            errors.append(
                f"compatibility hint activated during ingestion:{hint.get('profile_id')}"
            )

    _scan_bundle(bundle, "bundle", errors)
    return sorted(set(errors))


def extension_set_root(bundle_hashes: list[str]) -> str:
    return sha256_json(
        {
            "domain": "asklepios.content-registry.extension-set.v1",
            "bundle_hashes": sorted(bundle_hashes),
        }
    )


def composite_root(baseline: str, extension_root: str) -> str:
    return sha256_json(
        {
            "domain": "asklepios.content-registry.composite.v1",
            "baseline_registry_root": baseline,
            "extension_set_root": extension_root,
        }
    )
