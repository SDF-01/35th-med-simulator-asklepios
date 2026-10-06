# Facility Decision Integrity validity boundaries

This ledger prevents a software-assurance result from being misrepresented as clinical, empirical, causal, accessibility, or deployment validation.

The source of truth is [`config/facility-decision/VALIDITY_BOUNDARIES.json`](../config/facility-decision/VALIDITY_BOUNDARIES.json). Every domain contains:

- the strongest statement currently allowed;
- statements that remain forbidden;
- evidence required before the boundary may be promoted.

## Current boundary

The engine currently demonstrates deterministic decision orchestration, order/result causality, finite resource queues, role-specific projections, closed-loop handoff state, authenticated replay, sampled executable differential checks, and narrow formal noninterference properties.

It does not currently demonstrate empirically calibrated operational distributions, concrete treatment legitimacy, calibrated human-team policies, validated dynamic physiology, atomic claim entailment, causally identified AAR conclusions, full executable-to-formal refinement, WCAG conformance, or signed production provenance.

## Promotion rule

A status may be promoted only when all declared activation requirements have independently verifiable evidence. Editing the status or removing a requirement is a release failure. An implementation may improve while the status remains unchanged; the boundary moves only when the stronger claim is supportable.

## Non-circular release rule

The producer of a model, scenario, report, or attestation cannot be its sole verifier. A checker crash is an internal error, not a successful rejection. A `PASS` field is insufficient: final validation recomputes critical bindings from current files.
