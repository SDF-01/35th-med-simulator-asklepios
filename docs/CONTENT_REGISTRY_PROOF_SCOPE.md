# Content registry formal proof scope

The mechanized module proves narrow structural properties:

- generated operational content and supporting evidence deny clinical-rule, scoring-truth, and physiology capabilities;
- admitted claims carry explicit identity, entailment, contradiction, human-review, and authority witnesses;
- admitted imports carry integrity, public-boundary, authority, reference-resolution, and staging witnesses;
- staged content is not active;
- activated content carries compatibility, independent-check, human-review, and authority-preservation witnesses.

## RC3.1.2 definitional authority model

RC3.1 used `simp` for finite list non-membership and RC3.1.1 replaced it with `by decide`. The live Lean audits showed that both encodings still reported `propext` for the same five theorems. The trust budget is not widened.

RC3.1.2 changes the model instead of trying another tactic over the same proposition:

- each authority class is an exhaustive total `RegistryCapability → Bool` function;
- all eleven capability constructors have explicit branches;
- there is no wildcard branch;
- the allowed positive cases are explicit compile-time canaries;
- the five protected denials reduce definitionally to `false = false` and are proved by `rfl`.

The explicit truth table is fail-closed for maintenance: adding a new capability constructor makes Lean reject the non-exhaustive policies until both are reviewed. The static preflight also rejects missing constructors, wildcard branches, bit flips, weakened theorem statements, tactic regressions, comment spoofing, proof holes, and trust-manifest widening.

## Exact trust policy

The release requires:

- exactly 22 audited theorem declarations;
- an independently encoded empty axiom budget for every theorem;
- rejection of missing, duplicate, unexpected, malformed, or widened audit entries;
- no `sorry` or `admit`;
- a focused Lean build and `#print axioms` probe before the expensive registry and npm suites;
- a complete Lean kernel build and fresh `leanchecker` replay before publication.

The manifest cannot authorize a wider budget by changing itself because the independent checker separately hard-codes the exact theorem inventory and zero-axiom policy.

## Deliberate limits

These theorems do not prove clinical correctness, citation entailment, real-world calibration, human-performance validity, or executable-to-Lean refinement. The release remains research-sandbox-only, supporting-evidence-only, and non-activating.
