import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decode, encode } from '@toon-format/toon';
import {
  SCENARIO_CATEGORIES,
  getCategoryById,
  getEventTypeById,
  getSpecificOption,
  getSpecificsForEvent,
  normalizeScenarioSelection,
  type ScenarioCategoryId,
  type ScenarioEventTypeId,
  type ScenarioSelection,
} from '../src/content/scenarioTaxonomy.ts';
import type { HospitalDepartmentId } from '../src/types/providerProfile.ts';
import type { ExerciseSegmentDefinition, ExerciseTemplate } from '../src/types/exercise.ts';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..');
const TOON_DIR = join(ROOT, 'content/exercises/toon');
const OUT_TS = join(ROOT, 'src/content/exercises/catalog.generated.ts');
const OUT_ALLOCATION = join(TOON_DIR, 'exercise_allocation.toon');

const CATALOG_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const TARGET_COUNT = 100;

const FIELD_EVENTS = new Set([
  'inbound_missile',
  'drone_attack',
  'explosion_blast',
  'indirect_fire',
  'sniper_attack',
  'unexploded_ordnance',
  'active_shooter',
  'vehicle_accident',
]);

const FIELD_DEPARTMENTS = new Set<HospitalDepartmentId>([
  'field_response_team',
  'triage',
  'decon',
  'manpower_security',
]);

function resolveBaseScenarioId(
  selection: ScenarioSelection,
  department: HospitalDepartmentId,
): string {
  if (FIELD_DEPARTMENTS.has(department) || FIELD_EVENTS.has(selection.eventTypeId)) {
    return 'ASK-A-001';
  }
  return 'ASK-D-001';
}

const CATEGORY_QUOTAS: Record<ScenarioCategoryId, number> = {
  home_station: 18,
  deployed_location: 14,
  combat_theater: 12,
  joint_exercise: 12,
  humanitarian_assistance: 10,
  airshow_open_house: 10,
  garrison_training: 12,
  special_event: 12,
};

type Difficulty = 'intro' | 'intermediate' | 'advanced';

interface ArchetypeRow {
  id: string;
  label: string;
  minProviders: number;
  estimatedMinutes: number;
  difficulty: Difficulty;
}

interface SegmentStepRow {
  archetypeId: string;
  order: number;
  department: HospitalDepartmentId;
  label: string;
  briefingLead: string;
  isEntry: boolean;
  isTerminal: boolean;
}

interface EventRuleRow {
  eventTypeId: ScenarioEventTypeId;
  archetypeId: string;
}

interface CategoryOverrideRow {
  categoryId: ScenarioCategoryId;
  eventTypeId: ScenarioEventTypeId;
  archetypeId: string;
}

interface AllocationRow {
  catalogId: string;
  categoryId: ScenarioCategoryId;
  eventTypeId: ScenarioEventTypeId;
  specificId: string;
  chainArchetype: string;
  difficulty: Difficulty;
  estimatedMinutes: number;
  minProviders: number;
}

function readToon<T>(filename: string): T {
  const raw = readFileSync(join(TOON_DIR, filename), 'utf8');
  return decode(raw) as T;
}

