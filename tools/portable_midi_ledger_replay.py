"""Replay complete saved detector events through the native MIDI ledger.

This open-loop diagnostic accepts callbacks into a file, with no detector
feedback, host rejection, recovery controls or forced releases at EOF.
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
import subprocess
import tempfile
import zipfile

from tools.midi_lifecycle_analysis import read_events, raw_conflicts


MODES = ('reference-off', 'trial-on')
ROUTINGS = ('single', 'per_voice')
CALLBACK_FIELDS = ('sample', 'phase', 'kind', 'note', 'velocity', 'voice_id',
                   'channel', 'source_sequence')
LIMITATION = ('Offline open-loop production-ledger simulation with an accepting '
    'file sink. Saved detector events continue after a fault; the live plugin '
    'would gate detection. No waveform-dependent recovery, control changes, '
    'VST3 event-list rejection, host consumption, device output or timing is '
    'measured. Assigned voices sharing a pitch/channel remain separate identities. '
    'EOF opens are retained, not repaired or claimed to be stuck host notes.')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage_inputs(checkpoint, archive_path, destination):
    if (checkpoint['schema'] != 'm3_spectral_lane_collision_trial_v1'
            or checkpoint['state'] != 'completed' or checkpoint['final'] is not True):
        raise ValueError('Expected a final saved collision trial')
    artifact_name = (f"m3-evidence-{checkpoint['source']['run_id']}-"
                     f"{checkpoint['source']['run_attempt']}")
    artifacts = [item for item in checkpoint['artifacts'] if item['name'] == artifact_name]
    if len(artifacts) != 1 or digest(archive_path) != artifacts[0]['sha256']:
        raise ValueError('Saved evidence archive hash differs')
    results = {}
    with zipfile.ZipFile(archive_path) as archive:
        for mode in MODES:
            run = checkpoint['runs'][mode]
            trace = run['traces']['midi-event']
            if (trace['file'] != 'midi-event.tsv.gz' or trace['scope'] != 'complete recording'
                    or trace['start_sample_inclusive'] != 0
                    or trace['end_sample_exclusive'] != run['sample_count']
                    or trace['discarded_rows'] != 0
                    or trace['captured_rows'] != trace['retained_rows']
                    or trace['raw_sha256'] != trace['captured_raw_sha256']
                    or trace['raw_bytes'] != trace['captured_raw_bytes']
                    or not 0 < trace['raw_bytes'] <= 64 * 1024 * 1024):
                raise ValueError('Saved MIDI trace is not complete')
            members = [item for item in archive.infolist()
                       if item.filename.endswith(f'/{mode}/{trace["file"]}')]
            if len(members) != 1 or members[0].file_size != trace['bytes']:
                raise ValueError('Missing or ambiguous saved MIDI trace')
            compressed = archive.read(members[0])
            if hashlib.sha256(compressed).hexdigest() != trace['sha256']:
                raise ValueError('Compressed MIDI trace hash differs')
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw = stream.read(trace['raw_bytes'] + 1)
            if (len(raw) != trace['raw_bytes']
                    or hashlib.sha256(raw).hexdigest() != trace['raw_sha256']):
                raise ValueError('Complete MIDI capture hash differs')
            path = destination / f'{mode}.tsv'
            path.write_bytes(raw)
            events = read_events(path, sample_count=run['sample_count'],
                                 transition_count=trace['captured_rows'])
            conflicts = raw_conflicts(events)
            if (conflicts['counts'] != run['raw_midi_counts']
                    or conflicts['raw_note_ons_open_at_eof'] != run['raw_note_ons_open_at_eof']):
                raise ValueError('Raw event evidence differs from saved checkpoint')
            results[mode] = dict(path=path, events=events, trace=trace, raw_midi=conflicts,
                                sample_count=run['sample_count'], sample_rate=run['sample_rate'])
    return results, artifacts[0]


def check_callbacks(path, result, source):
    by_sequence = {event['sequence']: event for event in source['events']}
    seen, counts, previous_sample = set(), dict(source=0, cleanup=0), -1
    with path.open(newline='') as stream:
        if stream.readline().rstrip('\r\n') != '# m3_ledger_callbacks_v1':
            raise ValueError('Unknown callback trace')
        rows = csv.DictReader(stream, delimiter='\t')
        if rows.fieldnames != list(CALLBACK_FIELDS):
            raise ValueError('Malformed callback header')
        for row in rows:
            if (set(row) != set(CALLBACK_FIELDS) or any(value is None for value in row.values())
                    or row['phase'] not in counts or row['kind'] not in ('on', 'off')):
                raise ValueError('Malformed callback row')
            values = {key: int(row[key]) for key in
                      ('sample', 'note', 'velocity', 'voice_id', 'channel')}
            if (not previous_sample <= values['sample'] < source['sample_count']
                    or not 1 <= values['channel'] <= 16):
                raise ValueError('Callback clock or channel invalid')
            previous_sample = values['sample']
            if row['phase'] == 'source':
                sequence = int(row['source_sequence'])
                event = dict(kind=row['kind'], sequence=sequence,
                             **{key: values[key] for key in ('sample', 'note', 'velocity', 'voice_id')})
                if sequence in seen or by_sequence.get(sequence) != event:
                    raise ValueError('Callback is not a unique saved source event')
                seen.add(sequence)
            elif row['source_sequence'] or row['kind'] != 'off' or values['velocity'] != 0:
                raise ValueError('Cleanup callback claimed source provenance')
            counts[row['phase']] += 1
    if (result['input_events'] != len(source['events'])
            or result['source_callbacks'] != counts['source']
            or result['cleanup_callbacks'] != counts['cleanup']
            or result['suppressed_source_events'] != len(source['events']) - counts['source']
            or result['callback_pairing_errors'] != 0
            or result['host_delivery_verified'] is not False
            or result['forced_eof_releases'] is not False):
        raise ValueError('Callback accounting differs from native report')


def run(args):
    if not re.fullmatch('[0-9a-f]{40}', args.source_sha):
        raise ValueError('Expected full source commit')
    actual_source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    if actual_source != args.source_sha:
        raise ValueError('Harness source commit differs')
    args.output.mkdir(parents=True, exist_ok=False)
    checkpoint = json.loads(args.checkpoint.read_text())
    report = dict(schema='m3_saved_midi_ledger_diagnosis_v1', state='running', final=False,
        source_commit=actual_source, binary_sha256=digest(args.binary),
        saved_checkpoint_sha256=digest(args.checkpoint), trace_source=checkpoint['source'],
        original_detector_binary_sha256=checkpoint['binary_sha256'], block_size=512,
        installed_output_changed=False, promotion_accepted=False, host_delivery='not measured',
        native_timing='not measured', interpretation=LIMITATION, runs={})
    try:
        with tempfile.TemporaryDirectory(prefix='saved-events-', dir=args.output) as temporary:
            inputs, artifact = stage_inputs(checkpoint, args.archive, Path(temporary))
            report['saved_artifact'] = artifact
            for mode, source in inputs.items():
                report['runs'][mode] = dict(raw_midi=source['raw_midi'],
                    sample_count=source['sample_count'], sample_rate=source['sample_rate'],
                    trace=source['trace'], routings={})
                for routing in ROUTINGS:
                    stem = args.output / f'{mode}-{routing}'
                    callbacks = stem.with_suffix('.tsv')
                    command = [str(args.binary.resolve()), str(source['path']),
                        str(source['sample_count']), str(len(source['events'])),
                        '512', routing, str(callbacks)]
                    with stem.with_suffix('.json').open('w') as stdout, \
                            stem.with_suffix('.stderr').open('w') as stderr:
                        completed = subprocess.run(command, stdout=stdout, stderr=stderr,
                                                   timeout=90, check=False)
                    if completed.returncode:
                        raise RuntimeError(f'{mode}/{routing}: native exit {completed.returncode}')
                    result = json.loads(stem.with_suffix('.json').read_text())
                    if (result['schema'] != 'm3_ledger_replay_v1' or result['routing'] != routing
                            or result['block_size'] != 512
                            or result['sample_count'] != source['sample_count']):
                        raise ValueError('Native ledger report provenance differs')
                    check_callbacks(callbacks, result, source)
                    raw_hash, raw_bytes = digest(callbacks), callbacks.stat().st_size
                    compressed = callbacks.with_suffix('.tsv.gz')
                    with callbacks.open('rb') as raw, compressed.open('wb') as output:
                        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as archive:
                            while chunk := raw.read(1024 * 1024):
                                archive.write(chunk)
                    callbacks.unlink()
                    result['callbacks'] = dict(file=compressed.name, bytes=compressed.stat().st_size,
                        sha256=digest(compressed), raw_sha256=raw_hash, raw_bytes=raw_bytes)
                    report['runs'][mode]['routings'][routing] = result
            report['delta_on_minus_off'] = {routing: {key:
                report['runs']['trial-on']['routings'][routing][key]
                - report['runs']['reference-off']['routings'][routing][key]
                for key in ('source_callbacks', 'suppressed_source_events',
                            'cleanup_callbacks', 'blocked_blocks', 'queue_rejected_events')}
                for routing in ROUTINGS}
            report.update(state='completed', final=True, decision='offline diagnosis only')
    except Exception as error:
        report.update(state='error', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['observed_at'] = datetime.now(timezone.utc).isoformat()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    report = run(parser.parse_args())
    print(json.dumps(dict(state=report['state'], delta=report['delta_on_minus_off'])))


if __name__ == '__main__':
    main()
