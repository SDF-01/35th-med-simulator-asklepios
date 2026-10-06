import type { ExerciseTemplate } from '@/types/exercise';
import {
  EXERCISE_TEMPLATES as LEGACY_EXERCISE_TEMPLATES,
  exercisesById as legacyExercisesById,
} from '@/content/exercises/legacyTemplates';
import {
  GENERATED_EXERCISE_CATALOG,
  exercisesByCatalogId,
} from '@/content/exercises/catalog.generated';

/** Full exercise catalog (100 generated + optional legacy templates). */
export const EXERCISE_TEMPLATES: ExerciseTemplate[] = [
  ...GENERATED_EXERCISE_CATALOG,
  ...LEGACY_EXERCISE_TEMPLATES.filter(
    (legacy) => !GENERATED_EXERCISE_CATALOG.some((g) => g.id === legacy.id),
  ),
];

export const exercisesById: Record<string, ExerciseTemplate> = {
  ...Object.fromEntries(GENERATED_EXERCISE_CATALOG.map((t) => [t.id, t])),
  ...legacyExercisesById,
};

export { exercisesByCatalogId };

export function getExerciseTemplate(id: string): ExerciseTemplate | undefined {
  return exercisesById[id];
}

export function getExerciseByCatalogId(catalogId: string): ExerciseTemplate | undefined {
  const normalized = catalogId.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  return exercisesByCatalogId[normalized];
}

export function getEntrySegment(template: ExerciseTemplate) {
  return template.segments.find((s) => s.isEntryPoint) ?? template.segments[0];
}

export function getSegmentById(template: ExerciseTemplate, segmentId: string) {
  return template.segments.find((s) => s.id === segmentId);
}

export function getNextSegmentForDepartment(
  template: ExerciseTemplate,
  segmentId: string,
  targetDepartment: string,
) {
  const current = getSegmentById(template, segmentId);
  if (!current?.handoffTargets.includes(targetDepartment as never)) return undefined;
  return template.segments.find((s) => s.department === targetDepartment);
}

export function searchExerciseTemplates(filters: {
  categoryId?: string;
  eventTypeId?: string;
  catalogId?: string;
  query?: string;
}): ExerciseTemplate[] {
  const catalogQuery = filters.catalogId?.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
  const textQuery = filters.query?.trim().toLowerCase();

  return EXERCISE_TEMPLATES.filter((template) => {
    if (catalogQuery && !template.catalogId.includes(catalogQuery)) return false;
    if (filters.categoryId && template.scenarioSelection.categoryId !== filters.categoryId) {
      return false;
    }
    if (filters.eventTypeId && template.scenarioSelection.eventTypeId !== filters.eventTypeId) {
      return false;
    }
    if (textQuery) {
      const haystack = `${template.catalogId} ${template.title} ${template.description}`.toLowerCase();
      if (!haystack.includes(textQuery)) return false;
    }
    return true;
  });
}
