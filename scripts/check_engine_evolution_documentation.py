#!/usr/bin/env python3
"""Verify RC3.8A.1 engine-evolution documentation and artifact bindings."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from engine_evolution_common import (
    DOCUMENTATION_SURFACE_PHRASES,
    EVOLUTION_END_MARKER,
    EVOLUTION_START_MARKER,
    PROHIBITED_LIVE_DEPLOYMENT_CLAIMS,
    render_evolution_block,
    replace_marked_block,
)
from offline_scenario_release_common import expected_documentation, load_release_context, validate_documentation_semantics
from release_identity_common import GRAPH_BINDING_MODE, release_graph_contract_sha256
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code
from scenario_genome_common import GenomeError, atomic_write_json, file_sha256, load_object, safe_repo_path

DESCRIPTOR = "public/data/scenario_core/offline_scenario_release.json"
DOCS = {
    "root": "README.md",
    "facility": "examples/facility-arrival/README.md",
    "verified": "examples/verified-scenario/README.md",
    "standalone": "docs/FACILITY_ARRIVAL_STANDALONE.md",
}


def verify(repo: Path) -> dict[str, Any]:
    errors: list[str] = []
    context = load_release_context(repo)
    policy, genome, capability, debt, graph = (context[key] for key in ("policy", "genome", "capability", "debt", "graph"))
    descriptor = load_object(safe_repo_path(repo, DESCRIPTOR))
    expected_docs = expected_documentation(repo, context)
    errors.extend(validate_documentation_semantics(repo, context))
    documents: dict[str, str] = {}

    for name, relative in DOCS.items():
        path = safe_repo_path(repo, relative)
        if path.is_symlink() or not path.is_file():
            errors.append(f"engine-evolution document missing or unsafe:{relative}")
            continue
        raw = path.read_bytes()
        try:
            documents[name] = raw.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"engine-evolution document is not UTF-8:{relative}")
            continue
        if b"\r" in raw:
            errors.append(f"engine-evolution document contains carriage return:{relative}")
        if not raw.endswith(b"\n"):
            errors.append(f"engine-evolution document missing terminal LF:{relative}")
        if raw.endswith(b"\n\n"):
            errors.append(f"engine-evolution document has blank line at EOF:{relative}")
        for line_number, line in enumerate(raw.splitlines(), 1):
            if line.endswith((b" ", b"\t")):
                errors.append(f"engine-evolution document has trailing whitespace:{relative}:{line_number}")

    for relative, expected in expected_docs.items():
        path = safe_repo_path(repo, relative)
        if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != expected:
            errors.append(f"canonical engine-evolution document differs:{relative}")

    evolution = render_evolution_block(repo).strip()
    start_marker = EVOLUTION_START_MARKER
    end_marker = EVOLUTION_END_MARKER
    for name in ("facility", "verified"):
        current = documents.get(name)
        if current is None:
            continue
        try:
            if current.count(start_marker) != 1 or current.count(end_marker) != 1:
                raise GenomeError(f"documentation marker inventory differs:{name}")
            first = current.index(start_marker)
            last = current.index(end_marker, first) + len(end_marker)
            if current[first:last].strip() != evolution:
                errors.append(f"canonical engine-evolution block differs:{name}")
        except GenomeError as exc:
            errors.append(str(exc))

    tokens = [
        policy["release_id"], policy["display_version"], policy["engine_evolution"],
        genome["genome_id"], genome["genome_sha256"], capability["ratchet_id"],
        str(capability["ratchet_epoch"]), capability["ratchet_anchor_sha256"], debt["ratchet_id"],
        str(debt["ratchet_epoch"]), debt["ratchet_anchor_sha256"], graph["graph_id"],
        str(len(graph["stages"])), str(len(graph["targets"])),
        GRAPH_BINDING_MODE, release_graph_contract_sha256(graph),
    ]
    phrases = DOCUMENTATION_SURFACE_PHRASES
    for name, text in documents.items():
        for token in tokens:
            if token not in text:
                errors.append(f"engine-evolution identity missing:{name}:{token}")
        for phrase in phrases[name]:
            if phrase.casefold() not in text.casefold():
                errors.append(f"engine-evolution guardrail missing:{name}:{phrase}")
        active = text
        if name == "root":
            docs = policy["documentation_contract"]
            first = text.find(docs["root_start_marker"])
            last = text.find(docs["root_end_marker"], first)
            if first >= 0 and last >= 0:
                active = text[first:last + len(docs["root_end_marker"])]
        elif name == "standalone":
            docs = policy["documentation_contract"]
            first = text.find(docs["standalone_start_marker"])
            last = text.find(docs["standalone_end_marker"], first)
            if first >= 0 and last >= 0:
                active = text[first:last + len(docs["standalone_end_marker"])]
        else:
            first = text.find(EVOLUTION_START_MARKER)
            last = text.find(EVOLUTION_END_MARKER, first)
            if first >= 0 and last >= 0:
                active = text[first:last + len(EVOLUTION_END_MARKER)]
        if re.search(r"RC3\.7A\.[012](?!\d)", active):
            errors.append(f"stale active engine-evolution version:{name}")

    root = documents.get("root", "")
    repository_lines = [line.strip() for line in root.splitlines() if line.strip().casefold().startswith("canonical repository:")]
    if repository_lines != [f"Canonical repository: {policy['canonical_repository_url']}"]:
        errors.append("canonical repository declaration differs")
    if "## Static exercise catalog (100 TOON-authored exercises)" not in root:
        errors.append("static exercise catalog identity differs")
    if re.search(r"^##\s+Generated scenario catalog \(107 TOON-authored exercises\)\s*$", root, re.IGNORECASE | re.MULTILINE):
        errors.append("static exercise catalog conflated with generated scenarios")
    for prohibited in PROHIBITED_LIVE_DEPLOYMENT_CLAIMS:
        if prohibited in root.casefold():
            errors.append(f"unsupported live deployment claim:{prohibited}")

    artifact_map = {item.get("path"): item for item in descriptor.get("artifacts", []) if isinstance(item, dict)}
    for relative in DOCS.values():
        record = artifact_map.get(relative)
        if not isinstance(record, dict):
            errors.append(f"engine-evolution document absent from offline artifact inventory:{relative}")
            continue
        path = safe_repo_path(repo, relative)
        if path.is_file() and not path.is_symlink():
            if record.get("bytes") != path.stat().st_size:
                errors.append(f"engine-evolution document byte count differs:{relative}")
            if record.get("sha256") != file_sha256(path):
                errors.append(f"engine-evolution document hash differs:{relative}")

    classification = PASS if not errors else FAIL
    return {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "checker_profile": "PYTHON_ENGINE_EVOLUTION_DOCUMENTATION_V4",
        "documents": len(documents),
        "release_id": policy["release_id"],
        "genome_id": genome["genome_id"],
        "capability_ratchet_epoch": capability["ratchet_epoch"],
        "technical_debt_ratchet_epoch": debt["ratchet_epoch"],
        "graph_id": graph["graph_id"],
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = verify(repo)
    except GenomeError as exc:
        report = {"schema_version": "1.1.0", "classification": FAIL, "status": FAIL, "errors": [str(exc)]}
    except Exception as exc:  # noqa: BLE001
        report = {"schema_version": "1.1.0", "classification": INTERNAL_ERROR, "status": INTERNAL_ERROR, "errors": [f"{type(exc).__name__}:{exc}"]}
    if args.json_output is not None:
        atomic_write_json(safe_repo_path(repo, args.json_output.as_posix()), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
