import type { Scenario } from '../types';
import type { VerifiedScenarioPackage, ScenarioBuildStage, ScenarioStageId } from './types';
import { sha256Canonical } from './hash';

export type PackageWithoutCertificate = Omit<VerifiedScenarioPackage, 'certificate'>;

export function stagePayload(
  stageId: ScenarioStageId,
  generated: PackageWithoutCertificate,
  baseScenario: Scenario,
): unknown {
  switch (stageId) {
    case 'source':
      return {
        build: generated.build,
        base_scenario_sha256: sha256Canonical(baseScenario),
        blueprint_sha256: sha256Canonical(generated.blueprint),
        evidence_ids: generated.evidence.map((item) => item.evidence_id),
      };
    case 'setting':
      return {
        scenario_id: generated.scenario.scenario_id,
        title: generated.scenario.title,
        version: generated.scenario.version,
        fictionalization_notice: generated.scenario.fictionalization_notice,
        location_type: generated.scenario.operational_context.location_type,
        weather: generated.scenario.operational_context.weather,
        visibility: generated.scenario.operational_context.visibility,
        comms_status: generated.scenario.operational_context.comms_status,
        resource_status: generated.scenario.operational_context.resource_status,
      };
    case 'pressure':
      return {
        narrative: generated.scenario.operational_context.narrative,
        resource_event_atom_sha256: generated.atoms.find((atom) => atom.atom_id === 'atom-resource-event')?.atom_sha256 ?? '',
      };
    case 'route':
      return generated.route;
    case 'final':
      return {
        scenario: generated.scenario,
        route_sha256: sha256Canonical(generated.route),
        evidence_sha256: sha256Canonical(generated.evidence),
      };
  }
}

export function stageOutputDigest(
  stage: Omit<ScenarioBuildStage, 'output_sha256'>,
): string {
  return sha256Canonical(stage);
}

export function makeStage(input: {
  stage_id: ScenarioStageId;
  input_sha256: string;
  payload: unknown;
  selected_atom_ids: string[];
  touched_paths: string[];
}): ScenarioBuildStage {
  const withoutOutput: Omit<ScenarioBuildStage, 'output_sha256'> = {
    stage_id: input.stage_id,
    formula_version: '1.0.0',
    input_sha256: input.input_sha256,
    payload_sha256: sha256Canonical(input.payload),
    selected_atom_ids: [...input.selected_atom_ids],
    touched_paths: [...input.touched_paths],
  };
  return { ...withoutOutput, output_sha256: stageOutputDigest(withoutOutput) };
}
