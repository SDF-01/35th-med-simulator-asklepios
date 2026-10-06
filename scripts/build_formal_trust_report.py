#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


root = Path.cwd()
manifest = json.loads((root / "formal/TRUST_MANIFEST.json").read_text(encoding="utf-8"))
sources = sorted((root / "formal").rglob("*.lean"))
theorem_pattern = re.compile(r"^\s*(?:@\[[^\]]+\]\s*)?theorem\s+([A-Za-z0-9_.'-]+)", re.MULTILINE)
placeholder_pattern = re.compile(r"(^|[^A-Za-z0-9_])(sorry|admit)([^A-Za-z0-9_]|$)")

theorems: list[str] = []
placeholders: list[str] = []
files = []

for path in sources:
    text = path.read_text(encoding="utf-8")
    relative = path.relative_to(root).as_posix()
    theorems.extend(theorem_pattern.findall(text))
    if placeholder_pattern.search(text):
        placeholders.append(relative)
    files.append({"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size})

report = {
    "schema_version": "1.0.0",
    "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "status": "PASS" if not placeholders else "FAIL",
    "formal_root_module": manifest["formal_root_module"],
    "toolchain": (root / "lean-toolchain").read_text(encoding="utf-8").strip(),
    "lake_manifest_sha256": sha256(root / "lake-manifest.json"),
    "source_files": files,
    "theorem_declarations": sorted(theorems),
    "theorem_count": len(theorems),
    "incomplete_proof_files": placeholders,
    "required_checks": manifest["required_checks"],
    "independent_kernel_status": manifest["independent_kernel_status"],
    "scope": manifest["scope"],
}
output = root / "reports/formal-trust-report.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 3)
