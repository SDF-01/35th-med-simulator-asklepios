set_option autoImplicit false

namespace ScenarioContracts

inductive RegistryCapability where
  | catalogDisplay
  | preserveExistingContent
  | operationalContext
  | routing
  | learnerPrompt
  | citationReference
  | aarDiscussion
  | inheritedTemplateResearchSandbox
  | defineNewClinicalRule
  | defineScoringTruth
  | definePhysiology
  deriving DecidableEq, Repr

/-- A total, closed-world authority policy. Every capability constructor must be
handled explicitly, so adding a new capability forces this module to be reviewed. -/
abbrev CapabilityPolicy := RegistryCapability → Bool

def generatedOperationalCapabilities : CapabilityPolicy
  | RegistryCapability.catalogDisplay => true
  | RegistryCapability.preserveExistingContent => false
  | RegistryCapability.operationalContext => true
  | RegistryCapability.routing => true
  | RegistryCapability.learnerPrompt => true
  | RegistryCapability.citationReference => false
  | RegistryCapability.aarDiscussion => false
  | RegistryCapability.inheritedTemplateResearchSandbox => false
  | RegistryCapability.defineNewClinicalRule => false
  | RegistryCapability.defineScoringTruth => false
  | RegistryCapability.definePhysiology => false

def supportingEvidenceCapabilities : CapabilityPolicy
  | RegistryCapability.catalogDisplay => true
  | RegistryCapability.preserveExistingContent => false
  | RegistryCapability.operationalContext => false
  | RegistryCapability.routing => false
  | RegistryCapability.learnerPrompt => false
  | RegistryCapability.citationReference => true
  | RegistryCapability.aarDiscussion => true
  | RegistryCapability.inheritedTemplateResearchSandbox => false
  | RegistryCapability.defineNewClinicalRule => false
  | RegistryCapability.defineScoringTruth => false
  | RegistryCapability.definePhysiology => false

/-- These are definitional equalities. Their proof terms reduce to `Eq.refl`; no
proposition rewriting, decision tactic, native evaluator, or compiler-trust axiom
is involved. -/
theorem generated_content_cannot_define_clinical_rule :
    generatedOperationalCapabilities RegistryCapability.defineNewClinicalRule = false := rfl

theorem generated_content_cannot_define_scoring_truth :
    generatedOperationalCapabilities RegistryCapability.defineScoringTruth = false := rfl

theorem generated_content_cannot_define_physiology :
    generatedOperationalCapabilities RegistryCapability.definePhysiology = false := rfl

theorem supporting_evidence_cannot_define_clinical_rule :
    supportingEvidenceCapabilities RegistryCapability.defineNewClinicalRule = false := rfl

theorem supporting_evidence_cannot_define_scoring_truth :
    supportingEvidenceCapabilities RegistryCapability.defineScoringTruth = false := rfl

-- Compile-time positive canaries prevent an accidental all-deny policy.
example : generatedOperationalCapabilities RegistryCapability.catalogDisplay = true := rfl
example : generatedOperationalCapabilities RegistryCapability.operationalContext = true := rfl
example : generatedOperationalCapabilities RegistryCapability.routing = true := rfl
example : generatedOperationalCapabilities RegistryCapability.learnerPrompt = true := rfl
example : supportingEvidenceCapabilities RegistryCapability.citationReference = true := rfl
example : supportingEvidenceCapabilities RegistryCapability.aarDiscussion = true := rfl

def CapabilityIncluded (left right : CapabilityPolicy) : Prop :=
  ∀ capability, left capability = true → right capability = true

theorem capability_inclusion_reflexive (capabilities : CapabilityPolicy) :
    CapabilityIncluded capabilities capabilities := by
  intro capability member
  exact member

theorem capability_inclusion_transitive
    {first second third : CapabilityPolicy}
    (firstSecond : CapabilityIncluded first second)
    (secondThird : CapabilityIncluded second third) :
    CapabilityIncluded first third := by
  intro capability member
  exact secondThird capability (firstSecond capability member)

structure ClaimRecord where
  identityVerified : Bool
  entailmentVerified : Bool
  contradictionClear : Bool
  humanReviewed : Bool
  authorityPermitted : Bool
  deriving DecidableEq, Repr

