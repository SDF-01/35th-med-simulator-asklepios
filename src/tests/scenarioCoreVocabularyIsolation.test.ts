import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { relative, resolve } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { repositoryVocabularyFiles } from '../../scripts/checkRepositoryVocabulary';

async function withTemporaryRoot(run: (root: string) => Promise<void>): Promise<void> {
  const root = await mkdtemp(resolve(tmpdir(), 'asklepios-vocabulary-boundary-'));
  try {
    await run(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test('repository vocabulary scans tracked text and excludes release-runtime debris', async () => {
  await withTemporaryRoot(async (root) => {
    await mkdir(resolve(root, 'src'), { recursive: true });
    await mkdir(resolve(root, '.asklepios/release-receipts'), { recursive: true });
    await writeFile(resolve(root, 'src/tracked.ts'), 'export const safe = true;\n', 'utf8');
    await writeFile(resolve(root, '.asklepios/release-receipts/transient.json'), '{"runtime":true}\n', 'utf8');
    await writeFile(resolve(root, 'untracked.md'), 'transient diagnostic\n', 'utf8');
    execFileSync('git', ['init', '--quiet'], { cwd: root });
    execFileSync('git', ['add', 'src/tracked.ts'], { cwd: root });

    const files = (await repositoryVocabularyFiles(root)).map((path) => relative(root, path).replaceAll('\\', '/'));
    assert.deepEqual(files, ['src/tracked.ts']);
  });
});

test('non-git fallback still excludes checkpoint and interpreter caches', async () => {
  await withTemporaryRoot(async (root) => {
    await mkdir(resolve(root, 'src'), { recursive: true });
    await mkdir(resolve(root, '.asklepios'), { recursive: true });
    await mkdir(resolve(root, 'scripts/__pycache__'), { recursive: true });
    await writeFile(resolve(root, 'src/source.ts'), 'export const source = true;\n', 'utf8');
    await writeFile(resolve(root, '.asklepios/receipt.json'), '{"transient":true}\n', 'utf8');
    await writeFile(resolve(root, 'scripts/__pycache__/cache.py'), 'transient = True\n', 'utf8');

    const files = (await repositoryVocabularyFiles(root)).map((path) => relative(root, path).replaceAll('\\', '/'));
    assert.deepEqual(files, ['src/source.ts']);
  });
});
