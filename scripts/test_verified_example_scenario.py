#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from scenario_genome_common import GenomeError, atomic_write_json, safe_repo_path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_verified_example_scenario.py"
NODE_CHECKER = ROOT / "scripts/check_verified_example_scenario.mjs"
SAFE_INTEGER = 9_007_199_254_740_991
HASH_FIELDS = {
    "assets": "record_sha256",
    "relations": "relation_sha256",
    "agents": "record_sha256",
    "activities": "record_sha256",
    "evidence_attestations": "attestation_sha256",
    "claim_candidates": "claim_sha256",
    "compatibility_profiles": "profile_sha256",
}
RESULT_CLASSIFICATIONS = ("PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR")

COLLECTION_DOMAINS = {
    "assets": "asklepios.content-registry.assets.v1",
    "relations": "asklepios.content-registry.relations.v1",
    "agents": "asklepios.content-registry.agents.v1",
    "activities": "asklepios.content-registry.activities.v1",
    "evidence_attestations": "asklepios.content-registry.evidence-attestations.v1",
    "claim_candidates": "asklepios.content-registry.claim-candidates.v1",
    "compatibility_profiles": "asklepios.content-registry.compatibility-profiles.v1",
}


def normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise ValueError("unsafe integer")
        return value
    if isinstance(value, float):
        raise ValueError("float forbidden")
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(value[key]) for key in sorted(value)}
    raise ValueError("unsupported type")


def sha256_json(value: Any) -> str:
    raw = json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def refresh_manifest(repo: Path) -> None:
    path = repo / "examples/verified-scenario/manifest.json"
    manifest = read_json(path)
    manifest.pop("example_manifest_sha256", None)
    manifest["example_manifest_sha256"] = sha256_json(manifest)
    write_json(path, manifest)


def record_hash(record: dict[str, Any], field: str) -> str:
    candidate = copy.deepcopy(record)
    candidate.pop(field, None)
    return sha256_json(candidate)


def collection_root(domain: str, hashes: list[str]) -> str:
    return sha256_json({"domain": domain, "hashes": sorted(hashes)})


def refresh_registry(repo: Path) -> None:
    path = repo / "public/data/content_registry/content_registry.json"
    registry = read_json(path)
    roots: dict[str, str] = {}
    for name, hash_field in HASH_FIELDS.items():
        for record in registry.get(name, []):
            record[hash_field] = record_hash(record, hash_field)
        hashes = [record[hash_field] for record in registry.get(name, [])]
        roots[f"{name}_merkle_root"] = collection_root(COLLECTION_DOMAINS[name], hashes)
    roots["registry_merkle_root"] = sha256_json(
        {
            "domain": "asklepios.content-registry.v1",
            "source_manifest_sha256": registry["source_snapshot"]["source_manifest_sha256"],
            "authority_model_sha256": sha256_json(registry["authority_model"]),
            "release_boundary_sha256": sha256_json(registry["release_boundary"]),
            "component_roots": {key: roots[key] for key in sorted(roots)},
        }
    )
    registry["roots"] = roots
    write_json(path, registry)
    manifest_path = repo / "examples/verified-scenario/manifest.json"
    manifest = read_json(manifest_path)
    manifest["source_bindings"]["content_registry_file_sha256"] = sha256_file(path)
    manifest["source_bindings"]["content_registry_merkle_root"] = roots["registry_merkle_root"]
    write_json(manifest_path, manifest)
    refresh_manifest(repo)


def run_checker(repo: Path) -> tuple[bool, dict[str, Any]]:
    commands = (
        [sys.executable, str(CHECKER), "--repo", str(repo)],
        ["node", str(NODE_CHECKER), "--repo", str(repo)],
    )
    reports: list[dict[str, Any]] = []
    passed = True
    for command in commands:
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False, timeout=60)
        try:
            result = json.loads(completed.stdout)
        except Exception:
            result = {"status": "FAIL", "errors": [completed.stdout[-4000:]]}
        reports.append({"command": command[0], "exit_status": completed.returncode, **result})
        passed = passed and completed.returncode == 0 and result.get("status") == "PASS"
    return passed, {"status": "PASS" if passed else "FAIL", "errors": sorted({error for report in reports for error in report.get("errors", [])}), "checkers": reports}


def prepare_minimal(source: Path, destination: Path) -> None:
    """Copy the exact verified-example and engine-evolution fixture closure."""
    files = {
        "README.md",
        "examples/verified-scenario/README.md",
        "examples/verified-scenario/manifest.json",
        "public/data/scenario_core/verified_scenario_package.json",
        "public/data/scenario_core/verified_scenario_genome.json",
        "public/data/content_registry/content_registry.json",
        "config/release/OFFLINE_SCENARIO_RELEASE.json",
        "config/release/SCENARIO_CAPABILITY_RATCHET.json",
        "config/release/TECHNICAL_DEBT_RATCHET.json",
        "config/release/RELEASE_GRAPH.json",
    }
    for rel in sorted(files):
        source_path = source / rel
        if not source_path.is_file() or source_path.is_symlink():
            raise FileNotFoundError(f"declared verified-example fixture unavailable:{rel}")
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)


