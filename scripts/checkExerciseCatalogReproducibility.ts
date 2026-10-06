import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const files = [
  resolve(root, 'content/exercises/toon/exercise_allocation.toon'),
  resolve(root, 'src/content/exercises/catalog.generated.ts'),
];

function hashFiles(): string {
  const hash = createHash('sha256');
  for (const file of files) hash.update(readFileSync(file));
  return hash.digest('hex');
}

function generate(): void {
  execFileSync(process.execPath, ['--import', 'tsx', 'scripts/generateExerciseCatalog.ts'], {
    cwd: root,
    stdio: 'pipe',
  });
}

generate();
const first = hashFiles();
generate();
const second = hashFiles();
if (first !== second) {
  throw new Error(`Exercise catalog is not reproducible: ${first} != ${second}`);
}
console.log(JSON.stringify({ status: 'PASS', catalog_sha256: first, runs_compared: 2 }, null, 2));
