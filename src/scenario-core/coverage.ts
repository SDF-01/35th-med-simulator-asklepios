import { canonicalJson, sha256Canonical } from './hash';

export type FactorValues = Record<string, readonly string[]>;
export type FactorAssignment = Record<string, string>;
export type CoverageStrength = 2 | 3;
export type ConstraintValue = string | readonly string[];

interface ConstraintBase {
  constraint_id: string;
  reason: string;
}

/** Reject an assignment whenever every field in `when` has one of the listed values. */
export interface ForbidFactorConstraint extends ConstraintBase {
  kind: 'forbid';
  when: Record<string, ConstraintValue>;
}

/** When `when` matches, every field in `then` must have one of the listed values. */
export interface RequireFactorConstraint extends ConstraintBase {
  kind: 'require';
  when: Record<string, ConstraintValue>;
  then: Record<string, ConstraintValue>;
}

export type FactorConstraint = ForbidFactorConstraint | RequireFactorConstraint;

export interface CoverageOptions {
  strength?: CoverageStrength;
  constraints?: readonly FactorConstraint[];
  max_cartesian_assignments?: number;
  max_constraint_evaluations?: number;
  max_schedule_rows?: number;
}

export interface CoveringArrayCertificate {
  schema_version: '1.0.0';
  status: 'PASS';
  strength: CoverageStrength;
  factor_names: string[];
  factor_value_counts: Record<string, number>;
  constraint_ids: string[];
  total_cartesian_assignments: number;
  feasible_assignments: number;
  infeasible_assignments: number;
  potential_interactions: number;
  required_feasible_interactions: number;
  infeasible_interactions: number;
  covered_interactions: number;
  schedule_rows: number;
  constraint_evaluations: number;
  assignment_space_sha256: string;
  schedule_sha256: string;
}

export interface CoveringArrayResult {
  rows: FactorAssignment[];
  certificate: CoveringArrayCertificate;
}

export interface AssignmentCycleCertificate {
  schema_version: '1.0.0';
  status: 'PASS';
  selection_profile: 'CONSTRAINT_AWARE_AFFINE_PERMUTATION_V1';
  selection_key_sha256: string;
  assignment_space_sha256: string;
  cycle_sha256: string;
  cycle_length: number;
  offset: number;
  stride: number;
  constraint_ids: string[];
  constraint_evaluations: number;
}

export interface AssignmentCycleResult {
  assignments: FactorAssignment[];
  certificate: AssignmentCycleCertificate;
}

export interface SelectedAssignment {
  assignment: FactorAssignment;
  cycle_index: number;
  cycle_length: number;
  assignment_space_sha256: string;
  selection_profile: AssignmentCycleCertificate['selection_profile'];
}

interface NormalizedForbidConstraint {
  constraint_id: string;
  kind: 'forbid';
  reason: string;
  when: Record<string, readonly string[]>;
}

interface NormalizedRequireConstraint {
  constraint_id: string;
  kind: 'require';
  reason: string;
  when: Record<string, readonly string[]>;
  then: Record<string, readonly string[]>;
}

type NormalizedConstraint = NormalizedForbidConstraint | NormalizedRequireConstraint;

type ClauseState = 'MATCH' | 'MISMATCH' | 'UNKNOWN';

interface EnumeratedSpace {
  factors: Array<[string, readonly string[]]>;
  constraints: NormalizedConstraint[];
  rows: FactorAssignment[];
  totalCartesianAssignments: number;
  constraintEvaluations: number;
  assignmentSpaceSha256: string;
}

const DEFAULT_MAX_CARTESIAN_ASSIGNMENTS = 100_000;
const DEFAULT_MAX_CONSTRAINT_EVALUATIONS = 2_000_000;
const DEFAULT_MAX_SCHEDULE_ROWS = 10_000;

function stableAssignment(value: FactorAssignment): FactorAssignment {
  return Object.fromEntries(
    Object.entries(value).sort(([left], [right]) => left.localeCompare(right)),
  );
}

function assignmentKey(value: FactorAssignment): string {
  return canonicalJson(stableAssignment(value));
}

