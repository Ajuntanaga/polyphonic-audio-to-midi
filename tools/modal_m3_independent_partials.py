#!/usr/bin/env python3
"""Measure saved waveforms on Modal; no native build or MIDI replay."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re

import modal

ROOT = Path(__file__).resolve().parents[1]
MOUNT = Path('/mnt/m3')
MODULES = ('independent_partial_evidence', 'controlled_descriptor_overlap',
           'string_likelihood_decomposition', 'string_observation_shadow', 'string_evidence_audit')
app = modal.App('m3-independent-partials')
volume = modal.Volume.from_name('m3-protected-replay-data')
image = (modal.Image.debian_slim(python_version='3.12').pip_install('numpy<3')
         .env({'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}))
for module in MODULES:
    image = image.add_local_file(ROOT / 'tools' / (module + '.py'),
                                 '/opt/m3/tools/' + module + '.py', copy=True)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=1.0,
              memory=2048, timeout=600, max_containers=1)
def analyze_saved(run_id: str, source_run: str):
    import sys
    sys.path.insert(0, '/opt/m3')
    import numpy as np
    from tools.independent_partial_evidence import CONFIG, compare_local_reference, measure, summarize
    from tools.controlled_descriptor_overlap import read_float_wave
    for identifier in (run_id, source_run):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', identifier):
            raise ValueError('invalid run identifier')
    out, source = MOUNT / 'results' / run_id, MOUNT / 'results' / source_run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
                  stage='verify saved sources', installed_changed=False, config=CONFIG,
                  started_at=datetime.now(timezone.utc).isoformat(), cases={},
                  limits=['One low-note take and two higher-note crops; not held-out corpus evidence.',
                          'Component powers evaluate peak provenance only and do not enter the cue.',
                          'Component power shares omit cross terms; they are not fractions of mixture power.',
                          'Local prominence compares fixed sidebands, not noise or independent sources.',
                          'Control maxima are in-sample descriptions, not validated admission thresholds.',
                          'No native replay, MIDI counts, real-time performance or production gain measured.',
                          'The 170.7 ms causal window is separate from the unchanged three-second unison gate.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        capture = json.loads((source / 'report.json').read_text())
        if capture['run_id'] != source_run or capture['state'] != 'completed' or not capture['final']:
            raise ValueError('source report not final or identity differs')
        report['capture_report_sha256'] = digest(source / 'report.json')
        report['analysis_source_sha256'] = {name: digest('/opt/m3/tools/' + name + '.py') for name in MODULES}
        components = {}
        source_hashes = {}
        for name, identity in capture['components'].items():
            wav = MOUNT / 'corpus' / (identity['corpus'] + '.wav')
            labels = wav.with_suffix('.tsv')
            if str(wav) not in source_hashes:
                source_hashes[str(wav)] = digest(wav)
            if (source_hashes[str(wav)] != identity['audio_sha256'] or
                    digest(labels) != identity['labels_sha256']):
                raise ValueError('source audio or annotations changed')
            rate, audio = read_float_wave(wav)
            crop = audio[identity['start_sample']:identity['end_sample']]
            if hashlib.sha256(crop.tobytes()).hexdigest() != identity['component_sha256'] or rate != 96000:
                raise ValueError('source crop or sample clock changed')
            components[name] = crop.astype(np.float64)
        report['components'] = capture['components']
        measured_cases = {}
        for name, identity in capture['datasets'].items():
            report['stage'] = name + ' partial measurements'
            save()
            wav = source / (name + '.wav')
            if digest(wav) != identity['audio_sha256']:
                raise ValueError('saved mixture changed')
            rate, mixture = read_float_wave(wav)
            m = identity['mixture']
            if rate != identity['sample_rate'] or len(mixture) != identity['sample_count']:
                raise ValueError('mixture sample clock changed')
            target = np.pad(components['target'] * m['common_gain'],
                            (m['prefix_samples'], m['suffix_samples']))
            interferer = (np.zeros_like(target) if m['interferer'] is None else
                          np.pad(components[m['interferer']] * m['interferer_scale'] * m['common_gain'],
                                 (m['prefix_samples'], m['suffix_samples'])))
            if not np.array_equal(np.asarray(target + interferer, dtype='<f4'), mixture):
                raise ValueError('recorded components do not reconstruct exact saved float32 mixture')
            cases = [(name, mixture, target, interferer)]
            if m['interferer'] is not None:
                cases.append((name + '_source_only', interferer,
                              np.zeros_like(target), interferer))
            for key, values, target_values, added_values in cases:
                rows = list(measure(values, rate, components={'target': target_values,
                                                             'interferer': added_values}))
                trace = out / (key + '-partials.jsonl.gz')
                with gzip.open(trace, 'wt', compresslevel=1) as stream:
                    for row in rows:
                        stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n')
                report['cases'][key] = dict(source_mixture=name, source_only=key.endswith('_source_only'),
                    sample_rate=rate, sample_count=len(values), source_audio_sha256=identity['audio_sha256'],
                    measurement_audio_sha256=hashlib.sha256(np.asarray(values, dtype='<f8').tobytes()).hexdigest(),
                    trace_sha256=digest(trace), groups=summarize(rows,
                        start_sample=m['prefix_samples'],
                        end_sample=m['prefix_samples'] + m['target_samples'], sample_rate=rate))
                measured_cases[key] = dict(rows=rows, source_only=key.endswith('_source_only'),
                    start_sample=m['prefix_samples'], end_sample=m['prefix_samples'] + m['target_samples'])
                save()
        report['local_reference_diagnostic'] = compare_local_reference(measured_cases)
        report.update(state='completed', final=True, stage='independent partial measurements complete',
                      completed_at=datetime.now(timezone.utc).isoformat())
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
