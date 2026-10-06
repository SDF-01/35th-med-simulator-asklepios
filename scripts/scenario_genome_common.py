#!/usr/bin/env python3
"""Shared deterministic and path-safe primitives for Scenario Genome assurance.

This module is intentionally small and dependency free.  Every Python Genome,
ratchet, and receipt checker consumes the same canonical JSON and repository-path
contract, while independent Node implementations remain separate validators.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

SAFE_INTEGER = 9_007_199_254_740_991
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class GenomeError(ValueError):
    """A deterministic contract rejection, not an internal checker failure."""


def normalize(value: Any, path: str = "$") -> Any:
    """Return the canonical JSON value and reject non-portable values.

    Floats are forbidden because their textual encodings and arithmetic can vary
    across languages.  Timing and measurement evidence must use integer units or
    explicitly encoded decimal strings.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise GenomeError(f"unsafe integer in canonical artifact:{path}")
        return value
    if isinstance(value, float):
        raise GenomeError(f"floating-point value forbidden in canonical artifact:{path}")
    if isinstance(value, list):
        return [normalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise GenomeError(f"non-string object key in canonical artifact:{path}")
            normalized[key] = normalize(value[key], f"{path}.{key}")
        return normalized
    raise GenomeError(f"unsupported canonical JSON type:{path}:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def hash_without(value: dict[str, Any], *fields: str) -> str:
    candidate = dict(value)
    for field in fields:
        candidate.pop(field, None)
    return canonical_sha256(candidate)


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise GenomeError(f"regular file unavailable for hashing:{path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _validate_component(component: str) -> None:
    if component in {"", ".", ".."}:
        raise GenomeError(f"unsafe repository path component:{component!r}")
    if "\x00" in component:
        raise GenomeError("NUL character in repository path")
    if "\\" in component:
        raise GenomeError("Windows path separator forbidden in repository path")
    if ":" in component:
        raise GenomeError("drive or stream separator forbidden in repository path")
    if component.endswith((" ", ".")):
        raise GenomeError("trailing dot or space forbidden in repository path")
    stem = component.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise GenomeError(f"Windows reserved path component:{component}")


def safe_repo_path(repo: Path, relative: str | Path) -> Path:
    """Resolve a portable relative path while rejecting traversal and symlinks."""
    root = repo.resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise GenomeError("repository root is unavailable or unsafe")

    raw = relative.as_posix() if isinstance(relative, Path) else relative
    if not isinstance(raw, str) or not raw:
        raise GenomeError("repository-relative path is empty or malformed")
    if "\x00" in raw:
        raise GenomeError("NUL character in repository path")
    if "\\" in raw:
        raise GenomeError("Windows path separator forbidden in repository path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or raw.startswith("/"):
        raise GenomeError("absolute repository path forbidden")
    parts = pure.parts
    if not parts:
        raise GenomeError("repository-relative path is empty")
    for part in parts:
        _validate_component(part)

    current = root
    for part in parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise GenomeError(f"symlink forbidden in repository path:{raw}")

    candidate = root.joinpath(*parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise GenomeError(f"repository path escapes root:{raw}") from exc
    return candidate


def load_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GenomeError(f"JSON object unavailable or unsafe:{path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise GenomeError(f"JSON is not valid UTF-8:{path}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenomeError(f"JSON object malformed:{path}:{exc.msg}") from exc
    if not isinstance(value, dict):
        raise GenomeError(f"JSON root is not an object:{path}")
    return value


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write deterministic UTF-8 JSON without following symlinks."""
    path = path.resolve(strict=False)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise GenomeError(f"JSON output parent is unsafe:{parent}")
    if path.is_symlink():
        raise GenomeError(f"JSON output is a symlink:{path}")

    payload = (
        json.dumps(normalize(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    existing_mode = 0o644
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise GenomeError(f"JSON output is not a regular file:{path}")
        existing_mode = stat.S_IMODE(info.st_mode)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, existing_mode)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            except OSError:
                pass
            finally:
                os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
