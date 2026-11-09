"""Reject one recorded detector note-off, clean up, Panic, then resume audio.

Runs only the enabled ownership trial in the instrumented VST3 component.
The three inserted silent blocks are explicit; they never replace input audio.
"""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import time

from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, read_callbacks, verify_inputs


COUNTERS = ('sample_count', 'sample_rate', 'sample_bits', 'block_samples',
            'queue_rejections', 'output_blocked_blocks', 'dry_audio_mismatches',
            'process_failures')
FLAGS = ('trial', 'rejection_injected', 'unexpected_early_block',
         'calibration_merge_matches', 'invalid_event', 'trace_write_failed')
BOUNDARY_COUNTERS = ('timeline_samples', 'recording_samples', 'detector_samples',
                     'detector_transitions', 'accepted_events', 'event_add_attempts')
NAMES = ('fault', 'cleanup', 'panic', 'ready', 'end')
LIMITS = ('Offline instrumented M3 VST3 component, ownership trial ON, per-voice '
    'routing and restored calibration. Refuse the first real detector note-off '
    'once. Insert three silent blocks: accepting cleanup without Panic, Panic '
    'control, then quiet hold completion. Resume every remaining recorded sample. '
    'This measures one rejection/Panic scenario, not external DAW/device delivery, '
    'label matches, processing allocation or deadlines. EOF opens are retained '
    'before teardown without forced release; they are not proof of stuck MIDI.')


def identity(event):
    return event['channel'], event['note_id'], event['note']


def assess(native, callbacks, *, clock, sample_bits):
    if (any(type(native.get(key)) is not int or native[key] < 0 for key in COUNTERS)
            or any(type(native.get(key)) is not bool for key in FLAGS)):
        raise ValueError('Incomplete recovery counters or flags')
    if (native.get('schema') != 'm3_vst3_recovery_native_v1'
            or native.get('scenario') != 'reject-off-panic'
            or native.get('routing') != 'per_voice' or native['trial'] is not True
            or native['sample_bits'] != sample_bits or native['block_samples'] != 512
            or any(native[key] != value for key, value in clock.items())):
        raise ValueError('Recovery provenance differs')
    boundaries = native.get('boundaries')
    if (not isinstance(boundaries, list) or len(boundaries) != len(NAMES)
            or any(not isinstance(b, dict) or b.get('name') != name
                   or any(type(b.get(key)) is not int or b[key] < 0 for key in BOUNDARY_COUNTERS)
                   or any(type(b.get(key)) is not bool for key in ('output_blocked', 'panic_hold'))
                   for b, name in zip(boundaries, NAMES))):
        raise ValueError('Missing recovery stages or counters')
    fault, cleanup, panic, ready, end = boundaries
    rejected = native.get('rejected_event', {})
    if (any(type(rejected.get(key)) is not int for key in ('sample', 'note', 'note_id', 'channel'))
            or not 0 <= rejected['note'] <= 127 or not 0 <= rejected['channel'] < 8
            or rejected['note_id'] != -1000 - (rejected['channel'] * 128 + rejected['note'])):
        raise ValueError('Malformed refused event identity')
    events = callbacks['events']
    if (len(events) != end['accepted_events'] or len(events) != callbacks['observed_events']
            or any(b['accepted_events'] != sum(e['sample'] < b['timeline_samples'] for e in events)
                   or b['accepted_events'] > b['event_add_attempts']
                   or b['detector_samples'] > b['recording_samples'] for b in boundaries)
            or any(left[key] > right[key] for left, right in zip(boundaries, boundaries[1:])
                   for key in BOUNDARY_COUNTERS)):
        raise ValueError('Recovery callback or sample accounting differs')
    held = {}
    for event in events[:fault['accepted_events']]:
        if event['kind'] == 'on':
            held[identity(event)] = event
        else:
            held.pop(identity(event), None)
    cleanup_events = events[fault['accepted_events']:cleanup['accepted_events']]
    resumed_events = events[ready['accepted_events']:]
    resumed_transitions = end['detector_transitions'] - ready['detector_transitions']
    resumed_samples = clock['sample_count'] - fault['recording_samples']
    expected_timeline = clock['sample_count'] + 3 * 512
    gates = dict(
        rejection_is_real_owned_off=native['rejection_injected']
            and not native['unexpected_early_block'] and identity(rejected) in held
            and held[identity(rejected)]['sample'] <= rejected['sample']
            and fault['timeline_samples'] - 512 <= rejected['sample'] < fault['timeline_samples']
            and fault['detector_transitions'] > fault['accepted_events'],
        exactly_one_callback_refused=all(b['event_add_attempts'] == b['accepted_events'] + 1
                                       for b in boundaries),
        explicit_inserted_silence=fault['timeline_samples'] == fault['recording_samples']
            and 0 < fault['recording_samples'] < clock['sample_count']
            and fault['recording_samples'] % 512 == 0
            and all(b['timeline_samples'] == fault['timeline_samples'] + (index + 1) * 512
                    and b['recording_samples'] == fault['recording_samples']
                    for index, b in enumerate((cleanup, panic, ready))),
        expected_recovery_states=all(b['output_blocked'] == blocked and b['panic_hold'] == hold
            for b, blocked, hold in zip(boundaries, (True, True, True, False, False),
                                       (False, False, True, False, False)))
            and native['output_blocked_blocks'] == 3,
        prior_owners_released_once=len(cleanup_events) == len(held) > 0
            and {identity(e) for e in cleanup_events} == set(held)
            and all(e['kind'] == 'off' and e['sample'] == fault['timeline_samples'] for e in cleanup_events),
        panic_and_hold_emit_no_notes=panic['accepted_events'] == cleanup['accepted_events'] == ready['accepted_events']
            and panic['event_add_attempts'] == cleanup['event_add_attempts'] == ready['event_add_attempts'],
        detector_waits_for_recovery=all(b['detector_samples'] == fault['detector_samples']
            and b['detector_transitions'] == fault['detector_transitions'] for b in (cleanup, panic, ready)),
        full_recording_resumed=end['recording_samples'] == clock['sample_count']
            and end['timeline_samples'] == expected_timeline
            and fault['detector_samples'] == fault['recording_samples']
            and end['detector_samples'] == clock['sample_count']
            and end['detector_samples'] - ready['detector_samples'] == resumed_samples,
        resumed_transitions_delivered=len(resumed_events) == resumed_transitions > 0
            and any(e['kind'] == 'on' for e in resumed_events),
        no_extra_output_faults=native['queue_rejections'] == 0 and native['process_failures'] == 0,
        calibration_restored=native['calibration_merge_matches'],
        dry_audio_preserved=native['dry_audio_mismatches'] == 0,
        valid_capture=not native['invalid_event'] and not native['trace_write_failed'],
        legal_callback_ownership=all(value == 0 for value in callbacks['counts'].values()))
    return dict(gates=gates, gate_pass=all(gates.values()),
        accepted_cleanup_note_offs=len(cleanup_events),
        owners_before_cleanup=len(held), post_recovery_detector_transitions=resumed_transitions,
        post_recovery_accepted_events=len(resumed_events),
        post_recovery_note_ons=sum(e['kind'] == 'on' for e in resumed_events),
        expected_resumed_recording_samples=resumed_samples,
        inserted_silence_samples=3 * 512, expected_timeline_samples=expected_timeline)