function hash32(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function makeCatalogId(key: string, used: Set<string>): string {
  for (let attempt = 0; attempt < 64; attempt += 1) {
    let value = hash32(`${key}:${attempt}`);
    let id = '';
    for (let index = 0; index < 6; index += 1) {
      id += CATALOG_ALPHABET[value % CATALOG_ALPHABET.length];
      value = Math.floor(value / CATALOG_ALPHABET.length) ^ hash32(`${key}:${index}:${attempt}`);
    }
    if (!used.has(id)) {
      used.add(id);
      return id;
    }
  }
  throw new Error(`Could not generate unique catalog ID for ${key}`);
}

interface ExistingAllocationState {
  byTriple: Map<string, string>;
  generatedAt: string;
}

function loadExistingAllocationState(): ExistingAllocationState {
  try {
    const existing = readToon<{
      meta?: { generatedAt?: string };
      exercises?: AllocationRow[];
    }>('exercise_allocation.toon');
    const byTriple = new Map<string, string>();
    for (const row of existing.exercises ?? []) {
      if (!/^[A-Z0-9]{6}$/.test(row.catalogId)) continue;
      byTriple.set(`${row.categoryId}:${row.eventTypeId}:${row.specificId}`, row.catalogId);
    }
    return {
      byTriple,
      generatedAt: existing.meta?.generatedAt ?? 'deterministic-catalog-v1',
    };
  } catch {
    return { byTriple: new Map(), generatedAt: 'deterministic-catalog-v1' };
  }
}

function resolveArchetypeId(
  categoryId: ScenarioCategoryId,
  eventTypeId: ScenarioEventTypeId,
  eventRules: EventRuleRow[],
  categoryOverrides: CategoryOverrideRow[],
  fallback: string,
): string {
  const override = categoryOverrides.find(
    (row) => row.categoryId === categoryId && row.eventTypeId === eventTypeId,
  );
  if (override) return override.archetypeId;
  const rule = eventRules.find((row) => row.eventTypeId === eventTypeId);
  return rule?.archetypeId ?? fallback;
}

function buildAllocationRows(
  eventRules: EventRuleRow[],
  categoryOverrides: CategoryOverrideRow[],
  archetypes: ArchetypeRow[],
  fallback: string,
  existingByTriple: Map<string, string>,
): AllocationRow[] {
  const archetypeById = Object.fromEntries(archetypes.map((a) => [a.id, a]));
  const usedCatalogIds = new Set<string>();
  const usedTriples = new Set<string>();
  const rows: AllocationRow[] = [];

  for (const category of SCENARIO_CATEGORIES) {
    const quota = CATEGORY_QUOTAS[category.id];
    let added = 0;

    for (const eventTypeId of category.eventTypeIds) {
      if (added >= quota) break;
      const specifics = getSpecificsForEvent(eventTypeId);
      for (const specific of specifics) {
        if (added >= quota) break;
        const tripleKey = `${category.id}:${eventTypeId}:${specific.id}`;
        if (usedTriples.has(tripleKey)) continue;
        usedTriples.add(tripleKey);

        const chainArchetype = resolveArchetypeId(
          category.id,
          eventTypeId,
          eventRules,
          categoryOverrides,
          fallback,
        );
        const archetype = archetypeById[chainArchetype];
        if (!archetype) {
          throw new Error(`Unknown archetype ${chainArchetype} for ${tripleKey}`);
        }

        const existingCatalogId = existingByTriple.get(tripleKey);
        const catalogId =
          existingCatalogId && !usedCatalogIds.has(existingCatalogId)
            ? existingCatalogId
            : makeCatalogId(tripleKey, usedCatalogIds);
        usedCatalogIds.add(catalogId);

        rows.push({
          catalogId,
          categoryId: category.id,
          eventTypeId,
          specificId: specific.id,
          chainArchetype,
          difficulty: archetype.difficulty,
          estimatedMinutes: archetype.estimatedMinutes,
          minProviders: archetype.minProviders,
        });
        added += 1;
      }
    }
  }

  if (rows.length < TARGET_COUNT) {
    throw new Error(`Only ${rows.length} unique taxonomy triples — need ${TARGET_COUNT}`);
  }

  return rows.slice(0, TARGET_COUNT);
}

function buildTitle(selection: ScenarioSelection): string {
  const category = getCategoryById(selection.categoryId);
  const event = getEventTypeById(selection.eventTypeId);
  const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
  return `${category?.label ?? selection.categoryId} / ${event?.label ?? selection.eventTypeId} / ${specific?.label ?? selection.specificId}`;
}

function buildDescription(selection: ScenarioSelection, archetypeLabel: string): string {
  const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
  const event = getEventTypeById(selection.eventTypeId);
  return `${archetypeLabel}. ${specific?.description ?? event?.description ?? 'Multi-role training evolution.'}`;
}

function buildSegments(
  catalogId: string,
  selection: ScenarioSelection,
  archetypeId: string,
  steps: SegmentStepRow[],
): ExerciseSegmentDefinition[] {
  const archetypeSteps = steps
    .filter((step) => step.archetypeId === archetypeId)
    .sort((a, b) => a.order - b.order);

  if (archetypeSteps.length === 0) {
    throw new Error(`No segment steps for archetype ${archetypeId}`);
  }

  const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
  const narrative = specific?.narrativeDetail ?? '';

  return archetypeSteps.map((step, index) => {
    const futureDepartments = archetypeSteps.slice(index + 1).map((s) => s.department);
    const briefingLead = narrative
      ? `${step.briefingLead} Context: ${narrative}`
      : step.briefingLead;

    return {
      id: `${catalogId.toLowerCase()}-${step.department}`,
      department: step.department,
      label: step.label,
      briefingLead,
      baseScenarioId: resolveBaseScenarioId(selection, step.department),
      handoffTargets: step.isTerminal ? [] : futureDepartments,
      isEntryPoint: step.isEntry,
      isTerminal: step.isTerminal,
    };
  });
}

function buildTemplates(
  allocations: AllocationRow[],
  archetypes: ArchetypeRow[],
  steps: SegmentStepRow[],
): ExerciseTemplate[] {
  const archetypeLabelById = Object.fromEntries(archetypes.map((a) => [a.id, a.label]));

  return allocations.map((row) => {
    const selection = normalizeScenarioSelection({
      categoryId: row.categoryId,
      eventTypeId: row.eventTypeId,
      specificId: row.specificId,
    });
    const specific = getSpecificOption(selection.eventTypeId, selection.specificId);
    const segments = buildSegments(row.catalogId, selection, row.chainArchetype, steps);

    return {
      catalogId: row.catalogId,
      id: `EX-${row.catalogId}`,
      title: buildTitle(selection),
      description: buildDescription(selection, archetypeLabelById[row.chainArchetype] ?? row.chainArchetype),
      eventSummary: specific?.narrativeDetail ?? buildDescription(selection, row.chainArchetype),
      scenarioSelection: selection,
      chainArchetype: row.chainArchetype,
      difficulty: row.difficulty,
      estimatedMinutes: row.estimatedMinutes,
      minProviders: row.minProviders,
      segments,
    };
  });
}

function validateTemplates(templates: ExerciseTemplate[]): void {
  const catalogIds = new Set<string>();
  const slugs = new Set<string>();

  for (const template of templates) {
    if (!/^[A-Z0-9]{6}$/.test(template.catalogId)) {
      throw new Error(`Invalid catalogId ${template.catalogId}`);
    }
    if (catalogIds.has(template.catalogId)) {
      throw new Error(`Duplicate catalogId ${template.catalogId}`);
    }
    catalogIds.add(template.catalogId);

    if (slugs.has(template.id)) {
      throw new Error(`Duplicate template id ${template.id}`);
    }
    slugs.add(template.id);

    const entryCount = template.segments.filter((s) => s.isEntryPoint).length;
    if (entryCount !== 1) {
      throw new Error(`Template ${template.catalogId} must have exactly one entry segment`);
    }
    const terminalCount = template.segments.filter((s) => s.isTerminal).length;
    if (terminalCount < 1) {
      throw new Error(`Template ${template.catalogId} must have a terminal segment`);
    }
  }

  if (templates.length !== TARGET_COUNT) {
    throw new Error(`Expected ${TARGET_COUNT} templates, got ${templates.length}`);
  }
}

function writeAllocationToon(allocations: AllocationRow[], generatedAt: string): void {
  const payload = {
    meta: {
      version: 1,
      generatedAt,
      count: allocations.length,
    },
    exercises: allocations.map((row) => ({
      catalogId: row.catalogId,
      categoryId: row.categoryId,
      eventTypeId: row.eventTypeId,
      specificId: row.specificId,
      chainArchetype: row.chainArchetype,
      difficulty: row.difficulty,
      estimatedMinutes: row.estimatedMinutes,
      minProviders: row.minProviders,
    })),
  };

  writeFileSync(OUT_ALLOCATION, `${encode(payload)}\n`, 'utf8');
}

function writeCatalogTs(templates: ExerciseTemplate[]): void {
  const body = `/* eslint-disable */
// Generated by scripts/generateExerciseCatalog.ts. Do not edit manually.
import type { ExerciseTemplate } from '@/types/exercise';

export const GENERATED_EXERCISE_CATALOG: ExerciseTemplate[] = ${JSON.stringify(templates, null, 2)} as ExerciseTemplate[];

export const exercisesByCatalogId: Record<string, ExerciseTemplate> = Object.fromEntries(
  GENERATED_EXERCISE_CATALOG.map((template) => [template.catalogId, template]),
);
`;

  mkdirSync(dirname(OUT_TS), { recursive: true });
  writeFileSync(OUT_TS, body, 'utf8');
}

function main(): void {
  const archetypesFile = readToon<{
    archetypes: ArchetypeRow[];
    segment_steps: SegmentStepRow[];
  }>('chain_archetypes.toon');

  const mapFile = readToon<{
    defaults: { fallbackArchetype: string };
    event_rules: EventRuleRow[];
    category_overrides: CategoryOverrideRow[];
  }>('event_archetype_map.toon');

  const existingAllocation = loadExistingAllocationState();
  const allocations = buildAllocationRows(
    mapFile.event_rules,
    mapFile.category_overrides,
    archetypesFile.archetypes,
    mapFile.defaults.fallbackArchetype,
    existingAllocation.byTriple,
  );

  const templates = buildTemplates(
    allocations,
    archetypesFile.archetypes,
    archetypesFile.segment_steps,
  );

  validateTemplates(templates);
  writeAllocationToon(allocations, existingAllocation.generatedAt);
  writeCatalogTs(templates);

  console.log(`Generated ${templates.length} exercises`);
  console.log(`  TOON allocation: ${OUT_ALLOCATION}`);
  console.log(`  TypeScript catalog: ${OUT_TS}`);
}

main();
