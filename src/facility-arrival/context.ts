import { scenariosById } from '../content/scenarios';
import {
  FACILITY_CONTENT_REGISTRY_ROOT,
  FACILITY_TEMPLATE_RECORD_SHA256,
} from './bindings.generated';
import { FACILITY_ARRIVAL_SPEC } from './specification.generated';
import type { FacilitySourceContext } from './types';

const scenario = scenariosById[FACILITY_ARRIVAL_SPEC.source_scenario_id];
if (!scenario) {
  throw new Error(`Facility source scenario is missing: ${FACILITY_ARRIVAL_SPEC.source_scenario_id}`);
}

export const facilityArrivalContext: FacilitySourceContext = {
  scenario,
  spec: FACILITY_ARRIVAL_SPEC,
  template_record_sha256: FACILITY_TEMPLATE_RECORD_SHA256,
  content_registry_merkle_root: FACILITY_CONTENT_REGISTRY_ROOT,
};
