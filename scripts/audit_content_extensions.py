#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_bundle_core import composite_root, extension_set_root, validate_bundle
from content_registry_core import sha256_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry-dir", default="public/data/content_registry")
    args = parser.parse_args()
    root = Path(args.registry_dir)
    index = json.loads((root / "import_index.json").read_text(encoding="utf-8"))
    baseline = json.loads((root / "content_registry.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if index.get("baseline_registry_root") != baseline.get("roots", {}).get(
        "registry_merkle_root"
    ):
        errors.append("index baseline root mismatch")

    hashes: list[str] = []
    declared_extension_paths: set[str] = set()
    for row in index.get("extensions", []):
        declared_extension_paths.add(row["path"])
        path = root / row["path"]
        if not path.is_file():
            errors.append(f"extension missing:{row['path']}")
            continue
        bundle = json.loads(path.read_text(encoding="utf-8"))
        errors.extend(f"{row['path']}:{error}" for error in validate_bundle(bundle))
        if bundle.get("bundle_sha256") != row.get("bundle_sha256"):
            errors.append(f"index bundle hash mismatch:{row['path']}")
        if row.get("activation_status") != "STAGED_NOT_ACTIVE":
            errors.append(f"extension activated during ingestion:{row['path']}")
        hashes.append(row.get("bundle_sha256"))

    actual_extension_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "extensions").rglob("*.json")
    } if (root / "extensions").exists() else set()
    for orphan in sorted(actual_extension_paths - declared_extension_paths):
        errors.append(f"orphan extension file:{orphan}")

    extension_root = extension_set_root(hashes)
    composite = composite_root(index["baseline_registry_root"], extension_root)
    if extension_root != index.get("extension_set_root"):
        errors.append("extension set root mismatch")
    if composite != index.get("composite_registry_root"):
        errors.append("composite registry root mismatch")

    declared_receipt_paths = {row["path"] for row in index.get("receipts", [])}
    actual_receipt_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "receipts").rglob("*.json")
    } if (root / "receipts").exists() else set()
    for orphan in sorted(actual_receipt_paths - declared_receipt_paths):
        errors.append(f"orphan receipt file:{orphan}")

    previous = composite_root(index["baseline_registry_root"], extension_set_root([]))
    observed_bundle_hashes: list[str] = []
    for expected_sequence, row in enumerate(index.get("receipts", []), 1):
        path = root / row["path"]
        if not path.is_file():
            errors.append(f"receipt missing:{row['path']}")
            continue
        receipt = json.loads(path.read_text(encoding="utf-8"))
        temporary = dict(receipt)
        observed = temporary.pop("receipt_sha256", None)
        if observed != sha256_json(temporary):
            errors.append(f"receipt hash mismatch:{row['path']}")
        if observed != row.get("receipt_sha256"):
            errors.append(f"receipt index mismatch:{row['path']}")
        if receipt.get("sequence") != expected_sequence:
            errors.append(f"receipt sequence mismatch:{row['path']}")
        if receipt.get("previous_composite_root") != previous:
            errors.append(f"receipt chain break:{row['path']}")
        if receipt.get("activation_status") != "STAGED_NOT_ACTIVE":
            errors.append(f"receipt activation escalation:{row['path']}")
        observed_bundle_hashes.append(receipt.get("bundle_sha256"))
        expected_partial_root = extension_set_root(observed_bundle_hashes)
        expected_partial_composite = composite_root(
            index["baseline_registry_root"], expected_partial_root
        )
        if receipt.get("new_extension_set_root") != expected_partial_root:
            errors.append(f"receipt extension root mismatch:{row['path']}")
        if receipt.get("new_composite_root") != expected_partial_composite:
            errors.append(f"receipt composite root mismatch:{row['path']}")
        previous = receipt.get("new_composite_root")
    if index.get("receipts") and previous != composite:
        errors.append("receipt chain does not end at current root")
    if sorted(observed_bundle_hashes) != sorted(hashes):
        errors.append("receipt/bundle set mismatch")

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "extensions": len(index.get("extensions", [])),
        "receipts": len(index.get("receipts", [])),
        "composite_registry_root": composite,
        "errors": sorted(set(errors)),
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
