#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path('reports/facility-decision-build-provenance.json')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_output(command: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(command, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return 'unavailable'


def build_manifest(directory: Path) -> list[dict[str, Any]]:
    result=[]
    for path in sorted(item for item in directory.rglob('*') if item.is_file()):
        result.append({
            'name': path.relative_to(directory).as_posix(),
            'digest': {'sha256': digest(path)},
            'size': path.stat().st_size,
        })
    if not result:
        raise ValueError('build output is empty')
    return result


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--subject-dir', default='dist')
    parser.add_argument('--output', default=DEFAULT_OUTPUT.as_posix())
    parser.add_argument('--builder-id', default='https://github.com/SDF-01/ProjectAsklepios/actions/workflows/facility-decision-integrity-ci.yml')
    args=parser.parse_args()
    repo=Path(args.repo).resolve(); subject_dir=(repo/args.subject_dir).resolve(); errors=[]
    try:
        subjects=build_manifest(subject_dir)
    except Exception as exc:
        subjects=[]; errors.append(str(exc))
    required_inputs=[
        Path('config/facility-decision/ASK-D-001.json'),
        Path('config/facility-decision/VALIDITY_BOUNDARIES.json'),
        Path('src/facility-decision/contracts.generated.ts'),
        Path('package-lock.json'),
        Path('lean-toolchain'),
        Path('lake-manifest.json'),
        Path('.github/workflows/facility-decision-integrity-ci.yml'),
    ]
    resolved=[]
    for rel in required_inputs:
        path=repo/rel
        if not path.is_file():
            errors.append(f'missing resolved dependency:{rel.as_posix()}')
            continue
        resolved.append({'uri': f'git+https://github.com/SDF-01/ProjectAsklepios@{command_output(["git","rev-parse","HEAD"],repo)}#{rel.as_posix()}', 'digest': {'sha256': digest(path)}})
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
    commit=command_output(['git','rev-parse','HEAD'],repo)
    report={
        '_type': 'https://in-toto.io/Statement/v1',
        'subject': subjects,
        'predicateType': 'https://slsa.dev/provenance/v1',
        'predicate': {
            'buildDefinition': {
                'buildType': 'https://github.com/SDF-01/ProjectAsklepios/facility-decision-integrity/v1',
                'externalParameters': {
                    'gitCommit': commit,
                    'subjectDirectory': Path(args.subject_dir).as_posix(),
                    'releaseId': 'ASK-FACILITY-DECISION-RC3-6A',
                },
                'internalParameters': {
                    'operatingSystem': platform.platform(),
                    'python': platform.python_version(),
                    'node': command_output(['node','--version'],repo),
                    'npm': command_output(['npm','--version'],repo),
                    'lean': command_output(['lean','--version'],repo),
                    'lake': command_output(['lake','--version'],repo),
                },
                'resolvedDependencies': resolved,
            },
            'runDetails': {
                'builder': {'id': args.builder_id},
                'metadata': {
                    'invocationId': os.environ.get('GITHUB_RUN_ID') or str(uuid.uuid4()),
                    'startedOn': os.environ.get('ASKLEPIOS_BUILD_STARTED_AT') or now,
                    'finishedOn': now,
                },
                'byproducts': [
                    {'name': 'reports/facility-decision-build-reproducibility.json'},
                    {'name': 'reports/facility-decision-axiom-check.json'},
                    {'name': 'reports/facility-decision-release.json'},
                ],
            },
        },
        'asklepios_verification': {
            'signature_status': 'UNSIGNED',
            'claim_scope': 'BUILD_IDENTITY_ONLY',
            'note': 'This SLSA-shaped statement records build inputs and outputs. It is not a signed provenance attestation until a trusted builder signs and distributes it.',
            'errors': errors,
            'status': 'PASS' if not errors else 'FAIL',
        },
    }
    output=repo/args.output; output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':report['asklepios_verification']['status'],'subjects':len(subjects),'resolved_dependencies':len(resolved),'signature_status':'UNSIGNED','errors':errors},indent=2,sort_keys=True))
    return 0 if not errors else 3


if __name__=='__main__': raise SystemExit(main())
