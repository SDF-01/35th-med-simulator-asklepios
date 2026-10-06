#!/usr/bin/env python3
"""Focused adversarial tests for repository-local release source closure."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from release_graph_core import write_json
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification
from release_source_closure import build_dependency_index, transitive_closure_errors

OUTPUT = Path("reports/release-source-closure-mutations.json")
SCHEMA_VERSION = "1.0.0"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def evaluate(
    root: Path,
    entrypoints: list[str],
    locked: set[str],
    *,
    generated: set[str] | None = None,
) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    index, index_errors = build_dependency_index(root, entrypoints)
    closure_errors, dependencies, _visited = transitive_closure_errors(
        entrypoints,
        locked,
        index,
        scope="focused-test",
        authenticated_generated_files=generated or set(),
    )
    rendered = {
        source: [dependency.as_dict() for dependency in values]
        for source, values in sorted(index.items())
    }
    return sorted(set(index_errors + closure_errors)), rendered


def result_for(case_id: str, rejected: bool, expected_rejection: bool, errors: list[str], **details: object) -> dict:
    if expected_rejection:
        classification = EXPECTED_REJECTION if rejected else FAIL
        case_errors = [] if rejected else ["unsafe source closure was accepted"]
    else:
        classification = PASS if not rejected else FAIL
        case_errors = [] if not rejected else errors
    return case_result(
        case_id,
        classification,
        errors=case_errors,
        observed_errors=errors,
        **details,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    repo = args.repo.resolve()
    results: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="asklepios-source-closure-") as temporary:
        root = Path(temporary)

        # Baseline recursive Python closure.
        write(root / "scripts/main.py", "from helper import value\nprint(value)\n")
        write(root / "scripts/helper.py", "value = 1\n")
        errors, index = evaluate(root, ["scripts/main.py"], {"scripts/main.py", "scripts/helper.py"})
        results.append(result_for("python-recursive-baseline", bool(errors), False, errors, dependency_index=index))

        errors, _ = evaluate(root, ["scripts/main.py"], {"scripts/main.py"})
        results.append(result_for("python-local-helper-omitted", bool(errors), True, errors))

        # A second-level helper must not disappear merely because the first helper is locked.
        write(root / "scripts/helper.py", "from nested import value\n")
        write(root / "scripts/nested.py", "value = 1\n")
        errors, _ = evaluate(root, ["scripts/main.py"], {"scripts/main.py", "scripts/helper.py"})
        results.append(result_for("python-transitive-helper-omitted", bool(errors), True, errors))

        # Relative Node closure and the reviewed @/ -> src/ alias.
        write(root / "scripts/main.mjs", "import './helper.mjs';\nimport '@/shared/value';\n")
        write(root / "scripts/helper.mjs", "export const value = 1;\n")
        write(root / "src/shared/value.ts", "export const value = 1;\n")
        node_locked = {"scripts/main.mjs", "scripts/helper.mjs", "src/shared/value.ts"}
        errors, index = evaluate(root, ["scripts/main.mjs"], node_locked)
        results.append(result_for("node-relative-and-alias-baseline", bool(errors), False, errors, dependency_index=index))

        errors, _ = evaluate(root, ["scripts/main.mjs"], {"scripts/main.mjs", "scripts/helper.mjs"})
        results.append(result_for("node-alias-helper-omitted", bool(errors), True, errors))

        # TypeScript may intentionally retain a .js runtime specifier for a .ts source.
        write(root / "api/entry.ts", "import '../server/index.js';\n")
        write(root / "server/index.ts", "export const server = true;\n")
        errors, index = evaluate(root, ["api/entry.ts"], {"api/entry.ts", "server/index.ts"})
        results.append(result_for("typescript-js-specifier-resolves-source", bool(errors), False, errors, dependency_index=index))

        # Generated code is admissible only when a predecessor receipt binds it.
        write(root / "scripts/generated-user.mjs", "import './generated.mjs';\n")
        write(root / "scripts/generated.mjs", "export const generated = true;\n")
        errors, _ = evaluate(root, ["scripts/generated-user.mjs"], {"scripts/generated-user.mjs"})
        results.append(result_for("generated-dependency-without-receipt", bool(errors), True, errors))
        errors, _ = evaluate(
            root,
            ["scripts/generated-user.mjs"],
            {"scripts/generated-user.mjs"},
            generated={"scripts/generated.mjs"},
        )
        results.append(result_for("generated-dependency-with-predecessor-receipt", bool(errors), False, errors))

        # Ambiguous, missing, unsafe, and symlinked sources all fail closed.
        write(root / "scripts/ambiguous.mjs", "import './choice';\n")
        write(root / "scripts/choice.ts", "export const choice = 1;\n")
        write(root / "scripts/choice.tsx", "export const choice = 2;\n")
        errors, _ = evaluate(root, ["scripts/ambiguous.mjs"], {"scripts/ambiguous.mjs", "scripts/choice.ts"})
        results.append(result_for("ambiguous-node-import", bool(errors), True, errors))

        write(root / "scripts/missing.mjs", "import './does-not-exist';\n")
        errors, _ = evaluate(root, ["scripts/missing.mjs"], {"scripts/missing.mjs"})
        results.append(result_for("unresolved-node-import", bool(errors), True, errors))

        write(root / "scripts/backslash.mjs", "import '.\\\\escape';\n")
        errors, _ = evaluate(root, ["scripts/backslash.mjs"], {"scripts/backslash.mjs"})
        results.append(result_for("windows-separator-import", bool(errors), True, errors))

        outside = root.parent / f"{root.name}-outside.mjs"
        try:
            write(outside, "export const outside = true;\n")
            write(root / "scripts/escape.mjs", f"import '../../{outside.name}';\n")
            errors, _ = evaluate(root, ["scripts/escape.mjs"], {"scripts/escape.mjs"})
            results.append(result_for("repository-path-escape", bool(errors), True, errors))
        finally:
            outside.unlink(missing_ok=True)

        write(root / "scripts/real-helper.mjs", "export const value = 1;\n")
        symlink_path = root / "scripts/symlink-helper.mjs"
        try:
            os.symlink("real-helper.mjs", symlink_path)
            write(root / "scripts/symlink-user.mjs", "import './symlink-helper.mjs';\n")
            errors, _ = evaluate(
                root,
                ["scripts/symlink-user.mjs"],
                {"scripts/symlink-user.mjs", "scripts/symlink-helper.mjs"},
            )
            results.append(result_for("symlinked-local-helper", bool(errors), True, errors))
        except (OSError, NotImplementedError) as exc:
            results.append(case_result(
                "symlinked-local-helper",
                PASS,
                errors=[],
                skipped=True,
                skip_reason=f"symlink unavailable:{type(exc).__name__}",
            ))

        errors, _ = evaluate(root, ["scripts/main.py"], {"scripts/helper.py", "scripts/nested.py"})
        results.append(result_for("stage-entrypoint-not-locked", bool(errors), True, errors))

    classification = suite_classification(results)
    report = {
        "schema_version": SCHEMA_VERSION,
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "attacks": sum(1 for item in results if item["classification"] == EXPECTED_REJECTION),
        "accepted_attacks": sum(1 for item in results if item["classification"] == FAIL),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] == FAIL],
    }
    write_json(repo / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
