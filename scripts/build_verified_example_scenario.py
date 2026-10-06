#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from engine_evolution_common import render_evolution_block

SAFE_INTEGER = 9_007_199_254_740_991
EXAMPLE_ID = "ASK-EXAMPLE-RC3-2"
SCENARIO_PATH = Path("public/data/scenario_core/verified_scenario_package.json")
REGISTRY_PATH = Path("public/data/content_registry/content_registry.json")
EXAMPLE_DIR = Path("examples/verified-scenario")
MANIFEST_PATH = EXAMPLE_DIR / "manifest.json"
DOC_PATH = EXAMPLE_DIR / "README.md"
README_PATH = Path("README.md")

REQUIRED_AUTHORITY = {
    "clinical_authority": "NOT_GRANTED",
    "deployment_scope": "research_sandbox_only",
    "source_template_status": "repository_template_not_clinically_certified",
    "clinical_rule_source": "inherited_template",
    "evidence_authority": "supporting_only",
    "evidence_effect_scope": "citation_support_only",
    "scoring_behavior": "inherited_unchanged",
}

OPEN_GATES = [
    ("clinical_template_certification", "Independent clinical certification of the inherited source template."),
    ("claim_level_evidence_entailment", "Atomic scenario claims have not yet been adjudicated against exact source spans."),
    ("contradiction_search", "Contradictory or superseding sources have not yet been exhaustively reviewed."),
    ("real_world_operational_calibration", "Generated operational frequencies are not calibrated against held-out real-world data."),
    ("human_policy_calibration", "Actor and learner behavior models are not calibrated against observed team behavior."),
    ("executable_to_formal_refinement", "The executable implementation is not yet mechanized as a refinement of the Lean model."),
    ("independent_proof_kernel", "A compatible separately implemented proof kernel has not accepted the full release."),
    ("multi_template_clinical_breadth", "This example is based on one inherited clinical template."),
    ("training_effectiveness_validation", "Learner outcome and instructor usability studies remain open."),
]

FORBIDDEN_PUBLIC_KEYS = {
    "licensed_text",
    "full_text",
    "raw_text",
    "article_text",
    "xml_body",
    "institutional_token",
    "api_key",
    "embedding_vector",
    "private_prompt",
}


def normalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise ValueError(f"integer outside cross-language safe range:{value}")
        return value
    if isinstance(value, float):
        raise ValueError("floating-point values are forbidden in example manifest hashes")
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("all JSON object keys must be strings")
        return {key: normalize(value[key]) for key in sorted(value)}
    raise ValueError(f"unsupported canonical value:{type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()



def stable_public_value(value: Any) -> Any:
    """Convert selected source values into the cross-language committed domain."""
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, list):
        return [stable_public_value(item) for item in value]
    if isinstance(value, dict):
        return {key: stable_public_value(child) for key, child in value.items()}
    return value


