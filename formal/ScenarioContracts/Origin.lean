set_option autoImplicit false

namespace ScenarioContracts

structure FieldOrigin where
  fieldId : Nat
  sourceId : Nat
  deriving DecidableEq, Repr

def Covers (fields : List Nat) (origins : List FieldOrigin) : Prop :=
  ∀ field ∈ fields, ∃ origin ∈ origins, origin.fieldId = field

theorem covers_append
    {left right : List Nat} {origins : List FieldOrigin}
    (leftCovered : Covers left origins)
    (rightCovered : Covers right origins) :
    Covers (left ++ right) origins := by
  intro field member
  rcases List.mem_append.mp member with memberLeft | memberRight
  · exact leftCovered field memberLeft
  · exact rightCovered field memberRight

theorem covers_subset
    {small large : List Nat} {origins : List FieldOrigin}
    (covered : Covers large origins)
    (subset : ∀ field, field ∈ small → field ∈ large) :
    Covers small origins := by
  intro field member
  exact covered field (subset field member)

end ScenarioContracts
