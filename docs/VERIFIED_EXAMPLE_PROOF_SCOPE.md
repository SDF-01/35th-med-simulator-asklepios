# Canonical verified example: proof and validity scope

This release adds a human-readable, repository-root entry point for the existing template-locked scenario package. It does not create a new clinical template, new scoring rule, or new clinical claim.

## Demonstrated by the release

- The example binds to the existing verified scenario package by path, raw-file SHA-256, and package certificate SHA-256.
- The source scenario resolves to a protected-template asset in the content registry.
- The base and output protected-clinical hashes are identical.
- Every example citation resolves to an evidence asset, research-source asset, and identity-only attestation in the registry.
- Citation DOI, locator, chunk hash, and source-file hash agree across the scenario package and registry.
- Evidence remains `REFERENCE_ONLY`, `NOT_ADJUDICATED`, `NOT_SEARCHED`, and `NOT_REVIEWED`.
- The example remains `NOT_GRANTED`, `supporting_only`, and `research_sandbox_only`.
- The README link, generated Markdown, machine manifest, and source bindings are independently checked in Python and Node.
- Rehashed semantic forgeries are rejected by the independent checker.

## Not demonstrated

- Clinical correctness or certification of the inherited source template.
- Claim-level entailment from article span to scenario field.
- Exhaustive contradiction or supersession review.
- Real-world frequency calibration.
- Human-behavior calibration or learner effectiveness.
- End-to-end executable refinement into Lean semantics.
- Acceptance by a second independently implemented proof kernel.
- Production or operational suitability.

## Why no new Lean theorem is added

The example does not introduce a new authority transformation. It is a deterministic view over artifacts already governed by the scenario-contract and content-registry formal boundaries. Adding a new theorem only to restate file equality would increase the trusted surface without proving a new semantic property.

The existing Lean contracts remain mandatory in CI because this pull request targets `main` and therefore runs the scenario-contract and content-registry formal workflows. This release adds independent executable verification for the new documentation and binding layer.

## Next gate

The next release should compile compatibility-approved registry profiles into additional deterministic scenario specifications. Activation remains prohibited until a profile has complete field origins, independently verified compilation, explicit authority preservation, and human review. Evidence-dependent claims must remain blocked until claim-level entailment and contradiction review are complete.