def run(args):
    actual_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual_source != args.source_sha:
        raise ValueError('Harness source commit differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_recovery_replay_v1', state='running', final=False,
        source_commit=actual_source, dataset='ordinary', settings=SETTINGS,
        scenario='reject-off-panic', routing='per_voice', block_samples=512,
        runs={}, interpretation=LIMITS, installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured',
        native_timing='not measured', labeled_note_matches='not measured',
        processing_allocations='not measured')

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
        for sample_bits in (32, 64):
            name = f'on-{sample_bits}'
            directory = args.output / name
            directory.mkdir()
            callbacks_path = directory / 'callbacks.tsv'
            command = [str(args.binary.resolve()), '--wav', str((args.corpus / 'ordinary.wav').resolve()),
                '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                '--events', str(callbacks_path.resolve()), '--sample-bits', str(sample_bits),
                '--trial', '1', '--scenario', 'reject-off-panic']
            report['stage'] = name
            save()
            started = time.monotonic()
            with (directory / 'native.json').open('x') as stdout, (directory / 'native.stderr').open('x') as stderr:
                completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=600, check=False)
            if completed.returncode:
                raise RuntimeError(f'{name}: native exit {completed.returncode}; inspect captured output')
            native = json.loads((directory / 'native.json').read_text())
            callbacks = read_callbacks(callbacks_path, sample_count=clock['sample_count'] + 3 * 512,
                expected_count=native['boundaries'][-1]['accepted_events'], include_events=True)
            assessment = assess(native, callbacks, clock=clock, sample_bits=sample_bits)
            del callbacks['events']
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
        passed = sum(run['gate_pass'] for run in report['runs'].values())
        report.update(state='completed', final=True, stage='recorded VST3 rejection/Panic recovery collected',
            on_format_gates_passed=passed, on_format_gates_total=2, recovery_gate_pass=passed == 2,
            decision='offline recovery gate passed' if passed == 2 else 'rejected by offline recovery gate')
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
    print(json.dumps({key: report[key] for key in ('state', 'recovery_gate_pass', 'decision')}))
    return 0 if report['recovery_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
