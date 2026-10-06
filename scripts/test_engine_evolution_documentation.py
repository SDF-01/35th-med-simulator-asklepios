#!/usr/bin/env python3
"""Differential adversarial suite for RC3.8A.1 engine-evolution documentation.

The suite requires both independently implemented checkers to reject every
semantic, identity, marker, and artifact-binding regression.  A mutation is not
counted as a successful rejection when only one checker notices it.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, exit_code, suite_classification
from scenario_genome_common import atomic_write_json, canonical_sha256, safe_repo_path

CHECKER_ROOTS = (
    "scripts/check_engine_evolution_documentation.py",
    "scripts/check_engine_evolution_documentation.mjs",
)
_NODE_IMPORT_RE = re.compile(
    r"(?:import|export)\s+(?:[^'\"]*?\s+from\s+)?['\"](\.[^'\"]+)['\"]"
)
CORE_FILES = (
    "config/release/OFFLINE_SCENARIO_RELEASE.json",
    "config/release/RELEASE_GRAPH.json",
    "config/release/SCENARIO_CAPABILITY_RATCHET.json",
    "config/release/TECHNICAL_DEBT_RATCHET.json",
    "public/data/scenario_core/verified_scenario_genome.json",
    "public/data/scenario_core/offline_scenario_release.json",
    "README.md",
    "docs/FACILITY_ARRIVAL_STANDALONE.md",
    "examples/facility-arrival/README.md",
    "examples/verified-scenario/README.md",
)
Mutation = Callable[[Path], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-engine-evolution-doc-attacks.json"))
    return parser.parse_args()


def copy_file(source: Path, destination: Path, relative: str) -> None:
    src = source / relative
    if not src.is_file() or src.is_symlink():
        raise RuntimeError(f"fixture source unavailable:{relative}")
    dst = destination / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _resolve_python_import(source: Path, current: Path, module: str | None, level: int) -> str | None:
    if module is None:
        return None
    if level > 0:
        base = current.parent
        for _ in range(level - 1):
            base = base.parent
        candidate = base.joinpath(*module.split(".")).with_suffix(".py")
    else:
        candidate = source.joinpath("scripts", *module.split(".")).with_suffix(".py")
        if not candidate.is_file():
            candidate = source.joinpath(*module.split(".")).with_suffix(".py")
    try:
        relative = candidate.resolve(strict=True).relative_to(source.resolve(strict=True)).as_posix()
    except (FileNotFoundError, ValueError):
        return None
    return relative


def _local_imports(source: Path, relative: str) -> set[str]:
    path = safe_repo_path(source, relative)
    if path.suffix == ".py":
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                resolved = _resolve_python_import(source, path, node.module, node.level)
                if resolved is not None:
                    found.add(resolved)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = _resolve_python_import(source, path, alias.name, 0)
                    if resolved is not None:
                        found.add(resolved)
        return found
    if path.suffix in {".mjs", ".js", ".cjs"}:
        found: set[str] = set()
        for specifier in _NODE_IMPORT_RE.findall(path.read_text(encoding="utf-8")):
            candidate = (path.parent / specifier).resolve()
            if candidate.suffix == "":
                for suffix in (".mjs", ".js", ".cjs"):
                    expanded = candidate.with_suffix(suffix)
                    if expanded.is_file():
                        candidate = expanded
                        break
            try:
                found.add(candidate.resolve(strict=True).relative_to(source.resolve(strict=True)).as_posix())
            except (FileNotFoundError, ValueError):
                raise RuntimeError(f"local checker import unavailable or unsafe:{relative}:{specifier}")
        return found
    return set()


def checker_source_closure(source: Path) -> tuple[str, ...]:
    pending = list(CHECKER_ROOTS)
    observed: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in observed:
            continue
        path = safe_repo_path(source, relative)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"checker source unavailable:{relative}")
        observed.add(relative)
        pending.extend(sorted(_local_imports(source, relative) - observed))
    return tuple(sorted(observed))


def build_template(source: Path, destination: Path) -> tuple[str, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    closure = checker_source_closure(source)
    for relative in (*closure, *CORE_FILES):
        copy_file(source, destination, relative)
    return closure


def replace_text(root: Path, relative: str, old: str, new: str, *, count: int = 1) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"mutation target unavailable:{relative}:{old}")
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


def append_text(root: Path, relative: str) -> None:
    path = root / relative
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8", newline="\n")


def append_blank_line_at_eof(root: Path, relative: str) -> None:
    path = root / relative
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise RuntimeError(f"canonical EOF precondition differs:{relative}")
    path.write_bytes(raw + b"\n")


def remove_terminal_lf(root: Path, relative: str) -> None:
    path = root / relative
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise RuntimeError(f"terminal LF precondition differs:{relative}")
    path.write_bytes(raw[:-1])


def mutate_json(root: Path, relative: str, operation: Callable[[dict[str, Any]], None], *, refresh_release_hash: bool = False) -> None:
    path = root / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"mutation JSON root malformed:{relative}")
    operation(value)
    if refresh_release_hash:
        unsigned = dict(value)
        unsigned.pop("release_sha256", None)
        value["release_sha256"] = canonical_sha256(unsigned)
    atomic_write_json(path, value)


def symlink_document(root: Path) -> None:
    target = root / "README.md"
    outside = root / "outside-readme.md"
    outside.write_text(target.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    target.unlink()
    target.symlink_to(outside)


def run_json(command: list[str], *, cwd: Path) -> tuple[int, dict[str, Any], str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "TZ": "UTC"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=120,
    )
    output = completed.stdout
    try:
        value = json.loads(output)
        if not isinstance(value, dict):
            raise ValueError("JSON root is not an object")
    except Exception as exc:  # noqa: BLE001
        value = {"classification": INTERNAL_ERROR, "errors": [f"checker output malformed:{type(exc).__name__}:{exc}", output[-2000:]]}
    return completed.returncode, value, output[-2000:]


def run_checkers(fixture: Path, external_cwd: Path) -> dict[str, Any]:
    py_report = "reports/test-engine-docs-python.json"
    node_report = "reports/test-engine-docs-node.json"
    py_rc, py, py_tail = run_json([
        sys.executable,
        str(fixture / "scripts/check_engine_evolution_documentation.py"),
        "--repo", str(fixture),
        "--json-output", py_report,
    ], cwd=external_cwd)
    node_rc, node, node_tail = run_json([
        "node",
        str(fixture / "scripts/check_engine_evolution_documentation.mjs"),
        "--repo", str(fixture),
        "--json-output", node_report,
    ], cwd=external_cwd)
    return {
        "python_exit_status": py_rc,
        "python_classification": py.get("classification"),
        "python_errors": py.get("errors", []),
        "python_tail": py_tail,
        "node_exit_status": node_rc,
        "node_classification": node.get("classification"),
        "node_errors": node.get("errors", []),
        "node_tail": node_tail,
    }


def cases() -> list[tuple[str, Mutation | None]]:
    exact_debt_line = "- Technical-debt ratchet: reviewed debt records, blocker classifications, evidence floors, and final receipt obligations cannot be silently removed or weakened."
    return [
        ("baseline", None),
        ("root_start_marker_removed", lambda root: replace_text(root, "README.md", "<!-- asklepios-facility-arrival:start -->", "<!-- removed-root-start -->")),
        ("root_end_marker_duplicated", lambda root: replace_text(root, "README.md", "<!-- asklepios-facility-arrival:end -->", "<!-- asklepios-facility-arrival:end -->\n<!-- asklepios-facility-arrival:end -->")),
        ("facility_evolution_heading_removed", lambda root: replace_text(root, "examples/facility-arrival/README.md", "## Engine evolution binding", "## Removed evolution binding")),
        ("verified_debt_ratchet_removed", lambda root: replace_text(root, "examples/verified-scenario/README.md", "- Technical-debt ratchet:", "- Removed debt ratchet:", count=1)),
        ("standalone_title_removed", lambda root: replace_text(root, "docs/FACILITY_ARRIVAL_STANDALONE.md", "## Engine evolution and reproducibility boundary", "## Removed evolution boundary")),
        ("canonical_repository_declaration_changed", lambda root: replace_text(root, "README.md", "Canonical repository: https://github.com/SDF-01/ProjectAsklepios", "Canonical repository: https://github.com/example/other")),
        ("catalog_conflated_with_generated_scenarios", lambda root: replace_text(root, "README.md", "## Static exercise catalog (100 TOON-authored exercises)", "## Generated scenario catalog (107 TOON-authored exercises)")),
        ("live_deployment_claim_injected", lambda root: replace_text(root, "README.md", "Clinical authority remains NOT_GRANTED.", "The live deployment is healthy. Clinical authority remains NOT_GRANTED.")),
        ("checker_boundary_removed", lambda root: replace_text(root, "README.md", "- Checker boundary:", "- Removed checker boundary:", count=1)),
        ("artifact_authority_removed", lambda root: replace_text(root, "README.md", "- Artifact authority:", "- Removed artifact authority:", count=1)),
        ("evidence_freshness_removed", lambda root: replace_text(root, "README.md", "- Evidence freshness:", "- Removed evidence freshness:", count=1)),
        ("release_identity_dag_removed", lambda root: replace_text(root, "README.md", "- Release-identity DAG:", "- Removed release-identity DAG:", count=1)),
        ("route_topology_removed", lambda root: replace_text(root, "README.md", "- Route topology:", "- Removed route topology:", count=1)),
        ("technical_debt_guardrail_removed", lambda root: replace_text(root, "README.md", exact_debt_line, "- Removed technical-debt guardrail.")),
        ("diagnostic_model_removed", lambda root: replace_text(root, "README.md", "- Diagnostic model:", "- Removed diagnostic model:", count=1)),
        ("active_release_version_stale", lambda root: replace_text(root, "README.md", "## Current canonical offline scenario and engine evolution (RC3.8A.1)", "## Current canonical offline scenario and engine evolution (RC3.7A.2)")),
        ("standalone_blank_line_at_eof", lambda root: append_blank_line_at_eof(root, "docs/FACILITY_ARRIVAL_STANDALONE.md")),
        ("root_terminal_lf_removed", lambda root: remove_terminal_lf(root, "README.md")),
        ("document_hash_stale", lambda root: append_text(root, "examples/facility-arrival/README.md")),
        ("descriptor_document_binding_removed", lambda root: mutate_json(root, "public/data/scenario_core/offline_scenario_release.json", lambda value: value.__setitem__("artifacts", [item for item in value["artifacts"] if item.get("path") != "README.md"]), refresh_release_hash=True)),
        ("policy_required_literal_floor_weakened", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["documentation_contract"]["required_literals"]["root"].remove("- Checker boundary:"))),
        ("policy_graph_binding_mode_weakened", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value.__setitem__("release_graph_binding_mode", "RAW_FILE_SHA256_V0"))),
        ("policy_forbidden_claim_floor_weakened", lambda root: mutate_json(root, "config/release/OFFLINE_SCENARIO_RELEASE.json", lambda value: value["documentation_contract"]["forbidden_casefold_phrases"]["root"].remove("the live deployment is healthy"))),
        ("symlink_document_rejected", symlink_document),
    ]


def main() -> int:
    args = parse_args()
    source = args.repo.resolve(strict=True)
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="asklepios-engine-docs-") as temporary:
        temp_root = Path(temporary)
        template = temp_root / "template"
        external_cwd = temp_root / "external-cwd"
        external_cwd.mkdir()
        checker_closure = build_template(source, template)
        for case_id, mutation in cases():
            fixture = temp_root / case_id
            shutil.copytree(template, fixture, symlinks=True)
            expected_pass = mutation is None
            try:
                if mutation is not None:
                    mutation(fixture)
                observed = run_checkers(fixture, external_cwd)
                classifications = {observed["python_classification"], observed["node_classification"]}
                if INTERNAL_ERROR in classifications:
                    classification = INTERNAL_ERROR
                    errors = [*observed["python_errors"], *observed["node_errors"]]
                else:
                    observed_pass = observed["python_exit_status"] == 0 and observed["node_exit_status"] == 0 and classifications == {PASS}
                    rejected_by_both = observed["python_exit_status"] == 3 and observed["node_exit_status"] == 3 and classifications == {FAIL}
                    passed = observed_pass if expected_pass else rejected_by_both
                    classification = PASS if expected_pass and passed else EXPECTED_REJECTION if not expected_pass and passed else FAIL
                    errors = [] if passed else ["engine-evolution documentation verdict differed"]
                results.append(case_result(
                    case_id,
                    classification,
                    errors=errors,
                    expected_pass=expected_pass,
                    observed_pass=observed.get("python_exit_status") == 0 and observed.get("node_exit_status") == 0,
                    accepted_attack=not expected_pass and observed.get("python_exit_status") == 0 and observed.get("node_exit_status") == 0,
                    **observed,
                ))
            except Exception as exc:  # noqa: BLE001
                results.append(case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"]))
            shutil.rmtree(fixture, ignore_errors=True)

    classification = suite_classification(results)
    report = {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "attacks": len(results) - 1,
        "accepted_attacks": sum(bool(item.get("accepted_attack")) for item in results),
        "errors": sorted({error for item in results for error in item.get("errors", [])}),
        "results": results,
        "boundary": "Every active RC3.8A.1 documentation surface is independently checked for exact identity, semantic guardrails, artifact binding, and prohibited deployment or clinical claims.",
        "checker_source_closure": list(checker_closure),
        "checker_source_closure_files": len(checker_closure),
    }
    output = safe_repo_path(source, args.json_output.as_posix())
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
