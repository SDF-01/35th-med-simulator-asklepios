#!/usr/bin/env python3
"""Verify the canonical public facility artifacts and reject duplicate outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PAIRS = {
    "public/data/facility_arrival/reference-session.json": "examples/facility-arrival/interaction.json",
    "public/data/facility_arrival/reference-aar.json": "examples/facility-arrival/aar.json",
    "public/data/facility_arrival/reference-manifest.json": "examples/facility-arrival/manifest.json",
}
FORBIDDEN = {
    "public/data/facility_arrival/reference_session.json",
    "public/data/facility_arrival/reference_aar.json",
    "public/data/facility_arrival/manifest.json",
    "reports/facility-arrival-generation.json",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def validate(root: Path) -> dict:
    errors: list[str] = []
    public = root / "public/data/facility_arrival"
    expected_names = {Path(path).name for path in PAIRS}
    observed_names: set[str] = set()
    if not public.is_dir():
        errors.append("facility public-data directory missing")
    else:
        for path in sorted(public.iterdir()):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                errors.append(f"symlink forbidden:{rel}")
                continue
            if not path.is_file():
                errors.append(f"non-file artifact forbidden:{rel}")
                continue
            observed_names.add(path.name)
        for name in sorted(observed_names - expected_names):
            errors.append(f"unexpected public artifact:{name}")
        for name in sorted(expected_names - observed_names):
            errors.append(f"canonical public artifact missing:{name}")

    comparisons = []
    for public_rel, source_rel in PAIRS.items():
        public_path = root / public_rel
        source_path = root / source_rel
        public_hash = sha256(public_path) if public_path.is_file() and not public_path.is_symlink() else None
        source_hash = sha256(source_path) if source_path.is_file() and not source_path.is_symlink() else None
        if source_hash is None:
            errors.append(f"source artifact missing:{source_rel}")
        if public_hash is None:
            errors.append(f"public artifact missing:{public_rel}")
        if public_hash is not None and source_hash is not None and public_hash != source_hash:
            errors.append(f"public/source artifact mismatch:{public_rel}:{source_rel}")
        comparisons.append({
            "public_path": public_rel,
            "source_path": source_rel,
            "public_sha256": public_hash,
            "source_sha256": source_hash,
            "match": public_hash is not None and public_hash == source_hash,
        })

    for rel in sorted(FORBIDDEN):
        if (root / rel).exists() or (root / rel).is_symlink():
            errors.append(f"forbidden legacy/transient artifact present:{rel}")

    return {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "canonical_public_files": sorted(PAIRS),
        "observed_public_files": sorted(
            f"public/data/facility_arrival/{name}" for name in observed_names
        ),
        "comparisons": comparisons,
        "forbidden_paths": sorted(FORBIDDEN),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default="reports/facility-arrival-artifact-boundary.json")
    args = parser.parse_args()
    root = args.repo.resolve()
    report = validate(root)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
