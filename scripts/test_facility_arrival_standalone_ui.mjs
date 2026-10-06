#!/usr/bin/env node
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

const args = process.argv.slice(2);
const ri = args.indexOf('--repo');
const repo = resolve(ri >= 0 ? args[ri + 1] : '.');
const oi = args.indexOf('--output');
const output = resolve(repo, oi >= 0 ? args[oi + 1] : 'reports/facility-arrival-standalone-ui.json');
const html = readFileSync(resolve(repo, 'examples/facility-arrival/playable.html'), 'utf8');

function extract(tag, id) {
  const re = new RegExp(`<${tag}\\b[^>]*\\bid=["']${id}["'][^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i');
  const m = re.exec(html);
  if (!m) throw new Error(`missing ${tag}#${id}`);
  return m[1];
}

class FakeClassList {
  constructor() { this.values = new Set(); }
  add(...items) { items.forEach((value) => this.values.add(value)); }
  remove(...items) { items.forEach((value) => this.values.delete(value)); }
  toggle(value, force) {
    if (force === undefined) {
      if (this.values.has(value)) { this.values.delete(value); return false; }
      this.values.add(value); return true;
    }
    if (force) this.values.add(value); else this.values.delete(value);
    return Boolean(force);
  }
  contains(value) { return this.values.has(value); }
}

class FakeElement {
  constructor(document, { id = '', dataset = {} } = {}) {
    this.ownerDocument = document;
    this.id = id;
    this.dataset = { ...dataset };
    this.hidden = false;
    this.attributes = {};
    this.classList = new FakeClassList();
    this.listeners = new Map();
    this._text = '';
    this._html = '';
    this.href = '';
    this.download = '';
    this.clicked = 0;
  }
  set textContent(value) { this._text = String(value ?? ''); }
  get textContent() { return this._text; }
  set innerHTML(value) {
    this._html = String(value ?? '');
    if (this.id === 'actions') this.ownerDocument.refreshActions(this._html);
    if (this.id === 'profile-selector') this.ownerDocument.refreshProfiles(this._html);
  }
  get innerHTML() { return this._html; }
  addEventListener(type, fn) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(fn);
    this.listeners.set(type, listeners);
  }
  click() {
    this.clicked += 1;
    for (const fn of this.listeners.get('click') || []) fn({ currentTarget: this, target: this });
  }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key] ?? null; }
}

class FakeDocument {
  constructor(sourceHtml, dataText) {
    this.elements = new Map();
    this.dynamicActions = [];
    this.dynamicProfiles = [];
    this.created = [];
    for (const id of [...sourceHtml.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1])) {
      this.elements.set(id, new FakeElement(this, { id }));
    }
    this.elements.get('asklepios-scenario-data').textContent = dataText;
    this.tabs = [...sourceHtml.matchAll(/\bdata-tab="([^"]+)"/g)].map((match, index) => new FakeElement(this, { id: `tab-${index}`, dataset: { tab: match[1] } }));
    this.panels = [...sourceHtml.matchAll(/\bdata-panel="([^"]+)"/g)].map((match, index) => new FakeElement(this, { id: `panel-${index}`, dataset: { panel: match[1] } }));
  }
  getElementById(id) { return this.elements.get(id) || null; }
  querySelectorAll(selector) {
    if (selector === '[data-action]') return this.dynamicActions;
    if (selector === '[data-profile]') return this.dynamicProfiles;
    if (selector === '[data-tab]') return this.tabs;
    if (selector === '[data-panel]') return this.panels;
    return [];
  }
  refreshActions(markup) {
    this.dynamicActions = [...markup.matchAll(/\bdata-action="([^"]+)"/g)].map((match, index) => new FakeElement(this, { id: `action-${index}`, dataset: { action: match[1] } }));
  }
  refreshProfiles(markup) {
    this.dynamicProfiles = [...markup.matchAll(/\bdata-profile="([^"]+)"[^>]*aria-pressed="([^"]+)"/g)].map((match, index) => {
      const element = new FakeElement(this, { id: `profile-${index}`, dataset: { profile: match[1] } });
      element.setAttribute('aria-pressed', match[2]);
      return element;
    });
  }
  createElement() {
    const element = new FakeElement(this);
    this.created.push(element);
    return element;
  }
}

const dataText = extract('script', 'asklepios-scenario-data');
const document = new FakeDocument(html, dataText);
const errors = [];
const checks = [];
const check = (id, condition, detail = '') => {
  const pass = Boolean(condition);
  checks.push({ id, pass, detail: pass ? '' : String(detail) });
  if (!pass) errors.push(`${id}${detail ? `:${detail}` : ''}`);
};

