#!/usr/bin/env python3
"""Canonical acyclic release-identity projection primitives.

The release graph locks the generated offline descriptor. Therefore the descriptor
must never embed the graph's raw file digest or the mutable per-file lock digests
that include the descriptor itself. This module defines the canonical writer-side
semantic projection used by generated documentation and the offline descriptor.
Independent checkers reimplement the same contract rather than importing this file.
"""
from __future__ import annotations

from typing import Any, Mapping

from scenario_genome_common import GenomeError, canonical_sha256

GRAPH_BINDING_MODE = "ACYCLIC_SEMANTIC_PROJECTION_V1"
SEMANTIC_PROJECTION_EXCLUDES = ("input_sets.*.files.*",)
SEMANTIC_PROJECTION_PRESERVES = (
    "classifications",
    "graph_id",
    "input_set_path_inventory",
    "integrations",
    "managed_package_scripts",
    "production_designation",
    "release_candidate",
    "stages",
    "targets",
    "truth_boundaries",
)


def release_graph_contract_projection(graph: Mapping[str, Any]) -> dict[str, Any]:
    """Return stable graph semantics without self-referential lock digests."""
    raw_sets = graph.get("input_sets")
    if not isinstance(raw_sets, Mapping):
        raise GenomeError("release graph input-set inventory malformed")

    input_sets: dict[str, Any] = {}
    for set_id in sorted(raw_sets):
        specification = raw_sets[set_id]
        if not isinstance(specification, Mapping):
            raise GenomeError(f"release graph input set malformed:{set_id}")
        files = specification.get("files")
        if not isinstance(files, Mapping):
            raise GenomeError(f"release graph input lock malformed:{set_id}")
        include = specification.get("include", [])
        exclude = specification.get("exclude", [])
        if not isinstance(include, list) or not isinstance(exclude, list):
            raise GenomeError(f"release graph input path rules malformed:{set_id}")
        input_sets[str(set_id)] = {
            "include": include,
            "exclude": exclude,
            "file_paths": sorted(str(path) for path in files),
        }

    return {
        "schema_version": graph.get("schema_version"),
        "graph_id": graph.get("graph_id"),
        "classifications": graph.get("classifications"),
        "managed_package_scripts": graph.get("managed_package_scripts"),
        "production_designation": graph.get("production_designation"),
        "release_candidate": graph.get("release_candidate"),
        "truth_boundaries": graph.get("truth_boundaries"),
        "input_sets": input_sets,
        "stages": graph.get("stages"),
        "targets": graph.get("targets"),
        "integrations": graph.get("integrations"),
    }


def release_graph_contract_sha256(graph: Mapping[str, Any]) -> str:
    return canonical_sha256(release_graph_contract_projection(graph))
