#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from content_bundle_core import seal_bundle,validate_bundle
p=argparse.ArgumentParser(); p.add_argument('--input',required=True); p.add_argument('--output',required=True); a=p.parse_args()
b=seal_bundle(json.loads(Path(a.input).read_text(encoding='utf-8')))
errors=validate_bundle(b)
if errors:
 print(json.dumps({'status':'FAIL','errors':errors},indent=2)); raise SystemExit(3)
Path(a.output).write_text(json.dumps(b,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','bundle_sha256':b['bundle_sha256'],'output':a.output},indent=2))
