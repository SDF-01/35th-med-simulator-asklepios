import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildScenarioBehavioralEquivalenceArchive,
  buildScenarioBehavioralPolicyDescriptor,
  scenarioBehavioralPolicySignature,
} from '../scenario-core/behavioralEquivalence';
import type { VerifiedScenarioPackage } from '../scenario-core/types';

function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T; }

function fixture(packageHash: string): VerifiedScenarioPackage {
  return {
    schema_version: '2.1.0',
    build: {
      build_id: 'ASK-B-FIXTURE', build_version: '2.1.0', mode: 'template_locked', seed: 1,
      topic_id: 'massive_hemorrhage', retriever_track: 'fixture', blueprint_id: 'ASK-BP-FIELD-001',
      source_scenario_id: 'ASK-A-001', source_bridge_schema: '1.0.0', source_database_sha256: '1'.repeat(64),
      source_bridge_sha256: '2'.repeat(64), source_prototype_id: 'p', source_prototype_sha256: '3'.repeat(64),
      source_prototype_record_sha256: '4'.repeat(64),
    },
    blueprint: {
      blueprint_id: 'ASK-BP-FIELD-001', blueprint_version: '1.1.0', mode: 'template_locked', source_scenario_id: 'ASK-A-001',
      allowed_topics: ['massive_hemorrhage'], mutable_paths: [], location_options: ['alpha'], weather_options: ['clear'],
      visibility_options: ['Good'], communications_options: ['degraded'], resource_options: ['constrained'],
      resource_event_options: ['relay delayed'], route_template_id: 'ASK-ROUTE-FIELD-001',
    },
    authority: {
      clinical_authority: 'NOT_GRANTED', deployment_scope: 'research_sandbox_only',
      source_template_status: 'repository_template_not_clinically_certified', clinical_rule_source: 'inherited_template',
      evidence_authority: 'supporting_only', evidence_effect_scope: 'citation_support_only', scoring_behavior: 'inherited_unchanged',
    },
    scenario: {
      scenario_id: 'S1', title: 'Fixture', version: '1', fictionalization_notice: 'Training only.',
      operational_context: { location_type: 'alpha', threat_type: 'none', weather: 'clear', visibility: 'Good', comms_status: 'degraded', resource_status: 'constrained', narrative: 'fixture' },
      training_objectives: ['objective'], target_section: 'A_field_reaction_triage_incident_response', target_role: 'medic_or_technician',
      skill_level: 'intermediate', difficulty: 'intermediate', threat_type: 'none', casualty_count: 1,
      patients: [{
        patient_id: 'P1', age_band: 'adult', sex: 'unspecified', role_context: 'trainee', mechanism_of_injury: 'fixture',
        initial_presentation: 'fixture', injury_profile_refs: ['I1'], initial_vitals: { hr: 100, bp_systolic: 110, bp_diastolic: 70, rr: 20, spo2: 95, temp_c: 37, gcs: 15 },
        hidden_findings: ['hidden'], deterioration_timeline: ['later'], visible_body_zones: [],
      }],
      expected_actions: {
        critical: [{ id: 'a', label: 'Action A', priority: 'critical', synonyms: [], points: 10, marchStep: 'massive_hemorrhage' }],
        important: [], optional: [], unsafe: [{ id: 'u', label: 'Unsafe', priority: 'unsafe', synonyms: [], points: -10 }],
      },
      end_conditions: { success: ['complete'], failure: ['unsafe'], timeout_minutes: 20 },
      aar_teaching_points: ['point'],
    },
    route: {
      route_id: 'R1:DIRECT_HANDOFF_BASELINE', start_node_id: 'n1',
      nodes: [
        { node_id: 'n1', node_kind: 'briefing', label: 'Start here now', terminal: false },
        { node_id: 'n2', node_kind: 'pressure', label: 'Handle pressure now', terminal: false },
        { node_id: 'n3', node_kind: 'complete', label: 'Finish the route', terminal: true },
      ],
      edges: [
        { edge_id: 'e1', from: 'n1', to: 'n2', trigger: 'start', priority: 100 },
        { edge_id: 'e2', from: 'n2', to: 'n3', trigger: 'close', priority: 100 },
      ],
    },
    evidence: [], atoms: [{ atom_id: 'event', atom_kind: 'resource_event', value: 'relay delayed', source_kind: 'deterministic_selection', evidence_ids: [], authority: 'nonclinical', atom_sha256: '5'.repeat(64) }],
    stages: [], field_origins: [],
    certificate: {
      certificate_version: '1.1.0', checker_profile: 'scenario-contract-v1', base_scenario_sha256: '6'.repeat(64), base_protected_sha256: '7'.repeat(64),
      output_protected_sha256: '7'.repeat(64), source_bridge_sha256: '2'.repeat(64), source_prototype_sha256: '3'.repeat(64), source_prototype_record_sha256: '4'.repeat(64),
      blueprint_sha256: '8'.repeat(64), atom_root_sha256: '9'.repeat(64), stage_chain_sha256: 'a'.repeat(64), route_sha256: 'b'.repeat(64),
      field_origin_sha256: 'c'.repeat(64), evidence_sha256: 'd'.repeat(64), package_sha256: packageHash,
      checks: { protected_fields_unchanged: true, route_has_reachable_terminal: true, route_has_no_dead_end: true, field_origins_complete: true, evidence_scope_preserved: true, stage_chain_contiguous: true, stage_payloads_verified: true },
    },
  };
}

