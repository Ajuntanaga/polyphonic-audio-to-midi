"""Bounded runtime estimator diagnostic on staged note52 clips; GHA audio only."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from tools.controlled_descriptor_overlap import read_float_wave
from tools.portable_short_window_identity import features, evaluate
from tools.portable_corpus_replay import SETTINGS
from tools.frozen_cue_corpus_gate import read_replay, compare_replays


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_trace(rows, begin, rate):
    """Two fixed 80ms halves, no energy floor; zero bins remain ineligible."""
    half = round(rate * .080)
    buckets = [[], []]
    for row in rows:
        sample = int(row['sample'])
        if begin <= sample < begin + 2 * half:
            energy = [float(row[f'corrected_harmonic_energy_{h}']) for h in range(1, 7)]
            if not np.isfinite(energy).all() or min(energy) < 0:
                raise ValueError('Invalid runtime energy')
            buckets[(sample - begin) // half].append(energy)
    counts = [len(b) for b in buckets]
    means = [np.mean(b, axis=0).tolist() if b else None for b in buckets]
    eligible = all(b and np.all(np.asarray(b) > 0) for b in buckets)
    result = dict(ticks_per_half=counts, mean_energy_per_half=means,
                  eligible=eligible, eligibility='Both halves populated; all six energies positive at every tick. Numerical support only, not harmonic confidence.',
                  zero_ticks_per_harmonic=[sum(row[h] == 0 for b in buckets for row in b) for h in range(6)])
    if all(b for b in buckets):
        power = np.asarray(means)
        result['shares_per_half'] = [p.tolist() if p.sum() == 0 else (p / p.sum()).tolist() for p in power]
    if eligible:
        log_power = np.log10(np.asarray(means))
        shape = log_power.mean(axis=0)
        shape -= shape.mean()
        result['features'] = {'shape': shape.tolist()}
    return result


def eligible_evaluation(rows, lanes):
    """Reuse frozen evaluator when supported; abstain whole unsupported folds."""
    selected = [r for r in rows if r['string'] in lanes]
    predictions, folds = [], []
    for held in (1, 2, 3):
        train = [r for r in selected if r['pass'] != held and r['runtime']['eligible']]
        test = [r for r in selected if r['pass'] == held]
        supported = all(any(r['string'] == lane for r in train) for lane in lanes)
        center = scale = prototypes = None
        if supported:
            x = np.asarray([r['runtime']['features']['shape'] for r in train])
            center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
            x = (x - center) / scale
            prototypes = np.asarray([x[[r['string'] == lane for r in train]].mean(axis=0) for lane in lanes])
        outcomes = []
        for row in test:
            prediction, distances = None, None
            if supported and row['runtime']['eligible']:
                v = (np.asarray(row['runtime']['features']['shape']) - center) / scale
                d = np.mean((prototypes - v) ** 2, axis=1)
                order = np.argsort(d)
                if not np.isclose(d[order[0]], d[order[1]], rtol=1e-9, atol=1e-12):
                    prediction = lanes[int(order[0])]
                distances = d.tolist()
            outcomes.append(dict(clip=row['clip'], held_pass=held, expected=row['string'], predicted=prediction, distances=distances))
        predictions.extend(outcomes)
        folds.append(dict(held_pass=held, training_clips=[r['clip'] for r in train],
                          total=len(test), eligible=sum(r['runtime']['eligible'] for r in test),
                          correct=sum(r['expected'] == r['predicted'] for r in outcomes),
                          abstained=sum(r['predicted'] is None for r in outcomes),
                          training_center=None if center is None else center.tolist(),
                          training_scale=None if scale is None else scale.tolist()))
    return dict(lanes=lanes, total=len(selected), correct=sum(p['expected'] == p['predicted'] for p in predictions), folds=folds, predictions=predictions)


def run(binary, corpus, manifest, output):
    data = json.loads(manifest.read_text())
    clips = data['clips']
    if data['note'] != 52 or len(clips) != 28 or sorted({c['string'] for c in clips}) != list(range(6)):
        raise ValueError('Expected the fixed 28-clip note52 study')
    names = [c['clip'] for c in clips]
    if len(set(names)) != len(names) or any(Path(n).name != n for n in names):
        raise ValueError('Invalid clip identities')
    output.mkdir(parents=True, exist_ok=False)
    result = dict(schema='m3_runtime_harmonic_identity_v1', state='running', final=False,
                  source=data.get('source', {}), input_manifest_sha256=digest(manifest), binary_sha256=digest(binary),
                  settings=SETTINGS, calibration='Replay default bank; no uploaded personal bank in this input release.',
                  installed_output_changed=False, promotion_accepted=False, measurements=[],
                  limitations=['Known isolated note52; label-relative first160ms, onset unverified.',
                               'Clip-local detector state; not continuous-corpus state.',
                               'Runtime mean corrected energies differ from integrated Hann FFT powers.',
                               'Positive energies do not prove partial detection; same-session exploratory holdout only.',
                               'No chord, timing or live-host acceptance measured.'])
    def save():
        (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    save()
    try:
        for item in clips:
            wav = corpus / item['clip']
            if digest(wav) != item['sha256'] or item['midi_note'] != 52:
                raise ValueError('Input identity mismatch')
            rate, samples = read_float_wave(wav)
            begin, end = item['labeled_begin'], item['labeled_end']
            measured, context = features(samples, rate, begin, end, 52)
            directory = output / wav.stem
            directory.mkdir()
            labels = directory / 'labels.tsv'
            labels.write_text(f'start_sample\tend_sample\tmidi_note\tstring_mask\n{begin}\t{end}\t52\t{1 << item["string"]}\n')
            base = [str(binary.resolve()), '--wav', str(wav.resolve()), '--labels', str(labels.resolve()), '--block', '512', '--label-details']
            for key, value in SETTINGS.items():
                base += ['--' + key, str(value)]
            for mode in ('reference', 'traced'):
                command = base + ['--midi-event-trace', str((directory / (mode + '-midi.tsv')).resolve())]
                if mode == 'traced':
                    command += ['--candidate-trace', str((directory / 'candidate.tsv').resolve()), '--candidate-trace-note', '52',
                                '--candidate-trace-start', str(begin / rate), '--candidate-trace-end', str((begin + round(.160 * rate)) / rate)]
                with (directory / (mode + '.tsv')).open('x') as stdout, (directory / (mode + '.stderr')).open('x') as stderr:
                    subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=90)
            comparison = compare_replays(read_replay(directory / 'reference.tsv'), read_replay(directory / 'traced.tsv'))
            midi_identity = digest(directory / 'reference-midi.tsv') == digest(directory / 'traced-midi.tsv')
            if not comparison['output_bit_identical'] or comparison['changed_labels'] or not midi_identity:
                raise ValueError('Tracing changed output')
            with (directory / 'candidate.tsv').open() as stream:
                runtime = summarize_trace(list(csv.DictReader(stream, delimiter='\t')), begin, rate)
            result['measurements'].append({**item, 'features': measured, 'context': context, 'runtime': runtime,
                                           'comparison': comparison, 'midi_bit_identical': midi_identity,
                                           'trace_sha256': digest(directory / 'candidate.tsv')})
            save()
        result['runtime_evaluations'] = [eligible_evaluation(result['measurements'], lanes) for lanes in ([0, 1], list(range(6)))]
        result['fft_evaluations'] = [evaluate(result['measurements'], lanes, ['shape']) for lanes in ([0, 1], list(range(6)))]
        result.update(state='completed', final=True)
    except Exception as error:
        result.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.output)
