"""Compare actual VST3 callbacks with saved current/retention detector MIDI.

Four serialized component passes run on GitHub, without an external host.
The two small reference traces are extracted from an existing remote artifact;
no new detector replay is used to manufacture the expected result.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import zipfile

from tools.midi_lifecycle_analysis import raw_conflicts, read_events
from tools.portable_midi_ledger_replay import digest
from tools.portable_vst3_corpus_replay import SETTINGS, assess, read_callbacks


MODES = ('current-on', 'completion-midi-retention-on')
MAX_TRACE_BYTES = 1024 * 1024
LIMITS = ('Instrumented actual VST3 component and accepting test event list, '
    'physical-long recording, 512-sample buffers, 32/64-bit audio. Exact callback '
    'comparison preserves the saved offline MIDI evidence, including unlabeled '
    'gaps; it is not a fresh labeled-frame score or external DAW/device delivery. '
    'The ledger sorts same-sample NoteOff before NoteOn, then original sequence. '
    'No forced EOF release, silence or control changes. Allocation and timing '
    'are not measured. Production defaults and installed output are unchanged.')


def verify_inputs(corpus, manifest, reference, source_sha):
    if (not re.fullmatch('[0-9a-f]{40}', source_sha)
            or manifest['source']['commit'] != source_sha
            or reference['schema'] != 'm3_vst3_completion_midi_references_v1'
            or reference['state'] != 'completed' or reference['final'] is not True
            or reference['dataset'] != 'physical-long'
            or reference['settings'] != SETTINGS or set(reference['runs']) != set(MODES)):
        raise ValueError('Source or saved MIDI reference provenance differs')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if not reference['source'].get(key) or manifest['source'].get(key) != reference['source'][key]:
            raise ValueError('Recording bundle provenance differs: ' + key)
    verified = {}
    for name in ('physical-long.wav', 'calibration.m3cb'):
        actual = digest(corpus / name)
        if actual != manifest['files'][name]['sha256']:
            raise ValueError('Input hash differs: ' + name)
        verified[name] = actual
    clock = reference['recording_clock']
    if (set(clock) != {'sample_count', 'sample_rate'}
            or any(type(value) is not int or value <= 0 for value in clock.values())):
        raise ValueError('Invalid reference recording clock')
    return verified, clock


def stage_references(reference, archive_path, destination):
    """Read only the two named gzip members; reject partial or substituted data."""
    artifact = reference['artifact']
    if (archive_path.stat().st_size != artifact['size_in_bytes']
            or digest(archive_path) != artifact['sha256']):
        raise ValueError('Saved artifact size or SHA-256 differs')
    destination.mkdir(parents=True, exist_ok=False)
    result = {}
    with zipfile.ZipFile(archive_path) as archive:
        for mode in MODES:
            trace = reference['runs'][mode]
            count = trace['retained_rows']
            size = trace['raw_bytes']
            if (type(count) is not int or count <= 0
                    or type(size) is not int or not 0 < size <= MAX_TRACE_BYTES
                    or trace['captured_rows'] != count or trace['discarded_rows'] != 0
                    or trace['captured_raw_bytes'] != size
                    or trace['captured_raw_sha256'] != trace['raw_sha256']
                    or trace['start_sample_inclusive'] != 0
                    or trace['end_sample_exclusive'] != reference['recording_clock']['sample_count']):
                raise ValueError('Saved MIDI reference is not a complete capture')
            members = [item for item in archive.infolist()
                       if Path(item.filename).name == trace['file'] and not item.is_dir()]
            if (len(members) != 1 or members[0].file_size != trace['bytes']
                    or not 0 < members[0].file_size <= MAX_TRACE_BYTES):
                raise ValueError('Missing, duplicate or oversized reference member')
            compressed = archive.read(members[0])
            if hashlib.sha256(compressed).hexdigest() != trace['sha256']:
                raise ValueError('Compressed MIDI reference hash differs')
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(MAX_TRACE_BYTES + 1)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != trace['raw_sha256']:
                raise ValueError('Raw MIDI reference size or hash differs')
            path = destination / (mode + '.tsv')
            path.write_bytes(raw)
            events = read_events(path, sample_count=reference['recording_clock']['sample_count'],
                                 transition_count=count)
            if any(raw_conflicts(events)['counts'].values()):
                raise ValueError('Saved MIDI reference has ownership conflicts')
            result[mode] = events
    return result


def compare_callbacks(events, expected):
    """Compare all host-visible fields after the ledger's documented ordering."""
    ordered = sorted(expected, key=lambda e: (e['sample'], e['kind'] == 'on', e['sequence']))
    differences = []
    mismatch_count = abs(len(events) - len(ordered))
    for index, (actual, wanted) in enumerate(zip(events, ordered)):
        # VST3 velocity is the original seven-bit value divided by 127 in float32.
        velocity = struct.unpack('f', struct.pack('f', wanted['velocity'] / 127.0))[0]
        if (any(actual[key] != wanted[key] for key in ('sample', 'kind', 'note', 'voice_id'))
                or abs(actual['velocity'] - velocity) > 1e-8):
            mismatch_count += 1
            if len(differences) < 8:
                differences.append(dict(index=index, callback=actual, expected=wanted))
    return dict(exact_saved_midi_match=mismatch_count == 0,
        expected_events=len(ordered), observed_events=len(events),
        differing_events=mismatch_count, examples=differences,
        ordering='sample, NoteOff before NoteOn, original sequence; VST3 float32 velocity')


