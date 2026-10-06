#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import ts from 'typescript';

const root = path.resolve(process.cwd());
const explicit = [
  'scripts/generateFacilityArrivalArtifacts.ts',
  'scripts/checkFacilityArrivalRuntimeResolution.ts',
  'src/facility-arrival-checker/verify.ts',
  'src/pages/FacilityArrivalExamplePage.tsx',
  'src/tests/facilityArrivalDecision.test.ts',
  'src/tests/facilityArrivalRelations.test.ts',
  'src/tests/facilityArrivalRuntime.test.ts',
];
const facilityDir = path.join(root, 'src/facility-arrival');
const facilityFiles = fs.readdirSync(facilityDir)
  .filter((name) => name.endsWith('.ts') || name.endsWith('.tsx'))
  .map((name) => path.posix.join('src/facility-arrival', name));
const files = [...new Set([...explicit, ...facilityFiles])].sort();
const errors = [];
for (const relative of files) {
  const full = path.join(root, relative);
  if (!fs.existsSync(full)) {
    errors.push(`TypeScript source missing:${relative}`);
    continue;
  }
  const text = fs.readFileSync(full, 'utf8');
  const kind = relative.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(relative, text, ts.ScriptTarget.Latest, true, kind);
  for (const diagnostic of source.parseDiagnostics ?? []) {
    const position = source.getLineAndCharacterOfPosition(diagnostic.start ?? 0);
    const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ');
    errors.push(`${relative}:${position.line + 1}:${position.character + 1}:${message}`);
  }
}
const report = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  parser: `typescript-${ts.version}`,
  files_checked: files.length,
  files,
  errors: [...new Set(errors)].sort(),
};
const output = path.join(root, 'reports/facility-arrival-typescript-syntax.json');
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
process.exit(report.status === 'PASS' ? 0 : 3);
