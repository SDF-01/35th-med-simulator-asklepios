#!/usr/bin/env python3
"""Fault-injection tests for the hermetic double-build release gate."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from release_graph_core import CLASSIFICATIONS, collect_input_files, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, exit_code, suite_classification

OUTPUT = Path("reports/release-build-reproducibility-mutations.json")
SCRIPT = Path(__file__).with_name("run_release_build_reproducibility.py")
SECRET = "ghp_RELEASE_BUILD_TEST_SECRET_123456789"


def git(root: Path, *args: str) -> None:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:{completed.stderr or completed.stdout}")


def make_repo(root: Path, mode: str) -> Path:
    root.mkdir(parents=True)
    (root / "config/release").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    package = {
        "name": "fixture",
        "version": "1.0.0",
        "scripts": {
            "build:generate": "fixture-generate",
            "build:typecheck": "fixture-typecheck",
            "build:bundle": "fixture-bundle",
        },
    }
    (root / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8", newline="\n")
    (root / "source.txt").write_text("caller-source\n", encoding="utf-8", newline="\n")
    if mode == "provenance-fails":
        (root / "provenance-fails").write_text("1\n", encoding="utf-8", newline="\n")
    if mode == "provenance-mutates-source":
        (root / "provenance-mutates-source").write_text("1\n", encoding="utf-8", newline="\n")
    provenance = '''#!/usr/bin/env python3
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo');p.add_argument('--subject-dir');p.add_argument('--output');a=p.parse_args()
if Path('provenance-fails').exists():
    print('deliberate provenance failure')
    raise SystemExit(9)
if Path('provenance-mutates-source').exists():
    Path('source.txt').write_text('mutated by provenance\\n', encoding='utf-8')
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'asklepios_verification':{'status':'PASS'}})+'\\n',encoding='utf-8');print(json.dumps({'status':'PASS'}));raise SystemExit(0)
'''
    (root / "scripts/build_facility_decision_provenance.py").write_text(provenance, encoding="utf-8", newline="\n")

    specification = {
        "include": ["package.json", "source.txt", "scripts/build_facility_decision_provenance.py", "provenance-fails", "provenance-mutates-source"],
        "exclude": [],
    }
    specification["files"] = collect_input_files(root, specification)
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "fixture-release-graph",
        "classifications": CLASSIFICATIONS,
        "production_designation": "NOT_GRANTED",
        "truth_boundaries": {
            "patient_care_use": "PROHIBITED",
            "operational_timing": "NOT_CALIBRATED",
            "concrete_treatments_admitted": 0,
            "production_ready": False,
        },
        "input_sets": {"source": specification},
        "managed_package_scripts": {},
        "stages": [{
            "id": "noop",
            "command": ["npm", "run", "noop"],
            "needs": [],
            "input_sets": ["source"],
            "outputs": [],
            "failure_classification": "FAIL",
            "read_only": True,
        }],
        "targets": {"noop": {"terminal_stages": ["noop"]}},
    }
    (root / "config/release/RELEASE_GRAPH.json").write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n",
    )
    git(root, "init", "-q")
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "fixture")
    (root / "node_modules").mkdir()

    driver = root.parent / f"fake-npm-{mode}.py"
    driver.write_text(f'''import sys
import time
from pathlib import Path
mode={mode!r}
script=sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='run' else ''
label=Path.cwd().name
print(f'fake npm label={{label}} script={{script}} mode={{mode}}')
if mode=='first-typecheck-fails' and label=='first-source' and script=='build:typecheck':
    print({SECRET!r})
    print('TYPECHECK FAILED: deliberate fixture failure')
    raise SystemExit(7)
if mode=='second-bundle-fails' and label=='second-source' and script=='build:bundle':
    print('BUNDLE FAILED: deliberate second-pass failure')
    raise SystemExit(8)
if mode=='hung-typecheck' and label=='first-source' and script=='build:typecheck':
    print('HANG FIXTURE: waiting until the release gate terminates this process', flush=True)
    time.sleep(120)
if script=='build:generate':
    Path('snapshot-only-generated.txt').write_text('generated\\n',encoding='utf-8')
if script=='build:bundle' and mode!='missing-dist':
    Path('dist').mkdir(exist_ok=True)
    if mode=='empty-dist':
        raise SystemExit(0)
    if mode=='symlink-output':
        Path('outside.txt').write_text('outside\\n',encoding='utf-8')
        Path('dist/index.html').symlink_to(Path('..') / 'outside.txt')
        raise SystemExit(0)
    content='stable' if mode!='nondeterministic' else label
    content += ':' + __import__('os').environ.get('SOURCE_DATE_EPOCH','missing')
    Path('dist/index.html').write_text(content+'\\n',encoding='utf-8')
raise SystemExit(0)
''', encoding="utf-8", newline="\n")
    fake = root.parent / f"fake-npm-{mode}"
    fake.write_text(f"#!/bin/sh\nexec {sys.executable!s} {driver!s} \"$@\"\n", encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    return fake


def run_case(parent: Path, mode: str, *, extra_environment: dict[str, str] | None = None) -> tuple[int, dict, Path]:
    print(f"[build-gate-test] start:{mode}", file=sys.stderr, flush=True)
    repo = parent / f"repo-{mode}"
    fake_npm = make_repo(repo, mode)
    if mode != "success":
        stale = repo / "reports/facility-decision-build-provenance.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("stale\n", encoding="utf-8", newline="\n")
    env = os.environ.copy()
    env["GH_TOKEN"] = SECRET
    if extra_environment:
        env.update(extra_environment)
    command = [
        sys.executable, str(SCRIPT), "--repo", str(repo),
        "--npm-executable", str(fake_npm),
        "--step-timeout-seconds", "2" if mode == "hung-typecheck" else "30",
        "--provenance-timeout-seconds", "30",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=parent,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, {
            "classification": INTERNAL_ERROR,
            "errors": [f"synthetic build case timed out after {exc.timeout}s:{mode}"],
            "first_build": {},
            "second_build": {},
            "provenance": {"status": "NOT_RUN_TIMEOUT"},
        }, repo
    report = json.loads((repo / "reports/facility-decision-build-reproducibility.json").read_text(encoding="utf-8"))
    print(
        f"[build-gate-test] done:{mode}:exit={completed.returncode}:classification={report.get('classification')}",
        file=sys.stderr,
        flush=True,
    )
    return completed.returncode, report, repo


def run_case_isolated(
    parent: Path,
    mode: str,
    *,
    extra_environment: dict[str, str] | None = None,
) -> tuple[int, dict, Path]:
    """Run each fault case in a fresh interpreter and filesystem island.

    Build fault cases intentionally terminate process groups, mutate source, and
    create unusual output trees.  Keeping every case in a separate interpreter
    prevents one adversarial case from influencing later cases through inherited
    subprocess state, temporary-directory cleanup, or platform process handles.
    """
    worker_root = parent / f"worker-{mode}"
    worker_root.mkdir(parents=True, exist_ok=False)
    result_path = worker_root / "worker-result.json"
    environment = os.environ.copy()
    if extra_environment:
        environment.update(extra_environment)
    command = [
        sys.executable, str(Path(__file__).resolve()),
        "--fixture-case", mode,
        "--fixture-root", str(worker_root),
        "--fixture-output", str(result_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=parent,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, {
            "classification": INTERNAL_ERROR,
            "errors": [f"isolated fixture worker timed out after {exc.timeout}s:{mode}"],
            "first_build": {},
            "second_build": {},
            "provenance": {"status": "NOT_RUN_TIMEOUT"},
        }, worker_root / f"repo-{mode}"
    if completed.returncode != 0 or not result_path.is_file():
        detail = (completed.stderr or completed.stdout)[-4000:]
        return 125, {
            "classification": INTERNAL_ERROR,
            "errors": [f"isolated fixture worker failed:{mode}:exit={completed.returncode}:{detail}"],
            "first_build": {},
            "second_build": {},
            "provenance": {"status": "NOT_RUN_WORKER_FAILED"},
        }, worker_root / f"repo-{mode}"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    return int(payload["case_exit_status"]), payload["report"], Path(payload["repo"])


def fixture_worker(mode: str, root: Path, output: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    code, report, repo = run_case(root, mode)
    write_json(output, {
        "schema_version": "1.0.0",
        "mode": mode,
        "case_exit_status": code,
        "report": report,
        "repo": str(repo),
    })
    return 0


def log_text(report: dict) -> str:
    chunks: list[str] = []
    for build_name in ("first_build", "second_build"):
        for step in report.get(build_name, {}).get("steps", []):
            chunks.extend(step.get("tail", []))
    chunks.extend(report.get("provenance", {}).get("tail", []))
    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    parser.add_argument("--fixture-case")
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--fixture-output", type=Path)
    args = parser.parse_args()
    if args.fixture_case:
        if args.fixture_root is None or args.fixture_output is None:
            parser.error("--fixture-case requires --fixture-root and --fixture-output")
        return fixture_worker(args.fixture_case, args.fixture_root.resolve(), args.fixture_output.resolve())
    root = args.repo.resolve()
    results: list[dict] = []

    try:
        with tempfile.TemporaryDirectory(prefix="asklepios-build-gate-tests-") as directory:
            fixture = Path(directory)

            code, report, repo = run_case_isolated(
                fixture, "success", extra_environment={"SOURCE_DATE_EPOCH": "9999999999"},
            )
            built_text = (repo / "dist/index.html").read_text(encoding="utf-8")
            success_ok = (
                code == 0
                and report.get("classification") == PASS
                and report.get("files_compared") == 1
                and report.get("first_build_root_sha256") == report.get("second_build_root_sha256")
                and built_text.startswith("stable:")
                and "9999999999" not in built_text
                and (repo / "source.txt").read_text(encoding="utf-8") == "caller-source\n"
                and not (repo / "snapshot-only-generated.txt").exists()
                and report.get("provenance", {}).get("status") == PASS
            )
            results.append(case_result(
                "isolated-double-build-pass", PASS if success_ok else FAIL,
                errors=[] if success_ok else ["isolated success contract differs"],
            ))

            code, report, repo = run_case_isolated(fixture, "first-typecheck-fails")
            errors = report.get("errors", [])
            text = log_text(report)
            failure_ok = (
                code != 0
                and report.get("classification") == FAIL
                and report.get("first_build", {}).get("failed_step") == "build:typecheck"
                and any("first production build failed:step=build:typecheck:exit=7" in item for item in errors)
                and "<REDACTED>" in text
                and SECRET not in text
                and report.get("provenance", {}).get("status") == "NOT_RUN_BUILD_FAILED"
                and not (repo / "reports/facility-decision-build-provenance.json").exists()
            )
            results.append(case_result(
                "first-build-failure-attributed-and-redacted",
                EXPECTED_REJECTION if failure_ok else FAIL,
                errors=[] if failure_ok else ["first failure attribution or redaction differs"],
            ))

            code, report, _ = run_case_isolated(fixture, "second-bundle-fails")
            second_ok = (
                code != 0
                and report.get("classification") == FAIL
                and report.get("second_build", {}).get("failed_step") == "build:bundle"
                and any("second production build failed:step=build:bundle:exit=8" in item for item in report.get("errors", []))
            )
            results.append(case_result(
                "second-build-failure-attributed",
                EXPECTED_REJECTION if second_ok else FAIL,
                errors=[] if second_ok else ["second failure attribution differs"],
            ))

            code, report, _ = run_case_isolated(fixture, "missing-dist")
            missing_ok = (
                code != 0
                and report.get("classification") == FAIL
                and any("production build output invalid" in item and "build directory missing" in item for item in report.get("errors", []))
            )
            results.append(case_result(
                "missing-build-output-rejected",
                EXPECTED_REJECTION if missing_ok else FAIL,
                errors=[] if missing_ok else ["missing dist was not rejected"],
            ))

            code, report, _ = run_case_isolated(fixture, "empty-dist")
            empty_ok = (
                code != 0
                and report.get("classification") == FAIL
                and any("production build output invalid" in item and "build directory empty" in item for item in report.get("errors", []))
            )
            results.append(case_result(
                "empty-build-output-rejected",
                EXPECTED_REJECTION if empty_ok else FAIL,
                errors=[] if empty_ok else ["empty dist was not rejected"],
            ))

            code, report, _ = run_case_isolated(fixture, "symlink-output")
            symlink_ok = (
                code != 0
                and report.get("classification") == FAIL
                and any("production build output invalid" in item and "build symlink forbidden" in item for item in report.get("errors", []))
            )
            results.append(case_result(
                "symlinked-build-output-rejected",
                EXPECTED_REJECTION if symlink_ok else FAIL,
                errors=[] if symlink_ok else ["symlinked dist output was not rejected"],
            ))

            code, report, _ = run_case_isolated(fixture, "nondeterministic")
            nondeterministic_ok = (
                code != 0
                and report.get("classification") == FAIL
                and any("build byte identity differs:index.html" in item for item in report.get("errors", []))
            )
            results.append(case_result(
                "nondeterministic-output-rejected",
                EXPECTED_REJECTION if nondeterministic_ok else FAIL,
                errors=[] if nondeterministic_ok else ["nondeterministic output was not rejected"],
            ))

            code, report, repo = run_case_isolated(fixture, "provenance-fails")
            provenance_ok = (
                code != 0
                and report.get("classification") == FAIL
                and report.get("provenance", {}).get("returncode") == 9
                and any("build provenance generation failed:exit=9" in item for item in report.get("errors", []))
                and not (repo / "reports/facility-decision-build-provenance.json").exists()
                and not (repo / "dist").exists()
            )
            results.append(case_result(
                "provenance-failure-invalidates-build",
                EXPECTED_REJECTION if provenance_ok else FAIL,
                errors=[] if provenance_ok else ["provenance failure did not invalidate outputs"],
            ))

            code, report, repo = run_case_isolated(fixture, "provenance-mutates-source")
            mutation_ok = (
                code != 0
                and report.get("classification") == FAIL
                and any("production build mutated locked source" in item for item in report.get("errors", []))
                and not (repo / "reports/facility-decision-build-provenance.json").exists()
                and not (repo / "dist").exists()
            )
            results.append(case_result(
                "provenance-source-mutation-invalidates-build",
                EXPECTED_REJECTION if mutation_ok else FAIL,
                errors=[] if mutation_ok else ["provenance source mutation was accepted"],
            ))

            code, report, _ = run_case_isolated(fixture, "hung-typecheck")
            first = report.get("first_build", {})
            timed_step = next(
                (item for item in first.get("steps", []) if item.get("script") == "build:typecheck"),
                {},
            )
            timeout_ok = (
                code != 0
                and report.get("classification") == FAIL
                and first.get("failed_step") == "build:typecheck"
                and timed_step.get("returncode") == 124
                and timed_step.get("timed_out") is True
                and timed_step.get("termination") not in {None, "NOT_REQUIRED"}
                and any("COMMAND TIMEOUT" in line for line in timed_step.get("tail", []))
            )
            results.append(case_result(
                "hung-build-step-is-bounded-and-attributed",
                EXPECTED_REJECTION if timeout_ok else FAIL,
                errors=[] if timeout_ok else ["hung build step was not terminated and attributed"],
            ))

    except Exception as exc:  # noqa: BLE001
        results.append(case_result("suite-internal-error", INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"]))

    classification = suite_classification(results)
    report = {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] in {FAIL, INTERNAL_ERROR}],
    }
    output = args.json_output if args.json_output.is_absolute() else root / args.json_output
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