function normalizeFactorValues(values: FactorValues): Array<[string, readonly string[]]> {
  const entries = Object.entries(values).sort(([left], [right]) => left.localeCompare(right));
  if (entries.length < 2) throw new Error('Coverage requires at least two factors.');
  for (const [name, options] of entries) {
    if (!name.trim()) throw new Error('Factor names must be nonempty.');
    if (options.length === 0) throw new Error(`Factor ${name} requires at least one value.`);
    if (options.some((value) => !value.trim())) throw new Error(`Factor ${name} contains a blank value.`);
    if (new Set(options).size !== options.length) throw new Error(`Factor ${name} contains duplicate values.`);
  }
  return entries.map(([name, options]) => [name, [...options].sort((left, right) => left.localeCompare(right))]);
}

function normalizeConstraintValues(value: ConstraintValue): readonly string[] {
  const values = typeof value === 'string' ? [value] : [...value];
  if (values.length === 0 || values.some((item) => !item.trim())) {
    throw new Error('Constraint value sets must contain nonblank values.');
  }
  return [...new Set(values)].sort((left, right) => left.localeCompare(right));
}

function normalizeClause(
  clause: Record<string, ConstraintValue>,
  factors: Map<string, Set<string>>,
  constraintId: string,
  clauseName: string,
): Record<string, readonly string[]> {
  const entries = Object.entries(clause).sort(([left], [right]) => left.localeCompare(right));
  if (entries.length === 0) throw new Error(`Constraint ${constraintId} has an empty ${clauseName} clause.`);
  const normalized: Record<string, readonly string[]> = {};
  for (const [factor, rawValues] of entries) {
    const admitted = factors.get(factor);
    if (!admitted) throw new Error(`Constraint ${constraintId} references unknown factor ${factor}.`);
    const options = normalizeConstraintValues(rawValues);
    for (const option of options) {
      if (!admitted.has(option)) {
        throw new Error(`Constraint ${constraintId} references unknown value ${factor}=${option}.`);
      }
    }
    normalized[factor] = options;
  }
  return normalized;
}

function normalizeConstraints(
  constraints: readonly FactorConstraint[],
  factors: Array<[string, readonly string[]]>,
): NormalizedConstraint[] {
  const factorMap = new Map(factors.map(([name, options]) => [name, new Set(options)] as const));
  const ids = constraints.map((constraint) => constraint.constraint_id);
  if (ids.some((id) => !id.trim())) throw new Error('Constraint IDs must be nonempty.');
  if (new Set(ids).size !== ids.length) throw new Error('Constraint IDs must be unique.');
  return [...constraints]
    .sort((left, right) => left.constraint_id.localeCompare(right.constraint_id))
    .map((constraint): NormalizedConstraint => {
      if (!constraint.reason.trim()) throw new Error(`Constraint ${constraint.constraint_id} requires a reason.`);
      if (constraint.kind === 'forbid') {
        return {
          constraint_id: constraint.constraint_id,
          kind: 'forbid',
          reason: constraint.reason,
          when: normalizeClause(constraint.when, factorMap, constraint.constraint_id, 'when'),
        };
      }
      return {
        constraint_id: constraint.constraint_id,
        kind: 'require',
        reason: constraint.reason,
        when: normalizeClause(constraint.when, factorMap, constraint.constraint_id, 'when'),
        then: normalizeClause(constraint.then, factorMap, constraint.constraint_id, 'then'),
      };
    });
}

function clauseState(
  assignment: Partial<FactorAssignment>,
  clause: Record<string, readonly string[]>,
): ClauseState {
  let unknown = false;
  for (const [factor, admitted] of Object.entries(clause)) {
    const observed = assignment[factor];
    if (observed === undefined) {
      unknown = true;
      continue;
    }
    if (!admitted.includes(observed)) return 'MISMATCH';
  }
  return unknown ? 'UNKNOWN' : 'MATCH';
}

function constraintAllowsPartial(
  assignment: Partial<FactorAssignment>,
  constraint: NormalizedConstraint,
): boolean {
  const antecedent = clauseState(assignment, constraint.when);
  if (constraint.kind === 'forbid') return antecedent !== 'MATCH';
  if (antecedent !== 'MATCH') return true;
  return clauseState(assignment, constraint.then) !== 'MISMATCH';
}

