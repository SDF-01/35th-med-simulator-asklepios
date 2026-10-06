import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readdir, readFile, stat } from 'node:fs/promises';
import { extname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const defaultRoot = resolve(fileURLToPath(new URL('..', import.meta.url)));
const textExtensions = new Set([
  '.ts', '.tsx', '.js', '.mjs', '.cjs', '.json', '.md', '.yml', '.yaml', '.toml', '.lean', '.css', '.html', '.txt', '.sh', '.py',
]);
const ignoredDirectories = new Set([
  '.git', '.asklepios', '.lake', '.mypy_cache', '.pytest_cache', '.ruff_cache', '.venv',
  '__pycache__', 'node_modules', 'dist', 'coverage', 'build',
]);
const reserved = [
  ['TERM_01', 3, 'acee0f8bfed6d6c859851ca993a63f424f0642cea4ef5f7b759a257b75d2e8b6'],
  ['TERM_02', 2, '2ce9470821a01a87ed199585320b26112b04b4bd9024ceb3aa35b7d916d61e7a'],
  ['TERM_03', 2, '638d2d923b3d21602bd8e58e1a3912bdf8c7bbc366ad2c4b23135454c05f4001'],
  ['TERM_04', 2, 'bd799eaeb71a8a4a6309c90b655f5866f44d3a77d026a7c260c77807ad9b9ac1'],
  ['TERM_05', 2, '48f48cb69192e11bd85549ea6309fbc8cde23d2e96fcc4f7ed143410fb478254'],
  ['TERM_06', 2, '9eacb534379aa7e50c555e20d9d81cf780e7ad52f487fe6387c8eb2496e29bb4'],
  ['TERM_07', 1, 'a0a803dfd9aefec4048268aeaf2aada67145eede963ba2f4c22d5dfca57a3d1a'],
  ['TERM_08', 2, '0c1e6b2b24d9626bce3f548fdb30467f77e698b64d13cc811a27ebe66bf0c0c3'],
  ['TERM_09', 5, 'ae14e4fb47fd92ae2ea2c7465d66c56142fed5bb878fafff2bc6c4c021c9c52b'],
  ['TERM_10', 4, '6cc7aafd4a7657388598fbcca689c47d68721ee9af8e79d96251eabacb7c0b59'],
  ['TERM_11', 3, '5565092836649a981871a9c847ef79a8739b2880fa05223c7436ddc4ba12de7e'],
  ['TERM_12', 3, '5061998af6c8712e854d892d09dbae96d57863c1097455bc5d46a4aa7e2bb12c'],
  ['TERM_13', 1, 'e123375a36c761365f1542008722e0c10464d55c44b538c50c6c9d40521719cc'],
  ['TERM_14', 1, '08af8acd5b6d479ebbf12aa8f0393e05f22595bd243637181416caf62e0872c0'],
] as const;

function digest(value: string): string {
  return createHash('sha256').update(value).digest('hex');
}

function isEligibleRelativePath(path: string): boolean {
  const normalized = path.replaceAll('\\', '/');
  const parts = normalized.split('/').filter(Boolean);
  return parts.length > 0
    && !parts.some((part) => ignoredDirectories.has(part))
    && textExtensions.has(extname(parts.at(-1) ?? '').toLowerCase());
}

async function walk(directory: string): Promise<string[]> {
  const output: string[] = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && ignoredDirectories.has(entry.name)) continue;
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) output.push(...await walk(path));
    else if (entry.isFile() && textExtensions.has(extname(entry.name).toLowerCase())) output.push(path);
  }
  return output;
}

function trackedVocabularyFiles(root: string): string[] | null {
  try {
    const output = execFileSync('git', ['ls-files', '-z', '--cached'], {
      cwd: root,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return output
      .split('\0')
      .filter(isEligibleRelativePath)
      .map((relativePath: string) => resolve(root, relativePath))
      .sort();
  } catch {
    return null;
  }
}

export async function repositoryVocabularyFiles(root = defaultRoot): Promise<string[]> {
  const tracked = trackedVocabularyFiles(root);
  if (tracked !== null) {
    const existing: string[] = [];
    for (const path of tracked) {
      try {
        if ((await stat(path)).isFile()) existing.push(path);
      } catch {
        // A tracked deletion is not readable and is handled by the repository diff gate.
      }
    }
    return existing;
  }
  return (await walk(root)).sort();
}

export interface RepositoryVocabularyFinding {
  code: string;
  file: string;
  token_offset: number;
}

export interface RepositoryVocabularyReport {
  status: 'PASS' | 'FAIL';
  findings: RepositoryVocabularyFinding[];
}

export async function checkRepositoryVocabulary(root = defaultRoot): Promise<RepositoryVocabularyReport> {
  const findings: RepositoryVocabularyFinding[] = [];
  for (const path of await repositoryVocabularyFiles(root)) {
    const content = await readFile(path, 'utf8');
    const tokens = content.toLowerCase().match(/[a-z0-9]+/g) ?? [];
    for (const [code, width, expected] of reserved) {
      for (let index = 0; index <= tokens.length - width; index += 1) {
        if (digest(tokens.slice(index, index + width).join(' ')) === expected) {
          findings.push({ code, file: relative(root, path), token_offset: index });
        }
      }
    }
  }
  return { status: findings.length === 0 ? 'PASS' : 'FAIL', findings };
}

const isMain = Boolean(process.argv[1])
  && resolve(process.argv[1]!) === fileURLToPath(import.meta.url);

if (isMain) {
  const report = await checkRepositoryVocabulary();
  console.log(JSON.stringify(report, null, 2));
  if (report.status !== 'PASS') process.exitCode = 3;
}
