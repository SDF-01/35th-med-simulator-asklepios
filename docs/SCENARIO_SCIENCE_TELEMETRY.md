# Scenario Science Telemetry v1

This vertical slice introduces a privacy-bounded, append-only telemetry contract for future timing calibration and psychometric scoring research.

## Current authority boundary

The telemetry is for healthcare simulation research only. It does not grant direct-patient-care authority, clinical decision support, treatment authority, or clinical timing calibration.

## Deterministic event chain

Each event records a contiguous sequence number, monotonic simulation logical time, state-before and state-after hashes, calibration use, scoring effect, previous-event hash, and its own event hash.

The event digest is:

```text
SHA-256(previous_event_sha256 + "\n" + canonical_event_without_event_sha256)
```

The run root hashes the ordered event-hash list. A changed, removed, reordered, or inserted event invalidates the chain.

## Privacy boundary

The canonical telemetry forbids direct identity fields including names, dates of birth, medical record numbers, street addresses, email addresses, phone numbers, and free-text patient identifiers. Sessions use non-personal pseudonyms.

## Timing and scoring boundary

Exercise-design timing may be recorded but cannot change a learner score while it remains uncalibrated. Timing can affect scoring only after the individual parameter reaches `CALIBRATED_FOR_DECLARED_SCOPE` through the declared state ladder.

A statistical or psychometric score can never override a deterministic critical-safety failure.

## Independent implementations

- Python constructs and verifies the canonical reference artifact.
- Node.js independently reconstructs policy floors, privacy rules, event chaining, Genome binding, and truth boundaries using only standard-library modules.

## Current tests

The mutation suite rejects PHI insertion, sequence gaps, logical-time regression, previous-hash and event-hash forgery, unknown event kinds, uncalibrated timing score effects, authority escalation, calibration and scoring ladder shortcuts, safety override, cosmetic novelty promotion, missing terminal events, duplicate event IDs, Genome binding forgery, and event-root forgery.
