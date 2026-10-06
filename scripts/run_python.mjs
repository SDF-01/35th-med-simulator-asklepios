#!/usr/bin/env node
/**
 * Run a Python script with a deterministic interpreter selection policy.
 *
 * Priority:
 *   1. ASKLEPIOS_PYTHON (explicit operator override)
 *   2. Python_ROOT_DIR from actions/setup-python
 *   3. platform PATH candidates
 *
 * Every candidate is probed and must be Python 3.12 or newer. The interpreter
 * selected by actions/setup-python therefore cannot be silently bypassed by a
 * different Windows `py -3` installation.
 */
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import process from 'node:process';

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('usage: node scripts/run_python.mjs <script-or-module-args...>');
  process.exit(2);
}

const minimum = [3, 12, 0];

function candidate(command, prefix = [], source = 'fallback') {
  return { command, prefix, source, key: `${command}\u0000${prefix.join('\u0000')}` };
}

function unique(items) {
  const observed = new Set();
  return items.filter((item) => {
    if (!item.command || observed.has(item.key)) return false;
    observed.add(item.key);
    return true;
  });
}

const strictGroups = [];
const explicit = process.env.ASKLEPIOS_PYTHON?.trim();
if (explicit) {
  strictGroups.push({
    source: 'ASKLEPIOS_PYTHON',
    candidates: [candidate(explicit, [], 'ASKLEPIOS_PYTHON')],
  });
}

const configuredRoot = process.env.Python_ROOT_DIR?.trim();
if (configuredRoot) {
  const rootCandidates = process.platform === 'win32'
    ? [candidate(join(configuredRoot, 'python.exe'), [], 'Python_ROOT_DIR')]
    : [
        candidate(join(configuredRoot, 'bin', 'python3'), [], 'Python_ROOT_DIR'),
        candidate(join(configuredRoot, 'bin', 'python'), [], 'Python_ROOT_DIR'),
      ];
  strictGroups.push({ source: 'Python_ROOT_DIR', candidates: unique(rootCandidates) });
}

const fallbackCandidates = process.platform === 'win32'
  ? unique([
      candidate('python', [], 'PATH'),
      candidate('python3', [], 'PATH'),
      candidate('py', ['-3'], 'Windows launcher'),
    ])
  : unique([
      candidate('python3', [], 'PATH'),
      candidate('python', [], 'PATH'),
    ]);

const probeSource = [
  'import json,sys',
  'print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3])},sort_keys=True))',
].join(';');

function versionAtLeast(observed, required) {
  for (let index = 0; index < required.length; index += 1) {
    const left = Number(observed[index] ?? 0);
    const right = Number(required[index] ?? 0);
    if (left > right) return true;
    if (left < right) return false;
  }
  return true;
}

function probe(item) {
  const result = spawnSync(
    item.command,
    [...item.prefix, '-c', probeSource],
    { encoding: 'utf8', shell: false },
  );

  if (result.error?.code === 'ENOENT') {
    return { ok: false, detail: 'not found' };
  }
  if (result.error) {
    return { ok: false, detail: result.error.message };
  }
  if (result.signal) {
    return { ok: false, detail: `terminated by signal ${result.signal}` };
  }
  if (result.status !== 0) {
    return {
      ok: false,
      detail: (result.stderr || result.stdout || `status ${result.status}`).trim(),
    };
  }

  let payload;
  try {
    const lines = result.stdout.split(/\r?\n/u).map((line) => line.trim()).filter(Boolean);
    payload = JSON.parse(lines.at(-1) ?? '');
  } catch (error) {
    return { ok: false, detail: `malformed probe output: ${error.message}` };
  }

  if (!Array.isArray(payload.version) || !versionAtLeast(payload.version, minimum)) {
    const rendered = Array.isArray(payload.version) ? payload.version.join('.') : 'unknown';
    return { ok: false, detail: `Python ${rendered}; Python 3.12+ is required` };
  }
  if (typeof payload.executable !== 'string' || payload.executable.length === 0) {
    return { ok: false, detail: 'probe omitted sys.executable' };
  }
  return { ok: true, payload };
}

let selected = null;
for (const group of strictGroups) {
  const failures = [];
  for (const item of group.candidates) {
    const outcome = probe(item);
    if (outcome.ok) {
      selected = { ...item, payload: outcome.payload };
      break;
    }
    failures.push(`${item.command}: ${outcome.detail}`);
  }
  if (selected) break;
  console.error(`configured Python group could not be used (${group.source}): ${failures.join('; ')}`);
  process.exit(127);
}

if (!selected) {
  for (const item of fallbackCandidates) {
    const outcome = probe(item);
    if (outcome.ok) {
      selected = { ...item, payload: outcome.payload };
      break;
    }
  }
}

if (!selected) {
  console.error('No supported Python 3.12+ interpreter was found. Install Python 3.12+ and retry.');
  process.exit(127);
}

const result = spawnSync(
  selected.command,
  [...selected.prefix, ...args],
  {
    stdio: 'inherit',
    shell: false,
    env: {
      ...process.env,
      ASKLEPIOS_SELECTED_PYTHON: selected.payload.executable,
    },
  },
);

if (result.error) {
  console.error(`failed to start ${selected.command}: ${result.error.message}`);
  process.exit(127);
}
if (result.signal) {
  console.error(`${selected.command} terminated by signal ${result.signal}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
