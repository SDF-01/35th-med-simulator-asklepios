#!/usr/bin/env python3
"""Statically verify the Node/tsx module graph for Facility Arrival.

This checker models the exact tsx invocation contract. It verifies that every
entry point is invoked with the explicit tsconfig containing the @/* mapping,
then resolves every static import/export/dynamic-import edge in the reachable
TypeScript graph. It never treats a parse or resolution failure as success.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import deque
from pathlib import Path
from typing import Any

ENTRYPOINTS = (
    "scripts/generateFacilityArrivalArtifacts.ts",
    "scripts/checkFacilityArrivalRuntimeResolution.ts",
    "src/tests/facilityArrivalDecision.test.ts",
    "src/tests/facilityArrivalRelations.test.ts",
    "src/tests/facilityArrivalRuntime.test.ts",
)
REQUIRED_SCRIPT_NAMES = (
    "generate:facility-arrival",
    "check:facility-arrival-generator-parity",
    "test:facility-arrival",
    "check:facility-arrival-runtime-resolution",
)

EXPECTED_REACHABLE = {
    "src/facility-arrival/context.ts",
    "src/facility-arrival/engine.ts",
    "src/facility-arrival/types.ts",
    "src/facility-arrival/specification.generated.ts",
    "src/facility-arrival/bindings.generated.ts",
    "src/facility-arrival-checker/verify.ts",
    "src/content/scenarios.ts",
    "src/types/index.ts",
    "src/scenario-core/hash.ts",
    "src/scenario-core/certificate.ts",
}
SOURCE_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".json")
NODE_BUILTIN_CAPABILITY_PROFILE = "EXACT_SOURCE_SCOPED_NODE_BUILTINS_V1"
# Each Node builtin is granted to one reviewed source boundary. A capability
# cannot be moved to a different module, broadened globally, or retained after
# its import disappears without failing this checker.
ALLOWED_NODE_BUILTINS_BY_SOURCE: dict[str, frozenset[str]] = {
    "scripts/checkFacilityArrivalRuntimeResolution.ts": frozenset({"node:fs", "node:path"}),
    "scripts/engine_evolution_documentation_common.mjs": frozenset({"node:crypto"}),
    "scripts/generateFacilityArrivalArtifacts.ts": frozenset({"node:fs", "node:path"}),
    "src/tests/facilityArrivalDecision.test.ts": frozenset({"node:assert/strict", "node:test"}),
    "src/tests/facilityArrivalRelations.test.ts": frozenset({"node:assert/strict", "node:test"}),
    "src/tests/facilityArrivalRuntime.test.ts": frozenset({"node:assert/strict", "node:test"}),
}

# Import forms supported by ESM/TypeScript. The source is also parsed by the
# TypeScript compiler in a separate gate; this regex is only for edge extraction.
IMPORT_PATTERNS = (
    re.compile(r"\bimport\s+(?:type\s+)?[^;]*?\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"(?:^|\n)\s*import\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"\bexport\s+(?:type\s+)?[^;]*?\s+from\s+['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
)


def canonical_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_object(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top-level JSON value is not an object")
        return value
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid {label}:{path.name}:{exc}")
        return {}


def extract_specifiers(text: str) -> list[str]:
    values: list[str] = []
    for pattern in IMPORT_PATTERNS:
        values.extend(match.group(1) for match in pattern.finditer(text))
    return sorted(set(values))


def resolve_file(root: Path, source: Path, specifier: str, errors: list[str]) -> Path | None:
    if specifier.startswith("node:"):
        source_path = canonical_path(source, root)
        allowed = ALLOWED_NODE_BUILTINS_BY_SOURCE.get(source_path, frozenset())
        if specifier not in allowed:
            errors.append(f"unreviewed Node builtin in facility runtime closure:{source_path}:{specifier}")
        return None

    if specifier.startswith("@/"):
        base = root / "src" / specifier[2:]
    elif specifier.startswith("./") or specifier.startswith("../"):
        base = source.parent / specifier
    else:
        errors.append(f"unreviewed bare package in facility runtime closure:{canonical_path(source, root)}:{specifier}")
        return None

    try:
        resolved_base = base.resolve()
        resolved_base.relative_to(root.resolve())
    except Exception:
        errors.append(f"module edge escapes repository:{canonical_path(source, root)}:{specifier}")
        return None

    candidates: list[Path] = []
    if base.suffix in SOURCE_EXTENSIONS:
        candidates.append(base)
    else:
        candidates.extend(Path(f"{base}{extension}") for extension in SOURCE_EXTENSIONS)
        candidates.extend(base / f"index{extension}" for extension in SOURCE_EXTENSIONS)

    existing = [candidate for candidate in candidates if candidate.is_file()]
    if len(existing) != 1:
        if not existing:
            errors.append(f"module target missing:{canonical_path(source, root)}:{specifier}")
        else:
            errors.append(f"module target ambiguous:{canonical_path(source, root)}:{specifier}")
        return None

    target = existing[0]
    if target.is_symlink():
        errors.append(f"symlinked runtime module forbidden:{canonical_path(target, root)}")
        return None
    try:
        target.resolve().relative_to(root.resolve())
    except Exception:
        errors.append(f"resolved module target escapes repository:{canonical_path(source, root)}:{specifier}")
        return None
    return target


def verify(root: Path, output: Path | None = None, *, emit: bool = True) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []

    package = load_object(root / "package.json", errors, "package manifest")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    if not scripts:
        errors.append("package scripts object missing")
    release_graph = load_object(root / "config/release/RELEASE_GRAPH.json", errors, "release graph")
    managed = release_graph.get("managed_package_scripts") if isinstance(release_graph.get("managed_package_scripts"), dict) else {}
    if not managed:
        errors.append("release graph managed package scripts missing")
    for key in REQUIRED_SCRIPT_NAMES:
        expected = managed.get(key)
        observed = scripts.get(key)
        if not isinstance(expected, str):
            errors.append(f"managed runtime command missing:{key}")
        elif observed != expected:
            errors.append(f"runtime command differs:{key}")
    generate_command = str(managed.get("generate:facility-arrival", ""))
    parity_command = str(managed.get("check:facility-arrival-generator-parity", ""))
    if "build_facility_arrival_example.py --repo ." not in generate_command:
        errors.append("Facility Arrival generation bypasses canonical Python writer")
    if "npm run check:facility-arrival-generator-parity" not in generate_command:
        errors.append("Facility Arrival generation bypasses independent generator parity")
    if "generateFacilityArrivalArtifacts.ts --check" not in parity_command:
        errors.append("Facility Arrival TypeScript generator is not check-only")

    tsconfig = load_object(root / "tsconfig.app.json", errors, "runtime tsconfig")
    compiler_options = tsconfig.get("compilerOptions") if isinstance(tsconfig.get("compilerOptions"), dict) else {}
    paths = compiler_options.get("paths") if isinstance(compiler_options.get("paths"), dict) else {}
    if compiler_options.get("baseUrl") != ".":
        errors.append("tsconfig.app.json baseUrl must be '.'")
    if paths.get("@/*") != ["src/*"]:
        errors.append("tsconfig.app.json @/* mapping differs")

    queue: deque[Path] = deque()
    for relative in ENTRYPOINTS:
        path = root / relative
        if not path.is_file():
            errors.append(f"runtime entry point missing:{relative}")
        else:
            queue.append(path)

    seen: set[str] = set()
    edges: list[dict[str, str]] = []
    while queue:
        source = queue.popleft()
        relative = canonical_path(source, root)
        if relative in seen:
            continue
        seen.add(relative)
        try:
            text = source.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"runtime module unreadable:{relative}:{exc}")
            continue
        literal_dynamic_imports = len(IMPORT_PATTERNS[-1].findall(text))
        all_dynamic_imports = len(re.findall(r"\bimport\s*\(", text))
        if all_dynamic_imports != literal_dynamic_imports:
            errors.append(f"nonliteral dynamic import forbidden:{relative}")
        if re.search(r"\brequire\s*\(", text):
            errors.append(f"CommonJS require forbidden in facility runtime closure:{relative}")
        for specifier in extract_specifiers(text):
            target = resolve_file(root, source, specifier, errors)
            edge: dict[str, str] = {"source": relative, "specifier": specifier}
            if target is not None:
                target_relative = canonical_path(target, root)
                edge["target"] = target_relative
                queue.append(target)
            else:
                edge["target"] = specifier if specifier.startswith("node:") else "UNRESOLVED"
            edges.append(edge)

    missing_reachable = sorted(EXPECTED_REACHABLE - seen)
    if missing_reachable:
        errors.extend(f"required runtime module not reachable:{value}" for value in missing_reachable)

    declared_builtin_edges = sorted(
        (
            {"source": source, "specifier": specifier}
            for source, specifiers in ALLOWED_NODE_BUILTINS_BY_SOURCE.items()
            for specifier in specifiers
        ),
        key=lambda item: (item["source"], item["specifier"]),
    )
    observed_builtin_edges = sorted(
        (
            {"source": edge["source"], "specifier": edge["specifier"]}
            for edge in edges
            if edge["specifier"].startswith("node:")
        ),
        key=lambda item: (item["source"], item["specifier"]),
    )
    declared_pairs = {(item["source"], item["specifier"]) for item in declared_builtin_edges}
    observed_pairs = {(item["source"], item["specifier"]) for item in observed_builtin_edges}
    for source, specifier in sorted(declared_pairs - observed_pairs):
        errors.append(f"declared Node builtin capability unused:{source}:{specifier}")

    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not errors else "FAIL",
        "tsconfig": "tsconfig.app.json",
        "node_builtin_capability_profile": NODE_BUILTIN_CAPABILITY_PROFILE,
        "declared_node_builtin_capabilities": declared_builtin_edges,
        "observed_node_builtin_edges": observed_builtin_edges,
        "entry_points": list(ENTRYPOINTS),
        "files_checked": len(seen),
        "module_edges_checked": len(edges),
        "reachable_files": sorted(seen),
        "edges": sorted(edges, key=lambda item: (item["source"], item["specifier"], item["target"])),
        "errors": sorted(set(errors)),
    }
    target = output or root / "reports/facility-arrival-module-resolution.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if emit:
        print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve() if args.output else None
    report = verify(args.repo, output)
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
