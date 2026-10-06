set_option autoImplicit false

namespace ScenarioContracts

inductive EvidenceClass where
  | supporting
  | template
  | nonclinical
  deriving DecidableEq, Repr

structure ClinicalView where
  protectedHash : String
  scoringEnabled : Bool
  actionCount : Nat
  deriving DecidableEq, Repr

structure ContextView where
  title : String
  narrative : String
  routeHash : String
  deriving DecidableEq, Repr

structure ScenarioState where
  clinical : ClinicalView
  context : ContextView
  deriving DecidableEq, Repr

structure ContextOverlay where
  title : String
  narrative : String
  routeHash : String
  deriving DecidableEq, Repr

/-- An operational overlay can replace contextual fields but has no constructor
    access to the inherited clinical value. -/
def applyOverlay (base : ScenarioState) (overlay : ContextOverlay) : ScenarioState :=
  { clinical := base.clinical
    context :=
      { title := overlay.title
        narrative := overlay.narrative
        routeHash := overlay.routeHash } }

@[simp] theorem overlay_preserves_protected
    (base : ScenarioState) (overlay : ContextOverlay) :
    (applyOverlay base overlay).clinical.protectedHash = base.clinical.protectedHash := by
  rfl

@[simp] theorem overlay_preserves_scoring
    (base : ScenarioState) (overlay : ContextOverlay) :
    (applyOverlay base overlay).clinical.scoringEnabled = base.clinical.scoringEnabled := by
  rfl

@[simp] theorem overlay_preserves_actions
    (base : ScenarioState) (overlay : ContextOverlay) :
    (applyOverlay base overlay).clinical.actionCount = base.clinical.actionCount := by
  rfl

structure EvidenceRef where
  evidenceClass : EvidenceClass
  identifier : String
  deriving DecidableEq, Repr

def supportingOnly (refs : List EvidenceRef) : Prop :=
  ∀ ref ∈ refs, ref.evidenceClass = EvidenceClass.supporting

/-- Supporting references can justify contextual selection, but the constructor
    still returns the inherited clinical value unchanged. -/
def applySupporting
    (base : ScenarioState) (overlay : ContextOverlay) (_refs : List EvidenceRef) :
    ScenarioState :=
  applyOverlay base overlay

@[simp] theorem supporting_overlay_preserves_protected
    (base : ScenarioState) (overlay : ContextOverlay) (refs : List EvidenceRef)
    (_safe : supportingOnly refs) :
    (applySupporting base overlay refs).clinical.protectedHash =
      base.clinical.protectedHash := by
  rfl

@[simp] theorem supporting_overlay_preserves_scoring
    (base : ScenarioState) (overlay : ContextOverlay) (refs : List EvidenceRef)
    (_safe : supportingOnly refs) :
    (applySupporting base overlay refs).clinical.scoringEnabled =
      base.clinical.scoringEnabled := by
  rfl

end ScenarioContracts
