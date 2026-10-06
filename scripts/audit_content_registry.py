#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from content_registry_core import validate_registry

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--registry',default='public/data/content_registry/content_registry.json')
    parser.add_argument('--repo-root',default='.')
    parser.add_argument('--output',default='reports/content-registry-audit.json')
    args=parser.parse_args()
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8'))
    report=validate_registry(registry,Path(args.repo_root).resolve())
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 3
if __name__=='__main__': raise SystemExit(main())
