#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from content_bundle_core import seal_bundle, validate_bundle

ROOT = Path.cwd()
cases: list[dict[str, object]] = []


def result(name: str, passed: bool) -> None:
    cases.append({"case_id": name, "pass": bool(passed)})


def raw_bundle(namespace: str, suffix: str) -> dict:
    source_id = f"extension:{namespace}:source-{suffix}"
    evidence_id = f"extension:{namespace}:evidence-{suffix}"
    return {
        "schema_version": "1.0.0",
        "bundle_id": f"{namespace}-{suffix}",
        "namespace": namespace,
        "source_kind": "evidence_identity",
        "activation_status": "STAGED_NOT_ACTIVE",
        "source_manifest_sha256": (suffix[0] if suffix[0] in "0123456789abcdef" else "1") * 64,
        "assets": [
            {
                "asset_id": source_id,
                "kind": "research_source",
                "capabilities": ["catalog_display", "citation_reference"],
                "metadata": {"doi": f"10.0000/{namespace}.{suffix}"},
            },
            {
                "asset_id": evidence_id,
                "kind": "research_evidence_reference",
                "capabilities": ["citation_reference", "aar_discussion"],
                "metadata": {"doi": f"10.0000/{namespace}.{suffix}"},
            },
        ],
        "relations": [
            {
                "relation_id": f"extension:{namespace}:relation-{suffix}",
                "predicate": "derivedFrom",
                "subject_id": evidence_id,
                "object_id": source_id,
            }
        ],
        "evidence_attestations": [
            {
                "attestation_id": f"extension:{namespace}:attestation-{suffix}",
                "evidence_asset_id": evidence_id,
                "source_asset_id": source_id,
                "relation": "REFERENCE_ONLY",
                "identity_verification": "PASS",
                "entailment_status": "NOT_ADJUDICATED",
                "contradiction_status": "NOT_SEARCHED",
                "human_review_status": "NOT_REVIEWED",
                "clinical_authority": "NOT_GRANTED",
                "independent_verifiers": [],
            }
        ],
        "claim_candidates": [
            {
                "claim_id": f"extension:{namespace}:claim-{suffix}",
                "evidence_asset_ids": [evidence_id],
                "support_bit": False,
                "refute_bit": False,
                "relation": "UNRESOLVED",
                "admission_status": "BLOCKED_FOR_SUPPORT_CLAIM",
            }
        ],
        "compatibility_hints": [],
    }


baseline_raw = raw_bundle("future-evidence", "a")
baseline = seal_bundle(baseline_raw)
result("valid_bundle", not validate_bundle(baseline))

for name, mutation in [
    (
        "clinical_capability_rejected",
        lambda value: value["assets"][0]["capabilities"].append(
            "define_new_clinical_rule"
        ),
    ),
    (
        "self_certification_rejected",
        lambda value: value["evidence_attestations"][0].update(
            {"relation": "SUPPORTS"}
        ),
    ),
    (
        "licensed_text_rejected",
        lambda value: value["assets"][0]["metadata"].update(
            {"licensed_text": "forbidden"}
        ),
    ),
    ("activation_rejected", lambda value: value.update({"activation_status": "ACTIVE"})),
    (
        "unsafe_integer_rejected",
        lambda value: value["assets"][0]["metadata"].update({"count": 2**60}),
    ),
    (
        "namespace_escape_rejected",
        lambda value: value["claim_candidates"][0].update(
            {"claim_id": "extension:other:claim"}
        ),
    ),
    (
        "executable_field_rejected",
        lambda value: value["assets"][0].update({"script": "rm -rf /"}),
    ),
]:
    changed = copy.deepcopy(baseline_raw)
    mutation(changed)
    try:
        sealed = seal_bundle(changed)
        passed = bool(validate_bundle(sealed))
    except Exception:
        passed = True
    result(name, passed)


