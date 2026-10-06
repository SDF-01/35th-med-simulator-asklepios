#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def manifest(directory: Path) -> dict[str, dict[str, int | str]]:
    if not directory.is_dir():
        raise ValueError(f"build directory missing:{directory}")
    result: dict[str, dict[str, int | str]] = {}
    for path in sorted(item for item in directory.rglob('*') if item.is_file()):
        relative = path.relative_to(directory).as_posix()
        data = path.read_bytes()
        result[relative] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if not result:
        raise ValueError(f"build directory empty:{directory}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--second', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('reports/facility-arrival-build-reproducibility.json'))
    args = parser.parse_args()
    try:
        first = manifest(args.first.resolve())
        second = manifest(args.second.resolve())
        first_keys, second_keys = set(first), set(second)
        changed = sorted(key for key in first_keys & second_keys if first[key] != second[key])
        missing = sorted(first_keys - second_keys)
        unexpected = sorted(second_keys - first_keys)
        errors = [*(f"changed:{item}" for item in changed), *(f"missing:{item}" for item in missing), *(f"unexpected:{item}" for item in unexpected)]
        report = {
            "schema_version": "1.0.0",
            "status": "PASS" if not errors else "FAIL",
            "files_compared": len(first_keys | second_keys),
            "first_manifest": first,
            "second_manifest": second,
            "errors": errors,
        }
    except (OSError, ValueError) as exc:
        report = {"schema_version": "1.0.0", "status": "FAIL", "files_compared": 0, "errors": [str(exc)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in {'first_manifest','second_manifest'}}, indent=2, sort_keys=True))
    return 0 if report['status'] == 'PASS' else 3

if __name__ == '__main__':
    raise SystemExit(main())
