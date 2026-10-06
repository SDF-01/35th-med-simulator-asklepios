#!/usr/bin/env python3
"""Create or verify the content-addressed input locks in RELEASE_GRAPH.json."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from release_graph_core import GRAPH_PATH, ReleaseGraphError, canonical_json, lock_input_sets, read_json, write_json
from release_result import FAIL, PASS, exit_code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--input-set", action="append", dest="input_sets")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = args.repo.resolve()
    graph_path = args.graph if args.graph.is_absolute() else root / args.graph
    try:
        original = read_json(graph_path)
        locked = lock_input_sets(root, original, args.input_sets)
        differs = canonical_json(original) != canonical_json(locked)
        if args.check:
            classification = FAIL if differs else PASS
            errors = ["release graph input locks are stale"] if differs else []
        else:
            write_json(graph_path, locked)
            classification = PASS
            errors = []
        report = {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "mode": "check" if args.check else "write",
            "input_sets": sorted(args.input_sets or locked.get("input_sets", {})),
            "changed": differs,
            "errors": errors,
        }
    except Exception as exc:  # noqa: BLE001
        classification = FAIL
        report = {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "mode": "check" if args.check else "write",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
