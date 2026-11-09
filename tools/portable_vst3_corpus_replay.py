"""Feed a recorded waveform through the VST3 processor and its MIDI ledger.

The accepting test event list observes the component's real detector feedback.
It does not measure an external DAW, MIDI device, control recovery or deadlines.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

from tools.midi_lifecycle_analysis import raw_conflicts
from tools.portable_midi_ledger_replay import digest


FIELDS = ('sample', 'kind', 'note', 'velocity', 'note_id', 'channel')
COUNTERS = ('sample_count', 'sample_rate', 'sample_bits', 'block_samples',
    'processed_samples', 'blocks', 'detector_samples', 'detector_transitions',
    'queue_rejections', 'event_add_attempts', 'accepted_events',
    'output_blocked_blocks', 'dry_audio_mismatches', 'process_failures')
FLAGS = ('trial', 'output_blocked_at_eof', 'calibration_merge_matches',
         'invalid_event', 'trace_write_failed')
SETTINGS = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
            'max-polyphony': 5, 'max-fret': 24}
LIMITS = ('Offline instrumented M3 VST3 component with an accepting test event '
    'list, restored calibration, canonical M3 settings, per-voice routing and '
    'no control changes. Detection is gated by the '
    'actual production ledger. Accepted callbacks are not external DAW or device '
    'delivery. Label matches, allocation, timing and rejection recovery are not '
    'measured. EOF opens are retained before teardown; no forced release or '
    'extra silence is injected, and an EOF open alone is not a stuck MIDI note.')


def verify_inputs(corpus, manifest, reference, source_sha):
    if (not re.fullmatch('[0-9a-f]{40}', source_sha)
            or manifest['source']['commit'] != source_sha
            or reference['state'] != 'completed' or reference['final'] is not True
            or reference['dataset'] != 'ordinary' or reference['settings'] != SETTINGS):
        raise ValueError('Source or ordinary reference provenance differs')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if manifest['source'].get(key) != reference['source'].get(key) or not reference['source'].get(key):
            raise ValueError('Recording bundle provenance differs: ' + key)
    verified = {}
    for name in ('ordinary.wav', 'calibration.m3cb'):
        actual = digest(corpus / name)
        if actual != manifest['files'][name]['sha256']:
            raise ValueError('Input hash differs: ' + name)
        verified[name] = actual
    # These counts belong to the same hash-verified recording bundle, not to a
    # native run whose partial processing could otherwise certify itself.
    clock = {key: reference['runs']['reference-off'][key]
             for key in ('sample_count', 'sample_rate')}
    if any(type(value) is not int or value <= 0 for value in clock.values()):
        raise ValueError('Invalid reference recording clock')
    return verified, clock


def read_callbacks(path, *, sample_count, expected_count):
    events = []
    with Path(path).open(newline='') as stream:
        if stream.readline().rstrip('\r\n') != '# m3_vst3_corpus_events_v1':
            raise ValueError('Unknown VST3 callback trace')
        rows = csv.DictReader(stream, delimiter='\t')
        if rows.fieldnames != list(FIELDS):
            raise ValueError('Malformed VST3 callback header')
        for row in rows:
            if set(row) != set(FIELDS) or any(value is None for value in row.values()):
                raise ValueError('Malformed VST3 callback row')
            numbers = {key: int(row[key]) for key in ('sample', 'note', 'note_id', 'channel')}
            sample, note, channel = (numbers[key] for key in ('sample', 'note', 'channel'))
            velocity = float(row['velocity'])
            if (row['kind'] not in ('on', 'off') or not 0 <= sample < sample_count
                    or not 0 <= note <= 127 or not 0 <= channel < 8
                    or numbers['note_id'] != -1000 - (channel * 128 + note)
                    or not math.isfinite(velocity) or not 0 <= velocity <= 1
                    or (row['kind'] == 'on' and velocity == 0)
                    or (row['kind'] == 'off' and velocity != 0)
                    or (events and sample < events[-1]['sample'])):
                raise ValueError('Invalid VST3 callback identity, clock or velocity')
            # With base channel one, assigned M3 lanes map to zero-based VST3
            # channels. Validate noteId too; never discard the observed channel.
            events.append(dict(kind=row['kind'], velocity=velocity,
                voice_id=channel, sequence=len(events), **numbers))
    if len(events) != expected_count:
        raise ValueError('Callback count differs from native report')
    conflicts = raw_conflicts(events)
    return dict(counts=conflicts['counts'], examples=conflicts['examples'],
        note_ons_open_at_eof=conflicts['raw_note_ons_open_at_eof'],
        observed_events=len(events), scope='Accepted VST3 callbacks, by channel and noteId')


def assess(native, callbacks, *, clock, sample_bits, trial):
    if (any(type(native.get(key)) is not int or native[key] < 0 for key in COUNTERS)
            or any(type(native.get(key)) is not bool for key in FLAGS)):
        raise ValueError('Incomplete native counters or flags')
    if (native.get('schema') != 'm3_vst3_corpus_native_v1'
            or native.get('routing') != 'per_voice' or native['sample_bits'] != sample_bits
            or native['trial'] != trial or native['block_samples'] != 512
            or any(native[key] != value for key, value in clock.items())):
        raise ValueError('Native report provenance differs')
    first = native.get('first_blocked_sample')
    blocked = native['output_blocked_blocks']
    if (native['processed_samples'] > clock['sample_count']
            or native['detector_samples'] > native['processed_samples']
            or native['blocks'] != (native['processed_samples'] + 511) // 512
            or blocked > native['blocks']
            or native['accepted_events'] != callbacks['observed_events']
            or native['accepted_events'] > native['event_add_attempts']
            or (blocked == 0 and (first is not None or native['output_blocked_at_eof']))
            or (blocked > 0 and (type(first) is not int or not 0 <= first < native['processed_samples']
                               or first % 512 != 0))):
        raise ValueError('Native callback or sample accounting differs')
    gates = dict(
        full_audio_processed=native['processed_samples'] == clock['sample_count'] and native['process_failures'] == 0,
        full_detector_coverage=native['detector_samples'] == clock['sample_count'],
        no_output_faults=native['queue_rejections'] == 0 and blocked == 0 and not native['output_blocked_at_eof'],
        all_transitions_delivered=native['accepted_events'] == native['detector_transitions'] > 0,
        accepting_event_list=native['event_add_attempts'] == native['accepted_events'],
        calibration_restored=native['calibration_merge_matches'],
        dry_audio_preserved=native['dry_audio_mismatches'] == 0,
        valid_capture=not native['invalid_event'] and not native['trace_write_failed'],
        legal_callback_ownership=all(value == 0 for value in callbacks['counts'].values()))
    return dict(gates=gates, gate_pass=all(gates.values()),
                samples_not_analyzed=clock['sample_count'] - native['detector_samples'])


def run(args):
    actual_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual_source != args.source_sha:
        raise ValueError('Harness source commit differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_corpus_replay_v1', state='running', final=False,
        source_commit=actual_source, dataset='ordinary', settings=SETTINGS,
        routing='per_voice', block_samples=512, runs={}, interpretation=LIMITS,
        installed_output_changed=False, promotion_accepted=False,
        live_readiness='not measured', native_timing='not measured',
        labeled_note_matches='not measured', processing_allocations='not measured')

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temporary = args.output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    save()
    try:
        manifest = json.loads(args.manifest.read_text())
        reference = json.loads(args.reference_checkpoint.read_text())
        verified, clock = verify_inputs(args.corpus, manifest, reference, actual_source)
        report.update(source=manifest['source'], verified_input_sha256=verified,
            recording_clock=clock, reference_checkpoint_sha256=digest(args.reference_checkpoint),
            input_manifest_sha256=digest(args.manifest), binary_sha256=digest(args.binary))
        # Native cases are serialized and limited to this one recording.
        for sample_bits in (32, 64):
            for trial in (False, True):
                name = f'{"on" if trial else "off"}-{sample_bits}'
                directory = args.output / name
                directory.mkdir()
                callbacks_path = directory / 'callbacks.tsv'
                command = [str(args.binary.resolve()), '--wav', str((args.corpus / 'ordinary.wav').resolve()),
                    '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                    '--events', str(callbacks_path.resolve()), '--sample-bits', str(sample_bits),
                    '--trial', '1' if trial else '0']
                report['stage'] = name
                save()
                started = time.monotonic()
                with (directory / 'native.json').open('x') as stdout, (directory / 'native.stderr').open('x') as stderr:
                    completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=600, check=False)
                if completed.returncode:
                    raise RuntimeError(f'{name}: native exit {completed.returncode}; inspect captured output')
                native = json.loads((directory / 'native.json').read_text())
                callbacks = read_callbacks(callbacks_path, sample_count=clock['sample_count'],
                                           expected_count=native['accepted_events'])
                assessment = assess(native, callbacks, clock=clock, sample_bits=sample_bits, trial=trial)
                raw_sha, raw_bytes = digest(callbacks_path), callbacks_path.stat().st_size
                compressed = callbacks_path.with_suffix('.tsv.gz')
                with callbacks_path.open('rb') as raw, compressed.open('xb') as output:
                    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as archive:
                        shutil.copyfileobj(raw, archive)
                callbacks_path.unlink()
                report['runs'][name] = dict(native=native, callbacks=callbacks, **assessment,
                    elapsed_seconds=time.monotonic() - started,
                    trace=dict(file=f'{name}/{compressed.name}', bytes=compressed.stat().st_size,
                        sha256=digest(compressed), raw_bytes=raw_bytes, raw_sha256=raw_sha))
                save()
        passed = sum(report['runs'][f'on-{bits}']['gate_pass'] for bits in (32, 64))
        report.update(state='completed', final=True, stage='recorded VST3 integration collected',
            on_format_gates_passed=passed, on_format_gates_total=2, integration_gate_pass=passed == 2,
            decision='offline integration gate passed' if passed == 2 else 'rejected by offline integration gate')
        report['delta_on_minus_off'] = {str(bits): {key:
            report['runs'][f'on-{bits}']['native'][key] - report['runs'][f'off-{bits}']['native'][key]
            for key in ('detector_samples', 'detector_transitions', 'accepted_events',
                        'queue_rejections', 'output_blocked_blocks')}
            for bits in (32, 64)}
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-checkpoint', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    report = run(parser.parse_args())
    print(json.dumps({key: report[key] for key in ('state', 'integration_gate_pass', 'decision')}))
    return 0 if report['integration_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
