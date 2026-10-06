set_option autoImplicit false

namespace ScenarioContracts

/-- Source-governed clinical state. Operational decision orchestration may carry
this projection but does not receive a constructor that can rewrite it. -/
structure DecisionClinicalProjection where
  protectedHash : Nat
  clinicalScore : Int
  deriving DecidableEq, Repr

structure DecisionOperationalProjection where
  elapsedSeconds : Nat
  visibleWorldEventCount : Nat
  completedOrderCount : Nat
  deriving DecidableEq, Repr

structure DecisionIntegrityState where
  clinical : DecisionClinicalProjection
  operational : DecisionOperationalProjection
  deriving DecidableEq, Repr

structure DecisionOperationalPatch where
  elapsedSeconds : Nat
  visibleWorldEventCount : Nat
  completedOrderCount : Nat
  deriving DecidableEq, Repr

/-- Applying an operational patch replaces only the operational projection. -/
def applyDecisionOperationalPatch
    (state : DecisionIntegrityState)
    (patch : DecisionOperationalPatch) : DecisionIntegrityState :=
  {
    clinical := state.clinical
    operational := {
      elapsedSeconds := patch.elapsedSeconds
      visibleWorldEventCount := patch.visibleWorldEventCount
      completedOrderCount := patch.completedOrderCount
    }
  }

theorem decision_operational_transition_preserves_clinical
    (state : DecisionIntegrityState)
    (patch : DecisionOperationalPatch) :
    (applyDecisionOperationalPatch state patch).clinical = state.clinical := rfl

structure DecisionLearnerProjection where
  clinical : DecisionClinicalProjection
  elapsedSeconds : Nat
  observationCount : Nat
  deriving DecidableEq, Repr

/-- Instructor score and provenance are deliberately ignored by the learner
projection. -/
def projectDecisionLearnerView
    (clinical : DecisionClinicalProjection)
    (elapsedSeconds : Nat)
    (observationCount : Nat)
    (_instructorScore : Int)
    (_provenanceHash : Nat) : DecisionLearnerProjection :=
  { clinical := clinical, elapsedSeconds := elapsedSeconds, observationCount := observationCount }

theorem decision_learner_projection_ignores_instructor_score
    (clinical : DecisionClinicalProjection)
    (elapsed observations provenance : Nat)
    (leftScore rightScore : Int) :
    projectDecisionLearnerView clinical elapsed observations leftScore provenance =
      projectDecisionLearnerView clinical elapsed observations rightScore provenance := rfl

theorem decision_learner_projection_ignores_provenance
    (clinical : DecisionClinicalProjection)
    (elapsed observations leftProvenance rightProvenance : Nat)
    (score : Int) :
    projectDecisionLearnerView clinical elapsed observations score leftProvenance =
      projectDecisionLearnerView clinical elapsed observations score rightProvenance := rfl

inductive DecisionTreatmentRuleStatus where
  | notAdjudicated
  | adjudicated
  deriving DecidableEq, Repr

/-- Concrete treatment admission requires an adjudicated rule, provider scope,
patient-specific eligibility, and a source attestation. -/
def decisionConcreteTreatmentAdmitted
    (status : DecisionTreatmentRuleStatus)
    (providerInScope patientEligible sourceAttested : Bool) : Bool :=
  match status with
  | DecisionTreatmentRuleStatus.notAdjudicated => false
  | DecisionTreatmentRuleStatus.adjudicated =>
      providerInScope && patientEligible && sourceAttested

theorem decision_unadjudicated_treatment_is_blocked
    (providerInScope patientEligible sourceAttested : Bool) :
    decisionConcreteTreatmentAdmitted
      DecisionTreatmentRuleStatus.notAdjudicated
      providerInScope patientEligible sourceAttested = false := rfl

theorem decision_missing_scope_blocks_treatment
    (patientEligible sourceAttested : Bool) :
    decisionConcreteTreatmentAdmitted
      DecisionTreatmentRuleStatus.adjudicated
      false patientEligible sourceAttested = false := rfl

theorem decision_missing_eligibility_blocks_treatment
    (sourceAttested : Bool) :
    decisionConcreteTreatmentAdmitted
      DecisionTreatmentRuleStatus.adjudicated
      true false sourceAttested = false := rfl

theorem decision_missing_source_attestation_blocks_treatment :
    decisionConcreteTreatmentAdmitted
      DecisionTreatmentRuleStatus.adjudicated
      true true false = false := rfl

inductive DecisionOrderStatus where
  | absent
  | queued
  | completed
  deriving DecidableEq, Repr

/-- Result visibility is determined by order completion, not by a free-standing
result flag. -/
def decisionResultVisible : DecisionOrderStatus → Bool
  | DecisionOrderStatus.absent => false
  | DecisionOrderStatus.queued => false
  | DecisionOrderStatus.completed => true

theorem decision_absent_order_blocks_result :
    decisionResultVisible DecisionOrderStatus.absent = false := rfl

theorem decision_queued_order_blocks_result :
    decisionResultVisible DecisionOrderStatus.queued = false := rfl

theorem decision_completed_order_allows_result :
    decisionResultVisible DecisionOrderStatus.completed = true := rfl

/-- The second-casualty event is a function of world time. The last learner
action identifier is intentionally ignored. -/
def decisionSecondCasualtyVisible
    (elapsedSeconds : Nat)
    (_lastActionId : Nat) : Bool :=
  decide (240 ≤ elapsedSeconds)

theorem decision_world_event_independent_of_action_identity
    (elapsed leftAction rightAction : Nat) :
    decisionSecondCasualtyVisible elapsed leftAction =
      decisionSecondCasualtyVisible elapsed rightAction := rfl

/-- Responsibility transfers only after the receiver acknowledges, questions are
offered, and the sender confirms shared understanding. -/
def decisionHandoffTransferred
    (receiverAcknowledged questionsOffered senderConfirmed : Bool) : Bool :=
  receiverAcknowledged && questionsOffered && senderConfirmed

theorem decision_handoff_without_ack_is_blocked
    (questionsOffered senderConfirmed : Bool) :
    decisionHandoffTransferred false questionsOffered senderConfirmed = false := rfl

theorem decision_handoff_without_questions_is_blocked
    (senderConfirmed : Bool) :
    decisionHandoffTransferred true false senderConfirmed = false := rfl

theorem decision_handoff_without_sender_confirmation_is_blocked :
    decisionHandoffTransferred true true false = false := rfl

theorem decision_complete_closed_loop_handoff_transfers :
    decisionHandoffTransferred true true true = true := rfl

def replayDecisionOperationalPatches
    (state : DecisionIntegrityState)
    (patches : List DecisionOperationalPatch) : DecisionIntegrityState :=
  match patches with
  | [] => state
  | patch :: rest =>
      replayDecisionOperationalPatches (applyDecisionOperationalPatch state patch) rest

theorem decision_operational_replay_preserves_clinical
    (state : DecisionIntegrityState)
    (patches : List DecisionOperationalPatch) :
    (replayDecisionOperationalPatches state patches).clinical = state.clinical := by
  induction patches generalizing state with
  | nil => rfl
  | cons patch rest inductionHypothesis =>
      exact Eq.trans
        (inductionHypothesis (applyDecisionOperationalPatch state patch))
        (decision_operational_transition_preserves_clinical state patch)

def decisionPatientCareUseAllowed : Bool := false

theorem decision_training_prohibits_patient_care :
    decisionPatientCareUseAllowed = false := rfl

end ScenarioContracts