def run_import(registry: Path, bundle_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            "scripts/import_content_bundle.py",
            "--bundle",
            str(bundle_path),
            "--registry-dir",
            str(registry),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    registry = temp / "registry"
    shutil.copytree(ROOT / "public/data/content_registry", registry)
    bundle_path = temp / "bundle.json"
    bundle_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    first = run_import(registry, bundle_path)
    second = run_import(registry, bundle_path)
    audit = subprocess.run(
        [
            "python3",
            "scripts/audit_content_extensions.py",
            "--registry-dir",
            str(registry),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result("atomic_import", first.returncode == 0)
    result(
        "idempotent_reimport",
        second.returncode == 0 and '"idempotent": true' in second.stdout.casefold(),
    )
    result("receipt_chain_audit", audit.returncode == 0)

    collision_raw = raw_bundle("collision", "a")
    collision_raw["assets"][0]["asset_id"] = "template:ASK-A-001"
    collision = seal_bundle(collision_raw)
    collision_path = temp / "collision.json"
    collision_path.write_text(json.dumps(collision, indent=2), encoding="utf-8")
    collision_result = run_import(registry, collision_path)
    result("baseline_identifier_collision_rejected", collision_result.returncode != 0)

    unknown_raw = raw_bundle("unknown-reference", "a")
    unknown_raw["relations"][0]["object_id"] = "extension:missing:source"
    unknown = seal_bundle(unknown_raw)
    unknown_path = temp / "unknown.json"
    unknown_path.write_text(json.dumps(unknown, indent=2), encoding="utf-8")
    unknown_result = run_import(registry, unknown_path)
    result("unknown_relation_endpoint_rejected", unknown_result.returncode != 0)

# Import order must not change the final extension-set/composite root.
with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    registry_ab = temp / "registry-ab"
    registry_ba = temp / "registry-ba"
    shutil.copytree(ROOT / "public/data/content_registry", registry_ab)
    shutil.copytree(ROOT / "public/data/content_registry", registry_ba)
    bundle_a = seal_bundle(raw_bundle("order-a", "a"))
    bundle_b = seal_bundle(raw_bundle("order-b", "b"))
    path_a = temp / "a.json"
    path_b = temp / "b.json"
    path_a.write_text(json.dumps(bundle_a, indent=2), encoding="utf-8")
    path_b.write_text(json.dumps(bundle_b, indent=2), encoding="utf-8")
    run_import(registry_ab, path_a)
    run_import(registry_ab, path_b)
    run_import(registry_ba, path_b)
    run_import(registry_ba, path_a)
    index_ab = json.loads((registry_ab / "import_index.json").read_text())
    index_ba = json.loads((registry_ba / "import_index.json").read_text())
    result(
        "order_independent_composite_root",
        index_ab["composite_registry_root"] == index_ba["composite_registry_root"],
    )

# Two concurrent writers must both survive the lock-protected transaction.
with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    registry = temp / "registry"
    shutil.copytree(ROOT / "public/data/content_registry", registry)
    paths = []
    for namespace, suffix in (("concurrent-a", "a"), ("concurrent-b", "b")):
        path = temp / f"{namespace}.json"
        path.write_text(
            json.dumps(seal_bundle(raw_bundle(namespace, suffix)), indent=2),
            encoding="utf-8",
        )
        paths.append(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda path: run_import(registry, path), paths))
    index = json.loads((registry / "import_index.json").read_text())
    audit = subprocess.run(
        [
            "python3",
            "scripts/audit_content_extensions.py",
            "--registry-dir",
            str(registry),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    result(
        "concurrent_imports_preserved",
        all(run.returncode == 0 for run in runs)
        and len(index["extensions"]) == 2
        and audit.returncode == 0,
    )

errors = [case["case_id"] for case in cases if not case["pass"]]
print(
    json.dumps(
        {
            "schema_version": "1.1.0",
            "status": "PASS" if not errors else "FAIL",
            "cases": len(cases),
            "errors": errors,
            "results": cases,
        },
        indent=2,
    )
)
raise SystemExit(0 if not errors else 3)
