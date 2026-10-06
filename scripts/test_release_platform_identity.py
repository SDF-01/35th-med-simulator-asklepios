#!/usr/bin/env python3
"""Adversarial cross-platform identity tests for the canonical release graph."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from release_graph_core import (
    GRAPH_PATH,
    ReleaseGraphError,
    canonical_repository_bytes,
    collect_input_files,
    load_graph,
    native_command,
    sha256_repository_file,
    verify_input_set,
    write_json,
)
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification

OUTPUT = Path("reports/release-platform-identity.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    root = args.repo.resolve()
    results: list[dict] = []

    attributes = (root / ".gitattributes").read_text(encoding="utf-8")
    results.append(case_result(
        "repository-wide-lf-policy",
        PASS if "* text=auto eol=lf" in attributes else FAIL,
        errors=[] if "* text=auto eol=lf" in attributes else ["repository-wide LF policy missing"],
    ))

    windows_npm = native_command(["npm", "run", "build"], "nt", comspec="cmd.exe")
    results.append(case_result(
        "windows-npm-shim",
        PASS if windows_npm[:4] == ["cmd.exe", "/d", "/s", "/c"] and "npm.cmd" in windows_npm[4] else FAIL,
        execution_argv=windows_npm,
    ))
    windows_npx = native_command(["npx", "tsx", "x.ts"], "nt", comspec="cmd.exe")
    results.append(case_result(
        "windows-npx-shim",
        PASS if windows_npx[:4] == ["cmd.exe", "/d", "/s", "/c"] and "npx.cmd" in windows_npx[4] else FAIL,
        execution_argv=windows_npx,
    ))
    quoted = native_command(["npm", "run", "fixture", "--", "value with spaces", "A&B"], "nt", comspec="C:/Windows/System32/cmd.exe")
    results.append(case_result(
        "windows-shim-arguments-quoted",
        PASS if quoted[:4] == ["C:/Windows/System32/cmd.exe", "/d", "/s", "/c"] and '"value with spaces"' in quoted[4] and 'A&B' in quoted[4] else FAIL,
        execution_argv=quoted,
    ))
    results.append(case_result(
        "posix-npm-identity",
        PASS if native_command(["npm", "run", "build"], "posix")[0] == "npm" else FAIL,
    ))

    with tempfile.TemporaryDirectory(prefix="asklepios-platform-identity-") as directory:
        temp = Path(directory)
        source = temp / "source.txt"
        source.write_bytes(b"alpha\nbeta\n")
        lf_hash = sha256_repository_file(source)
        source.write_bytes(b"alpha\r\nbeta\r\n")
        crlf_hash = sha256_repository_file(source)
        results.append(case_result(
            "crlf-is-semantic-identity",
            PASS if lf_hash == crlf_hash else FAIL,
            errors=[] if lf_hash == crlf_hash else ["CRLF changed canonical source identity"],
        ))

        source.write_bytes(b"alpha\rbeta\r")
        cr_hash = sha256_repository_file(source)
        results.append(case_result(
            "lone-cr-is-semantic-identity",
            PASS if lf_hash == cr_hash else FAIL,
            errors=[] if lf_hash == cr_hash else ["lone CR changed canonical source identity"],
        ))

        source.write_bytes(b"alpha\nbeta changed\n")
        semantic_hash = sha256_repository_file(source)
        results.append(case_result(
            "semantic-change-rejected",
            EXPECTED_REJECTION if semantic_hash != lf_hash else FAIL,
            errors=[] if semantic_hash != lf_hash else ["semantic mutation retained source identity"],
        ))

        source.write_bytes(b"\xef\xbb\xbfalpha\nbeta\n")
        bom_rejected = False
        try:
            canonical_repository_bytes(source)
        except ReleaseGraphError:
            bom_rejected = True
        results.append(case_result(
            "utf8-bom-rejected",
            EXPECTED_REJECTION if bom_rejected else FAIL,
            errors=[] if bom_rejected else ["UTF-8 BOM was silently normalized"],
        ))

        source.write_bytes(b"alpha\nbeta\n")
        specification = {"include": ["source.txt"], "exclude": [], "files": collect_input_files(temp, {"include": ["source.txt"], "exclude": []})}
        source.write_bytes(b"alpha\r\nbeta\r\n")
        errors = verify_input_set(temp, "fixture", specification)
        results.append(case_result(
            "locked-input-crlf-checkout",
            PASS if not errors else FAIL,
            errors=errors,
        ))
        source.write_bytes(b"alpha\r\nbeta changed\r\n")
        errors = verify_input_set(temp, "fixture", specification)
        results.append(case_result(
            "locked-input-semantic-mutation",
            EXPECTED_REJECTION if any("hash differs" in item for item in errors) else FAIL,
            errors=[] if errors else ["semantic locked-input mutation was accepted"],
        ))

    graph = load_graph(root, GRAPH_PATH)
    locked_paths = sorted({path for spec in graph["input_sets"].values() for path in spec.get("files", {})})
    forbidden: list[str] = []
    text_count = 0
    for relative in locked_paths:
        value = (root / relative).read_bytes()
        if value.startswith(b"\xef\xbb\xbf"):
            forbidden.append(f"UTF-8 BOM:{relative}")
            continue
        if b"\x00" in value:
            continue
        try:
            value.decode("utf-8")
        except UnicodeDecodeError:
            continue
        text_count += 1
        if b"\r" in value:
            forbidden.append(f"non-LF text:{relative}")
    results.append(case_result(
        "working-tree-locked-text-is-lf",
        PASS if not forbidden else FAIL,
        errors=forbidden[:50],
        locked_text_files=text_count,
    ))

    classification = suite_classification(results)
    report = {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] == FAIL],
    }
    output = args.json_output if args.json_output.is_absolute() else root / args.json_output
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