let objectUrlCounter = 0;
const blobs = [];
const URLStub = {
  createObjectURL(blob) { blobs.push(blob); return `blob:offline-${++objectUrlCounter}`; },
  revokeObjectURL() {},
};
class BlobStub {
  constructor(parts, options) { this.parts = parts; this.options = options; }
}
const sandbox = { console, JSON, Math, Number, String, Object, Array, Set, Map, Error, Date, Blob: BlobStub, URL: URLStub, document };
sandbox.globalThis = sandbox;
sandbox.setTimeout = (fn) => { queueMicrotask(fn); return 1; };
sandbox.clearTimeout = () => {};
vm.createContext(sandbox);
vm.runInContext(extract('script', 'asklepios-engine'), sandbox, { filename: 'standalone-engine.js' });
vm.runInContext(extract('script', 'asklepios-ui'), sandbox, { filename: 'standalone-ui.js' });

const PROFILE_IDS = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];

check('ui_initialized', document.getElementById('status-badges').innerHTML.includes('active'));
check('initial_score', document.getElementById('score').textContent === '0.00%', document.getElementById('score').textContent);
check('initial_hidden_findings', document.getElementById('findings').innerHTML.includes('withheld'));
check('initial_actions_rendered', document.dynamicActions.some((item) => item.dataset.action === 'receive_handoff'));
check('initial_tabs', document.tabs.length === 3, String(document.tabs.length));
check('learner_panel_visible', document.panels.find((item) => item.dataset.panel === 'learner')?.hidden === false);
check('genome_badge_rendered', document.getElementById('status-badges').innerHTML.includes('Genome:'));
check('capability_ratchet_badge_rendered', document.getElementById('status-badges').innerHTML.includes('Capability epoch'));
check('technical_debt_ratchet_badge_rendered', document.getElementById('status-badges').innerHTML.includes('Debt epoch'));

check('profile_selector_present', Boolean(document.getElementById('profile-selector')));
check('four_profile_buttons_rendered', document.dynamicProfiles.length === 4, String(document.dynamicProfiles.length));
check('profile_ids_rendered', JSON.stringify(document.dynamicProfiles.map((item) => item.dataset.profile)) === JSON.stringify(PROFILE_IDS));
check('direct_profile_selected_by_default', document.dynamicProfiles.find((item) => item.dataset.profile === 'DIRECT_HANDOFF_BASELINE')?.getAttribute('aria-pressed') === 'true');
check('direct_profile_brief_rendered', document.getElementById('profile-brief').innerHTML.includes('Direct handoff baseline'));
check('direct_profile_badge_rendered', document.getElementById('status-badges').innerHTML.includes('Challenge: Direct handoff baseline'));

const receive = document.dynamicActions.find((item) => item.dataset.action === 'receive_handoff');
receive?.click();
check('manual_action_updates_time', document.getElementById('elapsed').textContent !== '0:00', document.getElementById('elapsed').textContent);
check('manual_action_updates_timeline', document.getElementById('timeline').innerHTML.includes('learner_action') || document.getElementById('timeline').innerHTML.includes('Learner Action'));
document.getElementById('reset').click();
check('reset_restores_zero', document.getElementById('elapsed').textContent === '0:00');

// Play all four role-model examples through the actual UI selector and canonical replay.
const profileUiResults = [];
for (const profileId of PROFILE_IDS) {
  const button = document.dynamicProfiles.find((item) => item.dataset.profile === profileId);
  check(`${profileId}:selector_button_exists`, Boolean(button));
  button?.click();
  check(`${profileId}:selected_state`, document.dynamicProfiles.find((item) => item.dataset.profile === profileId)?.getAttribute('aria-pressed') === 'true');
  const expectedLabel = {
    DIRECT_HANDOFF_BASELINE: 'Direct handoff baseline',
    COMMUNICATION_RELAY_REQUIRED: 'Communications relay',
    RESOURCE_COORDINATION_REQUIRED: 'Resource coordination',
    DUAL_CONSTRAINT_RELAY_AND_COORDINATION: 'Relay and resource coordination',
  }[profileId];
  check(`${profileId}:brief_updated`, document.getElementById('profile-brief').innerHTML.includes(expectedLabel), document.getElementById('profile-brief').innerHTML);
  check(`${profileId}:header_updated`, document.getElementById('status-badges').innerHTML.includes(`Challenge: ${expectedLabel}`));
  document.getElementById('canonical').click();
  check(`${profileId}:canonical_completed`, document.getElementById('status-badges').innerHTML.includes('completed'));
  check(`${profileId}:canonical_score`, document.getElementById('score').textContent === '100.00%', document.getElementById('score').textContent);
  check(`${profileId}:aar_profile`, document.getElementById('aar').innerHTML.includes(expectedLabel));
  check(`${profileId}:aar_teamwork_pass`, document.getElementById('aar').innerHTML.includes('PASS'));
  if (profileId === 'COMMUNICATION_RELAY_REQUIRED' || profileId === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') {
    check(`${profileId}:relay_visible_in_timeline`, document.getElementById('timeline').innerHTML.includes('Establish a communications relay and confirm message receipt'));
  }
  if (profileId === 'RESOURCE_COORDINATION_REQUIRED' || profileId === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') {
    check(`${profileId}:resource_visible_in_timeline`, document.getElementById('timeline').innerHTML.includes('Coordinate the constrained resource and confirm ownership'));
  }
  profileUiResults.push({ profile_id: profileId, status: 'completed', score: document.getElementById('score').textContent });
}

