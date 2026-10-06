#!/usr/bin/env python3
"""Execute, resume, and attest the canonical Project Asklepios release graph."""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from release_graph_core import (
    GRAPH_PATH,
    ReleaseGraphError,
    collect_tool_versions,
    compute_stage_input_root,
    graph_file_sha256,
    load_graph,
    load_receipt,
    native_command,
    make_receipt,
    output_inventory,
    output_root_sha256,
    plan_payload,
    read_json,
    receipt_path,
    reusable_receipt,
    resolve_command,
    stage_input_snapshot,
    stage_map,
    target_plan,
    target_stage_ids,
    utc_now,
    verify_input_set,
    canonical_json,
    sha256_text,
    write_json,
)


_TOKEN_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"(?i)(authorization\s*:\s*(?:token|bearer)\s+)[^\s]+"),
)


def redact_diagnostic_text(value: str) -> str:
    text = value
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda match: match.group(1) + "<REDACTED>", text)
        else:
            text = pattern.sub("<REDACTED>", text)
    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_with_diagnostics(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> tuple[int, dict[str, Any]]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tail: deque[str] = deque(maxlen=80)
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = redact_diagnostic_text(raw_line)
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
            tail.append(line.rstrip("\r\n"))
        exit_status = int(process.wait())
    diagnostics = {
        "combined_log_path": str(log_path.relative_to(cwd)),
        "combined_log_sha256": sha256_file(log_path),
        "combined_log_bytes": log_path.stat().st_size,
        "redaction_mode": "KNOWN_GITHUB_TOKEN_PATTERNS_V1",
        "tail": list(tail),
    }
    return exit_status, diagnostics


def bind_receipt_diagnostics(receipt: dict[str, Any], diagnostics: dict[str, Any] | None) -> dict[str, Any]:
    if diagnostics is not None:
        receipt["diagnostics"] = diagnostics
        payload = dict(receipt)
        payload.pop("receipt_sha256", None)
        receipt["receipt_sha256"] = sha256_text(canonical_json(payload))
    return receipt


def compact_failure_inventory(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return bounded, machine-readable failure details without copying whole stage logs."""
    failed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for item in results:
        stage = item.get("stage")
        if item.get("executed") is False:
            blocked.append({
                "stage": stage,
                "classification": item.get("classification"),
                "blocked_by": list(item.get("blocked_by", [])),
                "errors": list(item.get("errors", [])),
            })
            continue
        if item.get("classification") not in {"FAIL", "INTERNAL_ERROR"}:
            continue
        diagnostics = item.get("diagnostics") or {}
        failed.append({
            "stage": stage,
            "classification": item.get("classification"),
            "exit_status": item.get("exit_status"),
            "errors": list(item.get("errors", [])),
            "combined_log_path": diagnostics.get("combined_log_path"),
            "combined_log_sha256": diagnostics.get("combined_log_sha256"),
            "combined_log_bytes": diagnostics.get("combined_log_bytes"),
            "tail": list(diagnostics.get("tail", []))[-60:],
        })
    return failed, blocked


def bind_failure_inventory(summary: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind a compact complete-DAG failure inventory into every failing summary."""
    failed, blocked = compact_failure_inventory(results)
    summary["failed_stage_details"] = failed
    summary["blocked_stage_details"] = blocked
    summary.setdefault("failed_stages", [item["stage"] for item in failed])
    summary.setdefault("failure_count", len(failed))
    summary.setdefault("blocked_stage_count", len(blocked))
    summary.setdefault(
        "passed_stage_count",
        sum(1 for item in results if item.get("classification") == "PASS"),
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--target", required=True)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--no-reuse", action="store_true")
    parser.add_argument(
        "--collect-independent-failures",
        action="store_true",
        help=(
            "Continue across dependency-independent branches after a failed read-only stage "
            "that did not mutate locked inputs. Publication remains fail-closed."
        ),
    )
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()

    root = args.repo.resolve()
    try:
        graph = load_graph(root, args.graph)
        stages = stage_map(graph)
        stage_ids = target_stage_ids(graph, args.target)
        plan = target_plan(root, graph, args.target)
    except ReleaseGraphError as exc:
        print(json.dumps({"classification": "FAIL", "errors": [str(exc)]}, indent=2, sort_keys=True))
        return 3

    if args.plan_json:
        write_json(root / args.plan_json, {
            "schema_version": "1.0.0",
            "classification": "PASS",
            "target": args.target,
            "plan": plan_payload(plan),
        })

    receipt_dir = (args.receipt_dir if args.receipt_dir and args.receipt_dir.is_absolute()
                   else root / (args.receipt_dir or Path(".asklepios/release-receipts") / graph["graph_id"]))
    receipt_dir.mkdir(parents=True, exist_ok=True)
    package = read_json(root / "package.json")
    scripts = package.get("scripts", {})
    graph_hash = graph_file_sha256(root, args.graph)
    stage_log_root = root / ".asklepios/release-stage-logs" / graph["graph_id"]
    stage_log_root.mkdir(parents=True, exist_ok=True)

    used_sets = sorted({set_id for stage_id in stage_ids for set_id in stages[stage_id].get("input_sets", [])})
    lock_errors: list[str] = []
    for set_id in used_sets:
        lock_errors.extend(verify_input_set(root, set_id, graph["input_sets"][set_id]))
    if lock_errors:
        report = {
            "schema_version": "1.0.0",
            "classification": "FAIL",
            "target": args.target,
            "first_invalid_stage": "release-graph-input-locks",
            "receipt_dir": str(receipt_dir),
            "results": [],
            "errors": sorted(set(lock_errors)),
        }
        report = bind_failure_inventory(report, report["results"])
        if args.summary_output:
            write_json(root / args.summary_output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3

    completed_receipts: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    failed_stages: list[str] = []
    unavailable_stages: set[str] = set()
    for stage_id in stage_ids:
        stage = stages[stage_id]
        unavailable_needs = [need for need in stage.get("needs", []) if need in unavailable_stages]
        if unavailable_needs:
            unavailable_stages.add(stage_id)
            result = {
                "stage": stage_id,
                "classification": "FAIL",
                "exit_status": 3,
                "reused": False,
                "executed": False,
                "blocked_by": unavailable_needs,
                "errors": [f"blocked by failed predecessor:{need}" for need in unavailable_needs],
                "diagnostics": None,
            }
            results.append(result)
            print(json.dumps(result, sort_keys=True), flush=True)
            continue
        dependency_receipts = {need: completed_receipts[need] for need in stage.get("needs", [])}
        command = list(stage["command"])
        resolved = resolve_command(command, scripts)
        tools = collect_tool_versions(command)
        input_root: str | None = None
        diagnostics: dict[str, Any] | None = None
        started = utc_now()
        try:
            before_inputs = stage_input_snapshot(root, graph, stage)
            input_root = compute_stage_input_root(graph, stage, before_inputs, dependency_receipts, tools)
            current_outputs, output_errors = output_inventory(root, stage.get("outputs", []))
            current_output_root = output_root_sha256(current_outputs)
            prior = load_receipt(receipt_dir, stage_id)
            if not args.no_reuse and not output_errors and reusable_receipt(
                prior,
                graph=graph,
                graph_file_hash=graph_hash,
                stage=stage,
                input_root=input_root,
                current_output_root=current_output_root,
                tool_versions=tools,
                dependency_receipts=dependency_receipts,
            ):
                assert prior is not None
                completed_receipts[stage_id] = prior
                result = {
                    "stage": stage_id,
                    "classification": "PASS",
                    "exit_status": 0,
                    "reused": True,
                    "receipt_sha256": prior["receipt_sha256"],
                    "diagnostics": prior.get("diagnostics"),
                }
                results.append(result)
                print(json.dumps(result, sort_keys=True), flush=True)
                continue

            print(f"\n######## release stage: {stage_id} ########", flush=True)
            env = os.environ.copy()
            env["ASKLEPIOS_RELEASE_GRAPH"] = str((root / args.graph).resolve())
            env["ASKLEPIOS_RELEASE_TARGET"] = args.target
            env["ASKLEPIOS_RELEASE_RECEIPT_DIR"] = str(receipt_dir.resolve())
            execution_command = native_command(command)
            stage_log_path = stage_log_root / f"{stage_id}.log"
            exit_status, diagnostics = execute_with_diagnostics(
                execution_command, cwd=root, env=env, log_path=stage_log_path,
            )
            after_inputs = stage_input_snapshot(root, graph, stage)
            errors: list[str] = []
            if exit_status != 0:
                errors.append(f"stage command exited:{exit_status}")
            if stage.get("read_only") and before_inputs != after_inputs:
                changed = sorted(set(before_inputs) | set(after_inputs))
                changed = [path for path in changed if before_inputs.get(path) != after_inputs.get(path)]
                errors.append(f"read-only stage changed locked inputs:{changed}")
            outputs, output_errors = output_inventory(root, stage.get("outputs", []))
            errors.extend(output_errors)
            output_root = output_root_sha256(outputs)
            if exit_status == 0 and not errors:
                classification = "PASS"
            elif exit_status < 0:
                classification = "INTERNAL_ERROR"
                errors.append(f"stage terminated by signal:{-exit_status}")
            else:
                classification = str(stage.get("failure_classification", "FAIL"))
                if exit_status == 0:
                    exit_status = 3
            receipt = make_receipt(
                graph=graph,
                graph_file_hash=graph_hash,
                stage=stage,
                command=command,
                resolved_command=resolved,
                input_root=input_root,
                output_root=output_root,
                output_inventory_value=outputs,
                tool_versions=tools,
                dependency_receipts=dependency_receipts,
                exit_status=exit_status,
                classification=classification,
                started_at=started,
                completed_at=utc_now(),
                errors=errors,
            )
            receipt = bind_receipt_diagnostics(receipt, diagnostics)
            write_json(receipt_path(receipt_dir, stage_id), receipt)
            result = {
                "stage": stage_id,
                "classification": classification,
                "exit_status": exit_status,
                "reused": False,
                "receipt_sha256": receipt["receipt_sha256"],
                "errors": errors,
                "diagnostics": diagnostics,
            }
            results.append(result)
            print(json.dumps(result, sort_keys=True), flush=True)
            if classification != "PASS":
                failed_stages.append(stage_id)
                unavailable_stages.add(stage_id)
                safe_to_continue = (
                    args.collect_independent_failures
                    and classification == "FAIL"
                    and bool(stage.get("read_only"))
                    and before_inputs == after_inputs
                )
                if safe_to_continue:
                    continue
                summary = {
                    "schema_version": "1.1.0",
                    "classification": classification,
                    "target": args.target,
                    "diagnostic_mode": bool(args.collect_independent_failures),
                    "first_invalid_stage": stage_id,
                    "failure_count": len(failed_stages),
                    "blocked_stage_count": sum(1 for item in results if item.get("executed") is False),
                    "receipt_dir": str(receipt_dir),
                    "results": results,
                }
                summary = bind_failure_inventory(summary, results)
                if args.summary_output:
                    write_json(root / args.summary_output, summary)
                print(json.dumps(summary, indent=2, sort_keys=True))
                return 4 if classification == "INTERNAL_ERROR" else 3
            completed_receipts[stage_id] = receipt
        except Exception as exc:  # noqa: BLE001 - convert every orchestration fault into durable evidence
            completed_at = utc_now()
            error_text = f"{type(exc).__name__}:{exc}"
            try:
                outputs, output_errors = output_inventory(root, stage.get("outputs", []))
            except Exception as inventory_exc:  # noqa: BLE001
                outputs = {}
                output_errors = [f"output inventory failed:{type(inventory_exc).__name__}:{inventory_exc}"]
            fallback_input_root = input_root
            if not isinstance(fallback_input_root, str):
                fallback_input_root = sha256_text(canonical_json({
                    "graph_id": graph.get("graph_id"),
                    "stage": stage_id,
                    "dependency_receipts": {
                        key: value.get("receipt_sha256")
                        for key, value in sorted(dependency_receipts.items())
                    },
                    "tool_versions": dict(sorted(tools.items())),
                    "internal_error": error_text,
                }))
            receipt = make_receipt(
                graph=graph,
                graph_file_hash=graph_hash,
                stage=stage,
                command=command,
                resolved_command=resolved,
                input_root=fallback_input_root,
                output_root=output_root_sha256(outputs),
                output_inventory_value=outputs,
                tool_versions=tools,
                dependency_receipts=dependency_receipts,
                exit_status=4,
                classification="INTERNAL_ERROR",
                started_at=started,
                completed_at=completed_at,
                errors=[error_text, *output_errors],
            )
            receipt = bind_receipt_diagnostics(receipt, diagnostics)
            write_json(receipt_path(receipt_dir, stage_id), receipt)
            result = {
                "stage": stage_id,
                "classification": "INTERNAL_ERROR",
                "exit_status": 4,
                "reused": False,
                "receipt_sha256": receipt["receipt_sha256"],
                "errors": [error_text, *output_errors],
                "diagnostics": diagnostics,
            }
            results.append(result)
            summary = {
                "schema_version": "1.0.0",
                "classification": "INTERNAL_ERROR",
                "target": args.target,
                "first_invalid_stage": stage_id,
                "receipt_dir": str(receipt_dir),
                "results": results,
            }
            summary = bind_failure_inventory(summary, results)
            if args.summary_output:
                write_json(root / args.summary_output, summary)
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 4

    if failed_stages:
        summary = {
            "schema_version": "1.1.0",
            "classification": "FAIL",
            "target": args.target,
            "diagnostic_mode": True,
            "first_invalid_stage": failed_stages[0],
            "failed_stages": failed_stages,
            "failure_count": len(failed_stages),
            "blocked_stage_count": sum(1 for item in results if item.get("executed") is False),
            "passed_stage_count": sum(1 for item in results if item.get("classification") == "PASS"),
            "receipt_dir": str(receipt_dir),
            "results": results,
        }
        summary = bind_failure_inventory(summary, results)
        if args.summary_output:
            write_json(root / args.summary_output, summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 3

    summary = {
        "schema_version": "1.1.0",
        "classification": "PASS",
        "target": args.target,
        "diagnostic_mode": bool(args.collect_independent_failures),
        "stages": len(stage_ids),
        "reused": sum(1 for item in results if item.get("reused")),
        "executed": sum(1 for item in results if not item.get("reused")),
        "receipt_dir": str(receipt_dir),
        "terminal_receipts": {
            stage_id: completed_receipts[stage_id]["receipt_sha256"]
            for stage_id in graph["targets"][args.target]["terminal_stages"]
        },
        "results": results,
    }
    if args.summary_output:
        write_json(root / args.summary_output, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
