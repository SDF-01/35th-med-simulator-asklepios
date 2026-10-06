# Facility Arrival standalone offline scenario — RC3.8A.1

`examples/facility-arrival/playable.html` is the single-file offline reference for the canonical post-CUF/TFC receiving-clinic scenario. It is bound to the current Scenario Genome, capability ratchet, technical-debt ratchet, release graph, generated manifests, and versioned offline-release descriptor.

## Runtime boundary

The file embeds its CSS, JavaScript state machine, scenario specification, source snapshot, scope references, provenance hashes, WIT process view, alternate branches, and after-action review. It does not load a package, contact an API, use a WebSocket, or require a local server. Its Content Security Policy blocks outbound connections, and independent checkers reject external runtime assets or executable network APIs.

Open it by downloading the file and double-clicking it. On Linux:

```bash
xdg-open examples/facility-arrival/playable.html
```

## Verified behaviors

- hidden source findings remain unavailable before `diagnostics_ready`;
- source-template actions alone contribute clinical points;
- operational workflow and WIT observations contribute zero clinical points;
- unsafe discharge and unsafe tourniquet branches fail closed;
- repeated waiting reaches the source-bound timeout exactly;
- canonical and alternate valid orders are deterministic;
- the completed canonical replay scores 10,000 basis points and reaches handoff;
- every WIT observation remains process-only with no clinical directive;
- the learner UI, autoplay, WIT tab, provenance tab, run export, and AAR are exercised by an independent minimal-DOM test;
- the embedded release identity matches the current Scenario Genome, both ratchets, and canonical release graph;
- the repository README, generated manifests, and offline descriptor are hash-bound to the same release.

## Rebuild and challenge

```bash
npm run generate:facility-arrival
npm run generate:facility-arrival-standalone
npm run verify:facility-arrival-standalone
npm run generate:offline-scenario-release
npm run verify:offline-scenario-release
npm run verify:engine-evolution-docs
```

## Limits

This is a healthcare-simulation training reference, not patient-care software. Clinical content is inherited from `ASK-D-001`. Diagnostic timing and the passing threshold remain exercise-design assumptions marked `NOT_CALIBRATED`. The Scenario Genome proves structural identity and provenance; it does not establish clinical correctness, empirical human behavior, dynamic physiology, treatment effect, psychometric validity, or causal outcome attribution.

<!-- asklepios-offline-evolution:start -->
## Engine evolution and reproducibility boundary

The canonical offline artifact is bound to **RC3.8A.1** (`ASK-OFFLINE-RC3.8A.1`) and `SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8`.

- Scenario Genome: `ASK-GENOME-528E11A5CC61EE45` (`53b695595dd7d053cac1468992db51cb5519d4761a6cf644a895ee008e2fe8ff`)
- Capability ratchet: `asklepios-scenario-capability-ratchet-v1`, epoch `5` (`870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e`)
- Technical-debt ratchet: `asklepios-technical-debt-ratchet-v1`, epoch `8` (`84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91`)
- Release graph: `asklepios-rc3.8a.1-scenario-science-stakeholder-graph` with `122` stages and `26` targets
- Release-identity DAG: `ACYCLIC_SEMANTIC_PROJECTION_V1` contract `0f202ff8af5bacd6817f93443e1d8cf4573524f4c676e9d1701d9c50b783fb8e`
- Canonical writer: `scripts/build_facility_arrival_standalone.py`
- Independent verifier: `scripts/check_facility_arrival_standalone.py`
- Offline release writer: `scripts/build_offline_scenario_release.py`
- Independent offline verifier: `scripts/check_offline_scenario_release.mjs`

The single-file artifact has no external runtime asset, server, API, WebSocket, or network request. Its content-security policy includes `connect-src 'none'`. The embedded simulation clock is deterministic and reproducible; it is not an empirically calibrated real-clinical workflow clock.

Behavioral quality-diversity is structural and deterministic: 107 unique behavior signatures occupy all 30 observed cells. Narrative-only and provenance-only changes do not create new behavior, and the integer quality vector is restricted to scenario selection rather than learner scoring.

Behavioral policy diversity distinguishes four genuinely different coordination policies. The operational scenario pack contains 12 reviewed scenarios, balanced three per policy profile.

### Four playable offline role-model teamwork challenges

The standalone page itself exposes **Direct handoff baseline**, **Communications relay**, **Resource coordination**, and **Relay and resource coordination**. The user can select any challenge and complete it manually, replay the canonical route immediately, or watch the deterministic autoplay. Added relay and resource actions are operational only, carry zero clinical points, and do not claim calibrated human timing.

The source-conformance scorecard preserves hard safety failure and reports insufficient evidence rather than fabricated proficiency. The treatment-admission pipeline tracks two discovered concepts, but zero are simulation-admitted and zero active learner treatment choices exist. Plain-language release translation is required for every release.

A release report is not accepted merely because it says `PASS`. Evidence consumers authenticate the current release graph, stage configuration, source inputs, output inventory, output hashes, and receipt chain. The offline descriptor uses an acyclic semantic graph projection instead of a raw graph-file digest, and capability and technical-debt floors are monotonic across ratchet epochs.

This boundary demonstrates software integrity and simulation behavior only. It does not establish clinical certification, treatment authority, dynamic physiology, causal effect, human-team calibration, psychometric validity, or suitability for direct patient care.
<!-- asklepios-offline-evolution:end -->