function safeCartesianSize(factors: Array<[string, readonly string[]]>, maximum: number): number {
  let size = 1n;
  for (const [, options] of factors) size *= BigInt(options.length);
  if (size > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('Coverage Cartesian space exceeds the safe integer range.');
  if (size > BigInt(maximum)) {
    throw new Error(`Coverage budget exceeded: Cartesian space ${size} is above ${maximum}.`);
  }
  return Number(size);
}

function enumerateFeasibleAssignments(values: FactorValues, options: CoverageOptions = {}): EnumeratedSpace {
  const factors = normalizeFactorValues(values);
  const constraints = normalizeConstraints(options.constraints ?? [], factors);
  const maxCartesian = options.max_cartesian_assignments ?? DEFAULT_MAX_CARTESIAN_ASSIGNMENTS;
  const maxEvaluations = options.max_constraint_evaluations ?? DEFAULT_MAX_CONSTRAINT_EVALUATIONS;
  if (!Number.isSafeInteger(maxCartesian) || maxCartesian < 1) throw new Error('max_cartesian_assignments must be a positive safe integer.');
  if (!Number.isSafeInteger(maxEvaluations) || maxEvaluations < 1) throw new Error('max_constraint_evaluations must be a positive safe integer.');
  const totalCartesianAssignments = safeCartesianSize(factors, maxCartesian);
  const rows: FactorAssignment[] = [];
  const partial: FactorAssignment = {};
  let constraintEvaluations = 0;

  const recurse = (index: number): void => {
    if (index === factors.length) {
      rows.push(stableAssignment(partial));
      return;
    }
    const [factor, admitted] = factors[index]!;
    for (const value of admitted) {
      partial[factor] = value;
      let feasible = true;
      for (const constraint of constraints) {
        constraintEvaluations += 1;
        if (constraintEvaluations > maxEvaluations) {
          throw new Error(`Coverage budget exceeded: constraint evaluations are above ${maxEvaluations}.`);
        }
        if (!constraintAllowsPartial(partial, constraint)) {
          feasible = false;
          break;
        }
      }
      if (feasible) recurse(index + 1);
      delete partial[factor];
    }
  };
  recurse(0);
  rows.sort((left, right) => assignmentKey(left).localeCompare(assignmentKey(right)));
  if (rows.length === 0) throw new Error('Constraint set is contradictory: no feasible factor assignment exists.');
  const assignmentSpaceSha256 = sha256Canonical({
    factors,
    constraints,
    rows,
  });
  return {
    factors,
    constraints,
    rows,
    totalCartesianAssignments,
    constraintEvaluations,
    assignmentSpaceSha256,
  };
}

function combinations<T>(values: readonly T[], size: number): T[][] {
  const result: T[][] = [];
  const selected: T[] = [];
  const visit = (start: number): void => {
    if (selected.length === size) {
      result.push([...selected]);
      return;
    }
    for (let index = start; index <= values.length - (size - selected.length); index += 1) {
      selected.push(values[index]!);
      visit(index + 1);
      selected.pop();
    }
  };
  visit(0);
  return result;
}

function interactionKeys(row: FactorAssignment, strength: CoverageStrength): string[] {
  const entries = Object.entries(stableAssignment(row));
  return combinations(entries, strength).map((items) => canonicalJson(items));
}

function potentialInteractionCount(
  factors: Array<[string, readonly string[]]>,
  strength: CoverageStrength,
): number {
  return combinations(factors, strength).reduce((total, group) => (
    total + group.reduce((product, [, options]) => product * options.length, 1)
  ), 0);
}

function requiredInteractions(rows: readonly FactorAssignment[], strength: CoverageStrength): Set<string> {
  return new Set(rows.flatMap((row) => interactionKeys(row, strength)));
}

/**
 * Build a deterministic t-way covering array over only feasible assignments.
 * Infeasible tuples are not counted as missing coverage, and every limit fails closed.
 */
export function buildConstraintAwareCoveringArray(
  values: FactorValues,
  options: CoverageOptions = {},
): CoveringArrayResult {
  const strength = options.strength ?? 2;
  if (strength !== 2 && strength !== 3) throw new Error('Coverage strength must be 2 or 3.');
  const space = enumerateFeasibleAssignments(values, options);
  if (strength > space.factors.length) throw new Error('Coverage strength exceeds the factor count.');
  const maximumRows = options.max_schedule_rows ?? DEFAULT_MAX_SCHEDULE_ROWS;
  if (!Number.isSafeInteger(maximumRows) || maximumRows < 1) throw new Error('max_schedule_rows must be a positive safe integer.');

  const required = requiredInteractions(space.rows, strength);
  const uncovered = new Set(required);
  const candidates = space.rows.map((row) => ({
    row,
    key: assignmentKey(row),
    interactions: interactionKeys(row, strength),
  }));
  const selected: typeof candidates = [];

  while (uncovered.size > 0) {
    let bestIndex = -1;
    let bestGain = -1;
    let bestKey = '';
    for (let index = 0; index < candidates.length; index += 1) {
      const candidate = candidates[index]!;
      const gain = candidate.interactions.reduce((count, key) => count + Number(uncovered.has(key)), 0);
      if (gain > bestGain || (gain === bestGain && gain > 0 && candidate.key < bestKey)) {
        bestIndex = index;
        bestGain = gain;
        bestKey = candidate.key;
      }
    }
    if (bestIndex < 0 || bestGain <= 0) {
      throw new Error(`Could not cover ${uncovered.size} feasible ${strength}-way interactions.`);
    }
    const [best] = candidates.splice(bestIndex, 1);
    selected.push(best!);
    for (const key of best!.interactions) uncovered.delete(key);
    if (selected.length > maximumRows) {
      throw new Error(`Coverage budget exceeded: schedule rows are above ${maximumRows}.`);
    }
  }

  // Deterministic redundancy elimination keeps the schedule compact without
  // changing coverage. Reverse order preserves the strongest greedy choices.
  const counts = new Map<string, number>();
  for (const candidate of selected) {
    for (const key of candidate.interactions) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  for (let index = selected.length - 1; index >= 0; index -= 1) {
    const candidate = selected[index]!;
    if (candidate.interactions.every((key) => (counts.get(key) ?? 0) > 1)) {
      selected.splice(index, 1);
      for (const key of candidate.interactions) counts.set(key, (counts.get(key) ?? 0) - 1);
    }
  }

  const rows = selected.map((candidate) => stableAssignment(candidate.row));
  const observed = requiredInteractions(rows, strength);
  const missing = [...required].filter((key) => !observed.has(key));
  if (missing.length > 0) throw new Error(`Coverage compaction lost ${missing.length} required interactions.`);
  const potential = potentialInteractionCount(space.factors, strength);
  const certificate: CoveringArrayCertificate = {
    schema_version: '1.0.0',
    status: 'PASS',
    strength,
    factor_names: space.factors.map(([name]) => name),
    factor_value_counts: Object.fromEntries(space.factors.map(([name, admitted]) => [name, admitted.length])),
    constraint_ids: space.constraints.map((constraint) => constraint.constraint_id),
    total_cartesian_assignments: space.totalCartesianAssignments,
    feasible_assignments: space.rows.length,
    infeasible_assignments: space.totalCartesianAssignments - space.rows.length,
    potential_interactions: potential,
    required_feasible_interactions: required.size,
    infeasible_interactions: potential - required.size,
    covered_interactions: observed.size,
    schedule_rows: rows.length,
    constraint_evaluations: space.constraintEvaluations,
    assignment_space_sha256: space.assignmentSpaceSha256,
    schedule_sha256: sha256Canonical(rows),
  };
  return { rows, certificate };
}

function gcd(left: number, right: number): number {
  let a = Math.abs(left);
  let b = Math.abs(right);
  while (b !== 0) [a, b] = [b, a % b];
  return a;
}

/**
 * Return a deterministic permutation of every feasible assignment. The first
 * `cycle_length` nonnegative seeds therefore visit every feasible context once.
 */
export function buildDeterministicAssignmentCycle(
  values: FactorValues,
  selectionKey: string,
  options: Omit<CoverageOptions, 'strength' | 'max_schedule_rows'> = {},
): AssignmentCycleResult {
  if (!selectionKey.trim()) throw new Error('Selection key must be nonempty.');
  const space = enumerateFeasibleAssignments(values, options);
  const length = space.rows.length;
  const selectionKeySha256 = sha256Canonical({ selection_key: selectionKey, assignment_space: space.assignmentSpaceSha256 });
  const offset = Number.parseInt(selectionKeySha256.slice(0, 8), 16) % length;
  let stride = length === 1 ? 1 : Number.parseInt(selectionKeySha256.slice(8, 16), 16) % length;
  if (stride === 0) stride = 1;
  while (length > 1 && gcd(stride, length) !== 1) {
    stride = (stride + 1) % length;
    if (stride === 0) stride = 1;
  }
  const assignments = Array.from({ length }, (_, seed) => (
    stableAssignment(space.rows[(offset + seed * stride) % length]!)
  ));
  if (new Set(assignments.map(assignmentKey)).size !== length) {
    throw new Error('Deterministic assignment cycle is not a bijection.');
  }
  const certificate: AssignmentCycleCertificate = {
    schema_version: '1.0.0',
    status: 'PASS',
    selection_profile: 'CONSTRAINT_AWARE_AFFINE_PERMUTATION_V1',
    selection_key_sha256: selectionKeySha256,
    assignment_space_sha256: space.assignmentSpaceSha256,
    cycle_sha256: sha256Canonical(assignments),
    cycle_length: length,
    offset,
    stride,
    constraint_ids: space.constraints.map((constraint) => constraint.constraint_id),
    constraint_evaluations: space.constraintEvaluations,
  };
  return { assignments, certificate };
}

export function selectDeterministicFeasibleAssignment(
  values: FactorValues,
  seed: number,
  selectionKey: string,
  options: Omit<CoverageOptions, 'strength' | 'max_schedule_rows'> = {},
): SelectedAssignment {
  if (!Number.isSafeInteger(seed) || seed < 0) throw new Error('Scenario seed must be a nonnegative safe integer.');
  const cycle = buildDeterministicAssignmentCycle(values, selectionKey, options);
  const cycleIndex = Number(BigInt(seed) % BigInt(cycle.assignments.length));
  return {
    assignment: stableAssignment(cycle.assignments[cycleIndex]!),
    cycle_index: cycleIndex,
    cycle_length: cycle.assignments.length,
    assignment_space_sha256: cycle.certificate.assignment_space_sha256,
    selection_profile: cycle.certificate.selection_profile,
  };
}

function cartesian(factors: Array<[string, readonly string[]]>): FactorAssignment[] {
  let rows: FactorAssignment[] = [{}];
  for (const [name, values] of factors) {
    rows = rows.flatMap((row) => values.map((value) => ({ ...row, [name]: value })));
  }
  return rows.map(stableAssignment);
}

function pairsFor(row: FactorAssignment): string[] {
  return interactionKeys(row, 2);
}

/** Backward-compatible unconstrained pairwise schedule. */
export function buildPairCoverageSchedule(values: FactorValues): FactorAssignment[] {
  return buildConstraintAwareCoveringArray(values, { strength: 2 }).rows;
}

export function countUncoveredPairs(
  schedule: readonly FactorAssignment[],
  values: FactorValues,
): number {
  const allRows = cartesian(normalizeFactorValues(values));
  const required = new Set(allRows.flatMap(pairsFor));
  for (const row of schedule) {
    for (const pair of pairsFor(row)) required.delete(pair);
  }
  return required.size;
}

export function countUncoveredFeasibleInteractions(
  schedule: readonly FactorAssignment[],
  values: FactorValues,
  options: CoverageOptions = {},
): number {
  const strength = options.strength ?? 2;
  const space = enumerateFeasibleAssignments(values, options);
  const required = requiredInteractions(space.rows, strength);
  for (const row of schedule) {
    for (const key of interactionKeys(row, strength)) required.delete(key);
  }
  return required.size;
}
