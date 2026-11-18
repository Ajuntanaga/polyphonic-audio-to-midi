"""Compare actual VST3 stable identities with frozen ledger callbacks on GHA.

No detector replay manufactures expectations. The old artifact supplies exact
callbacks; six component passes check accepting delivery and explicit recovery.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import zipfile

from tools.portable_midi_ledger_replay import digest
from tools.portable_stable_note_identity_ledger import CALLBACK_FIELDS, sink_spans, pitch_timeline
from tools.portable_vst3_completion_midi_replay import compare_callbacks
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks
from tools.portable_vst3_recovery_replay import assess as assess_recovery

MODES = ('per_voice', 'stable_note')
MAX_TRACE_BYTES = 1024 * 1024


def verify_inputs(corpus, manifest, reference, source_sha):
    if (not re.fullmatch('[0-9a-f]{40}', source_sha)
            or manifest['source']['commit'] != source_sha
            or reference['schema'] != 'm3_vst3_stable_note_identity_references_v1'
            or reference['state'] != 'completed' or reference['final'] is not True
            or reference['dataset'] != 'ordinary' or reference['settings'] != SETTINGS
            or set(reference['runs']) != set(MODES)):
        raise ValueError('Source or stable note reference provenance differs')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if not reference['source'].get(key) or manifest['source'].get(key) != reference['source'][key]:
            raise ValueError('Recording bundle provenance differs: ' + key)
    verified = {}
    for name in ('ordinary.wav', 'ordinary.tsv', 'calibration.m3cb'):
        actual = digest(corpus / name)
        if actual != manifest['files'][name]['sha256'] or actual != reference['inputs'][name]['sha256']:
            raise ValueError('Input hash differs: ' + name)
        verified[name] = actual
    clock = reference['recording_clock']
    if (set(clock) != {'sample_count', 'sample_rate'}
            or any(type(value) is not int or value <= 0 for value in clock.values())):
        raise ValueError('Invalid reference recording clock')
    return verified, clock


def stage_references(reference, archive_path, destination):
    artifact = reference['artifact']
    if (archive_path.stat().st_size != artifact['size_in_bytes']
            or digest(archive_path) != artifact['sha256']):
        raise ValueError('Saved artifact size or hash differs')
    destination.mkdir(parents=True, exist_ok=False)
    result = {}
    with zipfile.ZipFile(archive_path) as archive:
        for mode in MODES:
            trace = reference['runs'][mode]['callbacks']
            count, size = trace['retained_rows'], trace['raw_bytes']
            if (type(count) is not int or count <= 0
                    or type(size) is not int or not 0 < size <= MAX_TRACE_BYTES
                    or trace['captured_rows'] != count or trace['discarded_rows'] != 0
                    or trace['captured_raw_bytes'] != size
                    or trace['captured_raw_sha256'] != trace['raw_sha256']
                    or trace['start_sample_inclusive'] != 0
                    or trace['end_sample_exclusive'] != reference['recording_clock']['sample_count']):
                raise ValueError('Reference callbacks are not a complete capture')
            members = [item for item in archive.infolist()
                       if Path(item.filename).name == trace['file'] and not item.is_dir()]
            if (len(members) != 1 or members[0].file_size != trace['bytes']
                    or not 0 < members[0].file_size <= MAX_TRACE_BYTES):
                raise ValueError('Missing, duplicate or oversized callback member')
            compressed = archive.read(members[0])
            if hashlib.sha256(compressed).hexdigest() != trace['sha256']:
                raise ValueError('Compressed callback hash differs')
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(MAX_TRACE_BYTES + 1)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != trace['raw_sha256']:
                raise ValueError('Raw callback size or hash differs')
            (destination / (mode + '.tsv')).write_bytes(raw)
            stream = io.StringIO(raw.decode('utf-8'))
            if stream.readline() != '# m3_ledger_callbacks_v1\n':
                raise ValueError('Unknown saved callback schema')
            rows = csv.DictReader(stream, delimiter='\t')
            if rows.fieldnames != list(CALLBACK_FIELDS):
                raise ValueError('Malformed saved callback header')
            events = []
            for row in rows:
                if set(row) != set(CALLBACK_FIELDS) or row['phase'] != 'source':
                    raise ValueError('Unexpected saved cleanup callback')
                for key in CALLBACK_FIELDS:
                    if key not in ('kind', 'phase'):
                        row[key] = int(row[key])
                if (row['kind'] not in ('on', 'off') or not 0 <= row['voice_id'] < 8
                        or row['channel'] != row['voice_id'] + 1
                        or not 0 <= row['note'] <= 127 or not 0 <= row['velocity'] <= 127
                        or (row['kind'] == 'on') != (row['velocity'] > 0)
                        or not 0 <= row['sample'] < reference['recording_clock']['sample_count']
                        or (events and row['sample'] < events[-1]['sample'])):
                    raise ValueError('Invalid saved callback')
                row['sequence'] = len(events)
                events.append(row)
            if len(events) != count:
                raise ValueError('Saved callback count differs')
            sink_spans(events, reference['recording_clock']['sample_count'])
            result[mode] = events
    return result


def run(args):
    actual_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual_source != args.source_sha:
        raise ValueError('Harness source commit differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_stable_note_replay_v1', state='running', final=False,
        source_commit=actual_source, dataset='ordinary', settings=SETTINGS,
        block_samples=512, runs={}, installed_output_changed=False,
        production_defaults_changed=False, promotion_accepted=False,
        live_readiness='not measured', native_timing='not measured',
        processing_allocations='not measured', acoustic_repluck_quality='not measured',
        interpretation='Actual instrumented VST3 component with a test event list. '
            'Stable sink IDs are not physical strings. Full accepting callbacks must '
            'match the saved ledger including articulation and pitch multiplicity; '
            'recovery is a separate refused-Off/Panic scenario with three inserted '
            'silent blocks. No external DAW/device or live-readiness claim. '
            'Open notes at EOF are retained, not proof of stuck MIDI.')

    def save():
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        temporary = args.output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(args.output / 'report.json')

    save()
    try:
        manifest = json.loads(args.manifest.read_text())
        reference = json.loads(args.reference.read_text())
        verified, clock = verify_inputs(args.corpus, manifest, reference, actual_source)
        expected = stage_references(reference, args.evidence_archive, args.output / 'saved-callbacks')
        report.update(source=manifest['source'], verified_input_sha256=verified,
            recording_clock=clock, reference_sha256=digest(args.reference),
            reference_source=reference['source'], reference_artifact=reference['artifact'],
            input_manifest_sha256=digest(args.manifest), binary_sha256=digest(args.binary))
        for bits in (32, 64):
            for scenario, mode in (('accept', 'per_voice'), ('accept', 'stable_note'),
                                   ('reject-off-panic', 'stable_note')):
                stable = mode == 'stable_note'
                recovery = scenario != 'accept'
                name = f'{scenario}-{mode}-{bits}'
                directory = args.output / name
                directory.mkdir()
                trace = directory / 'callbacks.tsv'
                command = [str(args.binary.resolve()), '--wav', str((args.corpus / 'ordinary.wav').resolve()),
                    '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                    '--events', str(trace.resolve()), '--sample-bits', str(bits),
                    '--trial', '1', '--stable-note-identity', '1' if stable else '0']
                if recovery:
                    command += ['--scenario', scenario]
                report['stage'] = name
                save()
                started = time.monotonic()
                with (directory / 'native.json').open('x') as stdout, (directory / 'native.stderr').open('x') as stderr:
                    completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=900, check=False)
                if completed.returncode:
                    raise RuntimeError(f'{name}: native exit {completed.returncode}; inspect captured output')
                native = json.loads((directory / 'native.json').read_text())
                count = native['boundaries'][-1]['accepted_events'] if recovery else native['accepted_events']
                samples = clock['sample_count'] + (1536 if recovery else 0)
                callbacks = read_callbacks(trace, sample_count=samples, expected_count=count, include_events=True)
                comparison = None
                if recovery:
                    assessment = assess_recovery(native, callbacks, clock=clock, sample_bits=bits,
                                                 stable_note_identity=True)
                    assessment['gates']['stable_continuations_exercised'] = assessment['post_recovery_transferred_pairs'] > 0
                else:
                    assessment = assess(native, callbacks, clock=clock, sample_bits=bits,
                                        trial=True, stable_note_identity=stable)
                    comparison = compare_callbacks(callbacks['events'], expected[mode])
                    assessment['gates'].update(
                        exact_saved_callback_match=comparison['exact_saved_midi_match'],
                        exact_saved_transfers=native['transferred_pairs'] == reference['runs'][mode]['transferred_pairs'],
                        exact_detector_transition_count=native['detector_transitions'] == reference['detector_transitions'],
                        separate_retention_policy_off=native.get('completion_midi_retention') is False)
                assessment['gate_pass'] = all(assessment['gates'].values())
                callbacks.pop('events')
                raw_sha, raw_bytes = digest(trace), trace.stat().st_size
                compressed = trace.with_suffix('.tsv.gz')
                with trace.open('rb') as raw, compressed.open('xb') as output:
                    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as archive:
                        shutil.copyfileobj(raw, archive)
                trace.unlink()
                report['runs'][name] = dict(native=native, callbacks=callbacks, comparison=comparison,
                    **assessment, elapsed_seconds=time.monotonic() - started,
                    trace=dict(file=f'{name}/{compressed.name}', bytes=compressed.stat().st_size,
                               sha256=digest(compressed), raw_bytes=raw_bytes, raw_sha256=raw_sha))
                save()
        identity = {f'{scenario}-{mode}': report['runs'][f'{scenario}-{mode}-32']['trace']['raw_sha256'] ==
                    report['runs'][f'{scenario}-{mode}-64']['trace']['raw_sha256']
                    for scenario, mode in (('accept', 'per_voice'), ('accept', 'stable_note'),
                                           ('reject-off-panic', 'stable_note'))}
        expected_timelines = {mode: pitch_timeline(sink_spans(expected[mode], clock['sample_count'])[0],
                                                  clock['sample_count']) for mode in MODES}
        same_pitch = expected_timelines[MODES[0]] == expected_timelines[MODES[1]]
        passed = all(row['gate_pass'] for row in report['runs'].values()) and all(identity.values()) and same_pitch
        report.update(state='completed', final=True, stage='component stable-note screen complete',
            format_callback_identity=identity, saved_pitch_multiplicity_identical=same_pitch,
            integration_gate_pass=passed,
            saved_accepting_metrics_if_exact={mode: {key: reference['runs'][mode][key]
                for key in ('target', 'pitch_safety', 'open_pitches_at_eof')} for mode in MODES},
            saved_label_count=reference['label_count'],
            decision='offline component gate passed' if passed else 'rejected by component gate')
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference', 'evidence-archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    report = run(parser.parse_args())
    print(json.dumps({key: report[key] for key in ('state', 'integration_gate_pass', 'decision')}))
    return 0 if report['integration_gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
