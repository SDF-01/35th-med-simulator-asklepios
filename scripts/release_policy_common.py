#!/usr/bin/env python3
"""Shared fail-closed helpers for production healthcare-simulation release policy.

The helpers deliberately authenticate evidence from the current applied repository
rather than trusting committed PASS reports.  Receipts are content-addressed and
bound to the current release graph, current locked inputs, dependency receipts,
resolved npm command bodies, tool-version record, and current output inventory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from release_graph_core import (
    GRAPH_PATH,
    canonical_json,
    collect_tool_versions,
    compute_stage_input_root,
    graph_file_sha256,
    load_graph,
    load_receipt,
    output_inventory,
    output_root_sha256,
    read_json,
    receipt_valid,
    resolve_command,
    sha256_text,
    stage_input_snapshot,
    stage_map,
    verify_input_set,
)


def receipt_directory(root: Path, graph: dict[str, Any], explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else root / explicit
    configured = os.environ.get("ASKLEPIOS_RELEASE_RECEIPT_DIR")
    if configured:
        return Path(configured).resolve()
    return root / ".asklepios" / "release-receipts" / str(graph["graph_id"])


def classification_of(value: Any) -> str:
    if not isinstance(value, dict):
        return "MISSING"
    return str(value.get("classification", value.get("status", "MISSING"))).upper()


def require_json_pass(root: Path, relative: str, errors: list[str]) -> dict[str, Any] | None:
    path = root / relative
    try:
        report = read_json(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"required report unavailable:{relative}:{type(exc).__name__}:{exc}")
        return None
    if classification_of(report) != "PASS":
        errors.append(f"required report not PASS:{relative}:{classification_of(report)}")
    return report


def _ancestors(stages: Mapping[str, Mapping[str, Any]], terminal: str) -> list[str]:
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            raise ValueError(f"release evidence dependency cycle:{stage_id}")
        if stage_id in visited:
            return
        stage = stages.get(stage_id)
        if stage is None:
            raise ValueError(f"required evidence stage absent:{stage_id}")
        visiting.add(stage_id)
        for dependency in stage.get("needs", []):
            visit(str(dependency))
        visiting.remove(stage_id)
        visited.add(stage_id)
        ordered.append(stage_id)

    visit(terminal)
    return ordered


def authenticate_stage_receipt_chain(
    root: Path,
    graph: dict[str, Any],
    stage_id: str,
    *,
    receipt_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Authenticate one stage and its entire predecessor receipt chain.

    This is not a public-key signature.  It is a fail-closed, content-addressed
    replay check for accidental/stale evidence and local mutation.  Every input
    lock, receipt self-hash, predecessor digest, input root, command resolution,
    and output tree is recomputed from the current repository state.
    """
    root = root.resolve()
    errors: list[str] = []
    stages = stage_map(graph)
    try:
        ordered = _ancestors(stages, stage_id)
    except Exception as exc:  # noqa: BLE001
        return None, [str(exc)]

    receipts_root = receipt_directory(root, graph, receipt_dir)
    package = read_json(root / "package.json")
    scripts = package.get("scripts", {})
    if not isinstance(scripts, dict):
        return None, ["package scripts missing"]
    graph_hash = graph_file_sha256(root, GRAPH_PATH)
    authenticated_receipts: dict[str, dict[str, Any]] = {}
    evidence: dict[str, Any] = {}
    validated_input_sets: set[str] = set()

    for current_id in ordered:
        stage = stages[current_id]
        for set_id in stage.get("input_sets", []):
            if set_id in validated_input_sets:
                continue
            errors.extend(verify_input_set(root, set_id, graph["input_sets"][set_id]))
            validated_input_sets.add(set_id)

        receipt = load_receipt(receipts_root, current_id)
        if not receipt_valid(receipt):
            errors.append(f"required evidence receipt invalid or missing:{current_id}")
            continue
        assert receipt is not None

        dependency_receipts: dict[str, dict[str, Any]] = {}
        for dependency in stage.get("needs", []):
            prior = authenticated_receipts.get(str(dependency))
            if prior is None:
                errors.append(f"required evidence predecessor unavailable:{current_id}:{dependency}")
            else:
                dependency_receipts[str(dependency)] = prior

        receipt_tool_versions = receipt.get("tool_versions")
        if not isinstance(receipt_tool_versions, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in receipt_tool_versions.items()
        ):
            errors.append(f"required evidence receipt tool versions malformed:{current_id}")
            receipt_tool_versions = {}
        current_tool_versions = collect_tool_versions(list(stage["command"]))

        try:
            inputs = stage_input_snapshot(root, graph, stage)
            expected_input_root = compute_stage_input_root(
                graph,
                stage,
                inputs,
                dependency_receipts,
                current_tool_versions,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"required evidence input root unavailable:{current_id}:{type(exc).__name__}:{exc}")
            expected_input_root = "UNAVAILABLE"

        observed_outputs, output_errors = output_inventory(root, stage.get("outputs", []))
        errors.extend(f"{current_id}:{item}" for item in output_errors)
        observed_output_root = output_root_sha256(observed_outputs)
        expected_dependencies = {
            dependency: dependency_receipts[dependency].get("receipt_sha256")
            for dependency in sorted(dependency_receipts)
        }
        checks = {
            "schema_version": receipt.get("schema_version") == "1.0.0",
            "graph_id": receipt.get("graph_id") == graph.get("graph_id"),
            "graph_sha256": receipt.get("graph_sha256") == graph_hash,
            "stage": receipt.get("stage") == current_id,
            "stage_config_sha256": receipt.get("stage_config_sha256") == sha256_text(canonical_json(stage)),
            "command": receipt.get("command") == stage.get("command"),
            "resolved_command": receipt.get("resolved_command") == resolve_command(list(stage["command"]), scripts),
            "dependency_receipts": receipt.get("dependency_receipts") == expected_dependencies,
            "tool_versions": receipt_tool_versions == current_tool_versions,
            "input_root_sha256": receipt.get("input_root_sha256") == expected_input_root,
            "classification": receipt.get("classification") == "PASS",
            "exit_status": receipt.get("exit_status") == 0,
            "output_root_sha256": receipt.get("output_root_sha256") == observed_output_root,
            "output_inventory": receipt.get("output_inventory") == observed_outputs,
        }
        for name, passed in checks.items():
            if not passed:
                errors.append(f"required evidence receipt differs:{current_id}:{name}")

        # A receipt is allowed to become a predecessor only when all of its local
        # bindings passed.  This prevents a later forged link from hiding an
        # invalid ancestor.
        if all(checks.values()):
            authenticated_receipts[current_id] = receipt
        evidence[current_id] = {
            "receipt_sha256": receipt.get("receipt_sha256"),
            "input_root_sha256": expected_input_root,
            "output_root_sha256": observed_output_root,
            "output_inventory": observed_outputs,
            "checks": checks,
        }

    terminal = evidence.get(stage_id)
    if terminal is None:
        return None, sorted(set(errors))
    result = {
        "stage": stage_id,
        "receipt_sha256": terminal.get("receipt_sha256"),
        "input_root_sha256": terminal.get("input_root_sha256"),
        "output_root_sha256": terminal.get("output_root_sha256"),
        "checks": terminal.get("checks", {}),
        "authenticated_stage_count": len(authenticated_receipts),
        "required_stage_count": len(ordered),
        "receipt_chain_root_sha256": sha256_text(canonical_json({
            key: authenticated_receipts[key].get("receipt_sha256")
            for key in sorted(authenticated_receipts)
        })),
        "chain": evidence,
    }
    return result, sorted(set(errors))


def authenticate_stage_receipt(
    root: Path,
    graph: dict[str, Any],
    stage_id: str,
    *,
    receipt_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    return authenticate_stage_receipt_chain(
        root,
        graph,
        stage_id,
        receipt_dir=receipt_dir,
    )


def unique_nonempty_strings(values: Any) -> bool:
    return (
        isinstance(values, list)
        and bool(values)
        and all(isinstance(value, str) and value.strip() for value in values)
        and len(values) == len(set(values))
    )


def load_release_json(root: Path, relative: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        return read_json(root / relative)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"release policy unavailable:{relative}:{type(exc).__name__}:{exc}")
        return None


def report_root(reports: Iterable[dict[str, Any]]) -> str:
    return sha256_text(canonical_json(list(reports)))