structure AdmittedClaim (claim : ClaimRecord) : Type where
  identityWitness : claim.identityVerified = true
  entailmentWitness : claim.entailmentVerified = true
  contradictionWitness : claim.contradictionClear = true
  humanReviewWitness : claim.humanReviewed = true
  authorityWitness : claim.authorityPermitted = true

theorem admitted_claim_has_identity
    {claim : ClaimRecord} (accepted : AdmittedClaim claim) :
    claim.identityVerified = true := by
  exact accepted.identityWitness

theorem admitted_claim_has_entailment
    {claim : ClaimRecord} (accepted : AdmittedClaim claim) :
    claim.entailmentVerified = true := by
  exact accepted.entailmentWitness

theorem admitted_claim_has_contradiction_clearance
    {claim : ClaimRecord} (accepted : AdmittedClaim claim) :
    claim.contradictionClear = true := by
  exact accepted.contradictionWitness

theorem admitted_claim_has_human_review
    {claim : ClaimRecord} (accepted : AdmittedClaim claim) :
    claim.humanReviewed = true := by
  exact accepted.humanReviewWitness

theorem admitted_claim_has_authority_permission
    {claim : ClaimRecord} (accepted : AdmittedClaim claim) :
    claim.authorityPermitted = true := by
  exact accepted.authorityWitness

structure ImportRecord where
  integrityVerified : Bool
  publicBoundaryClear : Bool
  authorityPreserved : Bool
  referencesResolved : Bool
  stagingOnly : Bool
  deriving DecidableEq, Repr

structure AdmittedImport (record : ImportRecord) : Type where
  integrityWitness : record.integrityVerified = true
  publicBoundaryWitness : record.publicBoundaryClear = true
  authorityWitness : record.authorityPreserved = true
  referenceWitness : record.referencesResolved = true
  stagingWitness : record.stagingOnly = true

theorem admitted_import_has_integrity
    {record : ImportRecord} (accepted : AdmittedImport record) :
    record.integrityVerified = true := by
  exact accepted.integrityWitness

theorem admitted_import_clears_public_boundary
    {record : ImportRecord} (accepted : AdmittedImport record) :
    record.publicBoundaryClear = true := by
  exact accepted.publicBoundaryWitness

theorem admitted_import_preserves_authority
    {record : ImportRecord} (accepted : AdmittedImport record) :
    record.authorityPreserved = true := by
  exact accepted.authorityWitness

theorem admitted_import_resolves_references
    {record : ImportRecord} (accepted : AdmittedImport record) :
    record.referencesResolved = true := by
  exact accepted.referenceWitness

theorem admitted_import_is_staging_only
    {record : ImportRecord} (accepted : AdmittedImport record) :
    record.stagingOnly = true := by
  exact accepted.stagingWitness

structure StagedContent where
  active : Bool
  inactiveWitness : active = false

theorem staged_content_cannot_activate (content : StagedContent) :
    content.active = false := by
  exact content.inactiveWitness

structure ActivationRecord where
  compatibilityVerified : Bool
  independentlyChecked : Bool
  humanReviewed : Bool
  authorityPreserved : Bool
  deriving DecidableEq, Repr

structure ActivatedContent (record : ActivationRecord) : Type where
  compatibilityWitness : record.compatibilityVerified = true
  independentCheckWitness : record.independentlyChecked = true
  humanReviewWitness : record.humanReviewed = true
  authorityWitness : record.authorityPreserved = true

theorem activated_content_has_compatibility
    {record : ActivationRecord} (accepted : ActivatedContent record) :
    record.compatibilityVerified = true := by
  exact accepted.compatibilityWitness

theorem activated_content_has_independent_check
    {record : ActivationRecord} (accepted : ActivatedContent record) :
    record.independentlyChecked = true := by
  exact accepted.independentCheckWitness

theorem activated_content_has_human_review
    {record : ActivationRecord} (accepted : ActivatedContent record) :
    record.humanReviewed = true := by
  exact accepted.humanReviewWitness

theorem activated_content_preserves_authority
    {record : ActivationRecord} (accepted : ActivatedContent record) :
    record.authorityPreserved = true := by
  exact accepted.authorityWitness

end ScenarioContracts
