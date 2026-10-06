set_option autoImplicit false

namespace ScenarioContracts

/-- A canonical finite route contains stages `0` through `n`. -/
def canonicalRoute (n : Nat) : List Nat := List.range (n + 1)

@[simp] theorem route_contains_start (n : Nat) : 0 ∈ canonicalRoute n := by
  simp [canonicalRoute]

@[simp] theorem route_contains_terminal (n : Nat) : n ∈ canonicalRoute n := by
  simp [canonicalRoute]

/-- Extending a route keeps every previously reachable stage. -/
theorem route_extension_preserves_membership
    {n value : Nat}
    (member : value ∈ canonicalRoute n) :
    value ∈ canonicalRoute (n + 1) := by
  simp [canonicalRoute] at member ⊢
  exact Nat.lt_trans member (Nat.lt_succ_self (n + 1))

end ScenarioContracts
