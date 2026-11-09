"""Cloud-only routing diagnosis of the first rejected preview-ownership transfer.

Replay the complete ordinary recording with the original OFF and rejected ON
settings. Retain a small diagnostic window, requiring both complete outputs to
match their recorded hashes. This does not screen or accept a new runtime rule.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.candidate_outcome_analysis import HEADER, _candidates, _frame
from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_assignment_trace import (compress_trace_window, digest, read_rows,
                                             select_labels, verify_inputs)
from tools.portable_corpus_replay import SETTINGS, command_for


WINDOW = (944832, 945536)
ROUTING_FIELDS = (
    'tick', 'render_observed', 'continuity_observed', 'assigned_mask',
    'primary_string', 'spectral_mask', 'continuity_mask', 'cached_group_mask',
    'desired_mask', 'pruned_mask', 'midi_before', 'midi_after', 'other_owned',
    'final_continuity_mask', 'final_cached_group_mask', 'capacity_blocked')


def outcome_window(path, samples, start, end):
    retained = []
    with path.open(newline='') as stream:
        rows = csv.DictReader((line for line in stream if not line.startswith('#')), delimiter='\t')
        expected = 63
        for row in rows:
            sample = int(row['sample'])
            if sample != expected or int(row['tick']) * 64 - 1 != sample:
                raise ValueError('Incomplete or reordered full outcome capture')
            expected += 64
            if start <= sample < end:
                retained.append(row)
        if expected != 63 + (samples // 64) * 64:
            raise ValueError('Incomplete full outcome capture')
    return retained


def summarize_routing(candidates, outcomes, events, *, note, label_index, start, end):
    expected = set(range(((start + 1 + 63) // 64) * 64 - 1, end, 64))
    snapshots = {int(row['sample']): row for row in outcomes}
    if set(snapshots) != expected or len(snapshots) != len(outcomes):
        raise ValueError('Incomplete or duplicate routing outcome window')
    events_at = {}
    for row in events:
        sample = int(row['sample'])
        if start <= sample < end:
            if sample not in expected or row['kind'] not in ('on', 'off'):
                raise ValueError('Invalid routing MIDI event')
            events_at.setdefault(sample, []).append(dict(
                kind=row['kind'], note=int(row['note']), voice_id=int(row['voice_id'])))
    result, seen = [], set()
    columns = HEADER.rstrip('\n').split('\t')
    for row in candidates:
        sample, tick = int(row['sample']), int(row['tick'])
        if sample not in expected or sample in seen or tick * 64 - 1 != sample or int(row['note']) != note:
            raise ValueError('Invalid routing candidate clock, note or duplicate')
        seen.add(sample)
        routing = {key: int(row['route_' + key]) for key in ROUTING_FIELDS}
        observed = routing['render_observed'] or routing['continuity_observed']
        if routing['tick'] != (tick if observed else 0):
            raise ValueError('Stale or invalid routing stage observation')
        snapshot = snapshots[sample]
        if int(snapshot['tick']) != tick:
            raise ValueError('Routing snapshot clock mismatch')
        frame = _frame('\t'.join(snapshot[column] for column in columns))
        if not any(index == label_index and pitch == note for index, pitch, _ in frame['labels']):
            raise ValueError('Routing window does not contain the requested label')
        states = _candidates(frame)
        result.append(dict(sample=sample, tick=tick, routing=routing,
            label_matched=label_index in frame['matched'],
            voices=[voice for voice in frame['voices'] if voice[0] in (41, note)],
            candidate_states={str(pitch): states[pitch] for pitch in (41, note) if pitch in states},
            midi_events=events_at.get(sample, [])))
    if seen != expected:
        raise ValueError('Incomplete routing candidate window')
    return result


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    start, end = WINDOW
    report = dict(schema='m3_candidate_routing_trace_v1', state='running', final=False,
        stage='verify inputs', dataset='ordinary', settings=SETTINGS,
        candidate_note=52, label_index=54, window_start=start, window_end=end,
        runtime_rule_changed=False, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', live_readiness='not measured', runs={})

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
                      input_manifest_sha256=digest(manifest_path),
                      reference_report_sha256=digest(reference_path))
        parsed_runs = {}
        for stem in ('reference-off', 'trial-on'):
            destination = output / stem
            destination.mkdir()
            traces = {kind: destination / (kind + '.tsv')
                      for kind in ('candidate', 'outcome', 'midi-event')}
            command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
            if stem == 'trial-on':
                command.append('--diagnostic-projection-preview-admission')
            for kind, path in traces.items():
                command.extend(('--' + kind + '-trace', str(path)))
            command.extend(('--candidate-trace-note', '52', '--candidate-trace-start', str(start / 96000),
                            '--candidate-trace-end', str(end / 96000)))
            report.update(stage=stem, command=command)
            save()
            replay_path = destination / 'replay.tsv'
            started = time.monotonic()
            with replay_path.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            parsed = read_replay(replay_path)
            retained = reference['runs'][stem]
            result = dict(elapsed_seconds=time.monotonic() - started,
                          tsv_sha256=digest(replay_path), output=parsed['output'])
            result['reference_bit_identical'] = (result['tsv_sha256'] == retained['tsv_sha256']
                                                and result['output'] == retained['output'])
            report['runs'][stem] = result
            if not result['reference_bit_identical']:
                raise ValueError(stem + ' differs from the recorded full replay')
            with replay_path.open() as stream:
                aggregate = next(csv.DictReader(stream, delimiter='\t'))
            samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
            label = select_labels(parsed['labels'], note=52, label_index=54)[0]
            if rate != 96000 or not label['start_sample'] <= start < end <= label['end_sample'] <= samples:
                raise ValueError('Recorded routing window or sample rate changed')
            result.update(sample_rate=rate, sample_count=samples, label=label)
            rows = outcome_window(traces['outcome'], samples, start, end)
            result['routing_frames'] = summarize_routing(
                read_rows(traces['candidate']), rows, read_rows(traces['midi-event']),
                note=52, label_index=54, start=start, end=end)
            result['traces'] = {}
            for kind, path in traces.items():
                result['traces'][kind] = compress_trace_window(path, start=start, end=end)
                path.unlink()
            parsed_runs[stem] = parsed
            save()
        report['comparison'] = compare_replays(parsed_runs['reference-off'], parsed_runs['trial-on'])
        before, after = (report['runs'][stem]['routing_frames'] for stem in ('reference-off', 'trial-on'))
        report['routing_differences'] = [dict(sample=left['sample'], changed_fields=[
            key for key in ROUTING_FIELDS if left['routing'][key] != right['routing'][key]])
            for left, right in zip(before, after) if left['routing'] != right['routing']]
        report.update(state='completed', final=True, stage='paired routing trace collected',
            decision='unchanged; diagnostic collected from the previously rejected trial',
            interpretation='Render fields precede MIDI lane changes; continuity ownership is '
                'measured later in the same decision. Final masks are post-lifecycle snapshots. '
                'A skipped stage is unobserved, not a measured zero. Both full replay hashes '
                'must match their historical OFF/ON outputs. The ON trial remains rejected; '
                'these diagnostics do not establish new label gains or live readiness.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
