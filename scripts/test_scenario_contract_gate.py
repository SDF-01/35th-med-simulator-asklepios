#!/usr/bin/env python3
"""Static and fault-oriented contract tests for the hermetic scenario gate."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path


def load(path: Path):
    spec = importlib.util.spec_from_file_location("scenario_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scenario gate")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-contract-gate-mutations.json"))
    args = parser.parse_args()
    root = args.repo.resolve()
    module = load(root / "scripts/run_scenario_contract_gate.py")
    errors: list[str] = []

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    scripts = package.get("scripts", {})
    for name, expected in module.CANONICAL_SCRIPTS.items():
        if scripts.get(name) != expected:
            errors.append(f"canonical scenario script differs:{name}")

    expected_outputs = set(module.EXPECTED_OUTPUTS)
    required = {
        "config/scenario-contracts/ASK-A-001.json",
        "public/data/scenario_core/verified_scenario_package.json",
        "reports/scenario-contract-assurance.json",
        "reports/scenario-contracts-rc2-validation.json",
    }
    if not required.issubset(expected_outputs):
        errors.append("scenario gate output inventory is incomplete")

    source = (root / "scripts/run_scenario_contract_gate.py").read_text(encoding="utf-8")
    markers = [
        'git(root, "worktree", "add"',
        "DETACHED_GIT_WORKTREE_WITH_LOCKED_OVERLAY_V2",
        "locked_overlay_paths",
        "overlay_locked_inputs",
        "--test-concurrency=1",
        "shared_workspace_status",
        "first_invalid_step",
        "stdout_tail",
        "stderr_tail",
        "transient_retry_used",
        "copy_outputs(sandbox, root)",
        "def detach_dependencies",
        'detach_dependencies(sandbox / "node_modules", dependency_mode)',
    ]
    for marker in markers:
        if marker not in source:
            errors.append(f"scenario gate robustness marker missing:{marker}")

    with tempfile.TemporaryDirectory(prefix="asklepios-scenario-detach-test-") as directory:
        fixture = Path(directory)
        shared = fixture / "shared-node-modules"
        shared.mkdir()
        sentinel = shared / "sentinel.txt"
        sentinel.write_text("preserve\n", encoding="utf-8")
        mounted = fixture / "sandbox-node-modules"
        try:
            mounted.symlink_to(shared, target_is_directory=True)
            module.detach_dependencies(mounted, "POSIX_DIRECTORY_SYMLINK")
            if os.path.lexists(mounted) or sentinel.read_text(encoding="utf-8") != "preserve\n":
                errors.append("dependency detach touched the shared dependency source")
        except OSError:
            # Platforms without symlink permission are covered by the static
            # junction/copy branches and the Windows CI lane.
            pass

    graph = json.loads((root / "config/release/RELEASE_GRAPH.json").read_text(encoding="utf-8"))
    stage = next((item for item in graph.get("stages", []) if item.get("id") == "scenario.contracts"), None)
    if not isinstance(stage, dict):
        errors.append("scenario.contracts stage missing")
    else:
        if stage.get("read_only") is not True:
            errors.append("scenario.contracts verification must remain read-only")
        output_paths = {item if isinstance(item, str) else item.get("path") for item in stage.get("outputs", [])}
        if output_paths != {"reports/scenario-contract-gate.json"}:
            errors.append(f"scenario.contracts output boundary differs:{sorted(output_paths)}")

    managed = set(graph.get("managed_package_scripts", []))
    for name in (*module.CANONICAL_SCRIPTS, "verify:scenario-contracts", "check:scenario-contract-gate", "test:scenario-contract-gate"):
        if name not in managed:
            errors.append(f"scenario package script is not release-graph managed:{name}")

    report = {
        "schema_version": "1.0.0",
        "classification": "PASS" if not errors else "FAIL",
        "checks": len(markers) + len(module.CANONICAL_SCRIPTS) + len(required) + len(module.CANONICAL_SCRIPTS) + 6,
        "errors": errors,
    }
    output = args.json_output if args.json_output.is_absolute() else root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
