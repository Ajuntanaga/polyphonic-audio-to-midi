"""GitHub-only acoustic observation of a frozen stable-note event population.

Imports and metadata helpers are safe locally. Audio dependencies and data are
used only after the GitHub guard. This does not classify or certify re-plucks.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import zipfile


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify(path, expected):
    actual = sha(path)
    if actual != expected:
        raise ValueError(f'Hash mismatch for {Path(path).name}: {actual}')
    return actual


def extract_zip(archive, suffix, dest, expected):
    with zipfile.ZipFile(archive) as z:
        names = [n for n in z.namelist() if n == suffix or n.endswith('/' + suffix)]
        if len(names) != 1:
            raise ValueError(f'Expected one zip member ending {suffix}: {len(names)}')
        with z.open(names[0]) as source, dest.open('wb') as out:
            shutil.copyfileobj(source, out)
    verify(dest, expected)
    return names[0]


def extract_tar(archive, members):
    # Extract only named regular files to caller-chosen destinations, no paths
    # from the archive are ever used as filesystem destinations.
    found = {}
    with tarfile.open(archive, 'r:gz') as t:
        for member in t:
            key = member.name.removeprefix('./')
            if key not in members:
                continue
            if key in found or not member.isfile():
                raise ValueError(f'Duplicate or nonregular corpus member: {key}')
            dest, expected = members[key]
            with t.extractfile(member) as source, dest.open('wb') as out:
                shutil.copyfileobj(source, out)
            found[key] = verify(dest, expected)
    if set(found) != set(members):
        raise ValueError(f'Missing corpus members: {set(members) - set(found)}')
    return found


def read_trace(path, magic, fields):
    with gzip.open(path, 'rt') as f:
        if f.readline().rstrip('\n') != magic:
            raise ValueError('Trace marker differs')
        reader = csv.DictReader(f, delimiter='\t')
        if reader.fieldnames != fields:
            raise ValueError('Trace header differs')
        return list(reader)


def read_labels(path, samples):
    fields = ['start_sample', 'end_sample', 'midi_note', 'string_mask', 'calibration_pass']
    labels = []
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames not in (fields, fields + ['expected_cents']):
            raise ValueError('Annotation header differs')
        for index, row in enumerate(reader):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Annotation row {index} has missing or extra fields')
            start, end, note, mask, calibration_pass = (int(row[k]) for k in fields)
            if not (0 <= start < end <= samples and 0 <= note <= 127
                    and 0 <= mask < 256 and calibration_pass >= 0):
                raise ValueError(f'Annotation row {index} has invalid bounds or identity')
            if 'expected_cents' in row and not math.isfinite(float(row['expected_cents'])):
                raise ValueError(f'Annotation row {index} has nonfinite expected cents')
            labels.append((start, end, note))
    if not labels:
        raise ValueError('Empty annotation set')
    return labels


def paired_events(tagged, callbacks):
    source = {}
    for row in tagged:
        event = {k: (v if k == 'kind' else int(v)) for k, v in row.items()}
        q = event['sequence']
        if q in source or event['kind'] not in ('on', 'off'):
            raise ValueError('Duplicate source sequence or invalid kind')
        source[q] = event
    seen = set()
    for row in callbacks:
        q = int(row['source_sequence'])
        if q in seen or q not in source:
            raise ValueError('Duplicate or unknown callback source')
        original = source[q]
        if row['kind'] != original['kind'] or any(int(row[k]) != original[k] for k in ('sample', 'note')):
            raise ValueError('Callback sample/pitch/kind differs from its source')
        seen.add(q)
    missing = set(source) - seen
    keys = defaultdict(list)
    for q in missing:
        e = source[q]
        keys[(e['sample'], e['kind'], e['note'], e['voice_id'], e['continuation_voice_id'])].append(q)
    remaining = set(missing)
    pairs = 0
    while remaining:
        q = min(remaining)
        e = source[q]
        other_kind = 'off' if e['kind'] == 'on' else 'on'
        candidates = keys[(e['sample'], other_kind, e['note'], e['continuation_voice_id'], e['voice_id'])]
        if (e['voice_id'] == e['continuation_voice_id'] or len(candidates) != 1
                or candidates[0] not in remaining):
            raise ValueError('Suppressed event has no unique reciprocal partner')
        remaining.remove(q)
        remaining.remove(candidates[0])
        pairs += 1
    return source, missing, pairs


def attack_events(source, missing, labels, pre_samples, post_samples):
    selected = []
    for q, event in sorted(source.items()):
        if event['kind'] != 'on':
            continue
        referring = [i for i, (start, end, note) in enumerate(labels)
                     if note == event['note'] and start - pre_samples <= event['sample'] <= start + post_samples]
        if referring:
            selected.append({**event, 'suppressed': q in missing, 'label_indices': referring,
                             'label_start_offsets_samples': [event['sample'] - labels[i][0] for i in referring]})
    return selected


def annotation_context(event, labels, before, after, conf):
    start, end = event['sample'] - before, event['sample'] + after
    f = conf['a4'] * 2 ** ((event['note'] - 69) / 12)
    overlaps, same_pitch = [], []
    for i, (a, b, note) in enumerate(labels):
        if b <= start or a > end:
            continue
        if note == event['note']:
            same_pitch.append(i)
            continue
        fundamental = conf['a4'] * 2 ** ((note - 69) / 12)
        for h in conf['annotation_overlap_harmonics']:
            if conf['band_low_ratio'] * f <= h * fundamental <= conf['band_high_ratio'] * f:
                overlaps.append({'label_index': i, 'note': note, 'harmonic': h})
    return {'annotated_harmonic_overlap': overlaps,
            'same_pitch_labels_overlapping_window': same_pitch,
            'no_annotated_harmonic_overlap': not overlaps}


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    def q(p):
        x = p * (len(values) - 1)
        lo, hi = math.floor(x), math.ceil(x)
        return values[lo] + (values[hi] - values[lo]) * (x - lo)
    return {'min': values[0], 'p10': q(.1), 'median': q(.5), 'p90': q(.9), 'max': values[-1]}


def summarize(rows):
    summary = {}
    for name, group in [('suppressed', [r for r in rows if r['suppressed']]),
                        ('retained', [r for r in rows if not r['suppressed']])]:
        result = {}
        for subset, selected in [('all', group),
                                 ('no_annotated_harmonic_overlap', [r for r in group if r['no_annotated_harmonic_overlap']]),
                                 ('annotated_harmonic_overlap', [r for r in group if not r['no_annotated_harmonic_overlap']])]:
            ratios = [r['acoustic']['max_20ms_rise_within_40ms_of_event'] for r in selected]
            result[subset] = {'events': len(selected), 'unique_label_indices': sorted({i for r in selected for i in r['label_indices']}),
                              'local_rise_ratio': quantiles(ratios),
                              'env_at_dbfs': quantiles([r['acoustic']['env_at_dbfs'] for r in selected]),
                              'rise_bins': {'le_1': sum(x <= 1 for x in ratios),
                                            'gt_1_lt_2': sum(1 < x < 2 for x in ratios),
                                            'ge_2': sum(x >= 2 for x in ratios)}}
        summary[name] = result
    return summary


def measure(wave, event, conf):
    require_worker()
    import numpy as np
    from scipy import signal

    sr, sample = wave.samplerate, event['sample']
    ms = sr // 1000
    lo = max(0, sample - conf['excerpt_pre_ms'] * ms)
    hi = min(wave.frames, sample + conf['excerpt_post_ms'] * ms)
    wave.seek(lo)
    x = wave.read(hi - lo, dtype='float64', always_2d=False)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite waveform')
    f = conf['a4'] * 2 ** ((event['note'] - 69) / 12)
    sos = signal.butter(conf['butterworth_order'], [f * conf['band_low_ratio'], f * conf['band_high_ratio']],
                        btype='band', fs=sr, output='sos')
    env = np.abs(signal.hilbert(signal.sosfiltfilt(sos, x)))
    k = conf['envelope_smoothing_ms'] * ms
    env = np.convolve(env, np.ones(k) / k, 'same')
    if not np.isfinite(env).all():
        raise ValueError('Nonfinite envelope')
    centre = sample - lo
    def at(offset):
        i = centre + offset * ms
        return float(env[i]) if 0 <= i < len(env) else None
    step = conf['rise_ms'] * ms
    margin = conf['rise_edge_margin_ms'] * ms
    grid = range(margin, len(env) - step - margin, conf['rise_grid_ms'] * ms)
    rises = [(float(env[i + step] / max(env[i], conf['ratio_denominator_floor'])), i) for i in grid]
    local = [(r, i) for r, i in rises if abs(i - centre) <= conf['local_rise_start_radius_ms'] * ms]
    if not local:
        raise ValueError('No local rise measurement available')
    best, bi = max(rises)
    local_best, li = max(local)
    metrics = {'excerpt_start_sample': lo, 'excerpt_end_sample': hi,
               'excerpt_clipped': lo != sample - conf['excerpt_pre_ms'] * ms or hi != sample + conf['excerpt_post_ms'] * ms,
               'raw_excerpt_rms': float(np.sqrt(np.mean(x * x))),
               'env_minus_50ms': at(-50), 'env_at': at(0), 'env_plus_50ms': at(50), 'env_plus_300ms': at(300),
               'env_at_dbfs': 20 * math.log10(max(at(0), 1e-300)),
               'max_20ms_rise_within_40ms_of_event': local_best,
               'local_max_rise_midpoint_offset_ms': (li + step // 2 - centre) / ms,
               'max_20ms_rise_in_3s_window': best,
               'max_rise_offset_ms': (bi + step // 2 - centre) / ms}
    positions = list(range(0, len(env), conf['rise_grid_ms'] * ms))
    curve = {'sequence': event['sequence'], 'sample_offsets': [i - centre for i in positions],
             'envelope': [float(env[i]) for i in positions]}
    return metrics, curve


def require_worker():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise SystemExit('Audio observation is allowed only on the recorded GitHub worker')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source-sha', required=True)
    ap.add_argument('--spec', type=Path, required=True)
    ap.add_argument('--corpus-archive', type=Path, required=True)
    ap.add_argument('--ledger-archive', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    require_worker()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if head != args.source_sha:
        raise SystemExit('Source revision differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'm3_ordinary_attack_envelope_report_v1', 'state': 'running', 'final': False,
              'source_sha': head, 'started_at': datetime.now(timezone.utc).isoformat(),
              'installed_output_changed': False, 'promotion_accepted': False,
              'acoustic_repluck_preservation': 'not measured', 'integrity': {}}
    try:
        spec = json.loads(args.spec.read_text())
        report.update(spec=spec, spec_sha256=sha(args.spec), stage='verify pinned metadata')
        if spec['input_gain'] != 1.0:
            raise ValueError('Only unchanged input gain is in scope')
        verify(args.corpus_archive, spec['corpus']['sha256'])
        verify(args.ledger_archive, spec['ledger']['sha256'])
        inputs = args.output / 'inputs'
        inputs.mkdir()
        wave_path, label_path = inputs / 'ordinary.wav', inputs / 'ordinary.tsv'
        extract_tar(args.corpus_archive, {
            spec['corpus']['wave_member']: (wave_path, spec['corpus']['wave_sha256']),
            spec['corpus']['labels_member']: (label_path, spec['corpus']['labels_sha256'])})
        tagged_path, callbacks_path = inputs / 'midi-event.tsv.gz', inputs / 'callbacks.tsv.gz'
        extract_zip(args.ledger_archive, spec['ledger']['events_member'], tagged_path, spec['ledger']['events_sha256'])
        extract_zip(args.ledger_archive, spec['ledger']['callbacks_member'], callbacks_path, spec['ledger']['callbacks_sha256'])
        report['integrity']['all_input_hashes'] = True
        tagged = read_trace(tagged_path, '# m3_midi_events_v2',
                            ['sample', 'kind', 'note', 'velocity', 'voice_id', 'sequence', 'continuation_voice_id'])
        callbacks = read_trace(callbacks_path, '# m3_ledger_callbacks_v1',
                               ['sample', 'phase', 'kind', 'note', 'velocity', 'voice_id', 'channel', 'source_sequence'])
        source, missing, pairs = paired_events(tagged, callbacks)
        labels = read_labels(label_path, spec['samples'])
        canonical = json.dumps(labels, separators=(',', ':')).encode()
        label_sha = hashlib.sha256(canonical).hexdigest()
        if label_sha != spec['corpus']['label_triples_sha256']:
            raise ValueError(f'Label tuples differ from the saved 499-row reference: {label_sha}')
        report['integrity']['label_tuples_equal_saved_reference'] = True
        conf, ms = spec['method'], spec['sample_rate'] // 1000
        selected = attack_events(source, missing, labels, conf['attack_zone_pre_ms'] * ms, conf['attack_zone_post_ms'] * ms)
        counts = {'source_events': len(source), 'callbacks': len(callbacks), 'suppressed_pairs': pairs, 'labels': len(labels),
                  'attack_events': len(selected), 'suppressed_attack_events': sum(r['suppressed'] for r in selected),
                  'retained_attack_events': sum(not r['suppressed'] for r in selected),
                  'labels_with_attack_events': len({i for r in selected for i in r['label_indices']}),
                  'labels_with_suppressed_attack_events': len({i for r in selected if r['suppressed'] for i in r['label_indices']})}
        report['population'] = counts
        if counts != spec['expected']:
            raise ValueError(f'Frozen population differs: {counts}')
        report['integrity']['frozen_population'] = True
        report['stage'] = 'fixed nominal-band envelopes'
        import soundfile as sf
        report['runtime'] = {'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'soundfile')}}
        rows, curves = [], []
        with sf.SoundFile(wave_path) as wave:
            if (wave.samplerate, wave.frames, wave.channels) != (spec['sample_rate'], spec['samples'], spec['channels']):
                raise ValueError('Waveform geometry differs')
            report['integrity']['waveform_geometry'] = True
            for event in selected:
                metrics, curve = measure(wave, event, conf)
                context = annotation_context(event, labels, conf['local_rise_start_radius_ms'] * ms,
                                             (conf['local_rise_start_radius_ms'] + conf['rise_ms']) * ms, conf)
                rows.append({**event, **context, 'acoustic': metrics})
                curves.append(curve)
        report.update(events=rows, summary=summarize(rows), integrity_pass=all(report['integrity'].values()))
        curve_path = args.output / 'envelope-curves.json.gz'
        with gzip.open(curve_path, 'wt') as f:
            json.dump({'sample_rate': spec['sample_rate'], 'curves': curves}, f, allow_nan=False, separators=(',', ':'))
        report['curves'] = {'file': curve_path.name, 'bytes': curve_path.stat().st_size, 'sha256': sha(curve_path)}
        report.update(state='completed', final=True, stage='descriptive comparison complete',
                      decision='observation complete; acoustic re-pluck preservation remains not measured')
    except Exception as exc:
        report.update(state='failed', final=True, error=repr(exc))
        raise
    finally:
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'state': report['state'], 'population': report['population'], 'summary': report['summary']}))


if __name__ == '__main__':
    main()
