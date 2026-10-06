#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


AXIOM_LIST = re.compile(r"depends on axioms:\s*\[([^\]]*)\]", re.IGNORECASE)
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.'-]*")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--manifest", default="formal/TRUST_MANIFEST.json")
    args = parser.parse_args()

    log_path = Path(args.log)
    manifest_path = Path(args.manifest)
    if not log_path.exists():
        raise SystemExit(f"Axiom log missing: {log_path}")
    if not manifest_path.exists():
        raise SystemExit(f"Trust manifest missing: {manifest_path}")

    text = log_path.read_text(encoding="utf-8", errors="replace")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = list(manifest["required_theorems"])
    permitted = set(manifest["permitted_axioms"])

    errors: list[str] = []

    lowered = text.casefold()
    for forbidden in ("sorryax", "admit", "declaration uses 'sorry'"):
        if forbidden in lowered:
            errors.append(f"forbidden proof dependency found:{forbidden}")

    for theorem in expected:
        if theorem not in text:
            errors.append(f"theorem missing from axiom audit:{theorem}")

    observed: set[str] = set()
    for match in AXIOM_LIST.finditer(text):
        for token in IDENTIFIER.findall(match.group(1)):
            observed.add(token)

    unexpected = sorted(observed - permitted)
    if unexpected:
        errors.append("unexpected axioms:" + ",".join(unexpected))

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if not errors else "FAIL",
        "theorems_expected": len(expected),
        "theorems_observed": sum(1 for theorem in expected if theorem in text),
        "permitted_axioms": sorted(permitted),
        "observed_axioms": sorted(observed),
        "errors": errors,
    }
    print(json.dumps(report, indent=2))
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
