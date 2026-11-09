"""Screen a bounded spectral assignment or output policy, offline only.

Two complete ordinary-recording replays compare every label and false-output
count. Full raw MIDI captures retain overlapping pitches; only candidate and
outcome observations are reduced to the previously recorded conflict window.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.midi_lifecycle_analysis import CONFLICT_FIELDS, raw_conflicts, read_events
from tools.portable_assignment_trace import compress_trace_window, digest, read_rows, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_midi_lane_trace import LANE, TARGET_EVENTS, WINDOW, candidate_frames, raw_lane_history
from tools.portable_routing_trace import outcome_window


FLAG = '--diagnostic-retained-spectral-assignment'
COLLISION_FLAG = '--diagnostic-spectral-lane-collision'
POLICIES = {
    'retained-assignment': dict(flag=FLAG,
        schema='m3_retained_spectral_assignment_trial_v1',
        description='Parallel physical assignment constrained only by freshly revalidated '
            'single-lane MIDI incumbents; complete-solution fallback; no output guard.'),
    'spectral-lane-collision': dict(flag=COLLISION_FLAG,
        schema='m3_spectral_lane_collision_trial_v1',
        description='Keep ordinary physical assignment. Move a conflicting singleton '
            'spectral output to its own free physical string; release before claim. '
            'Groups and continuity expansions retain their existing output path.'),
}

def window_conflicts(history):
    return sum(row['event']['kind'] == 'on' and any(
        old['note'] != row['event']['note']
        for old in row['unreleased_raw_note_ons_before']) for row in history['events'])


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900,
        policy='retained-assignment'):
    selected_policy = POLICIES[policy]
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    start, end = WINDOW
    report = dict(schema=selected_policy['schema'], state='running', final=False,
        stage='verify inputs', dataset='ordinary', settings=SETTINGS,
        candidate_note=48, window_start=start, window_end=end, runs={},
        runtime_rule_changed=True, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', live_readiness='not measured',
        policy_name=policy, diagnostic_flag=selected_policy['flag'],
        policy=selected_policy['description'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())['runs']['reference-off']
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
            input_manifest_sha256=digest(manifest_path), reference_report_sha256=digest(reference_path))
        parsed_runs = []
        for stem, enabled in (('reference-off', False), ('trial-on', True)):
            destination = output / stem
            destination.mkdir()
            traces = {kind: destination / (kind + '.tsv')
                      for kind in ('candidate', 'outcome', 'midi-event')}
            command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
            if enabled:
                command.append(selected_policy['flag'])
            for kind, path in traces.items():
                command.extend(('--' + kind + '-trace', str(path)))
            command.extend(('--candidate-trace-note', '48',
                '--candidate-trace-start', str(start / 96000),
                '--candidate-trace-end', str(end / 96000)))
            report.update(stage=stem, command=command)
            save()
            replay_path = destination / 'replay.tsv'
            started = time.monotonic()
            with replay_path.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            parsed = read_replay(replay_path)
            parsed_runs.append(parsed)
            result = dict(elapsed_seconds=time.monotonic() - started,
                tsv_sha256=digest(replay_path), output=parsed['output'],
                exact_matches_by_string_count=parsed['exact_matches_by_string_count'])
            report['runs'][stem] = result
            if not enabled:
                identity = (result['tsv_sha256'] == reference['tsv_sha256']
                            and result['output'] == reference['output'])
                report['off_reference_bit_identical'] = identity
                if not identity:
                    raise ValueError('OFF reference differs from the retained ordinary baseline')
            with replay_path.open() as stream:
                aggregate = next(csv.DictReader(stream, delimiter='\t'))
            samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
            if rate != 96000 or not 0 <= start < end <= samples:
                raise ValueError('Recorded conflict window or sample clock changed')
            events = read_events(traces['midi-event'], sample_count=samples,
                                 transition_count=int(aggregate['transitions']))
            if not enabled and any(sum(all(event[key] == value for key, value in target.items())
                    for event in events) != 1 for target in TARGET_EVENTS):
                raise ValueError('Recorded OFF conflict changed or disappeared')
            outcomes = outcome_window(traces['outcome'], samples, start, end)
            result.update(sample_rate=rate, sample_count=samples,
                frames=candidate_frames(read_rows(traces['candidate']), outcomes,
                                        note=48, start=start, end=end),
                raw_midi=raw_conflicts(events),
                raw_lane_history=raw_lane_history(events, lane=LANE, start=start, end=end), traces={})
            result['recorded_lane_window_conflicts'] = window_conflicts(result['raw_lane_history'])
            for kind, path in traces.items():
                full_midi = kind == 'midi-event'
                result['traces'][kind] = compress_trace_window(path,
                    start=0 if full_midi else start, end=samples if full_midi else end)
                result['traces'][kind]['scope'] = 'complete recording' if full_midi else 'conflict window'
                path.unlink()
            save()
        comparison = compare_replays(*parsed_runs)
        off, on = (report['runs'][stem]['raw_midi']['counts']
                   for stem in ('reference-off', 'trial-on'))
        midi_delta = {key: on[key] - off[key] for key in CONFLICT_FIELDS}
        midi_no_regression = all(delta <= 0 for delta in midi_delta.values())
        conflict_improved = midi_delta['cross_pitch_on_before_release'] < 0
        window_resolved = (report['runs']['reference-off']['recorded_lane_window_conflicts'] > 0
            and report['runs']['trial-on']['recorded_lane_window_conflicts'] == 0)
        screen_pass = (comparison['gate_pass'] and midi_no_regression
                       and conflict_improved and window_resolved)
        report.update(state='completed', final=True, stage='offline screen collected',
            comparison=comparison, raw_midi_delta=midi_delta,
            raw_midi_no_regression=midi_no_regression, raw_conflicts_reduced=conflict_improved,
            recorded_lane_window_resolved=window_resolved,
            full_recording_screen_pass=screen_pass,
            decision='eligible for wider validation' if screen_pass else 'rejected',
            interpretation='A successful process is not acceptance. Every passage must '
                'retain its labeled matches, false outputs must not increase, and raw '
                'cross-pitch conflicts must decrease without another raw-event regression, '
                'with no remaining conflict in the recorded lane window. '
                'Buffer, allocation, timing, cross-corpus and live host gates remain unmeasured.')
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
    parser.add_argument('--policy', choices=POLICIES, default='retained-assignment')
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds, policy=args.policy)


if __name__ == '__main__':
    main()
