"""GitHub-only NINOS2 attack representation on six frozen copied-note WAVs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time

from tools.portable_complex_attack_baseline import sha, verify, extract
from tools.spectral_sparsity_attack import ninos2, peak_candidates, fit_threshold, score


def process(path, spec):
    import numpy as np
    import soundfile as sf

    signal, rate = sf.read(path, dtype='float64', always_2d=True)
    if rate != spec['sample_rate'] or signal.shape != (spec['samples'], 1):
        raise ValueError('Frozen waveform geometry differs')
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite waveform')
    conf = spec['feature']
    size, hop = conf['fft_samples'], conf['hop_samples']
    window = np.hanning(size)
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    selected = (frequencies > 0) & (frequencies <= conf['maximum_frequency_hz']) & (frequencies < rate / 2)
    buffer = np.zeros(size)
    rows, durations = [], []
    for start in range(0, len(signal), hop):
        real = min(hop, len(signal) - start)
        begin = time.perf_counter_ns()
        buffer[:-hop] = buffer[hop:]
        buffer[-hop:] = 0
        buffer[-hop:][:real] = signal[start:start + real, 0]
        magnitudes = np.abs(np.fft.rfft(buffer * window))[selected]
        feature = ninos2(magnitudes, conf['lowest_bin_fraction'])
        durations.append(time.perf_counter_ns() - begin)
        rows.append({'feature': feature, 'available_sample': start + hop,
                     'padded_samples': hop - real})
    max_history = math.ceil(conf['before_max_ms'] * rate / (1000 * hop))
    mean_history = math.ceil(conf['before_mean_ms'] * rate / (1000 * hop))
    candidates = peak_candidates(rows, max_history, mean_history)
    durations.sort()
    return {
        'rows': rows, 'candidates': candidates, 'processed_real_samples': len(signal),
        'padding_samples': (-len(signal)) % hop, 'frames': len(rows),
        'eligible_bins': int(selected.sum()),
        'retained_bins': math.floor(int(selected.sum()) * conf['lowest_bin_fraction']),
        'before_max_frames': max_history, 'before_mean_frames': mean_history,
        'feature_call_ns': {'median': durations[len(durations) // 2],
                            'p99': durations[math.ceil(.99 * len(durations)) - 1],
                            'max': max(durations)},
        'timing_scope': 'Python analysis only; not plugin callback timing',
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
        'schema': 'm3_spectral_sparsity_attack_report_v1', 'state': 'running', 'final': False,
        'harness_source_sha': head, 'started_at': datetime.now(timezone.utc).isoformat(),
        'installed_output_changed': False, 'promotion_accepted': False,
        'acoustic_repluck_preservation': 'not measured', 'new_m3_replay': False,
        'new_plugin_timing_measurement': False, 'fixtures': {}, 'integrity': {},
        'transfer_evaluated': False, 'test_used_to_select_threshold': False,
    }
    target = args.output / 'report.json'
    try:
        spec = json.loads(args.spec.read_text())
        report['spec'], report['spec_sha256'] = spec, sha(args.spec)
        report['runtime'] = {'python': platform.python_version(), 'platform': platform.platform(),
                             'numpy': importlib.metadata.version('numpy'),
                             'soundfile': importlib.metadata.version('soundfile')}
        if spec['input_gain'] != 1 or set(spec['datasets']) != {spec['calibration_dataset'], spec['transfer_dataset']}:
            raise ValueError('Frozen input roles differ')
        report['stage'] = 'verify pinned archives and all six members'
        verify(args.report_archive, spec['reference_report']['archive_sha256'])
        verify(args.evidence_archive, spec['reference_evidence']['archive_sha256'])
        report['integrity']['archives_pinned'] = True
        reference_path = args.output / 'reference-report.json'
        extract(args.report_archive, 'controlled-repluck/report.json', reference_path,
                spec['reference_report']['report_sha256'])
        reference = json.loads(reference_path.read_text())
        if not reference['integrity_pass'] or not reference['final']:
            raise ValueError('Reference lacks final passing integrity')
        report['integrity']['reference_final'] = True
        paths, geometries = {}, {}
        for dataset, selected in spec['datasets'].items():
            base = reference['datasets'][dataset]['comparisons']
            for layout, expected in selected['fixtures'].items():
                saved = reference['fixtures'][dataset]['fixtures'][layout]
                if saved['sha256'] != expected:
                    raise ValueError('Fixture pins disagree')
                key = dataset + '/' + layout
                paths[key] = args.output / 'fixtures' / dataset / (layout + '.wav')
                extract(args.evidence_archive, f'fixtures/{key}.wav', paths[key], expected)
                report['integrity'][key + '/wave_pinned'] = True
                markers = saved['markers']
                deadlines = [base['single']['responses']['per_voice']['first_added_on_sample']]
                if len(markers) == 2:
                    deadlines.append(base[layout]['responses']['per_voice']['first_added_on_sample'])
                geometries[key] = {
                    'insertions': [m - reference['spec']['pre_marker_samples'] for m in markers],
                    'markers': markers, 'deadlines': deadlines,
                    'sample_rate': spec['sample_rate'], 'samples': spec['samples'],
                }
        refractory = math.ceil(spec['feature']['fft_samples'] / spec['feature']['hop_samples'])
        report['refractory_frames'] = refractory
        calibration = []
        for role, dataset in [('calibration', spec['calibration_dataset']),
                              ('transfer', spec['transfer_dataset'])]:
            if role == 'transfer' and not report['calibration']['calibration_pass']:
                break  # No fallback threshold, and no peeking at transfer audio.
            report['stage'] = role + ' features'
            report['fixtures'][dataset] = {}
            prefix_rows = None
            for layout in ('single', 'overlap', 'separated'):
                key = dataset + '/' + layout
                stream = process(paths[key], spec)
                geometry = geometries[key]
                rows = stream.pop('rows')
                candidates = stream.pop('candidates')
                evidence_path = args.output / (dataset + '-' + layout + '-features.json.gz')
                with gzip.open(evidence_path, 'wt', encoding='utf-8') as out:
                    json.dump({'rows': rows, 'candidates': candidates}, out, allow_nan=False)
                result = {**stream, 'role': role, 'geometry': geometry,
                          'candidate_count': len(candidates),
                          'features_file': evidence_path.name, 'features_sha256': sha(evidence_path),
                          'wave_sha256': spec['datasets'][dataset]['fixtures'][layout]}
                report['fixtures'][dataset][layout] = result
                report['integrity'][key + '/shape_finite'] = True
                if layout == 'single':
                    prefix_rows = rows
                else:
                    through = geometry['insertions'][1]
                    identity = ([r for r in rows if r['available_sample'] <= through] ==
                                [r for r in prefix_rows if r['available_sample'] <= through])
                    report['integrity'][key + '/prefix_features_identical'] = identity
                    if not identity:
                        raise ValueError('Feature prefix identity failed')
                if role == 'calibration':
                    calibration.append({'candidates': candidates, 'geometry': geometry, 'result': result})
                else:
                    result.update(score(candidates, report['calibration']['selected_threshold'], refractory, geometry))
            if role == 'calibration':
                report['calibration'] = fit_threshold(calibration, refractory)
                threshold = report['calibration']['selected_threshold']
                if threshold is not None:
                    for item in calibration:
                        item['result'].update(score(item['candidates'], threshold, refractory, item['geometry']))
            else:
                report['transfer_evaluated'] = True
        report['integrity_pass'] = all(report['integrity'].values())
        transfer = list(report['fixtures'].get(spec['transfer_dataset'], {}).values())
        report['transfer_passed'] = sum(r['fixed_screen_pass'] for r in transfer)
        report['transfer_total'] = len(transfer)
        report['bounded_screen_pass'] = (report['integrity_pass'] and report['calibration']['calibration_pass']
                                         and len(transfer) == 3 and report['transfer_passed'] == 3)
        if not report['calibration']['calibration_pass']:
            report['decision'] = 'REJECTED_CALIBRATION: no delta passes three calibration fixtures; transfer not evaluated'
        elif not report['bounded_screen_pass']:
            report['decision'] = 'REJECTED_TRANSFER: frozen calibration fails cross-pitch fixtures; no retuning'
        else:
            report['decision'] = 'BOUNDED_CUE_SUPPORTED: six copied-note controls only; pitch attribution and acoustic preservation unmeasured'
        report['stage'], report['state'], report['final'] = 'frozen comparison complete', 'completed', True
    except Exception as exc:
        report['state'], report['final'], report['error'] = 'failed', True, repr(exc)
        raise
    finally:
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        target.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'state': report['state'], 'decision': report['decision'],
                      'calibration': report['calibration'], 'transfer_passed': report['transfer_passed']}))


if __name__ == '__main__':
    main()
