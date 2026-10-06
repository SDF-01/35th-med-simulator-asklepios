#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path

from content_bundle_core import composite_root, extension_set_root, validate_bundle
from content_registry_core import sha256_json


def atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_existing_ids(root: Path, index: dict) -> set[str]:
    baseline = json.loads((root / "content_registry.json").read_text(encoding="utf-8"))
    ids = {asset["asset_id"] for asset in baseline.get("assets", [])}
    ids.update(claim["claim_id"] for claim in baseline.get("claim_candidates", []))
    for row in index.get("extensions", []):
        bundle = json.loads((root / row["path"]).read_text(encoding="utf-8"))
        for collection, field in (
            ("assets", "asset_id"),
            ("claim_candidates", "claim_id"),
        ):
            ids.update(item[field] for item in bundle.get(collection, []))
    return ids


def validate_cross_references(bundle: dict, known_ids: set[str]) -> list[str]:
    errors: list[str] = []
    bundle_ids = {
        item[field]
        for collection, field in (
            ("assets", "asset_id"),
            ("claim_candidates", "claim_id"),
        )
        for item in bundle.get(collection, [])
    }
    all_ids = known_ids | bundle_ids
    collisions = known_ids & bundle_ids
    if collisions:
        errors.append("identifier collision:" + ",".join(sorted(collisions)))
    for relation in bundle.get("relations", []):
        for key in ("subject_id", "object_id"):
            endpoint = relation.get(key)
            if endpoint not in all_ids:
                errors.append(
                    f"unknown relation endpoint:{relation.get('relation_id')}:{endpoint}"
                )
    for attestation in bundle.get("evidence_attestations", []):
        for key in ("evidence_asset_id", "source_asset_id"):
            endpoint = attestation.get(key)
            if endpoint is not None and endpoint not in all_ids:
                errors.append(
                    f"unknown attestation endpoint:{attestation.get('attestation_id')}:{endpoint}"
                )
    for claim in bundle.get("claim_candidates", []):
        for endpoint in claim.get("evidence_asset_ids", []):
            if endpoint not in all_ids:
                errors.append(
                    f"unknown claim evidence:{claim.get('claim_id')}:{endpoint}"
                )
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--registry-dir", default="public/data/content_registry")
    args = parser.parse_args()

    root = Path(args.registry_dir).resolve()
    lock_name = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:20]
    lock = Path(tempfile.gettempdir()) / f"asklepios-content-import-{lock_name}.lock"

    with lock.open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
        errors = validate_bundle(bundle)
        index_path = root / "import_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        baseline = json.loads((root / "content_registry.json").read_text(encoding="utf-8"))
        if index.get("baseline_registry_root") != baseline.get("roots", {}).get(
            "registry_merkle_root"
        ):
            errors.append("index baseline root mismatch")

        bundle_hash = bundle["bundle_sha256"]
        namespace = bundle["namespace"]
        existing = {row["bundle_sha256"]: row for row in index["extensions"]}
        if errors:
            print(json.dumps({"status": "FAIL", "errors": sorted(set(errors))}, indent=2))
            return 3
        if bundle_hash in existing:
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "idempotent": True,
                        "bundle_sha256": bundle_hash,
                        "composite_registry_root": index["composite_registry_root"],
                    },
                    indent=2,
                )
            )
            return 0

        errors.extend(validate_cross_references(bundle, load_existing_ids(root, index)))
        if errors:
            print(json.dumps({"status": "FAIL", "errors": sorted(set(errors))}, indent=2))
            return 3
        if any(
            row["namespace"] == namespace and row["bundle_id"] == bundle["bundle_id"]
            for row in index["extensions"]
        ):
            print(json.dumps({"status": "FAIL", "errors": ["bundle identity conflict"]}, indent=2))
            return 3

        extension_path = root / "extensions" / namespace / f"{bundle_hash}.json"
        receipt_id = f"receipt-{len(index['receipts']) + 1:06d}-{bundle_hash[:12]}"
        receipt_path = root / "receipts" / f"{receipt_id}.json"
        new_extensions = index["extensions"] + [
            {
                "namespace": namespace,
                "bundle_id": bundle["bundle_id"],
                "bundle_sha256": bundle_hash,
                "path": extension_path.relative_to(root).as_posix(),
                "activation_status": "STAGED_NOT_ACTIVE",
            }
        ]
        extension_root = extension_set_root(
            [row["bundle_sha256"] for row in new_extensions]
        )
        composite = composite_root(index["baseline_registry_root"], extension_root)
        receipt = {
            "schema_version": "1.0.0",
            "receipt_id": receipt_id,
            "sequence": len(index["receipts"]) + 1,
            "previous_composite_root": index["composite_registry_root"],
            "bundle_sha256": bundle_hash,
            "new_extension_set_root": extension_root,
            "new_composite_root": composite,
            "activation_status": "STAGED_NOT_ACTIVE",
        }
        receipt["receipt_sha256"] = sha256_json(receipt)

        # The index is the commit point. Orphan files left by a crash are rejected by the auditor.
        atomic(extension_path, bundle)
        atomic(receipt_path, receipt)
        index.update(
            {
                "extensions": new_extensions,
                "receipts": index["receipts"]
                + [
                    {
                        "receipt_id": receipt_id,
                        "path": receipt_path.relative_to(root).as_posix(),
                        "receipt_sha256": receipt["receipt_sha256"],
                    }
                ],
                "extension_set_root": extension_root,
                "composite_registry_root": composite,
            }
        )
        atomic(index_path, index)
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "idempotent": False,
                    "bundle_sha256": bundle_hash,
                    "receipt_id": receipt_id,
                    "composite_registry_root": composite,
                    "activation_status": "STAGED_NOT_ACTIVE",
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