function signature(value: VerifiedScenarioPackage): string {
  return scenarioBehavioralPolicySignature(buildScenarioBehavioralPolicyDescriptor(value));
}

test('narrative and operational context changes do not create policy novelty', () => {
  const base=fixture('1'.repeat(64)); const variant=clone(base);
  variant.certificate.package_sha256='2'.repeat(64); variant.scenario.title='Different words';
  variant.scenario.operational_context.location_type='beta'; variant.scenario.operational_context.narrative='different';
  variant.atoms[0]!.value='different resource prose';
  assert.equal(signature(base), signature(variant));
  const archive=buildScenarioBehavioralEquivalenceArchive([base,variant]);
  assert.equal(archive.summary.unique_context_signatures,2);
  assert.equal(archive.summary.policy_equivalence_classes,1);
  assert.equal(archive.summary.behavioral_uniqueness_status,'CONTEXT_DIVERSITY_ONLY_POLICY_DIVERSITY_NOT_ESTABLISHED');
});

test('route IDs and labels are quotient-invariant', () => {
  const base=fixture('3'.repeat(64)); const variant=clone(base);
  variant.route.start_node_id='x1';
  variant.route.nodes=variant.route.nodes.map((node,index)=>({...node,node_id:`x${index+1}`,label:`Alternative words ${index}`}));
  variant.route.edges=variant.route.edges.map((edge,index)=>({...edge,edge_id:`z${index}`,from:edge.from==='n1'?'x1':edge.from==='n2'?'x2':'x3',to:edge.to==='n1'?'x1':edge.to==='n2'?'x2':'x3'}));
  assert.equal(signature(base),signature(variant));
});

test('route trigger changes create policy novelty', () => {
  const base=fixture('4'.repeat(64)); const variant=clone(base);
  variant.certificate.package_sha256='5'.repeat(64); variant.route.edges[1]!.trigger='handoff_ready';
  assert.notEqual(signature(base),signature(variant));
  const archive=buildScenarioBehavioralEquivalenceArchive([base,variant]);
  assert.equal(archive.summary.policy_equivalence_classes,2);
  assert.equal(archive.summary.behavioral_uniqueness_status,'EVERY_CANDIDATE_POLICY_DISTINCT');
});

test('source-bound action and information changes create policy novelty', () => {
  const base=fixture('6'.repeat(64)); const action=clone(base); const information=clone(base);
  action.scenario.expected_actions.critical[0]!.points=11;
  information.scenario.patients[0]!.hidden_findings.push('new finding');
  assert.notEqual(signature(base),signature(action));
  assert.notEqual(signature(base),signature(information));
});

test('archive identity is deterministic', () => {
  const a=fixture('7'.repeat(64)); const b=clone(a); b.certificate.package_sha256='8'.repeat(64); b.build.seed=2; b.scenario.operational_context.weather='rain';
  const first=buildScenarioBehavioralEquivalenceArchive([a,b]);
  const second=buildScenarioBehavioralEquivalenceArchive([b,a]);
  assert.deepEqual(first,second);
});


test('reviewed operational semantics distinguish equal-shaped route policies', () => {
  const communication=fixture('9'.repeat(64));
  communication.route.nodes[1]!.operational_semantic='communications_relay';
  const resource=clone(communication); resource.certificate.package_sha256='a'.repeat(64);
  resource.route.nodes[1]!.operational_semantic='resource_coordination';
  assert.notEqual(
    scenarioBehavioralPolicySignature(buildScenarioBehavioralPolicyDescriptor(communication)),
    scenarioBehavioralPolicySignature(buildScenarioBehavioralPolicyDescriptor(resource)),
  );
});


test('reviewed profile relabeling cannot create or collapse policy evidence', () => {
  const baseline=fixture('c'.repeat(64));
  const relabeled=clone(baseline);
  relabeled.certificate.package_sha256='d'.repeat(64);
  relabeled.route.route_id='R1:COMMUNICATION_RELAY_REQUIRED';
  assert.throws(
    () => buildScenarioBehavioralEquivalenceArchive([baseline,relabeled]),
    /collapses reviewed operational profiles/,
  );
});
