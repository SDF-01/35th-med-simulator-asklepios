# Scenario package provenance

A verified scenario package is a content-addressed derivation record rather than an untraceable generated object.

## Source bindings

Every package records:

- reviewed source scenario ID and SHA-256;
- protected-field SHA-256 before and after generation;
- evidence-database SHA-256;
- normalized public-bridge SHA-256;
- selected research prototype ID, declared hash, and complete record hash;
- blueprint ID, version, and SHA-256.

## Evidence bindings

Citation records carry:

- evidence ID;
- source ID;
- title, journal, DOI, and publication date;
- section locator;
- source-file SHA-256;
- evidence-unit SHA-256.

Research evidence remains supporting-only. It may help select an operational topic and provide after-action references, but it cannot define clinical actions, scoring, medication doses, provider scope, or physiology.

## Atoms and field origins

The generator reduces each permitted choice to a typed atom. Atoms identify their source kind, evidence relationships, authority, and hash. A Merkle root commits to the complete atom set.

Every changed field has an origin record that points to the atoms and evidence IDs that explain it. This provides field-level traceability without bundling licensed article text into the application.

## Independent checking

The project intentionally separates construction from checking:

- the generator and local validator share the application type system;
- a second TypeScript checker independently implements canonical encoding, hashing, route inspection, and package validation;
- a small Python checker independently validates the released JSON artifact;
- Lean declarations prove abstract preservation properties, and CI also invokes an external Lean type checker with incomplete proofs forbidden.

Passing these checks means that the package satisfies the declared software contract. It does not mean that the underlying source template has been clinically approved for operational use.