check('canonical_findings_revealed', !document.getElementById('findings').innerHTML.includes('withheld'));
check('canonical_timeline', document.getElementById('timeline').innerHTML.includes('Complete'));

document.getElementById('timeout').click();
check('timeout_status', document.getElementById('status-badges').innerHTML.includes('timeout'));
check('timeout_findings_hidden', document.getElementById('findings').innerHTML.includes('withheld'));
document.getElementById('unsafe-discharge').click();
check('unsafe_discharge_failed', document.getElementById('status-badges').innerHTML.includes('failed'));
document.getElementById('unsafe-tourniquet').click();
check('unsafe_tourniquet_failed', document.getElementById('status-badges').innerHTML.includes('failed'));

document.tabs.find((item) => item.dataset.tab === 'wit').click();
check('wit_panel_visible', document.panels.find((item) => item.dataset.panel === 'wit')?.hidden === false);
check('learner_panel_hidden', document.panels.find((item) => item.dataset.panel === 'learner')?.hidden === true);
document.tabs.find((item) => item.dataset.tab === 'provenance').click();
check('provenance_panel_visible', document.panels.find((item) => item.dataset.panel === 'provenance')?.hidden === false);
check('provenance_rendered', document.getElementById('provenance-table').innerHTML.includes('Content registry root'));
check('provenance_genome_rendered', document.getElementById('provenance-table').innerHTML.includes('Scenario Genome'));
check('provenance_ratchet_rendered', document.getElementById('provenance-table').innerHTML.includes('Capability ratchet'));
check('provenance_debt_ratchet_rendered', document.getElementById('provenance-table').innerHTML.includes('Technical-debt ratchet'));
check('provenance_graph_rendered', document.getElementById('provenance-table').innerHTML.includes('Release graph'));
check('provenance_role_model_contract_rendered', document.getElementById('provenance-table').innerHTML.includes('Role-model profile contract'));

// Select the dual challenge before export so the saved report proves the selected profile is bound.
document.dynamicProfiles.find((item) => item.dataset.profile === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION')?.click();
document.getElementById('canonical').click();
document.getElementById('save').click();
const anchor = document.created.at(-1);
check('export_created', Boolean(anchor?.download?.startsWith('asklepios-dual_constraint_relay_and_coordination-run-')), anchor?.download || '');
const exported = blobs.at(-1)?.parts?.join('') || '';
check('export_binds_selected_profile', exported.includes('DUAL_CONSTRAINT_RELAY_AND_COORDINATION') && exported.includes('ASK-OFFLINE-RM-DUAL'));

// Autoplay the communications-relay profile through the actual UI route.
document.dynamicProfiles.find((item) => item.dataset.profile === 'COMMUNICATION_RELAY_REQUIRED')?.click();
document.getElementById('autoplay').click();
await new Promise((resolvePromise) => setTimeout(resolvePromise, 25));
check('autoplay_completed', document.getElementById('status-badges').innerHTML.includes('completed'));
check('autoplay_score', document.getElementById('score').textContent === '100.00%', document.getElementById('score').textContent);
check('autoplay_relay_profile', document.getElementById('aar').innerHTML.includes('Communications relay'));

const report = {
  schema_version: '1.1.0',
  status: errors.length ? 'FAIL' : 'PASS',
  runtime: 'node:vm-minimal-dom-v2',
  checks: checks.length,
  playable_role_model_profiles: profileUiResults.length,
  role_model_results: profileUiResults,
  results: checks,
  errors,
};
mkdirSync(resolve(output, '..'), { recursive: true });
writeFileSync(output, JSON.stringify(report, null, 2) + '\n', 'utf8');
console.log(JSON.stringify(report, null, 2));
process.exit(errors.length ? 3 : 0);
