# Technical-debt ratchet

Project Asklepios does not claim that software can be proven absolutely free of undiscovered defects. The permitted release statement is narrower:

> No known release-blocking technical debt remains within the machine-checked scope and current authenticated evidence.

The technical-debt ratchet prevents that scoped claim from being obtained by deleting, reopening, reclassifying, or weakening previously reviewed debt records.

## Two independent floors

The ratchet is represented twice:

1. `config/release/TECHNICAL_DEBT_RATCHET.json` is the reviewed machine-readable policy.
2. `scripts/check_technical_debt_ratchet.py` contains an independently compiled floor and anchor.

Rewriting the JSON policy and recomputing its self-hash is therefore insufficient. The compiled floor must also be deliberately advanced in a reviewed ratchet epoch.

## Protected properties

The checker requires:

- the complete reviewed debt-ID inventory;
- the exact state and release-blocker classification for every entry;
- the minimum evidence-stage set for every entry;
- the complete final receipt inventory;
- current graph and output-hash binding;
- rejection of stale committed evidence;
- the exact terminal evidence stage;
- zero accepted risks in the current epoch;
- prohibition of an absolute debt-free claim.

New debt cannot be hidden by omitting it from the register. A new or changed entry requires an explicit ratchet-epoch update, new evidence, and adversarial regression coverage.

## Current epoch

The current reviewed ratchet epoch is **4**.  It protects:

- 15 reviewed debt records;
- 26 required final stage receipts;
- zero accepted risks;
- the final terminal evidence stage `final.decision-evidence`;
- the behavioral quality-diversity closure record
  `TD-BEHAVIOR-ARCHIVE-015`;
- the archive generation, independent checking, archive attacks, capability
  ratchet, and Scenario Evolution evidence chain.

The behavior-archive closure prevents cosmetic scenario variation from being
represented as genuine behavioral diversity and prevents the archive quality
vector from being reused as a learner or clinical score.

## Release ordering

```text
Hub and source-security assurance
        ↓
Technical-debt ratchet
        ↓
Technical-debt ratchet attacks
        ↓
Technical-debt source-policy validation
        ↓
Technical-debt policy attacks
        ↓
Runtime, formal, timing, build, and scenario evidence
        ↓
Final authenticated debt-evidence join
```

The final join authenticates stage receipts, the current graph hash, current input hashes, and current output hashes. A copied `PASS` report cannot satisfy the gate.

## Truth boundary

This ratchet protects engineering evidence and known-debt accounting. It does not establish clinical correctness, operational calibration, human-behavior calibration, dynamic patient physiology, psychometric validity, or direct patient-care authority.
