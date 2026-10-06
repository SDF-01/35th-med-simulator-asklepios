#!/usr/bin/env python3
"""Cross-platform path, interpreter, newline, and source-hash regressions."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any
from release_result import finalize_adversarial_report

OUTPUT = Path("reports/facility-arrival-cross-platform.json")


def run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def copy_repo(source: Path, target: Path) -> None:
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git",
            ".lake",
            "node_modules",
            "dist",
            "__pycache__",
            "*.pyc",
            "*.pyo",
        ),
    )


def result(
    case_id: str,
    passed: bool,
    completed: subprocess.CompletedProcess[str] | None = None,
    errors: list[str] | None = None,
    **details: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "case_id": case_id,
        "pass": passed,
        "errors": errors or [],
        **details,
    }
    if completed is not None:
        value["returncode"] = completed.returncode
        if not passed:
            value["stdout_tail"] = completed.stdout[-1500:]
            value["stderr_tail"] = completed.stderr[-1500:]
    return value


def load_binding_module(repo: Path) -> ModuleType:
    path = repo / "scripts/build_facility_arrival_bindings.py"
    spec = importlib.util.spec_from_file_location("asklepios_facility_binding_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load binding module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalized_executable(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(path)))


def within_root(path: str | Path, root: str | Path) -> bool:
    observed = normalized_executable(path)
    expected_root = normalized_executable(root)
    try:
        return os.path.commonpath([observed, expected_root]) == expected_root
    except ValueError:
        return False


def parse_last_json(text: str) -> dict[str, Any]:
    for raw in reversed(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("last JSON value is not an object")
        return value
    raise ValueError("JSON output missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    attributes = (
        (source / ".gitattributes").read_text(encoding="utf-8")
        if (source / ".gitattributes").is_file()
        else ""
    )
    required_attributes = [
        "src/content/scenarios.ts text eol=lf",
        "config/facility-arrival/*.json text eol=lf",
        "src/facility-arrival/*.ts text eol=lf",
        "examples/facility-arrival/* text eol=lf",
        ".github/workflows/facility-arrival-ci.yml text eol=lf",
    ]
    missing = [item for item in required_attributes if item not in attributes]
    passed = not missing
    results.append(
        result(
            "gitattributes_enforces_lf",
            passed,
            errors=[f"missing:{item}" for item in missing],
        )
    )
    if not passed:
        failures.append("gitattributes_enforces_lf")

    try:
        binding_module = load_binding_module(source)
        serializer = getattr(binding_module, "canonical_repo_path")
        observed_windows = serializer(PureWindowsPath(r"src\content\scenarios.ts"))
        observed_posix = serializer(PurePosixPath("src/content/scenarios.ts"))
        path_errors = []
        if observed_windows != "src/content/scenarios.ts":
            path_errors.append(f"Windows path serialized as:{observed_windows}")
        if observed_posix != "src/content/scenarios.ts":
            path_errors.append(f"POSIX path serialized as:{observed_posix}")
    except Exception as exc:  # independently reports source-load failures
        path_errors = [f"portable path serializer unavailable:{type(exc).__name__}:{exc}"]
    passed = not path_errors
    results.append(result("repository_paths_are_posix", passed, errors=path_errors))
    if not passed:
        failures.append("repository_paths_are_posix")

    launcher_source = (source / "scripts/run_python.mjs").read_text(encoding="utf-8")
    launcher_policy_errors: list[str] = []
    required_launcher_fragments = [
        "ASKLEPIOS_PYTHON",
        "Python_ROOT_DIR",
        "strictGroups",
        "fallbackCandidates",
        "Python 3.12+",
    ]
    for fragment in required_launcher_fragments:
        if fragment not in launcher_source:
            launcher_policy_errors.append(f"launcher policy marker missing:{fragment}")
    old_windows_prefix = "? [\n      { command: 'py', prefix: ['-3'] }"
    if old_windows_prefix in launcher_source:
        launcher_policy_errors.append("Windows py launcher is still the first unpinned candidate")
    if launcher_source.find("strictGroups") > launcher_source.find("fallbackCandidates"):
        launcher_policy_errors.append("configured interpreter groups are declared after fallback candidates")
    passed = not launcher_policy_errors
    results.append(result("launcher_policy_is_explicit", passed, errors=launcher_policy_errors))
    if not passed:
        failures.append("launcher_policy_is_explicit")

    override_env = os.environ.copy()
    override_env["ASKLEPIOS_PYTHON"] = sys.executable
    launcher_probe = run(
        [
            "node",
            "scripts/run_python.mjs",
            "-c",
            (
                "import json,sys;"
                "print(json.dumps({'executable':sys.executable,"
                "'version':list(sys.version_info[:3])},sort_keys=True))"
            ),
        ],
        source,
        env=override_env,
    )
    launcher_errors: list[str] = []
    launcher_payload: dict[str, Any] = {}
    if launcher_probe.returncode != 0:
        launcher_errors.append(
            f"launcher returned {launcher_probe.returncode}:"
            f"{launcher_probe.stderr[-500:]}{launcher_probe.stdout[-500:]}"
        )
    else:
        try:
            launcher_payload = parse_last_json(launcher_probe.stdout)
            if normalized_executable(launcher_payload.get("executable", "")) != normalized_executable(sys.executable):
                launcher_errors.append("ASKLEPIOS_PYTHON override was not selected")
            version = launcher_payload.get("version")
            if not isinstance(version, list) or tuple(version[:2]) < (3, 12):
                launcher_errors.append(f"launcher selected unsupported version:{version}")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            launcher_errors.append(f"launcher probe output invalid:{type(exc).__name__}:{exc}")
    passed = not launcher_errors
    results.append(
        result(
            "explicit_python_override_selected",
            passed,
            launcher_probe,
            errors=launcher_errors,
        )
    )
    if not passed:
        failures.append("explicit_python_override_selected")

    root_errors: list[str] = []
    configured_root = os.environ.get("Python_ROOT_DIR")
    if configured_root and not within_root(sys.executable, configured_root):
        root_errors.append("active interpreter is outside Python_ROOT_DIR")
    selected_env = os.environ.get("ASKLEPIOS_SELECTED_PYTHON")
    if configured_root and selected_env and not within_root(selected_env, configured_root):
        root_errors.append("launcher-selected interpreter is outside Python_ROOT_DIR")

    executable = Path(sys.executable).resolve()
    synthetic_root = executable.parent
    if os.name != "nt" and synthetic_root.name == "bin":
        synthetic_root = synthetic_root.parent
    root_env = os.environ.copy()
    root_env.pop("ASKLEPIOS_PYTHON", None)
    root_env["Python_ROOT_DIR"] = str(synthetic_root)
    root_probe = run(
        [
            "node",
            "scripts/run_python.mjs",
            "-c",
            "import json,sys;print(json.dumps({'executable':sys.executable},sort_keys=True))",
        ],
        source,
        env=root_env,
    )
    if root_probe.returncode != 0:
        root_errors.append(
            f"Python_ROOT_DIR launcher returned {root_probe.returncode}:"
            f"{root_probe.stderr[-500:]}{root_probe.stdout[-500:]}"
        )
    else:
        try:
            root_payload = parse_last_json(root_probe.stdout)
            if normalized_executable(root_payload.get("executable", "")) != normalized_executable(sys.executable):
                root_errors.append("Python_ROOT_DIR did not select the active configured interpreter")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            root_errors.append(f"Python_ROOT_DIR probe output invalid:{type(exc).__name__}:{exc}")

    passed = not root_errors
    results.append(
        result(
            "setup_python_root_selected",
            passed,
            root_probe,
            errors=root_errors,
        )
    )
    if not passed:
        failures.append("setup_python_root_selected")

    with tempfile.TemporaryDirectory(prefix="asklepios-facility-cross-platform-") as tmp:
        baseline = Path(tmp) / "baseline"
        copy_repo(source, baseline)

        command = [
            sys.executable,
            "scripts/build_facility_arrival_bindings.py",
            "--repo",
            ".",
            "--check",
        ]
        completed = run(command, baseline)
        passed = completed.returncode == 0
        results.append(result("baseline_binding_check", passed, completed))
        if not passed:
            failures.append("baseline_binding_check")

        crlf = Path(tmp) / "crlf"
        copy_repo(source, crlf)
        scenario = crlf / "src/content/scenarios.ts"
        text = scenario.read_text(encoding="utf-8")
        scenario.write_bytes(
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", "\r\n")
            .encode("utf-8")
        )
        commands = [
            [
                sys.executable,
                "scripts/build_facility_arrival_bindings.py",
                "--repo",
                ".",
                "--check",
            ],
            [
                sys.executable,
                "scripts/check_facility_arrival_example.py",
                "--repo",
                ".",
                "--json-output",
                "reports/cross-platform-python.json",
            ],
            [
                "node",
                "scripts/check_facility_arrival_example.mjs",
                "--repo",
                ".",
                "--output",
                "reports/cross-platform-node.json",
            ],
        ]
        crlf_errors: list[str] = []
        for cmd in commands:
            completed = run(cmd, crlf)
            if completed.returncode != 0:
                crlf_errors.append(
                    f"{' '.join(cmd)}:returncode={completed.returncode}:"
                    f"stdout={completed.stdout[-500:]}:stderr={completed.stderr[-500:]}"
                )
        passed = not crlf_errors
        results.append(
            result(
                "crlf_checkout_preserves_source_identity",
                passed,
                errors=crlf_errors,
            )
        )
        if not passed:
            failures.append("crlf_checkout_preserves_source_identity")

        semantic = Path(tmp) / "semantic"
        copy_repo(source, semantic)
        scenario = semantic / "src/content/scenarios.ts"
        scenario.write_bytes(scenario.read_bytes() + b"\n// semantic source mutation\n")
        completed = run(command, semantic)
        passed = completed.returncode != 0
        results.append(result("semantic_source_change_rejected", passed, completed))
        if not passed:
            failures.append("semantic_source_change_rejected")

        bom = Path(tmp) / "bom"
        copy_repo(source, bom)
        scenario = bom / "src/content/scenarios.ts"
        scenario.write_bytes(b"\xef\xbb\xbf" + scenario.read_bytes())
        completed = run(command, bom)
        passed = completed.returncode != 0
        results.append(result("utf8_bom_rejected", passed, completed))
        if not passed:
            failures.append("utf8_bom_rejected")

    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "hash_mode": "canonical_utf8_lf_v1",
        "path_mode": "repository_posix_v1",
        "python_policy": "setup_python_or_explicit_override_then_python_3_12_plus",
        "failures": failures,
        "results": results,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("gitattributes_enforces_lf", "repository_paths_are_posix", "launcher_policy_is_explicit", "explicit_python_override_selected", "setup_python_root_selected", "baseline_binding_check", "crlf_checkout_preserves_source_identity"))
    output = source / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
