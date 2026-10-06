#!/usr/bin/env node
import fs from 'node:fs';
import crypto from 'node:crypto';
const SAFE=Number.MAX_SAFE_INTEGER;
const normalize=(v)=>{if(v===null||typeof v==='string'||typeof v==='boolean')return v;if(typeof v==='number'){if(!Number.isSafeInteger(v))throw new Error('unsafe number');return v;}if(Array.isArray(v))return v.map(normalize);if(typeof v==='object'){const o={};for(const k of Object.keys(v).sort())o[k]=normalize(v[k]);return o;}throw new Error('unsupported value')};
const canonical=(v)=>JSON.stringify(normalize(v));
const hash=(v)=>crypto.createHash('sha256').update(canonical(v),'utf8').digest('hex');
const fileHash=(p)=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const root=(domain,hashes)=>hash({domain,hashes:[...hashes].sort()});
const reg=JSON.parse(fs.readFileSync('public/data/content_registry/content_registry.json','utf8')); const errors=[]; let checks=0;
const defs={assets:['record_sha256','asklepios.content-registry.assets.v1'],relations:['relation_sha256','asklepios.content-registry.relations.v1'],agents:['record_sha256','asklepios.content-registry.agents.v1'],activities:['record_sha256','asklepios.content-registry.activities.v1'],evidence_attestations:['attestation_sha256','asklepios.content-registry.evidence-attestations.v1'],claim_candidates:['claim_sha256','asklepios.content-registry.claim-candidates.v1'],compatibility_profiles:['profile_sha256','asklepios.content-registry.compatibility-profiles.v1']};
const roots={};
for(const [name,[hf,domain]] of Object.entries(defs)){const hashes=[];const ids=new Set();for(const rec of reg[name]??[]){const copy=structuredClone(rec);const observed=copy[hf];delete copy[hf];const expected=hash(copy);if(observed!==expected)errors.push(`record hash mismatch:${name}`);hashes.push(expected);checks++;}roots[`${name}_merkle_root`]=root(domain,hashes);}
const sourceFiles=[];for(const row of reg.source_snapshot.source_files){if(!fs.existsSync(row.path))errors.push(`source file missing:${row.path}`);else{const observed={path:row.path,bytes:fs.statSync(row.path).size,sha256:fileHash(row.path)};sourceFiles.push(observed);if(observed.bytes!==row.bytes||observed.sha256!==row.sha256)errors.push(`source binding mismatch:${row.path}`);}checks++;}
const sm=hash({domain:'asklepios.content-registry.source-manifest.v1',files:sourceFiles.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0)});if(sm!==reg.source_snapshot.source_manifest_sha256)errors.push('source manifest mismatch');
roots.registry_merkle_root=hash({domain:'asklepios.content-registry.v1',source_manifest_sha256:reg.source_snapshot.source_manifest_sha256,authority_model_sha256:hash(reg.authority_model),release_boundary_sha256:hash(reg.release_boundary),component_roots:Object.fromEntries(Object.keys(roots).sort().map(k=>[k,roots[k]]))});
for(const [k,v] of Object.entries(roots))if(reg.roots[k]!==v)errors.push(`root mismatch:${k}`);
const forbidden=new Set(['define_new_clinical_rule','define_scoring_truth','define_physiology','define_medication_dose','define_provider_scope']);for(const a of reg.assets){if(a.capabilities.some(x=>forbidden.has(x)))errors.push(`forbidden capability:${a.asset_id}`);if(a.kind==='scenario_seed'&&a.status!=='seed_only_not_deployable')errors.push(`seed active:${a.asset_id}`);}
for(const a of reg.evidence_attestations){if(a.relation!=='REFERENCE_ONLY'||a.entailment_status!=='NOT_ADJUDICATED'||a.human_review_status!=='NOT_REVIEWED'||a.clinical_authority!=='NOT_GRANTED')errors.push(`evidence escalation:${a.attestation_id}`)}
for(const c of reg.claim_candidates){if(c.support_bit!==false||c.refute_bit!==false||c.relation!=='UNRESOLVED'||c.admission_status!=='BLOCKED_FOR_SUPPORT_CLAIM')errors.push(`claim escalation:${c.claim_id}`)}
for(const p of reg.compatibility_profiles)if(!['ACTIVATION_CANDIDATE','BLOCKED_PENDING_ENGINE_PROFILE'].includes(p.activation_status))errors.push(`automatic activation:${p.profile_id}`);
if(reg.release_boundary.clinical_authority!=='NOT_GRANTED'||reg.release_boundary.contains_licensed_source_text!==false)errors.push('release boundary escalation');
const report={schema_version:'1.0.0',status:errors.length?'FAIL':'PASS',checks,registry_merkle_root:roots.registry_merkle_root,errors:[...new Set(errors)].sort()};console.log(JSON.stringify(report,null,2));process.exit(errors.length?3:0);
