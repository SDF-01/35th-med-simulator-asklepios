#!/usr/bin/env python3
"""Deterministic repository-local import closure for release-graph source locks.

The release graph authenticates stage inputs by content hash. A stage input union
is incomplete when one of its locked scripts imports another repository-local
module that is not also locked by that stage. This module resolves only static,
repository-local imports and ignores standard-library and installed packages.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

SCHEMA_VERSION = "1.1.0"
PYTHON_MODE = "AST_REPOSITORY_LOCAL_IMPORT_CLOSURE_V2"
NODE_MODE = "STATIC_REPOSITORY_LOCAL_ESM_IMPORT_CLOSURE_V2"
CLOSURE_SCOPE = "STAGE_ENTRYPOINT_TRANSITIVE_REPOSITORY_LOCAL_SOURCE_V2"

PYTHON_SUFFIXES = (".py",)
NODE_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".json")
NODE_SOURCE_SUFFIXES = NODE_SUFFIXES[:-1]
SOURCE_SUFFIXES = (*PYTHON_SUFFIXES, *NODE_SUFFIXES)
_NODE_IMPORT_FROM = re.compile(r"\b(?:import|export)\b[^;\n]*?\bfrom\s*[\"']([^\"']+)[\"']")
_NODE_IMPORT_SIDE_EFFECT = re.compile(r"^\s*import\s*[\"']([^\"']+)[\"']", re.MULTILINE)
_NODE_IMPORT_DYNAMIC = re.compile(r"\b(?:import|require)\s*\(\s*[\"']([^\"']+)[\"']\s*\)")


class SourceClosureError(ValueError):
    """Raised when repository-local source closure cannot be determined safely."""


@dataclass(frozen=True, order=True)
class LocalDependency:
    source: str
    specifier: str
    target: str
    language: str

    def as_dict(self) -> dict[str, str]:
        return {
            "source": self.source,
            "specifier": self.specifier,
            "target": self.target,
            "language": self.language,
        }


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceClosureError("source path is empty")
    if "\x00" in value or "\\" in value:
        raise SourceClosureError(f"source path is unsafe:{value}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise SourceClosureError(f"source path is unsafe:{value}")
    if any(":" in part or part.endswith((".", " ")) for part in pure.parts):
        raise SourceClosureError(f"source path is unsafe:{value}")
    return pure.as_posix()


def _repo_file(root: Path, relative: str) -> Path:
    relative = _safe_relative(relative)
    root_resolved = root.resolve()
    candidate = root / relative
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise SourceClosureError(f"repository-local source is symlinked:{relative}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise SourceClosureError(f"repository-local source escapes root:{relative}") from exc
    return resolved


def _existing_candidates(root: Path, candidates: Iterable[Path], *, source: str, specifier: str) -> list[str]:
    root_resolved = root.resolve()
    found: list[str] = []
    unsafe_escape = False
    for candidate in candidates:
        # Inspect the lexical repository path before resolving symlinks. Calling
        # ``resolve`` first would erase the evidence that an import traversed a
        # symlink and could make a redirected helper look like an ordinary file.
        lexical = Path(os.path.abspath(candidate))
        try:
            lexical_relative = lexical.relative_to(root_resolved).as_posix()
        except ValueError:
            unsafe_escape = True
            continue
        try:
            _repo_file(root, lexical_relative)
        except SourceClosureError as exc:
            if lexical.exists() or lexical.is_symlink():
                raise exc
            continue
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(root_resolved).as_posix()
        except ValueError:
            unsafe_escape = True
            continue
        if not resolved.is_file():
            continue
        found.append(relative)
    unique = sorted(set(found))
    if unsafe_escape and not unique:
        raise SourceClosureError(f"repository-local import escapes root:{source}:{specifier}")
    if len(unique) > 1:
        raise SourceClosureError(
            f"repository-local import is ambiguous:{source}:{specifier}:{','.join(unique)}"
        )
    return unique


def _python_module_candidates(root: Path, source: str, module: str, level: int) -> list[Path]:
    source_path = _repo_file(root, source)
    if level:
        base = source_path.parent
        for _ in range(level - 1):
            base = base.parent
        if module:
            base = base.joinpath(*module.split("."))
        return [Path(f"{base}.py"), base / "__init__.py"]

    parts = module.split(".")
    module_path = Path(*parts)
    if parts and parts[0] == "scripts":
        return [root / module_path.with_suffix(".py"), root / module_path / "__init__.py"]
    return [
        root / "scripts" / module_path.with_suffix(".py"),
        root / "scripts" / module_path / "__init__.py",
        root / module_path.with_suffix(".py"),
        root / module_path / "__init__.py",
    ]


def python_local_dependencies(root: Path, source: str) -> tuple[list[LocalDependency], list[str]]:
    source = _safe_relative(source)
    path = _repo_file(root, source)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=source)
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [], [f"Python source parse failed:{source}:{type(exc).__name__}:{exc}"]

    requests: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            requests.extend((alias.name, alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                requests.append(("." * node.level + module, module, node.level))
            elif node.level:
                for alias in node.names:
                    requests.append(("." * node.level + alias.name, alias.name, node.level))

    dependencies: list[LocalDependency] = []
    errors: list[str] = []
    for display, module, level in sorted(set(requests)):
        try:
            found = _existing_candidates(
                root,
                _python_module_candidates(root, source, module, level),
                source=source,
                specifier=display,
            )
        except SourceClosureError as exc:
            errors.append(str(exc))
            continue
        if found:
            dependencies.append(LocalDependency(source, display, found[0], "python"))
    return sorted(set(dependencies)), sorted(set(errors))


def _node_specifiers(text: str) -> list[str]:
    return sorted(
        set(
            _NODE_IMPORT_FROM.findall(text)
            + _NODE_IMPORT_SIDE_EFFECT.findall(text)
            + _NODE_IMPORT_DYNAMIC.findall(text)
        )
    )


def _node_base_path(root: Path, source_path: Path, specifier: str) -> Path | None:
    """Resolve the repository-local base path for a static Node specifier.

    The application has one reviewed TypeScript alias (``@/`` -> ``src/``).
    Bare package imports and Node built-ins are intentionally outside this
    repository-content closure.
    """
    if specifier.startswith("@/"):
        return root / "src" / specifier[2:]
    if specifier.startswith("."):
        return source_path.parent / specifier
    return None


def _node_candidates(base: Path) -> list[Path]:
    """Return deterministic TypeScript/JavaScript resolution candidates.

    TypeScript commonly emits ``.js`` specifiers while resolving them to
    ``.ts``/``.tsx`` source during typechecking.  We therefore test the exact
    path first and then the reviewed source-extension substitutions.
    """
    candidates: list[Path] = []
    suffix = base.suffix
    if suffix in NODE_SUFFIXES:
        candidates.append(base)
        if suffix in {".js", ".mjs", ".cjs"}:
            stem = base.with_suffix("")
            candidates.extend(Path(f"{stem}{candidate_suffix}") for candidate_suffix in NODE_SOURCE_SUFFIXES)
    else:
        candidates.extend(Path(f"{base}{candidate_suffix}") for candidate_suffix in NODE_SUFFIXES)
        candidates.extend(base / f"index{candidate_suffix}" for candidate_suffix in NODE_SUFFIXES)
    # Stable de-duplication preserves the declared precedence above.
    return list(dict.fromkeys(candidates))


def node_local_dependencies(root: Path, source: str) -> tuple[list[LocalDependency], list[str]]:
    source = _safe_relative(source)
    path = _repo_file(root, source)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], [f"Node source read failed:{source}:{type(exc).__name__}:{exc}"]

    dependencies: list[LocalDependency] = []
    errors: list[str] = []
    for specifier in _node_specifiers(text):
        base = _node_base_path(root, path, specifier)
        if base is None:
            continue
        if "\x00" in specifier or "\\" in specifier:
            errors.append(f"repository-local Node import is unsafe:{source}:{specifier}")
            continue
        try:
            found = _existing_candidates(root, _node_candidates(base), source=source, specifier=specifier)
        except SourceClosureError as exc:
            errors.append(str(exc))
            continue
        if not found:
            errors.append(f"repository-local Node import does not resolve:{source}:{specifier}")
            continue
        dependencies.append(LocalDependency(source, specifier, found[0], "node"))
    return sorted(set(dependencies)), sorted(set(errors))


def build_dependency_index(
    root: Path,
    source_paths: Iterable[str],
) -> tuple[dict[str, list[LocalDependency]], list[str]]:
    """Build the complete repository-local dependency index from entrypoints.

    Discovered local targets are recursively parsed even when they are absent
    from a stage lock.  That detail is essential: otherwise an unlisted helper
    could terminate traversal and hide its own transitive dependencies.
    """
    root = root.resolve()
    index: dict[str, list[LocalDependency]] = {}
    errors: list[str] = []
    pending = sorted(set(source_paths), reverse=True)
    visited: set[str] = set()
    while pending:
        raw = pending.pop()
        try:
            source = _safe_relative(raw)
            path = _repo_file(root, source)
        except SourceClosureError as exc:
            errors.append(str(exc))
            continue
        if source in visited:
            continue
        visited.add(source)
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if path.suffix in PYTHON_SUFFIXES:
            dependencies, local_errors = python_local_dependencies(root, source)
        elif path.suffix in NODE_SOURCE_SUFFIXES:
            dependencies, local_errors = node_local_dependencies(root, source)
        else:
            dependencies, local_errors = [], []
        index[source] = dependencies
        errors.extend(local_errors)
        for dependency in reversed(dependencies):
            if dependency.target not in visited:
                pending.append(dependency.target)
    return index, sorted(set(errors))


def closure_errors(
    locked_files: Iterable[str],
    dependency_index: Mapping[str, Iterable[LocalDependency]],
    *,
    scope: str,
) -> list[str]:
    locked = set(locked_files)
    errors: list[str] = []
    for source in sorted(locked):
        for dependency in dependency_index.get(source, ()):
            if dependency.target not in locked:
                errors.append(
                    "repository-local source dependency is not locked:"
                    f"{scope}:{dependency.target}:imported-by:{source}:{dependency.specifier}"
                )
    return sorted(set(errors))


def transitive_closure_errors(
    entrypoints: Iterable[str],
    locked_files: Iterable[str],
    dependency_index: Mapping[str, Iterable[LocalDependency]],
    *,
    scope: str,
    authenticated_generated_files: Iterable[str] = (),
) -> tuple[list[str], list[LocalDependency], list[str]]:
    """Validate the import closure reachable from exact stage entrypoints.

    Returns ``(errors, dependencies, visited_sources)``.  Only repository-local
    script imports are traversed; external packages and the Python standard
    library are outside this content-lock contract.
    """
    locked = set(locked_files)
    generated = set(authenticated_generated_files)
    admitted = locked | generated
    pending = sorted(set(entrypoints), reverse=True)
    visited: set[str] = set()
    dependencies: set[LocalDependency] = set()
    errors: list[str] = []

    for entrypoint in sorted(set(entrypoints)):
        if entrypoint.startswith("scripts/") and entrypoint not in locked:
            errors.append(f"release stage entrypoint is not locked:{scope}:{entrypoint}")

    while pending:
        source = pending.pop()
        if source in visited:
            continue
        visited.add(source)
        for dependency in dependency_index.get(source, ()):
            dependencies.add(dependency)
            if dependency.target not in admitted:
                errors.append(
                    "repository-local source dependency is not locked:"
                    f"{scope}:{dependency.target}:imported-by:{source}:{dependency.specifier}"
                )
                continue
            if dependency.target not in visited:
                pending.append(dependency.target)
    return sorted(set(errors)), sorted(dependencies), sorted(visited)
