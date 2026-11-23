"""GitHub-only standalone aubio baseline on six already staged waveforms."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time
import zipfile

from tools.complex_attack_baseline import event_identity, event_record, score_fixture


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f'Hash mismatch for {Path(path).name}: {actual}')
    return actual


def extract(archive, suffix, destination, expected):
    with zipfile.ZipFile(archive) as z:
        matches = [n for n in z.namelist() if n == suffix or n.endswith('/' + suffix)]
        if len(matches) != 1:
            raise ValueError(f'Expected one member ending {suffix}, found {len(matches)}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(z.read(matches[0]))
    verify(destination, expected)
    return matches[0]


def configuration(detector):
    return {
        'threshold': float(detector.get_threshold()),
        'minioi_ms': float(detector.get_minioi_ms()),
        'silence_db': float(detector.get_silence()),
        'adaptive_whitening': int(detector.get_awhitening()),
        'compression': float(detector.get_compression()),
        'nominal_delay_samples': int(detector.get_delay()),
    }


def process(path, spec):
    # These dependencies are intentionally loaded only after the remote guard.
    import aubio
    import numpy as np
    import soundfile as sf

    signal, rate = sf.read(path, dtype='float32', always_2d=True)
    if rate != spec['sample_rate'] or signal.shape != (spec['samples'], 1):
        raise ValueError('Frozen mono waveform geometry differs')
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite waveform')
    conf = spec['aubio']
    detector = aubio.onset(conf['method'], conf['fft_samples'], conf['hop_samples'], rate)
    observed = configuration(detector)
    for key, value in observed.items():
        if not math.isclose(value, conf[key], rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError(f'Upstream default differs: {key}={value}')
    hop = conf['hop_samples']
    events, durations = [], []
    for start in range(0, len(signal), hop):
        real = min(hop, len(signal) - start)
        block = np.zeros(hop, dtype=aubio.float_type)
        block[:real] = signal[start:start + real, 0]
        begin = time.perf_counter_ns()
        returned = float(detector(block)[0])
        duration = time.perf_counter_ns() - begin
        durations.append(duration)
        if returned > 0:
            event = event_record(start, hop, real, detector.get_last(), duration)
            event['descriptor'] = float(detector.get_descriptor())
            event['peakpicker_output'] = returned
            events.append(event)
    durations.sort()
    return {
        'configuration': observed, 'events': events, 'processed_real_samples': len(signal),
        'padding_samples': (-len(signal)) % hop, 'calls': len(durations),
        'call_ns': {'median': durations[len(durations) // 2],
                    'p99': durations[math.ceil(.99 * len(durations)) - 1],
                    'max': max(durations)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-sha', required=True)
    ap.add_argument('--spec', type=Path, required=True)
    ap.add_argument('--report-archive', type=Path, required=True)
    ap.add_argument('--evidence-archive', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise SystemExit('Audio execution is allowed only in the recorded GitHub worker')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if head != args.source_sha:
        raise SystemExit('Source revision differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        'schema': 'm3_complex_attack_baseline_report_v1', 'state': 'running', 'final': False,
        'harness_source_sha': head, 'observed_at': datetime.now(timezone.utc).isoformat(),
        'installed_output_changed': False, 'promotion_accepted': False,
        'acoustic_repluck_preservation': 'not measured',
        'new_m3_replay': False, 'new_plugin_timing_measurement': False,
        'primary_clock': 'exclusive hop end, not backdated onset time',
        'fixtures': {}, 'integrity': {},
    }
    target = args.output / 'report.json'
    try:
        spec = json.loads(args.spec.read_text())
        report['spec'], report['spec_sha256'] = spec, sha(args.spec)
        report['stage'] = 'verify inputs and dependency'
        if spec['input_gain'] != 1.0:
            raise ValueError('No gain change is in scope')
        version = importlib.metadata.version('aubio')
        if version != spec['aubio']['version']:
            raise ValueError('aubio version differs')
        report['runtime'] = {'python': platform.python_version(), 'platform': platform.platform(),
                             'aubio': version, 'numpy': importlib.metadata.version('numpy'),
                             'soundfile': importlib.metadata.version('soundfile')}
        verify(args.report_archive, spec['reference_report']['archive_sha256'])
        verify(args.evidence_archive, spec['reference_evidence']['archive_sha256'])
        report['integrity']['archives_pinned'] = True
        reference_path = args.output / 'reference-report.json'
        extract(args.report_archive, 'controlled-repluck/report.json', reference_path,
                spec['reference_report']['report_sha256'])
        reference = json.loads(reference_path.read_text())
        if not reference['integrity_pass'] or not reference['final']:
            raise ValueError('Reference is not final with passing integrity')
        report['integrity']['reference_final'] = True
        report['stage'] = 'six frozen fixture streams'
        for dataset, selected in spec['datasets'].items():
            outputs = {}
            report['fixtures'][dataset] = outputs
            base = reference['datasets'][dataset]['comparisons']
            first_deadline = base['single']['responses']['per_voice']['first_added_on_sample']
            for layout, expected in selected['fixtures'].items():
                saved = reference['fixtures'][dataset]['fixtures'][layout]
                if saved['sha256'] != expected:
                    raise ValueError('Fixture hash differs between spec and reference')
                path = args.output / 'fixtures' / dataset / (layout + '.wav')
                member = extract(args.evidence_archive, f'fixtures/{dataset}/{layout}.wav', path, expected)
                stream = process(path, spec)
                markers = saved['markers']
                insertions = [m - reference['spec']['pre_marker_samples'] for m in markers]
                deadlines = [first_deadline]
                if len(markers) == 2:
                    deadlines.append(base[layout]['responses']['per_voice']['first_added_on_sample'])
                scored = score_fixture(stream.pop('events'), insertions, markers, deadlines,
                                       spec['sample_rate'], spec['samples'])
                outputs[layout] = {**stream, **scored, 'wave_sha256': expected, 'archive_member': member}
                report['integrity'][dataset + '/' + layout + '/pinned_shape_config'] = True
                if layout != 'single':
                    prefix = event_identity(scored['events'], insertions[1]) == event_identity(
                        outputs['single']['events'], insertions[1])
                    report['integrity'][dataset + '/' + layout + '/prefix_cues_identical'] = prefix
        report['integrity_pass'] = all(report['integrity'].values())
        if not report['integrity_pass']:
            raise ValueError('Unchanged-prefix cue identity failed')
        values = [r for ds in report['fixtures'].values() for r in ds.values()]
        report['fixtures_passed'] = sum(r['fixed_screen_pass'] for r in values)
        report['fixtures_total'] = len(values)
        report['fixed_screen_pass'] = all(r['fixed_screen_pass'] for r in values)
        report['decision'] = ('bounded cue supported; acoustic and polyphonic generalization unmeasured'
                              if report['fixed_screen_pass'] else
                              'fixed setting rejected; no tuning or policy change')
        report['stage'] = 'fixed comparison complete'
        report['state'], report['final'] = 'completed', True
    except Exception as exc:
        report['state'], report['final'], report['error'] = 'failed', True, repr(exc)
        raise
    finally:
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        target.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'state': report['state'], 'fixtures_passed': report['fixtures_passed'],
                      'fixtures_total': report['fixtures_total'], 'decision': report['decision']}))


if __name__ == '__main__':
    main()
