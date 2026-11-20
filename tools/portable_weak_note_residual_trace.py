"""Bounded weak-note residual observation; never changes admission."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import subprocess

from tools.portable_assignment_trace import compress_trace_window, digest, read_rows, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for

RATE = 96000
# Genuine octave windows are the saved outcome coverage for labels 29 and 42.
CASES = (
    ('genuine56', 56, 489855, 561600),
    ('genuine60', 60, 653055, 724800),
    ('missing81', 81, 2692986, 2764800),
    ('missing72', 72, 2692986, 2764800),
    ('false74', 74, 2939903, 3009600),
    ('genuine70', 70, 5958719, 6007296),
    ('genuine74', 74, 7100415, 7171200),
)
LIMITS = ('Observation only; target omitted from base fit even if owned. '
          'Invalid fits are unavailable, not negative evidence. Decimated samples; '
          'no admission, timing or host acceptance claim.')


def summarize(rows, note, start, end):
    if not rows:
        raise ValueError('No residual observations')
    samples = [int(r['sample']) for r in rows]
    if samples != sorted(set(samples)) or any(not start <= s < end for s in samples):
        raise ValueError('Duplicate, unordered or out-of-window observations')
    for row in rows:
        if int(row['note']) != note or note in [int(n) for n in row['base_notes'].split(',') if n]:
            raise ValueError('Wrong target or target included in base')
        if int(row['tick']) % 16:
            raise ValueError('Unexpected decimation')
        for key in ('base_valid', 'added_valid', 'paired_available', 'paired_base_valid', 'paired_added_valid', 'parent_evidence', 'parent_in_base'):
            if row[key] not in ('0', '1'):
                raise ValueError('Invalid validity flag')
    valid = [r for r in rows if r['base_valid'] == r['added_valid'] == '1']
    result = dict(rows=len(rows), jointly_valid=len(valid), first_sample=samples[0],
                  last_sample=samples[-1], expected_rows=sum(int(r['expected_note']) for r in rows),
                  emitted_rows=sum(int(r['already_emitted']) for r in rows))
    for key in ('residual_gain', 'independent_energy', 'fundamental_overlap', 'score_ratio'):
        values = [float(r[key]) for r in valid]
        if any(not math.isfinite(v) for v in values):
            raise ValueError('Nonfinite valid-fit observation')
        result[key] = dict(min=min(values), median=statistics.median(values), max=max(values)) if values else None
    paired = []
    for row in rows:
        if int(row['parent_note']) != note - 12:
            raise ValueError('Wrong octave competitor')
        available = row['paired_available'] == '1'
        if not available and (row['paired_base_valid'] == '1' or row['paired_added_valid'] == '1'):
            raise ValueError('Unavailable pair marked valid')
        if available and row['parent_evidence'] != '1':
            raise ValueError('Pair lacks candidate evidence')
        if available and row['paired_base_valid'] == row['paired_added_valid'] == '1':
            value = float(row['paired_gain'])
            if not math.isfinite(value):
                raise ValueError('Nonfinite paired gain')
            paired.append(value)
    result['paired_available_rows'] = sum(r['paired_available'] == '1' for r in rows)
    result['paired_jointly_valid'] = len(paired)
    result['paired_gain'] = dict(min=min(paired), median=statistics.median(paired), max=max(paired)) if paired else None
    return result


def check_identity(snapshot, midi, saved):
    if digest(snapshot) != saved['tsv_sha256'] or digest(midi) != saved['midi_trace_sha256']:
        raise ValueError('Complete saved snapshot or raw MIDI identity failed')


def run(binary, corpus, manifest_path, reference_path, output, timeout=900):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_weak_note_residual_trace_v2', state='running', final=False,
                  installed_output_changed=False, promotion_accepted=False,
                  limits=LIMITS, captures=[], cases={}, settings=SETTINGS)
    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        verify_inputs(corpus, manifest, 'ordinary')
        if reference['dataset'] != 'ordinary' or reference['settings'] != SETTINGS:
            raise ValueError('Reference configuration mismatch')
        if reference['block_samples'] != 512 or reference['reference_flags']['current-on'] != ['--diagnostic-spectral-lane-collision']:
            raise ValueError('Reference policy mismatch')
        for name, identity in reference['inputs'].items():
            if manifest['files'][name] != identity:
                raise ValueError('Saved input identity mismatch: ' + name)
        for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
            if manifest['source'][key] != reference['source'][key]:
                raise ValueError('Input provenance mismatch: ' + key)
        report.update(source=manifest['source'], binary_sha256=digest(binary),
                      manifest_sha256=digest(manifest_path), reference_sha256=digest(reference_path))
        base = command_for(binary.resolve(), corpus.resolve(), 'ordinary', 'on', 512,
                           None, spectral_lane_collision=True)
        saved = reference['runs']['current-on']
        def replay(stem, extra):
            snapshot, midi = output / (stem + '.tsv'), output / (stem + '-midi.tsv')
            command = base + ['--midi-event-trace', str(midi)] + extra
            report.update(stage=stem, command=command)
            save()
            with snapshot.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, timeout=timeout, check=True)
            check_identity(snapshot, midi, saved)
            return dict(snapshot_sha256=digest(snapshot), midi_sha256=digest(midi),
                        saved_identity=True)
        for name, note, start, end in CASES:
            trace = output / (name + '-residual.tsv')
            identity = replay(name, ['--residual-admission-trace', str(trace),
                '--residual-admission-note', str(note), '--residual-admission-start', str(start / RATE),
                '--residual-admission-end', str(end / RATE)])
            report['cases'][name] = summarize(read_rows(trace), note, start, end)
            retained = compress_trace_window(trace, start=start, end=end)
            trace.unlink()
            report['captures'].append(dict(name=name, note=note, start=start, end=end,
                                          identity=identity, trace=retained))
            save()
        report.update(state='completed', final=True, stage='bounded residual observations collected')
    except Exception as error:
        report.update(state='failed', final=True, error=str(error))
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference, args.output)


if __name__ == '__main__':
    main()
