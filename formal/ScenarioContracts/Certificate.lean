set_option autoImplicit false

namespace ScenarioContracts

structure CertificateFlags where
  protectedFieldsUnchanged : Bool
  routeReachable : Bool
  routeHasNoDeadEnd : Bool
  originsComplete : Bool
  evidenceScopePreserved : Bool
  stageChainValid : Bool
  stagePayloadsValid : Bool
  deriving DecidableEq, Repr

def Accepted (flags : CertificateFlags) : Prop :=
  flags.protectedFieldsUnchanged = true ∧
  flags.routeReachable = true ∧
  flags.routeHasNoDeadEnd = true ∧
  flags.originsComplete = true ∧
  flags.evidenceScopePreserved = true ∧
  flags.stageChainValid = true ∧
  flags.stagePayloadsValid = true

theorem accepted_protects_fields
    {flags : CertificateFlags} (accepted : Accepted flags) :
    flags.protectedFieldsUnchanged = true := by
  exact accepted.1

theorem accepted_has_route
    {flags : CertificateFlags} (accepted : Accepted flags) :
    flags.routeReachable = true ∧ flags.routeHasNoDeadEnd = true := by
  exact ⟨accepted.2.1, accepted.2.2.1⟩

theorem accepted_has_origins
    {flags : CertificateFlags} (accepted : Accepted flags) :
    flags.originsComplete = true := by
  exact accepted.2.2.2.1

theorem accepted_has_valid_stage_payloads
    {flags : CertificateFlags} (accepted : Accepted flags) :
    flags.stagePayloadsValid = true := by
  exact accepted.2.2.2.2.2.2

end ScenarioContracts
