#!/usr/bin/env node
/** Adversarial regression suite for the shared Node checker CLI/report boundary. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { spawnSync } from 'node:child_process';
import {
  atomicWriteJson,
  emitCheckerResult,
  parseCheckerArgs,
  resolveRepoPath,
} from './node_checker_cli.mjs';

const CLASSIFICATIONS = new Set(['PASS', 'EXPECTED_REJECTION', 'FAIL', 'INTERNAL_ERROR']);

function parseSuiteArgs(argv) {
  let repo = '.';
  let output = 'reports/node-checker-cli-mutations.json';
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--repo') {
      if (index + 1 >= argv.length) throw new Error('suite --repo value missing');
      repo = argv[++index];
    } else if (token === '--json-output' || token === '--report') {
      if (index + 1 >= argv.length) throw new Error('suite report value missing');
      output = argv[++index];
    } else {
      throw new Error(`suite unknown argument:${token}`);
    }
  }
  return { repo: path.resolve(repo), output };
}

function caseResult(caseId, expectedPass, observedPass, observedErrors = []) {
  const pass = expectedPass === observedPass;
  return {
    case_id: caseId,
    classification: pass ? (expectedPass ? 'PASS' : 'EXPECTED_REJECTION') : 'FAIL',
    status: pass ? (expectedPass ? 'PASS' : 'EXPECTED_REJECTION') : 'FAIL',
    expected_pass: expectedPass,
    observed_pass: observedPass,
    pass,
    errors: pass ? [] : [`expected ${expectedPass ? 'PASS' : 'REJECTION'} but observed ${observedPass ? 'PASS' : 'REJECTION'}`],
    observed_errors: [...new Set(observedErrors.map(String))].sort(),
  };
}

function runCase(caseId, expectedPass, action, expectedError = null) {
  try {
    action();
    if (expectedPass) return caseResult(caseId, true, true);
    return caseResult(caseId, false, true, ['attack was accepted']);
  } catch (error) {
    const observed = `${error?.name ?? 'Error'}:${error?.message ?? String(error)}`;
    const errorMatches = expectedError === null || observed.includes(expectedError);
    if (!expectedPass && errorMatches) return caseResult(caseId, false, false, [observed]);
    return caseResult(caseId, expectedPass, false, [observed, ...(expectedError && !errorMatches ? [`required error missing:${expectedError}`] : [])]);
  }
}

function parseJsonOutput(text) {
  const trimmed = String(text ?? '').trim();
  if (!trimmed) throw new Error('checker emitted no JSON');
  const value = JSON.parse(trimmed);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('checker JSON root is not an object');
  if (!CLASSIFICATIONS.has(value.classification)) throw new Error(`checker classification invalid:${value.classification}`);
  return value;
}

function runChecker(repo, checker, args, cwd) {
  const result = spawnSync(process.execPath, [path.join(repo, checker), ...args], {
    cwd,
    encoding: 'utf8',
    timeout: 120_000,
    windowsHide: true,
  });
  if (result.error) throw result.error;
  const value = parseJsonOutput(result.stdout);
  return { result, value };
}

const suiteArgs = parseSuiteArgs(process.argv.slice(2));
const repo = suiteArgs.repo;
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'asklepios-node-cli-'));
const externalCwd = fs.mkdtempSync(path.join(os.tmpdir(), 'asklepios-node-cli-cwd-'));
const fixtureRepo = path.join(tempRoot, 'repo');
fs.mkdirSync(fixtureRepo, { recursive: true });
const results = [];

try {
  results.push(runCase('default_arguments', true, () => {
    const value = parseCheckerArgs([], { allowPositionalRepo: true });
    if (value.repo !== process.cwd()) throw new Error('default repository differs');
    if (value.report !== null) throw new Error('default report differs');
  }));
  results.push(runCase('explicit_repo_and_report', true, () => {
    const value = parseCheckerArgs(['--repo', fixtureRepo, '--report', 'reports/a.json'], { allowPositionalRepo: true });
    if (value.repo !== path.resolve(fixtureRepo) || value.report !== 'reports/a.json') throw new Error('explicit arguments differ');
  }));
  results.push(runCase('json_output_alias', true, () => {
    const value = parseCheckerArgs(['--repo', fixtureRepo, '--json-output', 'reports/a.json'], { allowPositionalRepo: true });
    if (value.report !== 'reports/a.json' || value.reportFlag !== '--json-output') throw new Error('JSON output alias differs');
  }));
  results.push(runCase('legacy_single_positional_repo', true, () => {
    const value = parseCheckerArgs([fixtureRepo], { allowPositionalRepo: true });
    if (value.repo !== path.resolve(fixtureRepo)) throw new Error('positional repository differs');
  }));
  results.push(runCase('unknown_option_rejected', false, () => parseCheckerArgs(['--unknown'], { allowPositionalRepo: true }), "Unknown option '--unknown'"));
  results.push(runCase('missing_repo_value_rejected', false, () => parseCheckerArgs(['--repo'], { allowPositionalRepo: true }), "Option '--repo <value>' argument missing"));
  results.push(runCase('conflicting_report_aliases_rejected', false, () => parseCheckerArgs(['--repo', fixtureRepo, '--report', 'a.json', '--json-output', 'b.json'], { allowPositionalRepo: true }), 'report path supplied through both'));
  results.push(runCase('duplicate_repo_forms_rejected', false, () => parseCheckerArgs(['--repo', fixtureRepo, fixtureRepo], { allowPositionalRepo: true }), 'repository path supplied both positionally and through --repo'));
  results.push(runCase('atomic_nested_report_write', true, () => {
    const destination = atomicWriteJson(fixtureRepo, 'nested/reports/result.json', { z: 1, a: true });
    const text = fs.readFileSync(destination, 'utf8');
    if (text !== '{\n  "a": true,\n  "z": 1\n}\n') throw new Error('atomic report bytes differ');
    if (fs.readdirSync(path.dirname(destination)).some((name) => name.includes('.tmp-'))) throw new Error('temporary report leaked');
  }));
  results.push(runCase('report_traversal_rejected', false, () => atomicWriteJson(fixtureRepo, '../escape.json', {}), 'report path contains traversal component'));
  results.push(runCase('report_windows_separator_rejected', false, () => atomicWriteJson(fixtureRepo, 'reports\\escape.json', {}), 'report path uses Windows separator'));
  results.push(runCase('report_absolute_path_rejected', false, () => atomicWriteJson(fixtureRepo, path.resolve(tempRoot, 'escape.json'), {}), 'report path is absolute'));
  results.push(runCase('report_symlink_parent_rejected', false, () => {
    const outside = path.join(tempRoot, 'outside');
    fs.mkdirSync(outside, { recursive: true });
    fs.symlinkSync(outside, path.join(fixtureRepo, 'linked'), process.platform === 'win32' ? 'junction' : 'dir');
    atomicWriteJson(fixtureRepo, 'linked/report.json', {});
  }, 'report parent is unsafe'));
  results.push(runCase('report_symlink_destination_rejected', false, () => {
    const target = path.join(fixtureRepo, 'real.json');
    fs.writeFileSync(target, '{}\n');
    fs.symlinkSync(target, path.join(fixtureRepo, 'report-link.json'), 'file');
    atomicWriteJson(fixtureRepo, 'report-link.json', {});
  }, 'report destination is a symlink'));

  const checkerCases = [
    ['verified-example', 'scripts/check_verified_example_scenario.mjs'],
    ['scenario-genome', 'scripts/check_scenario_genome.mjs'],
    ['offline-release', 'scripts/check_offline_scenario_release.mjs'],
  ];
  for (const [label, checker] of checkerCases) {
    results.push(runCase(`${label}_explicit_repo_external_cwd`, true, () => {
      const report = `.asklepios/node-cli-test/${label}.json`;
      const { result, value } = runChecker(repo, checker, ['--repo', repo, '--json-output', report], externalCwd);
      try {
        if (result.status !== 0 || value.classification !== 'PASS') throw new Error(`checker did not pass:${value.errors ?? []}`);
        const persisted = JSON.parse(fs.readFileSync(resolveRepoPath(repo, report, { allowMissing: false }), 'utf8'));
        if (persisted.classification !== 'PASS') throw new Error('persisted checker report differs');
      } finally {
        fs.rmSync(path.join(repo, '.asklepios/node-cli-test'), { recursive: true, force: true });
      }
    }));
    results.push(runCase(`${label}_unknown_option_structured_rejection`, true, () => {
      const { result, value } = runChecker(repo, checker, ['--unknown'], externalCwd);
      if (result.status !== 3 || value.classification !== 'FAIL') throw new Error('unknown option was not a structured FAIL');
      if (!Array.isArray(value.errors) || !value.errors.some((item) => String(item).includes('Unknown option'))) throw new Error('unknown-option diagnostic missing');
    }));
  }
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true });
  fs.rmSync(externalCwd, { recursive: true, force: true });
}

const classification = results.every((item) => item.pass) ? 'PASS' : 'FAIL';
const report = {
  schema_version: '1.0.0',
  classification,
  status: classification,
  cases: results.length,
  expected_rejections: results.filter((item) => item.classification === 'EXPECTED_REJECTION').length,
  accepted_attacks: results.filter((item) => item.expected_pass === false && item.observed_pass === true).length,
  checker_count: 3,
  errors: results.flatMap((item) => item.errors).sort(),
  results,
  boundary: 'One strict, cross-platform CLI and report-path contract is shared by every Node scenario release checker.',
};
process.exit(emitCheckerResult(report, { repo, report: suiteArgs.output }));