def mutate_manifest(repo: Path, fn: Callable[[dict[str, Any]], None]) -> None:
    path = repo / "examples/verified-scenario/manifest.json"
    value = read_json(path)
    fn(value)
    write_json(path, value)
    refresh_manifest(repo)


def refresh_genome(genome: dict[str, Any]) -> None:
    genome["genome_id"] = "PENDING"; genome["genome_sha256"] = "PENDING"
    identity = copy.deepcopy(genome); identity.pop("genome_id", None); identity.pop("genome_sha256", None)
    digest = sha256_json(identity)
    genome["genome_id"] = f"ASK-GENOME-{digest[:16].upper()}"
    candidate = copy.deepcopy(genome); candidate.pop("genome_sha256", None)
    genome["genome_sha256"] = sha256_json(candidate)


def main() -> int:
    parser = argparse.ArgumentParser(description="Adversarial assurance for the verified scenario example")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=str)
    args = parser.parse_args()

    source = args.repo.resolve(strict=True)
    cases: list[dict[str, Any]] = []

    def execute(case_id: str, mutation: Callable[[Path], None] | None, should_pass: bool) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="ask-example-") as tmp:
                repo = Path(tmp)
                prepare_minimal(source, repo)
                if mutation:
                    mutation(repo)
                passed, result = run_checker(repo)
                case_pass = passed is should_pass
                classification = (
                    "PASS" if case_pass and should_pass
                    else "EXPECTED_REJECTION" if case_pass
                    else "FAIL"
                )
                cases.append(
                    {
                        "case_id": case_id,
                        "classification": classification,
                        "expected_checker_pass": should_pass,
                        "observed_checker_pass": passed,
                        "pass": case_pass,
                        "checker_errors": result.get("errors", []),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            cases.append({
                "case_id": case_id,
                "classification": "INTERNAL_ERROR",
                "expected_checker_pass": should_pass,
                "observed_checker_pass": False,
                "pass": False,
                "checker_errors": [f"{type(exc).__name__}:{exc}"],
            })

    execute("baseline", None, True)
    execute(
        "documentation_trailing_whitespace_rejected",
        lambda repo: (repo / "examples/verified-scenario/README.md").write_text(
            (repo / "examples/verified-scenario/README.md").read_text(encoding="utf-8").replace(
                "Machine-readable bindings: [`manifest.json`](manifest.json).", "Machine-readable bindings: [`manifest.json`](manifest.json).  "
            ),
            encoding="utf-8",
        ),
        False,
    )
    execute(
        "scenario_id_forgery_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["scenario"].__setitem__("scenario_id", "ASK-FORGED")),
        False,
    )
    execute(
        "certificate_hash_forgery_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["certificate"].__setitem__("package_sha256", "0" * 64)),
        False,
    )
    execute(
        "citation_doi_forgery_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["citations"][0].__setitem__("doi", "10.0000/forged")),
        False,
    )
    execute(
        "citation_entailment_escalation_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["citations"][0].__setitem__("entailment_status", "VERIFIED")),
        False,
    )
    execute(
        "clinical_authority_escalation_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["authority"].__setitem__("clinical_authority", "GRANTED")),
        False,
    )
    execute(
        "unknown_evidence_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["citations"][0].__setitem__("evidence_id", "els_unknown")),
        False,
    )
    execute(
        "hidden_licensed_text_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m.__setitem__("licensed_text", "forbidden")),
        False,
    )
    execute(
        "open_gate_falsely_closed_rehashed",
        lambda repo: mutate_manifest(
            repo,
            lambda m: next(x for x in m["validity_ledger"] if x["gate_id"] == "clinical_template_certification").update(
                {"status": "DEMONSTRATED", "evidence_paths": ["self"]}
            ),
        ),
        False,
    )

    def registry_self_certification(repo: Path) -> None:
        path = repo / "public/data/content_registry/content_registry.json"
        registry = read_json(path)
        target = registry["evidence_attestations"][0]
        target["relation"] = "SUPPORTS"
        target["entailment_status"] = "VERIFIED"
        target["human_review_status"] = "APPROVED"
        target["independent_verifiers"] = ["generator"]
        write_json(path, registry)
        refresh_registry(repo)

    execute("registry_self_certification_globally_rehashed", registry_self_certification, False)

    def source_package_forgery(repo: Path) -> None:
        path = repo / "public/data/scenario_core/verified_scenario_package.json"
        package = read_json(path)
        package["evidence"][0]["chunk_sha256"] = "f" * 64
        write_json(path, package)
        manifest_path = repo / "examples/verified-scenario/manifest.json"
        manifest = read_json(manifest_path)
        manifest["source_bindings"]["scenario_package_file_sha256"] = sha256_file(path)
        manifest["citations"][0]["chunk_sha256"] = "f" * 64
        write_json(manifest_path, manifest)
        refresh_manifest(repo)

    execute("source_package_and_manifest_forgery_rehashed", source_package_forgery, False)

    execute(
        "readme_link_removed",
        lambda repo: (repo / "README.md").write_text(
            (repo / "README.md").read_text(encoding="utf-8").replace(
                "[Open the canonical verified example](examples/verified-scenario/README.md)", "link removed"
            ),
            encoding="utf-8",
        ),
        False,
    )
    execute(
        "documentation_manifest_hash_forged",
        lambda repo: (repo / "examples/verified-scenario/README.md").write_text(
            (repo / "examples/verified-scenario/README.md").read_text(encoding="utf-8").replace(
                read_json(repo / "examples/verified-scenario/manifest.json")["example_manifest_sha256"], "0" * 64
            ),
            encoding="utf-8",
        ),
        False,
    )
    execute(
        "unsafe_source_path_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["source_bindings"].__setitem__("scenario_package_path", "../escape.json")),
        False,
    )
    execute(
        "duplicate_citation_rehashed",
        lambda repo: mutate_manifest(repo, lambda m: m["citations"].append(copy.deepcopy(m["citations"][0]))),
        False,
    )

    execute(
        "engine_evolution_block_removed",
        lambda repo: (repo / "examples/verified-scenario/README.md").write_text(
            (repo / "examples/verified-scenario/README.md").read_text(encoding="utf-8").replace(
                "## Engine evolution binding", "## Removed evolution binding", 1
            ),
            encoding="utf-8",
            newline="\n",
        ),
        False,
    )
    def forge_policy(repo: Path) -> None:
        path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
        value = read_json(path)
        value["release_id"] = "ASK-OFFLINE-FORGED"
        write_json(path, value)
    execute("offline_policy_identity_forgery", forge_policy, False)
    def forge_genome(repo: Path) -> None:
        path = repo / "public/data/scenario_core/verified_scenario_genome.json"
        value = read_json(path); value["behavior_descriptor"]["cycle_free"] = False; refresh_genome(value); write_json(path, value)
    execute("genome_semantic_forgery_rehashed", forge_genome, False)

    def graph_stage_policy_mismatch(repo: Path) -> None:
        path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
        value = read_json(path)
        value["expected_graph_stage_count"] += 1
        write_json(path, value)

    execute("graph_stage_policy_mismatch", graph_stage_policy_mismatch, False)

    def graph_stage_floor_regression(repo: Path) -> None:
        graph_path = repo / "config/release/RELEASE_GRAPH.json"
        policy_path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
        graph = read_json(graph_path)
        graph["stages"] = graph.get("stages", [])[:107]
        write_json(graph_path, graph)
        policy = read_json(policy_path)
        policy["expected_graph_stage_count"] = 113
        write_json(policy_path, policy)

    execute("graph_stage_floor_regression", graph_stage_floor_regression, False)

    def graph_target_floor_regression(repo: Path) -> None:
        graph_path = repo / "config/release/RELEASE_GRAPH.json"
        policy_path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
        graph = read_json(graph_path)
        target_ids = sorted(graph.get("targets", {}))
        graph["targets"].pop(target_ids[-1])
        write_json(graph_path, graph)
        policy = read_json(policy_path)
        policy["expected_graph_target_count"] = len(graph["targets"])
        write_json(policy_path, policy)

    execute("graph_target_floor_regression", graph_target_floor_regression, False)


    def lower_debt_ratchet_epoch_and_rehash(repo: Path) -> None:
        path = repo / "config/release/TECHNICAL_DEBT_RATCHET.json"
        value = read_json(path)
        value["ratchet_epoch"] = 7
        value["ratchet_anchor_sha256"] = sha256_json({
            "ratchet_id": value.get("ratchet_id"),
            "ratchet_epoch": value.get("ratchet_epoch"),
            "register_id": value.get("register_id"),
            "required_entry_floors": value.get("required_entry_floors"),
            "required_final_stage_receipts": value.get("required_final_stage_receipts"),
            "required_contract": value.get("required_contract"),
        })
        write_json(path, value)

    execute("technical_debt_ratchet_epoch_regression_rehashed", lower_debt_ratchet_epoch_and_rehash, False)

    execute(
        "psychometric_false_promotion",
        lambda repo: (repo / "README.md").write_text(
            (repo / "README.md").read_text(encoding="utf-8") + "\nPsychometric validity:   ESTABLISHED\n", encoding="utf-8", newline="\n"
        ),
        False,
    )

    errors = [case["case_id"] for case in cases if not case["pass"]]
    report = {
        "schema_version": "1.0.0",
        "classification": "PASS" if not errors else "FAIL",
        "status": "PASS" if not errors else "FAIL",
        "cases": len(cases),
        "passed": len(cases) - len(errors),
        "errors": errors,
        "results": cases,
        "anti_circular_note": "Semantic forgeries are rehashed before checking; rejection cannot depend only on stale digests.",
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.json_output:
        try:
            output = safe_repo_path(source, args.json_output)
            atomic_write_json(output, report)
        except GenomeError as exc:
            print(json.dumps({
                "schema_version": "1.0.0",
                "classification": "FAIL",
                "status": "FAIL",
                "errors": [str(exc)],
            }, indent=2, sort_keys=True))
            return 3
    return 0 if not errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