def run(args):
    actual_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual_source != args.source_sha:
        raise ValueError('Harness source commit differs')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(schema='m3_vst3_completion_midi_replay_v1', state='running', final=False,
        source_commit=actual_source, dataset='physical-long', settings=SETTINGS,
        routing='per_voice', block_samples=512, runs={}, interpretation=LIMITS,
        installed_output_changed=False, production_defaults_changed=False,
        promotion_accepted=False, live_readiness='not measured',
        native_timing='not measured', processing_allocations='not measured')

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
        expected = stage_references(reference, args.evidence_archive, args.output / 'saved-midi')
        report.update(source=manifest['source'], verified_input_sha256=verified,
            recording_clock=clock, reference_sha256=digest(args.reference),
            reference_source=reference['source'], reference_artifact=reference['artifact'],
            input_manifest_sha256=digest(args.manifest), binary_sha256=digest(args.binary))
        for sample_bits in (32, 64):
            for mode in MODES:
                retention = mode == MODES[1]
                name = f'{mode}-{sample_bits}'
                directory = args.output / name
                directory.mkdir()
                callbacks_path = directory / 'callbacks.tsv'
                command = [str(args.binary.resolve()), '--wav', str((args.corpus / 'physical-long.wav').resolve()),
                    '--calibration', str((args.corpus / 'calibration.m3cb').resolve()),
                    '--events', str(callbacks_path.resolve()), '--sample-bits', str(sample_bits),
                    '--trial', '1', '--completion-midi-retention', '1' if retention else '0']
                report['stage'] = name
                save()
                started = time.monotonic()
                with (directory / 'native.json').open('x') as stdout, (directory / 'native.stderr').open('x') as stderr:
                    completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=900, check=False)
                if completed.returncode:
                    raise RuntimeError(f'{name}: native exit {completed.returncode}; inspect captured output')
                native = json.loads((directory / 'native.json').read_text())
                if native.get('completion_midi_retention') is not retention:
                    raise ValueError('Native retention policy differs')
                callbacks = read_callbacks(callbacks_path, sample_count=clock['sample_count'],
                    expected_count=native['accepted_events'], include_events=True)
                assessment = assess(native, callbacks, clock=clock, sample_bits=sample_bits, trial=True)
                comparison = compare_callbacks(callbacks.pop('events'), expected[mode])
                assessment['gates']['exact_saved_midi_match'] = comparison['exact_saved_midi_match']
                assessment['gate_pass'] = all(assessment['gates'].values())
                raw_sha, raw_bytes = digest(callbacks_path), callbacks_path.stat().st_size
                compressed = callbacks_path.with_suffix('.tsv.gz')
                with callbacks_path.open('rb') as raw, compressed.open('xb') as output:
                    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as archive:
                        shutil.copyfileobj(raw, archive)
                callbacks_path.unlink()
                report['runs'][name] = dict(native=native, callbacks=callbacks,
                    comparison=comparison, **assessment, command=command,
                    elapsed_seconds=time.monotonic() - started,
                    trace=dict(file=f'{name}/{compressed.name}', bytes=compressed.stat().st_size,
                        sha256=digest(compressed), raw_bytes=raw_bytes, raw_sha256=raw_sha))
                save()
                if not assessment['gate_pass']:
                    report.update(state='completed', final=True, integration_gate_pass=False,
                        decision='rejected by component callback gate')
                    return report
        identity = {mode: report['runs'][f'{mode}-32']['trace']['raw_sha256'] ==
                    report['runs'][f'{mode}-64']['trace']['raw_sha256'] for mode in MODES}
        passed = all(identity.values())
        report.update(state='completed', final=True, stage='component callback comparison collected',
            format_callback_identity=identity, integration_gate_pass=passed,
            decision='offline component gate passed' if passed else 'rejected by sample-format identity')
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
