"""Fixed-window, selection-independent phase observation; never changes admission."""
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
CASES = (
    ('annotated70', 70, 5958719, 6007296),
    ('gap70', 70, 6007359, 6030528),
    ('annotated74', 74, 7100415, 7171200),
    ('octave_negative74', 74, 2939903, 3009600),
)
CAPTURES = ((70, 5958719, 6030528), (74, 7100415, 7171200),
            (74, 2939903, 3009600))
LIMITS = ('Selection-independent phase is not independent-source evidence. '
          'Frequency agreement cannot reject genuine octaves. Missing/invalid phase '
          'is unavailable, not zero. Same-recording diagnostic, no threshold selection, '
          'allocation/timing acceptance or host-delivery claim.')


def phase_rows(rows, note, start, end):
    expected = list(range(start, end, 64))
    if [int(r['sample']) for r in rows] != expected:
        raise ValueError('Missing, duplicate or misaligned candidate ticks')
    result = {}
    for row in rows:
        if int(row['note']) != note:
            raise ValueError('Wrong candidate note')
        valid = int(row['independent_phase_valid'])
        cents = float(row['independent_phase_cents'])
        updates = int(row['independent_phase_updates'])
        if valid not in (0, 1) or not math.isfinite(cents) or updates < 0:
            raise ValueError('Invalid phase observation')
        result[int(row['sample'])] = cents if valid else None
    return result


def paired_summary(target, parent, start, end):
    samples = list(range(start, end, 64))
    differences = [target[s] - parent[s] for s in samples
                   if target.get(s) is not None and parent.get(s) is not None]
    return dict(ticks=len(samples), target_valid=sum(target.get(s) is not None for s in samples),
                parent_valid=sum(parent.get(s) is not None for s in samples),
                jointly_valid=len(differences),
                # Cents relative to MIDI centers: subtracting removes exactly one octave.
                upper_minus_parent_octave_cents=(dict(min=min(differences),
                    median=statistics.median(differences), max=max(differences))
                    if differences else None))


def check_identity(snapshot, midi, saved):
    if digest(snapshot) != saved['tsv_sha256'] or digest(midi) != saved['midi_trace_sha256']:
        raise ValueError('Complete saved snapshot or raw MIDI identity failed')


def run(binary, corpus, manifest_path, reference_path, output, timeout=900):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_octave_phase_trace_v1', state='running', final=False,
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
        report['reference'] = replay('reference-current-on', [])
        for upper, start, end in CAPTURES:
            observations = {}
            for note in (upper, upper - 12):
                stem = f'n{note}-{start}'
                trace = output / (stem + '-candidate.tsv')
                identity = replay(stem, ['--candidate-trace', str(trace),
                    '--candidate-trace-note', str(note), '--candidate-trace-start', str(start / RATE),
                    '--candidate-trace-end', str(end / RATE)])
                observations[note] = phase_rows(read_rows(trace), note, start, end)
                retained = compress_trace_window(trace, start=start, end=end)
                trace.unlink()  # Only this runner's redundant uncompressed file.
                report['captures'].append(dict(note=note, start=start, end=end,
                                              identity=identity, trace=retained))
                save()
            for name, note, begin, finish in CASES:
                if note == upper and start <= begin < finish <= end:
                    report['cases'][name] = paired_summary(observations[upper],
                                                          observations[upper - 12], begin, finish)
        report.update(state='completed', final=True, stage='fixed phase observations collected')
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
