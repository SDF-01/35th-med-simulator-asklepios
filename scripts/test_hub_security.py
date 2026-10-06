#!/usr/bin/env python3
"""Mutation tests for the multiplayer hub security boundary."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from check_hub_security import validate
from release_result import EXPECTED_REJECTION, FAIL, PASS, case_result, exit_code, suite_classification

Mutation = Callable[[Path], None]


def replace(repo: Path, relative: str, old: str, new: str) -> None:
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"mutation marker absent:{relative}:{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def remove_tsconfig_include(repo: Path, entry: str) -> None:
    """Remove one exact include entry without depending on JSON formatting or order."""
    path = repo / "tsconfig.node.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("tsconfig.node.json root is not an object")
    include = value.get("include")
    if not isinstance(include, list):
        raise AssertionError("tsconfig.node.json include is not a list")
    if entry not in include:
        raise AssertionError(f"tsconfig include entry absent:{entry}")
    if include.count(entry) != 1:
        raise AssertionError(f"tsconfig include entry is not unique:{entry}")
    value["include"] = [item for item in include if item != entry]
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n")


def replace_in_event(repo: Path, event: str, old: str, new: str) -> None:
    path = repo / "server/index.ts"
    text = path.read_text(encoding="utf-8")
    marker = f"'{event}'"
    start = text.find(marker)
    if start < 0:
        raise AssertionError(f"event marker absent:{event}")
    next_event = text.find("socket.on(", start + len(marker))
    end = next_event if next_event >= 0 else len(text)
    body = text[start:end]
    if old not in body:
        raise AssertionError(f"event mutation marker absent:{event}:{old}")
    body = body.replace(old, new, 1)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")


def run(root: Path) -> dict:
    cases: list[tuple[str, Mutation | None, str | None]] = [
        ("baseline", None, None),
        ("weak_lobby_randomness", lambda r: replace(r, "server/hubSecurity.ts", "randomInt(0, LOBBY_ALPHABET.length)", "Math.floor(Math.random() * LOBBY_ALPHABET.length)"), "hub cryptographic randomness missing"),
        ("timing_safe_compare_removed", lambda r: replace(r, "server/hubSecurity.ts", "timingSafeEqual(observed, expected)", "observed.equals(expected)"), "hub timing-safe capability comparison missing"),
        ("production_cors_wildcard", lambda r: replace(r, "server/index.ts", "throw new Error('ASKLEPIOS_CORS_ORIGIN must list explicit origins in production. Wildcard CORS is prohibited.');", "return { origins: ['*'], option: true };"), "production wildcard CORS is not fail-closed"),
        ("controller_join_code_only", lambda r: replace(r, "server/index.ts", "if (!verifyCapability(payload?.controllerCapability, lobby.controllerCapabilityDigest))", "if (false)"), "controller capability verification missing"),
        ("provider_takeover_guard_removed", lambda r: replace(r, "server/index.ts", "securityCounters.providerTakeoverRejected += 1;", "securityCounters.providerAuthorizationRejected += 1;"), "provider identity takeover defense missing"),
        ("stale_socket_guard_removed", lambda r: replace(r, "server/index.ts", "if (device.socketId !== socket.id)", "if (false)"), "stale provider socket defense missing"),
        ("public_socket_leak", lambda r: replace(r, "server/index.ts", "exerciseStartedAt: record.exerciseStartedAt,", "exerciseStartedAt: record.exerciseStartedAt,\n    socketId: record.socketId,"), "public provider projection leaks:socketId"),
        ("capability_query_transport", lambda r: replace(r, "src/utils/lobbyCapability.ts", "`${window.location.origin}${path}#${fragment}`", "`${window.location.origin}${path}?${fragment}`"), "controller capability is not transported in URL fragment"),
        ("command_checkbox_reintroduced", lambda r: replace(r, "src/pages/JoinLobbyPage.tsx", "export function JoinLobbyPage()", "const joinAsCommand = false;\nexport function JoinLobbyPage()"), "lobby code still grants command-role routing"),
        ("provider_status_auth_removed", lambda r: replace_in_event(r, "provider:status", "const auth = authorizeProvider(socket, payload);", "const auth = requireLobby(payload.lobbyCode) as never;"), "provider event lacks authorization:provider:status"),
        ("wit_hook_boundary_regression", lambda r: replace(r, "src/pages/WitDashboardPage.tsx", "return <WitDashboardDesktop lobbyCode={lobbyCode} />;", "return <div>desktop</div>;"), "WIT desktop hooks are not isolated"),
        ("command_hook_boundary_regression", lambda r: replace(r, "src/pages/CommandRoomPage.tsx", "return <CommandRoomDesktop lobbyCode={lobbyCode} />;", "return <div>desktop</div>;"), "command desktop hooks are not isolated"),
        ("authorization_error_subscription_removed", lambda r: replace(r, "src/services/networkHub.ts", "export function subscribeHubAuthorizationErrors(", "function removedHubAuthorizationErrors("), "controller authorization failure subscription missing"),
        ("unused_payload_helper_reintroduced", lambda r: replace(r, "src/services/networkHub.ts", "function requireControllerCapability(): string {", "function withLobby<T extends object>(payload: T): T & { lobbyCode: string } {\n  return { ...payload, lobbyCode: requireLobbyCode() };\n}\n\nfunction requireControllerCapability(): string {"), "hub payload helper declared but unused:withLobby"),
        ("provider_replacement_recovery_removed", lambda r: replace(r, "src/pages/ProviderLobbyPage.tsx", "onProviderConnectionReplaced((payload)", "removedProviderConnectionReplaced((payload)"), "provider replacement recovery UX missing"),
        ("acknowledgement_type_guard_removed", lambda r: replace(r, "server/index.ts", "if (typeof candidate === 'function')", "if (candidate)"), "hub acknowledgement type guard missing"),
        ("raw_optional_callback_reintroduced", lambda r: replace(r, "server/index.ts", "acknowledge(callback, { ok: false, error: lobbyResult.error });", "callback?.({ ok: false, error: lobbyResult.error });"), "raw optional callback invocation remains"),
        ("hub_ping_payload_ack_resolution_removed", lambda r: replace(r, "server/index.ts", "resolveAcknowledgement(payloadOrAcknowledgement, callback)", "resolveAcknowledgement(payloadOrAcknowledgement)"), "hub ping payload-and-ack signature missing"),
        ("malformed_ack_runtime_regression_removed", lambda r: replace(r, "scripts/testHubRuntimeSmoke.ts", "hub_survives_malformed_acknowledgement", "removed_malformed_acknowledgement_survival"), "hub malformed acknowledgement survival regression missing"),
        ("malformed_ack_candidate_discarded", lambda r: replace(r, "server/index.ts", "return acknowledgement === undefined ? payloadOrAcknowledgement : acknowledgement;", "return acknowledgement;"), "malformed acknowledgement candidate is discarded before audit"),
        ("hub_server_typecheck_scope_removed", lambda r: remove_tsconfig_include(r, "server/**/*.ts"), "hub server is outside strict TypeScript build scope"),
        ("hub_smoke_typecheck_scope_removed", lambda r: remove_tsconfig_include(r, "scripts/testHubRuntimeSmoke.ts"), "hub runtime smoke is outside strict TypeScript build scope"),
    ]
    results = []
    for case_id, mutation, required in cases:
        with tempfile.TemporaryDirectory(prefix="asklepios-hub-security-") as tmp:
            repo = Path(tmp) / "repo"
            shutil.copytree(root, repo, ignore=shutil.ignore_patterns(".git", "node_modules", ".asklepios", "dist", "__pycache__"))
            if mutation:
                mutation(repo)
            observed = validate(repo)
            errors = observed.get("errors", [])
            if mutation is None:
                passed = observed.get("classification") == PASS
                classification = PASS if passed else FAIL
            else:
                passed = observed.get("classification") == FAIL and any(required in error for error in errors)
                classification = EXPECTED_REJECTION if passed else FAIL
            results.append(
                case_result(
                    case_id,
                    classification,
                    errors=[] if passed else errors,
                    required_error=required,
                    observed_classification=observed.get("classification"),
                )
            )
    classification = suite_classification(results)
    return {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "results": results,
        "errors": [] if classification == PASS else ["hub security mutation suite failed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/hub-security-mutations.json"))
    args = parser.parse_args()
    root = args.repo.resolve()
    report = run(root)
    (root / args.json_output).parent.mkdir(parents=True, exist_ok=True)
    (root / args.json_output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
