#!/usr/bin/env python3
"""Static security contract for the multiplayer healthcare-simulation hub."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from release_graph_core import write_json
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

OUTPUT = Path("reports/hub-security.json")


def between(text: str, start: str, end: str) -> str:
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0]


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        server = (root / "server/index.ts").read_text(encoding="utf-8")
        security = (root / "server/hubSecurity.ts").read_text(encoding="utf-8")
        client = (root / "src/services/networkHub.ts").read_text(encoding="utf-8")
        capability = (root / "src/utils/lobbyCapability.ts").read_text(encoding="utf-8")
        join_page = (root / "src/pages/JoinLobbyPage.tsx").read_text(encoding="utf-8")
        use_lobby = (root / "src/hooks/useLobbyCode.ts").read_text(encoding="utf-8")
        public_type = (root / "src/types/device.ts").read_text(encoding="utf-8")
        wit_page = (root / "src/pages/WitDashboardPage.tsx").read_text(encoding="utf-8")
        command_page = (root / "src/pages/CommandRoomPage.tsx").read_text(encoding="utf-8")
        provider_page = (root / "src/pages/ProviderLobbyPage.tsx").read_text(encoding="utf-8")
        runtime_smoke = (root / "scripts/testHubRuntimeSmoke.ts").read_text(encoding="utf-8")
        node_tsconfig = json.loads((root / "tsconfig.node.json").read_text(encoding="utf-8"))

        require("LOBBY_ALPHABET[randomInt(" in security and "randomBytes(bytes).toString('base64url')" in security, "hub cryptographic randomness missing")
        require("timingSafeEqual(observed, expected)" in security, "hub timing-safe capability comparison missing")
        require("createHash('sha256')" in security, "hub capability digest missing")
        require("Math.random" not in server and "Math.random" not in client, "hub or client uses Math.random for security identity")
        require("controllerCapabilityDigest" in server, "controller capability is not stored as a digest")
        require("capabilityDigest: string" in server, "provider capability digest missing")
        require("controllerCapability:" not in between(server, "interface LobbyState", "const LEGACY_DEPARTMENT_MAP"), "raw controller capability stored in lobby state")
        require(server.count("verifyCapability(payload?.controllerCapability, lobby.controllerCapabilityDigest)") >= 2, "controller capability verification missing")
        require("verifyCapability(payload?.providerCapability" in server, "provider capability verification missing")
        require("securityCounters.providerTakeoverRejected += 1;" in server, "provider identity takeover defense missing")
        require(server.count("device.socketId !== socket.id") >= 2, "stale provider socket defense missing")
        require("priorSocketId" in server and "disconnect(true)" in server, "authenticated provider reconnect replacement missing")
        require("Rotate the capability at every authenticated registration" in server, "provider reconnect capability rotation missing")
        require("device.socketId !== socket.id) return" in server, "stale disconnect cannot be distinguished from current connection")
        require("ASKLEPIOS_CORS_ORIGIN must list explicit origins in production" in server, "production wildcard CORS is not fail-closed")
        require("X-Asklepios-Controller-Capability" in server, "controller HTTP authorization header missing")
        require("controllerCapabilityFromRequest" in server and "res.status(403)" in server, "device inventory HTTP authorization missing")
        require("MAX_LOBBIES" in server and "MAX_DEVICES_PER_LOBBY" in server, "hub capacity bounds missing")
        require("LOBBY_TTL_MS" in server and "cleanupExpiredLobbies" in server, "lobby expiry policy missing")
        require("consumeLobbyCreateBudget" in server and "res.status(429)" in server, "lobby creation rate limit missing")
        require("app.disable('x-powered-by')" in server, "Express fingerprint header not disabled")
        require("function acknowledge<T extends object>(candidate: unknown" in server, "hub acknowledgement type guard missing")
        require("return acknowledgement === undefined ? payloadOrAcknowledgement : acknowledgement;" in server, "malformed acknowledgement candidate is discarded before audit")
        require("if (typeof candidate === 'function')" in server, "hub acknowledgement type guard missing")
        require("callback?.(" not in server, "raw optional callback invocation remains")
        require(server.count("acknowledge(callback,") >= 30, "hub acknowledgement guard is not used by all callback handlers")
        require("malformedAcknowledgementIgnored" in server, "malformed acknowledgement audit counter missing")
        require(server.count("resolveAcknowledgement(payloadOrAcknowledgement, callback)") >= 2, "hub ping payload-and-ack signature missing")
        require("emitAckWithoutPayload" in runtime_smoke and "hub_ping_without_payload_ack_passes" in runtime_smoke, "hub no-payload acknowledgement regression missing")
        require("hub_ping_with_payload_ack_passes" in runtime_smoke, "hub payload acknowledgement regression missing")
        require("emitMalformedAcknowledgement" in runtime_smoke and "hub_survives_malformed_acknowledgement" in runtime_smoke, "hub malformed acknowledgement survival regression missing")
        require("malformed_acknowledgement_is_audited" in runtime_smoke, "hub malformed acknowledgement audit regression missing")
        include = node_tsconfig.get("include") if isinstance(node_tsconfig, dict) else None
        require(isinstance(include, list) and "server/**/*.ts" in include, "hub server is outside strict TypeScript build scope")
        require(isinstance(include, list) and "scripts/testHubRuntimeSmoke.ts" in include, "hub runtime smoke is outside strict TypeScript build scope")

        projection = between(server, "function publicDevice", "function listDevices")
        require(bool(projection), "public provider projection missing")
        for restricted in ("socketId", "capabilityDigest", "userAgent"):
            require(restricted not in projection, f"public provider projection leaks:{restricted}")
        require("userAgent" not in public_type, "public provider type exposes user agent")

        controller_events = {
            "wit:request-session",
            "wit:deploy",
            "wit:start-exercise",
            "wit:arm-exercise",
            "wit:end-exercise",
            "wit:endex",
        }
        for event in sorted(controller_events):
            match = re.search(rf"socket\.on\(\s*['\"]{re.escape(event)}['\"](?P<body>[\s\S]*?)(?=\n\s*socket\.on\(|\n\s*function cleanupExpiredLobbies)", server)
            require(match is not None, f"controller event missing:{event}")
            require(match is not None and "authorizeController" in match.group("body"), f"controller event lacks authorization:{event}")

        provider_events = {
            "provider:update-name",
            "provider:update-profile",
            "provider:execute-handoff",
            "provider:return-standby",
            "provider:status",
            "session:sync",
        }
        for event in sorted(provider_events):
            match = re.search(rf"socket\.on\(\s*['\"]{re.escape(event)}['\"](?P<body>[\s\S]*?)(?=\n\s*socket\.on\(|\n\s*function cleanupExpiredLobbies)", server)
            require(match is not None, f"provider event missing:{event}")
            require(match is not None and "authorizeProvider" in match.group("body"), f"provider event lacks authorization:{event}")

        require("`${window.location.origin}${path}#${fragment}`" in capability and "FRAGMENT_KEY" in capability, "controller capability is not transported in URL fragment")
        require("window.history.replaceState" in capability, "controller capability fragment is not removed from browser history")
        require("window.location.search" in capability, "controller link fragment removal does not preserve existing query")
        require("controllerCapability" not in (root / "src/utils/lobbyCode.ts").read_text(encoding="utf-8"), "controller capability leaked into normal lobby URL helper")
        require("joinAsCommand" not in join_page, "lobby code still grants command-role routing")
        require("provider code never grants exercise-control access" in join_page, "provider/control role boundary not visible in join UX")
        require("importControllerCapabilityFromFragment(code)" in use_lobby, "secure controller fragment is not imported on route entry")
        require("saveControllerCapability" in client and "saveProviderCapability" in client, "client capability persistence missing")
        require("withController" in client and "withProvider" in client, "client authorization payload helpers missing")
        local_payload_helpers = sorted(set(re.findall(r"^function\s+(with[A-Z][A-Za-z0-9_]*)\s*(?:<[^>\n]+>)?\s*\(", client, re.MULTILINE)))
        for helper in local_payload_helpers:
            references = len(re.findall(rf"\b{re.escape(helper)}\s*\(", client))
            require(references > 1, f"hub payload helper declared but unused:{helper}")
        require("emitAuthorized" in client and "payloadFactory" in client, "fire-and-forget authorization failures are not safely captured")
        require("subscribeHubAuthorizationErrors" in client, "controller authorization failure subscription missing")
        require("export function onProviderConnectionReplaced" in client and "onProviderConnectionReplaced((payload)" in provider_page and "connectionReplacementNotice" in provider_page, "provider replacement recovery UX missing")
        require("function WitDashboardDesktop" in wit_page and "return <WitDashboardDesktop" in wit_page, "WIT desktop hooks are not isolated from the mobile conditional boundary")
        require("function CommandRoomDesktop" in command_page and "return <CommandRoomDesktop" in command_page, "command desktop hooks are not isolated from the mobile conditional boundary")
        require("subscribeHubAuthorizationErrors" in wit_page and "subscribeHubAuthorizationErrors" in command_page, "controller authorization failures are not surfaced in both command interfaces")

        classification = PASS if not errors else FAIL
        return {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "checks": checks,
            "security_model": "DIGESTED_CAPABILITY_BOUND_SOCKET_V1",
            "controller_capability_transport": "URL_FRAGMENT_THEN_SESSION_STORAGE",
            "provider_identity_takeover_protection": classification == PASS,
            "acknowledgement_policy": "TYPE_GUARDED_DUAL_SIGNATURE_ACK_WITH_MALFORMED_INPUT_AUDIT_V2",
            "typecheck_policy": "STRICT_ROOT_BUILD_INCLUDES_HUB_SERVER_AND_RUNTIME_SMOKE_V1",
            "public_device_projection_restricted": classification == PASS,
            "healthcare_simulation_training": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "simulated_patient_care_workflows": "PERMITTED_WITHIN_VALIDATED_SCOPE",
            "direct_patient_care": "PROHIBITED",
            "clinical_decision_support": "PROHIBITED",
            "direct_patient_care_authority_granted": False,
            "errors": sorted(set(errors)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.0.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "checks": checks,
            "direct_patient_care": "PROHIBITED",
            "clinical_decision_support": "PROHIBITED",
            "direct_patient_care_authority_granted": False,
            "errors": sorted(set(errors + [f"{type(exc).__name__}:{exc}"])),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = validate(root)
    write_json(root / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