def scan_forbidden(value: Any, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in FORBIDDEN_PUBLIC_KEYS:
                findings.append(f"{path}.{key}")
            findings.extend(scan_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(scan_forbidden(child, f"{path}[{index}]"))
    return findings


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object:{path}")
    return value


def exact_asset(assets: dict[str, dict[str, Any]], asset_id: str) -> dict[str, Any]:
    try:
        return assets[asset_id]
    except KeyError as exc:
        raise ValueError(f"registry asset missing:{asset_id}") from exc


def build_manifest(repo: Path) -> dict[str, Any]:
    scenario_file = repo / SCENARIO_PATH
    registry_file = repo / REGISTRY_PATH
    if not scenario_file.is_file():
        raise ValueError(f"verified scenario package missing:{SCENARIO_PATH}")
    if not registry_file.is_file():
        raise ValueError(f"content registry missing:{REGISTRY_PATH}")

    package = load_json(scenario_file)
    registry = load_json(registry_file)

    forbidden = scan_forbidden(package) + scan_forbidden(registry)
    if forbidden:
        raise ValueError("forbidden public fields:" + ",".join(forbidden[:20]))

    authority = package.get("authority")
    if authority != REQUIRED_AUTHORITY:
        raise ValueError("scenario authority boundary differs from reviewed example policy")

    certificate = package.get("certificate", {})
    checks = certificate.get("checks", {})
    if not checks or not all(value is True for value in checks.values()):
        raise ValueError("scenario certificate contains a failed or missing check")
    if certificate.get("base_protected_sha256") != certificate.get("output_protected_sha256"):
        raise ValueError("protected clinical projection changed")

    source_scenario_id = package.get("build", {}).get("source_scenario_id")
    scenario_id = package.get("scenario", {}).get("scenario_id")
    if not isinstance(source_scenario_id, str) or not source_scenario_id:
        raise ValueError("source scenario ID missing")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValueError("scenario ID missing")

    assets = {item["asset_id"]: item for item in registry.get("assets", [])}
    attestations = {
        item["evidence_asset_id"].removeprefix("evidence:"): item
        for item in registry.get("evidence_attestations", [])
    }

    template_id = f"template:{source_scenario_id}"
    template = exact_asset(assets, template_id)
    if template.get("kind") != "protected_template":
        raise ValueError("source scenario registry asset is not a protected template")
    template_meta = template.get("metadata", {})
    if template_meta.get("clinical_certification") != "NOT_GRANTED":
        raise ValueError("source template unexpectedly claims clinical certification")

    citations: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for order, evidence in enumerate(package.get("evidence", []), start=1):
        evidence_id = evidence.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError("scenario evidence record lacks evidence_id")
        if evidence_id in seen_evidence:
            raise ValueError(f"duplicate scenario evidence:{evidence_id}")
        seen_evidence.add(evidence_id)

        evidence_asset_id = f"evidence:{evidence_id}"
        evidence_asset = exact_asset(assets, evidence_asset_id)
        evidence_meta = evidence_asset.get("metadata", {})
        source_asset_id = evidence_meta.get("source_asset_id")
        if not isinstance(source_asset_id, str):
            raise ValueError(f"evidence source link missing:{evidence_id}")
        source_asset = exact_asset(assets, source_asset_id)
        source_meta = source_asset.get("metadata", {})
        attestation = attestations.get(evidence_id)
        if attestation is None:
            raise ValueError(f"identity attestation missing:{evidence_id}")

        comparisons = {
            "doi": evidence.get("doi"),
            "locator": evidence.get("locator"),
            "chunk_sha256": evidence.get("chunk_sha256"),
            "source_file_sha256": evidence.get("source_file_sha256"),
        }
        for field, value in comparisons.items():
            if evidence_meta.get(field) != value:
                raise ValueError(f"evidence identity mismatch:{evidence_id}:{field}")
        for field in ("title", "journal", "doi", "source_file_sha256"):
            if source_meta.get(field) != evidence.get(field):
                raise ValueError(f"source identity mismatch:{evidence_id}:{field}")

        expected_attestation = {
            "relation": "REFERENCE_ONLY",
            "identity_verification": "PASS",
            "entailment_status": "NOT_ADJUDICATED",
            "contradiction_status": "NOT_SEARCHED",
            "human_review_status": "NOT_REVIEWED",
            "clinical_authority": "NOT_GRANTED",
            "authority_tier": 3,
        }
        for field, expected in expected_attestation.items():
            if attestation.get(field) != expected:
                raise ValueError(f"evidence status escalation:{evidence_id}:{field}")
        if attestation.get("independent_verifiers") != []:
            raise ValueError(f"unreviewed evidence claims independent verification:{evidence_id}")

        citations.append(
            {
                "order": order,
                "evidence_id": evidence_id,
                "title": evidence.get("title"),
                "journal": evidence.get("journal"),
                "doi": evidence.get("doi"),
                "locator": evidence.get("locator"),
                "chunk_sha256": evidence.get("chunk_sha256"),
                "source_file_sha256": evidence.get("source_file_sha256"),
                "evidence_asset_id": evidence_asset_id,
                "evidence_asset_record_sha256": evidence_asset.get("record_sha256"),
                "source_asset_id": source_asset_id,
                "source_asset_record_sha256": source_asset.get("record_sha256"),
                "attestation_id": attestation.get("attestation_id"),
                "attestation_sha256": attestation.get("attestation_sha256"),
                "relation": "REFERENCE_ONLY",
                "identity_verification": "PASS",
                "entailment_status": "NOT_ADJUDICATED",
                "contradiction_status": "NOT_SEARCHED",
                "human_review_status": "NOT_REVIEWED",
                "clinical_authority": "NOT_GRANTED",
                "authority_tier": 3,
            }
        )

    route = package.get("route", {})
    route_nodes = route.get("nodes", [])
    route_edges = route.get("edges", [])
    terminal_nodes = [node.get("node_id") for node in route_nodes if node.get("terminal") is True]
    if not terminal_nodes:
        raise ValueError("example route has no terminal node")

    patient = (package.get("scenario", {}).get("patients") or [{}])[0]
    context = package.get("scenario", {}).get("operational_context", {})

    demonstrated_gates = [
        {
            "gate_id": "source_template_binding",
            "status": "DEMONSTRATED",
            "scope": "The example resolves to the protected-template registry asset and source file hash.",
            "evidence_paths": [str(REGISTRY_PATH), str(SCENARIO_PATH)],
        },
        {
            "gate_id": "protected_projection_preservation",
            "status": "DEMONSTRATED",
            "scope": "The scenario certificate reports identical base and output protected hashes.",
            "evidence_paths": [str(SCENARIO_PATH)],
        },
        {
            "gate_id": "deterministic_package_certificate",
            "status": "DEMONSTRATED",
            "scope": "The existing scenario-contract generator and independent checkers bind the package hash.",
            "evidence_paths": [str(SCENARIO_PATH)],
        },
        {
            "gate_id": "citation_identity_provenance",
            "status": "DEMONSTRATED",
            "scope": "Every citation matches a registry evidence asset, source asset, and identity-only attestation.",
            "evidence_paths": [str(REGISTRY_PATH), str(SCENARIO_PATH)],
        },
        {
            "gate_id": "authority_non_escalation",
            "status": "DEMONSTRATED",
            "scope": "The example remains research-sandbox-only with supporting-only evidence and inherited scoring.",
            "evidence_paths": [str(REGISTRY_PATH), str(SCENARIO_PATH)],
        },
    ]
    open_gates = [
        {
            "gate_id": gate_id,
            "status": "OPEN",
            "scope": scope,
            "evidence_paths": [],
        }
        for gate_id, scope in OPEN_GATES
    ]

    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "example_id": EXAMPLE_ID,
        "purpose": "Canonical human-readable entry point for the existing verified template-locked scenario package.",
        "source_bindings": {
            "scenario_package_path": str(SCENARIO_PATH),
            "scenario_package_file_sha256": sha256_file(scenario_file),
            "scenario_package_sha256": certificate.get("package_sha256"),
            "content_registry_path": str(REGISTRY_PATH),
            "content_registry_file_sha256": sha256_file(registry_file),
            "content_registry_merkle_root": registry.get("roots", {}).get("registry_merkle_root"),
            "source_database_sha256": package.get("build", {}).get("source_database_sha256"),
            "source_bridge_sha256": package.get("build", {}).get("source_bridge_sha256"),
        },
        "authority": copy.deepcopy(authority),
        "protected_template": {
            "asset_id": template_id,
            "record_sha256": template.get("record_sha256"),
            "source_path": template.get("source", {}).get("path"),
            "source_file_sha256": template.get("source", {}).get("file_sha256"),
            "title": template_meta.get("title"),
            "clinical_certification": template_meta.get("clinical_certification"),
            "review_record_status": template_meta.get("review_record_status"),
        },
        "scenario": {
            "scenario_id": scenario_id,
            "source_scenario_id": source_scenario_id,
            "title": package.get("scenario", {}).get("title"),
            "topic_id": package.get("build", {}).get("topic_id"),
            "seed": package.get("build", {}).get("seed"),
            "mode": package.get("build", {}).get("mode"),
            "operational_context": {
                "location_type": context.get("location_type"),
                "weather": context.get("weather"),
                "visibility": context.get("visibility"),
                "comms_status": context.get("comms_status"),
                "resource_status": context.get("resource_status"),
            },
            "patient_summary": {
                "patient_id": patient.get("patient_id"),
                "role_context": patient.get("role_context"),
                "mechanism_of_injury": patient.get("mechanism_of_injury"),
                "initial_presentation": patient.get("initial_presentation"),
                "initial_vitals": stable_public_value(patient.get("initial_vitals")),
            },
        },
        "route_summary": {
            "route_id": route.get("route_id"),
            "start_node_id": route.get("start_node_id"),
            "node_count": len(route_nodes),
            "edge_count": len(route_edges),
            "terminal_node_ids": terminal_nodes,
            "nodes": [
                {
                    "node_id": node.get("node_id"),
                    "node_kind": node.get("node_kind"),
                    "label": node.get("label"),
                    "terminal": node.get("terminal"),
                }
                for node in route_nodes
            ],
            "edges": [
                {
                    "edge_id": edge.get("edge_id"),
                    "from": edge.get("from"),
                    "to": edge.get("to"),
                    "trigger": edge.get("trigger"),
                    "priority": edge.get("priority"),
                }
                for edge in route_edges
            ],
        },
        "certificate": {
            "certificate_version": certificate.get("certificate_version"),
            "checker_profile": certificate.get("checker_profile"),
            "base_scenario_sha256": certificate.get("base_scenario_sha256"),
            "base_protected_sha256": certificate.get("base_protected_sha256"),
            "output_protected_sha256": certificate.get("output_protected_sha256"),
            "route_sha256": certificate.get("route_sha256"),
            "field_origin_sha256": certificate.get("field_origin_sha256"),
            "evidence_sha256": certificate.get("evidence_sha256"),
            "package_sha256": certificate.get("package_sha256"),
            "checks": copy.deepcopy(checks),
        },
        "citations": citations,
        "validity_ledger": demonstrated_gates + open_gates,
        "claim_language": {
            "strongest_supported_claim": "This repository contains a deterministic, certificate-bound research-sandbox scenario example whose protected template and citation identities are traceable to the content registry.",
            "prohibited_claims": [
                "clinically certified",
                "real-world validated",
                "citation entailment verified",
                "authoritative treatment guidance",
            ],
        },
        "documentation": {
            "readme_path": str(DOC_PATH),
            "root_readme_path": str(README_PATH),
            "source_package_path": str(SCENARIO_PATH),
            "content_registry_path": str(REGISTRY_PATH),
        },
        "hashing": {
            "canonicalization": "UTF-8 JSON with lexicographically sorted object keys, no insignificant whitespace, no floats, and JavaScript-safe integers",
            "hash_algorithm": "SHA-256",
        },
    }
    manifest["example_manifest_sha256"] = sha256_json(manifest)
    return manifest


def markdown_escape(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render_doc(repo: Path, manifest: dict[str, Any]) -> str:
    scenario = manifest["scenario"]
    context = scenario["operational_context"]
    patient = scenario["patient_summary"]
    route = manifest["route_summary"]
    authority = manifest["authority"]
    certificate = manifest["certificate"]
    lines: list[str] = []
    lines.extend(
        [
            "# Canonical verified example scenario",
            "",
            "> **Training research sandbox only. Clinical authority is NOT GRANTED.** The inherited source template is not clinically certified, the citations are identity-verified reference records only, and this example is not medical guidance.",
            "",
            f"- **Example ID:** `{manifest['example_id']}`",
            f"- **Scenario ID:** `{scenario['scenario_id']}`",
            f"- **Source template:** `{scenario['source_scenario_id']}`",
            f"- **Scenario package SHA-256:** `{manifest['source_bindings']['scenario_package_sha256']}`",
            f"- **Content registry root:** `{manifest['source_bindings']['content_registry_merkle_root']}`",
            f"- **Example manifest SHA-256:** `{manifest['example_manifest_sha256']}`",
            "",
            "Machine-readable bindings: [`manifest.json`](manifest.json).",
            "Authoritative source artifact for this example: [`public/data/scenario_core/verified_scenario_package.json`](../../public/data/scenario_core/verified_scenario_package.json).",
            "",
        ]
    )
    lines.extend(render_evolution_block(repo).rstrip("\n").split("\n"))
    lines.extend(
        [
            "",
            "## Learner-facing brief",
            "",
            f"### {scenario['title']}",
            "",
            "Fictional training scenario. Follow local medical authority and current approved guidance. Operational details were varied inside an allowlisted template; the inherited clinical scaffold and scoring were not changed by this example release.",
            "",
            f"- **Setting:** {markdown_escape(context['location_type'])}",
            f"- **Weather:** {markdown_escape(context['weather'])}",
            f"- **Visibility:** {markdown_escape(context['visibility'])}",
            f"- **Communications:** {markdown_escape(context['comms_status'])}",
            f"- **Resources:** {markdown_escape(context['resource_status'])}",
            "",
            "### Initial casualty presentation",
            "",
            markdown_escape(patient["initial_presentation"]),
            "",
            f"- **Patient:** `{markdown_escape(patient['patient_id'])}` — {markdown_escape(patient['role_context'])}",
            f"- **Mechanism:** {markdown_escape(patient['mechanism_of_injury'])}",
            f"- **Initial vitals:** `{json.dumps(patient['initial_vitals'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Decision route",
            "",
            f"The compiled route has **{route['node_count']} nodes**, **{route['edge_count']} edges**, and terminal node(s) `{', '.join(route['terminal_node_ids'])}`.",
            "",
            "| From | Trigger | To | Priority |",
            "|---|---|---|---:|",
        ]
    )
    for edge in route["edges"]:
        lines.append(
            f"| `{markdown_escape(edge['from'])}` | `{markdown_escape(edge['trigger'])}` | `{markdown_escape(edge['to'])}` | {edge['priority']} |"
        )

    lines.extend(
        [
            "",
            "## Certificate checks",
            "",
            "| Check | Result |",
            "|---|---|",
        ]
    )
    for key, value in certificate["checks"].items():
        lines.append(f"| `{key}` | **{'PASS' if value else 'FAIL'}** |")

    lines.extend(
        [
            "",
            "## Citation identity ledger",
            "",
            "> The records below establish source identity and chain of custody. They do **not** yet establish claim-level entailment, contradiction clearance, or clinical authority.",
            "",
        ]
    )
    for citation in manifest["citations"]:
        lines.extend(
            [
                f"{citation['order']}. **{markdown_escape(citation['title'])}**. *{markdown_escape(citation['journal'])}*. DOI `{markdown_escape(citation['doi'])}`.",
                f"   - Locator: {markdown_escape(citation['locator'])}",
                f"   - Evidence ID: `{citation['evidence_id']}`",
                f"   - Chunk SHA-256: `{citation['chunk_sha256']}`",
                f"   - Source-file SHA-256: `{citation['source_file_sha256']}`",
                f"   - Status: `{citation['identity_verification']}` identity, `{citation['relation']}`, entailment `{citation['entailment_status']}`, contradiction `{citation['contradiction_status']}`, human review `{citation['human_review_status']}`",
            ]
        )

    lines.extend(
        [
            "",
            "## What this example demonstrates",
            "",
        ]
    )
    for gate in manifest["validity_ledger"]:
        if gate["status"] == "DEMONSTRATED":
            lines.append(f"- **{gate['gate_id']} — DEMONSTRATED:** {gate['scope']}")

    lines.extend(
        [
            "",
            "## Open validity gates",
            "",
            "These are deliberately visible so the README example cannot be mistaken for a clinically certified or real-world-calibrated simulator.",
            "",
        ]
    )
    for gate in manifest["validity_ledger"]:
        if gate["status"] == "OPEN":
            lines.append(f"- **{gate['gate_id']} — OPEN:** {gate['scope']}")

    lines.extend(
        [
            "",
            "## Rebuild and independently verify",
            "",
            "```bash",
            "python3 scripts/build_verified_example_scenario.py --repo . --check",
            "python3 scripts/check_verified_example_scenario.py --repo .",
            "node scripts/check_verified_example_scenario.mjs",
            "python3 scripts/test_verified_example_scenario.py",
            "npm run verify:scenario-contracts",
            "```",
            "",
            "The Python and Node checkers independently reconstruct the bindings from the source package and content registry. The mutation suite includes rehashed semantic forgeries so a stale digest is not the only reason an attack is rejected.",
            "",
            "## Next refinement gate",
            "",
            "The next engine release should compile compatibility-approved registry assets into additional deterministic scenario specifications. It must not activate a profile unless field origins are complete, citation claims are adjudicated where required, independent checkers agree, and the authority boundary remains unchanged.",
            "",
        ]
    )
    return "\n".join(line.rstrip(" \t") for line in lines).rstrip() + "\n"


def write_or_check(path: Path, text: str, check: bool, mismatches: list[str]) -> None:
    if check:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            mismatches.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()

    try:
        manifest = build_manifest(repo)
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        doc_text = render_doc(repo, manifest)
        mismatches: list[str] = []
        write_or_check(repo / MANIFEST_PATH, manifest_text, args.check, mismatches)
        write_or_check(repo / DOC_PATH, doc_text, args.check, mismatches)
        status = "PASS" if not mismatches else "FAIL"
        report = {
            "schema_version": "1.0.0",
            "status": status,
            "mode": "check" if args.check else "write",
            "example_id": EXAMPLE_ID,
            "scenario_id": manifest["scenario"]["scenario_id"],
            "citation_count": len(manifest["citations"]),
            "demonstrated_gates": sum(1 for item in manifest["validity_ledger"] if item["status"] == "DEMONSTRATED"),
            "open_gates": sum(1 for item in manifest["validity_ledger"] if item["status"] == "OPEN"),
            "example_manifest_sha256": manifest["example_manifest_sha256"],
            "mismatches": mismatches,
            "errors": [],
        }
    except Exception as exc:
        report = {
            "schema_version": "1.0.0",
            "status": "FAIL",
            "mode": "check" if args.check else "write",
            "errors": [str(exc)],
        }

    output = json.dumps(report, indent=2, sort_keys=True)
    print(output)
    if args.report:
        report_path = Path(args.report)
        if not report_path.is_absolute():
            report_path = repo / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(output + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
