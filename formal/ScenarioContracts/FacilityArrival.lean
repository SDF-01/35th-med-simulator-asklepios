set_option autoImplicit false

namespace ScenarioContracts

/-- The clinical projection is source-governed. Operational orchestration may
carry it, but has no constructor that can rewrite its fields. -/
structure FacilityClinicalProjection where
  protectedHash : Nat
  clinicalScore : Int
  deriving DecidableEq, Repr

structure FacilityOperationalProjection where
  elapsedSeconds : Nat
  diagnosticsReady : Bool
  witObservationCount : Nat
  deriving DecidableEq, Repr

structure FacilityArrivalState where
  clinical : FacilityClinicalProjection
  operational : FacilityOperationalProjection
  deriving DecidableEq, Repr

structure FacilityOperationalPatch where
  elapsedSeconds : Nat
  diagnosticsReady : Bool
  deriving DecidableEq, Repr

/-- Operational patches replace only the operational projection. -/
def applyFacilityOperationalPatch
    (state : FacilityArrivalState)
    (patch : FacilityOperationalPatch) : FacilityArrivalState :=
  {
    clinical := state.clinical
    operational := {
      elapsedSeconds := patch.elapsedSeconds
      diagnosticsReady := patch.diagnosticsReady
      witObservationCount := state.operational.witObservationCount
    }
  }

theorem facility_operational_transition_preserves_clinical
    (state : FacilityArrivalState)
    (patch : FacilityOperationalPatch) :
    (applyFacilityOperationalPatch state patch).clinical = state.clinical := rfl

inductive FacilityActionKind where
  | sourceClinical (binding : Nat) (points : Int)
  | operational
  deriving DecidableEq, Repr

def facilitySourceBinding : FacilityActionKind → Option Nat
  | FacilityActionKind.sourceClinical binding _ => some binding
  | FacilityActionKind.operational => none

def facilityClinicalPoints : FacilityActionKind → Int
  | FacilityActionKind.sourceClinical _ points => points
  | FacilityActionKind.operational => 0

theorem facility_operational_action_has_no_source_binding :
    facilitySourceBinding FacilityActionKind.operational = none := rfl

theorem facility_operational_action_has_zero_clinical_points :
    facilityClinicalPoints FacilityActionKind.operational = 0 := rfl

structure FacilityWitObservation where
  messageId : Nat
  deriving DecidableEq, Repr

/-- The WIT operation records a process observation without receiving a clinical
projection or clinical directive field. -/
def applyFacilityWitObservation
    (state : FacilityArrivalState)
    (_observation : FacilityWitObservation) : FacilityArrivalState :=
  {
    clinical := state.clinical
    operational := {
      state.operational with
      witObservationCount := state.operational.witObservationCount + 1
    }
  }

def facilityWitClinicalDirectiveAllowed (_observation : FacilityWitObservation) : Bool := false

theorem facility_wit_transition_preserves_clinical_score
    (state : FacilityArrivalState)
    (observation : FacilityWitObservation) :
    (applyFacilityWitObservation state observation).clinical.clinicalScore =
      state.clinical.clinicalScore := rfl

theorem facility_wit_observation_has_no_clinical_directive
    (observation : FacilityWitObservation) :
    facilityWitClinicalDirectiveAllowed observation = false := rfl

def facilityVisibleHiddenFindings
    (diagnosticsReady : Bool)
    (hiddenFindings : List Nat) : List Nat :=
  if diagnosticsReady then hiddenFindings else []

theorem facility_hidden_findings_before_diagnostics_are_empty
    (hiddenFindings : List Nat) :
    facilityVisibleHiddenFindings false hiddenFindings = [] := rfl

theorem facility_diagnostics_ready_reveals_exact_hidden_findings
    (hiddenFindings : List Nat) :
    facilityVisibleHiddenFindings true hiddenFindings = hiddenFindings := rfl

inductive FacilityTerminalStatus where
  | active
  | completed
  | failed
  | timeout
  deriving DecidableEq, Repr

inductive FacilityTerminalEvent where
  | ordinary
  | timeoutReached
  | unsafeSourceAction
  | receivingHandoffCompleted
  deriving DecidableEq, Repr

def applyFacilityTerminalEvent
    (current : FacilityTerminalStatus)
    (event : FacilityTerminalEvent) : FacilityTerminalStatus :=
  match event with
  | FacilityTerminalEvent.ordinary => current
  | FacilityTerminalEvent.timeoutReached => FacilityTerminalStatus.timeout
  | FacilityTerminalEvent.unsafeSourceAction => FacilityTerminalStatus.failed
  | FacilityTerminalEvent.receivingHandoffCompleted => FacilityTerminalStatus.completed

theorem facility_timeout_event_maps_to_timeout_terminal
    (current : FacilityTerminalStatus) :
    applyFacilityTerminalEvent current FacilityTerminalEvent.timeoutReached =
      FacilityTerminalStatus.timeout := rfl

theorem facility_unsafe_event_maps_to_failed_terminal
    (current : FacilityTerminalStatus) :
    applyFacilityTerminalEvent current FacilityTerminalEvent.unsafeSourceAction =
      FacilityTerminalStatus.failed := rfl

theorem facility_handoff_event_maps_to_completed_terminal
    (current : FacilityTerminalStatus) :
    applyFacilityTerminalEvent current FacilityTerminalEvent.receivingHandoffCompleted =
      FacilityTerminalStatus.completed := rfl

def facilityPatientCareUseAllowed : Bool := false

theorem facility_production_training_prohibits_patient_care :
    facilityPatientCareUseAllowed = false := rfl

def replayFacilityOperationalPatches
    (state : FacilityArrivalState)
    (patches : List FacilityOperationalPatch) : FacilityArrivalState :=
  match patches with
  | [] => state
  | patch :: rest => replayFacilityOperationalPatches (applyFacilityOperationalPatch state patch) rest

theorem facility_operational_replay_preserves_clinical
    (state : FacilityArrivalState)
    (patches : List FacilityOperationalPatch) :
    (replayFacilityOperationalPatches state patches).clinical = state.clinical := by
  induction patches generalizing state with
  | nil => rfl
  | cons patch rest inductionHypothesis =>
      exact Eq.trans
        (inductionHypothesis (applyFacilityOperationalPatch state patch))
        (facility_operational_transition_preserves_clinical state patch)

end ScenarioContracts
