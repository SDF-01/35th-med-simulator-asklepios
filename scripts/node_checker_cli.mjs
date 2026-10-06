#!/usr/bin/env node
/**
 * Shared strict CLI and atomic report boundary for Node release checkers.
 *
 * This module intentionally owns only transport concerns: argument parsing,
 * repository-relative path confinement, symlink rejection, canonical JSON, and
 * atomic report replacement. Domain checkers remain independently implemented.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const WINDOWS_DRIVE = /^[A-Za-z]:/;
const WINDOWS_RESERVED = new Set([
  'CON', 'PRN', 'AUX', 'NUL',
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
]);

export class CheckerContractError extends Error {
  constructor(message) {
    super(message);
    this.name = 'CheckerContractError';
  }
}

function fail(message) {
  throw new CheckerContractError(message);
}

function assertPortableRelative(relative, label = 'path') {
  if (typeof relative !== 'string' || relative.length === 0) fail(`${label} is missing`);
  if (relative.includes('\0')) fail(`${label} contains NUL`);
  if (relative.includes('\\')) fail(`${label} uses Windows separator`);
  if (path.posix.isAbsolute(relative) || WINDOWS_DRIVE.test(relative)) fail(`${label} is absolute`);
  const parts = relative.split('/');
  if (parts.includes('..')) fail(`${label} contains traversal component`);
  if (parts.some((part) => part === '' || part === '.')) fail(`${label} contains empty or dot component`);
  for (const part of parts) {
    if (part.includes(':')) fail(`${label} contains colon component`);
    if (part.endsWith('.') || part.endsWith(' ')) fail(`${label} has unsafe trailing character`);
    const stem = part.split('.', 1)[0].toUpperCase();
    if (WINDOWS_RESERVED.has(stem)) fail(`${label} contains Windows reserved component:${part}`);
  }
  return parts;
}

function lstatIfExists(file) {
  try {
    return fs.lstatSync(file);
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw error;
  }
}

function assertDirectoryChain(root, parts, label, { allowMissing = true } = {}) {
  let current = root;
  for (let index = 0; index < parts.length; index += 1) {
    current = path.join(current, parts[index]);
    const info = lstatIfExists(current);
    if (!info) {
      if (!allowMissing) fail(`${label} parent is unsafe:${parts.join('/')}`);
      break;
    }
    if (info.isSymbolicLink() || (index < parts.length - 1 && !info.isDirectory())) {
      fail(`${label} parent is unsafe:${parts.join('/')}`);
    }
  }
}

export function parseCheckerArgs(argv, options = {}) {
  const outputFlags = new Set(options.outputFlags ?? ['--report', '--json-output']);
  const allowPositionalRepo = options.allowPositionalRepo ?? false;
  let repo = null;
  let report = null;
  let outputFlag = null;
  let afterSeparator = false;

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--' && !afterSeparator) {
      afterSeparator = true;
      continue;
    }
    if (!afterSeparator && token === '--repo') {
      if (repo !== null) fail('repository path supplied more than once');
      if (index + 1 >= argv.length) throw new TypeError("Option '--repo <value>' argument missing");
      repo = argv[++index];
      continue;
    }
    if (!afterSeparator && outputFlags.has(token)) {
      if (index + 1 >= argv.length) throw new TypeError(`Option '${token} <value>' argument missing`);
      if (report !== null) fail(`report path supplied through both ${outputFlag} and ${token}`);
      outputFlag = token;
      report = argv[++index];
      continue;
    }
    if (!afterSeparator && token.startsWith('-')) throw new TypeError(`Unknown option '${token}'`);
    if (!allowPositionalRepo) fail(`unexpected positional argument:${token}`);
    if (repo !== null) fail('repository path supplied both positionally and through --repo');
    repo = token;
  }

  const root = path.resolve(repo ?? '.');
  const info = lstatIfExists(root);
  if (!info || !info.isDirectory() || info.isSymbolicLink()) fail(`repository root is unsafe or missing:${root}`);
  return { repo: root, report, reportFlag: outputFlag };
}

export function resolveRepoPath(repo, relative, options = {}) {
  const root = path.resolve(repo);
  const rootInfo = lstatIfExists(root);
  if (!rootInfo || !rootInfo.isDirectory() || rootInfo.isSymbolicLink()) fail(`repository root is unsafe or missing:${root}`);
  const label = options.label ?? 'path';
  const parts = assertPortableRelative(relative, label);
  assertDirectoryChain(root, parts, label, { allowMissing: options.allowMissing ?? true });
  const candidate = path.join(root, ...parts);
  const rel = path.relative(root, path.resolve(candidate));
  if (rel === '..' || rel.startsWith(`..${path.sep}`) || path.isAbsolute(rel)) fail(`${label} escapes repository:${relative}`);
  if (!(options.allowMissing ?? true)) {
    const info = lstatIfExists(candidate);
    if (!info || !info.isFile() || info.isSymbolicLink()) fail(`unsafe or missing regular file:${relative}`);
  }
  return candidate;
}

function normalize(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) fail(`non-safe or non-integer number:${location}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => normalize(item, `${location}[${index}]`));
  if (typeof value === 'object') {
    const output = {};
    for (const key of Object.keys(value).sort()) output[key] = normalize(value[key], `${location}.${key}`);
    return output;
  }
  fail(`unsupported canonical type:${location}:${typeof value}`);
}

export function canonicalJson(value) {
  return JSON.stringify(normalize(value));
}

export function atomicWriteJson(repo, reportPath, value) {
  const parts = assertPortableRelative(reportPath, 'report path');
  const root = path.resolve(repo);
  const parentParts = parts.slice(0, -1);
  const destination = path.join(root, ...parts);
  const parent = path.join(root, ...parentParts);

  assertDirectoryChain(root, parentParts, 'report', { allowMissing: true });
  fs.mkdirSync(parent, { recursive: true, mode: 0o755 });
  assertDirectoryChain(root, parentParts, 'report', { allowMissing: false });

  const existing = lstatIfExists(destination);
  if (existing?.isSymbolicLink()) fail(`report destination is a symlink:${reportPath}`);
  if (existing && !existing.isFile()) fail(`report destination is not a regular file:${reportPath}`);

  const payload = `${JSON.stringify(normalize(value), null, 2)}\n`;
  const temporary = path.join(parent, `.${path.basename(destination)}.tmp-${process.pid}-${crypto.randomBytes(12).toString('hex')}`);
  let descriptor;
  try {
    descriptor = fs.openSync(temporary, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY, 0o644);
    fs.writeFileSync(descriptor, payload, { encoding: 'utf8' });
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;
    // Recheck immediately before replacement so a changed parent cannot redirect
    // an ordinary CI write outside the repository.
    assertDirectoryChain(root, parentParts, 'report', { allowMissing: false });
    fs.renameSync(temporary, destination);
    try {
      const parentDescriptor = fs.openSync(parent, fs.constants.O_RDONLY);
      try { fs.fsyncSync(parentDescriptor); } finally { fs.closeSync(parentDescriptor); }
    } catch (error) {
      // Directory fsync is not available on every supported platform. The file
      // replacement remains atomic even when this durability enhancement is absent.
      if (!['EINVAL', 'EPERM', 'EISDIR', 'EBADF'].includes(error?.code)) throw error;
    }
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
    try { fs.unlinkSync(temporary); } catch (error) { if (error?.code !== 'ENOENT') throw error; }
  }
  return destination;
}

export function normalizedFailure(error, profile = 'NODE_CHECKER_CLI_V2') {
  return {
    schema_version: '1.0.0',
    classification: 'FAIL',
    status: 'FAIL',
    checker_profile: profile,
    errors: [`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`],
  };
}

export function emitCheckerResult(result, { repo = '.', report = null } = {}) {
  let output = result;
  try {
    if (!output || typeof output !== 'object' || Array.isArray(output)) fail('checker result is not an object');
    output = { ...output };
    if (typeof output.classification !== 'string') output.classification = output.status ?? 'INTERNAL_ERROR';
    if (typeof output.status !== 'string') output.status = output.classification;
    if (!['PASS', 'EXPECTED_REJECTION', 'FAIL', 'INTERNAL_ERROR'].includes(output.classification)) fail(`unsupported classification:${output.classification}`);
    if (!Array.isArray(output.errors)) output.errors = [];
    output.errors = [...new Set(output.errors.map(String).filter(Boolean))].sort();
    if (report !== null) atomicWriteJson(repo, report, output);
  } catch (error) {
    output = {
      schema_version: '1.0.0',
      classification: 'INTERNAL_ERROR',
      status: 'INTERNAL_ERROR',
      errors: [`${error?.name ?? 'Error'}:${error?.message ?? String(error)}`],
    };
  }
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  if (output.classification === 'PASS' || output.classification === 'EXPECTED_REJECTION') return 0;
  if (output.classification === 'INTERNAL_ERROR') return 4;
  return 3;
}
