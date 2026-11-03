#!/usr/bin/env python3
"""Analyze two saved traces on Modal; no build, replay, or policy change."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import modal

ROOT = Path(__file__).resolve().parents[1]
MOUNT = Path('/mnt/m3')
MODULES = ('string_descriptor_context', 'string_likelihood_decomposition',
           'string_observation_shadow', 'string_evidence_audit')
app = modal.App('m3-descriptor-context')
volume = modal.Volume.from_name('m3-protected-replay-data')
image = modal.Image.debian_slim(python_version='3.12')
for module in MODULES:
    image = image.add_local_file(ROOT / 'tools' / (module + '.py'),
                                 '/opt/m3/tools/' + module + '.py', copy=True)


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=1.0,
              memory=1024, timeout=600, max_containers=1)
def analyze_saved(run_id: str, source_run: str):
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.string_descriptor_context import run
    for identifier in (run_id, source_run):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', identifier):
            raise ValueError('invalid run identifier')
    out, source = MOUNT / 'results' / run_id, MOUNT / 'results' / source_run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
                  stage='matched descriptor context analysis', installed_changed=False,
                  started_at=datetime.now(timezone.utc).isoformat())

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        raw = (source / 'report.json').read_bytes()
        capture = json.loads(raw)
        if capture['run_id'] != source_run:
            raise ValueError('source report identity mismatch')
        report['capture_report_sha256'] = hashlib.sha256(raw).hexdigest()
        report['analysis_source_sha256'] = {
            module: hashlib.sha256(Path('/opt/m3/tools/' + module + '.py').read_bytes()).hexdigest()
            for module in MODULES}
        report['analysis'] = run({name: source / (name + '-assignment.tsv.gz')
                                  for name in ('ordinary', 'isolated-08')}, capture)
        report.update(state='completed', final=True, stage='matched descriptor context analysis complete')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
    save()
    return report


@app.local_entrypoint()
def main(run_id: str, source_run: str):
    result = analyze_saved.remote(run_id, source_run)
    path = ROOT / 'build/modal' / (run_id + '.json')
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in ('run_id', 'state', 'stage', 'final')}))
    if result['state'] != 'completed':
        raise SystemExit(1)
