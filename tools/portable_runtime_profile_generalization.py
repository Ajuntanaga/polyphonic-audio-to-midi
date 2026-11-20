"""GHA-only runtime profile extraction for a frozen multi-pitch clip manifest."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import numpy as np
from tools.controlled_descriptor_overlap import read_float_wave
from tools.portable_runtime_harmonic_identity import digest, summarize_trace
from tools.portable_corpus_replay import SETTINGS
from tools.frozen_cue_corpus_gate import read_replay, compare_replays
from tools.runtime_profile_generalization import evaluate


def validate_manifest(data):
    clips = data['clips']
    if not clips or len({c['clip'] for c in clips}) != len(clips):
        raise ValueError('Unique nonempty clip list required')
    for c in clips:
        if Path(c['clip']).name != c['clip'] or c['string'] not in range(6):
            raise ValueError('Invalid clip or lane')
        if c['pass'] not in (1, 2, 3) or not 0 <= c['labeled_begin'] < c['labeled_end']:
            raise ValueError('Invalid pass or label interval')
        if c['midi_note'] not in range(52, 57):
            raise ValueError('Outside frozen common-pitch selection')
    if {(c['string'], c['midi_note']) for c in clips} != {(s, n) for s in range(6) for n in range(52, 57)}:
        raise ValueError('Incomplete lane/pitch coverage')
    if len(clips) != 91:
        raise ValueError('Expected all 91 saved takes')
    return clips


# Fixed before rerun: silence padding is not signal warm-up. No per-clip search.
MEASUREMENT_OFFSET_SECONDS = .320
HARMONICS = 4


def measurement_bounds(begin, end, rate):
    start = begin + round(MEASUREMENT_OFFSET_SECONDS * rate)
    stop = start + 2 * round(.080 * rate)
    if stop > end:
        raise ValueError('Incomplete fixed post-warm-up window')
    return start, stop


def profile(rows, begin, rate):
    rows = [r for r in rows if begin <= int(r['sample']) < begin + 2 * round(rate * .080)]
    summary = summarize_trace(rows, begin, rate, harmonics=HARMONICS)
    phase_ok = bool(rows) and all(r['independent_phase_valid'] == '1' and
        np.isfinite(float(r['independent_phase_cents'])) and abs(float(r['independent_phase_cents'])) <= 50 for r in rows)
    eligible = bool(summary['eligible'] and phase_ok)
    shares = np.mean(summary['shares_per_half'], axis=0).tolist() if eligible else None
    return dict(eligible=eligible, shares=shares, runtime=summary, independent_phase_eligible=phase_ok)


def run(binary, corpus, manifest, output):
    data = json.loads(manifest.read_text())
    clips = validate_manifest(data)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema=2, state='running', final=False, input_manifest_sha256=digest(manifest),
        binary_sha256=digest(binary), source=data.get('source', {}), settings=SETTINGS,
        measurement_offset_seconds=MEASUREMENT_OFFSET_SECONDS, harmonics=HARMONICS,
        measurements=[], installed_output_changed=False, promotion_accepted=False,
        limitations=['Known-pitch isolated clips; same-session held-out pass/pitch classification only.',
                     'Fixed320–480ms relative to label, not verified onset; clip-local state.',
                     'No chord, continuous-state, allocation, timing or host acceptance.'])
    def save():
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    try:
        for c in clips:
            wav = corpus/c['clip']
            if digest(wav) != c['sha256']:
                raise ValueError('Clip hash mismatch')
            rate, samples = read_float_wave(wav)
            begin, end, note = c['labeled_begin'], c['labeled_end'], c['midi_note']
            if end > len(samples) or begin + round(.160*rate) > end:
                raise ValueError('Incomplete labeled window')
            measurement_begin, measurement_end = measurement_bounds(begin, end, rate)
            directory = output/wav.stem
            directory.mkdir()
            labels = directory/'labels.tsv'
            labels.write_text(f'start_sample\tend_sample\tmidi_note\tstring_mask\n{begin}\t{end}\t{note}\t{1 << c["string"]}\n')
            base = [str(binary.resolve()), '--wav', str(wav.resolve()), '--labels', str(labels.resolve()), '--block', '512', '--label-details']
            for k,v in SETTINGS.items():
                base += ['--'+k, str(v)]
            for mode in ('reference', 'traced'):
                command = base + ['--midi-event-trace', str((directory/(mode+'-midi.tsv')).resolve())]
                if mode == 'traced':
                    command += ['--candidate-trace', str((directory/'candidate.tsv').resolve()), '--candidate-trace-note', str(note),
                        '--candidate-trace-start', '0', '--candidate-trace-end', str(measurement_end/rate)]
                with (directory/(mode+'.tsv')).open('x') as stdout, (directory/(mode+'.stderr')).open('x') as stderr:
                    subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=90)
            comparison = compare_replays(read_replay(directory/'reference.tsv'), read_replay(directory/'traced.tsv'))
            midi_same = digest(directory/'reference-midi.tsv') == digest(directory/'traced-midi.tsv')
            if not comparison['output_bit_identical'] or comparison['changed_labels'] or not midi_same:
                raise ValueError('Tracing changed detector output')
            with (directory/'candidate.tsv').open() as f:
                measured = profile(list(csv.DictReader(f, delimiter='\t')), measurement_begin, rate)
            report['measurements'].append({**c, **measured, 'measurement_begin':measurement_begin, 'measurement_end':measurement_end, 'measurement_source':'runtime', 'comparison':comparison, 'midi_bit_identical':midi_same})
            save()
        report['evaluations'] = [evaluate(report['measurements'], holdout=h, lanes=list(range(6)), harmonics=HARMONICS) for h in ('pass', 'midi_note')]
        report.update(state='completed', final=True)
    except Exception as error:
        report.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(**vars(parser.parse_args()))
