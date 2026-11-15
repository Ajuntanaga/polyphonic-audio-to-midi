"""Observe the accepted reference and rejected reservation policy on three labels.

Run native replays only on the offloaded worker. Complete scored output and raw
MIDI must retain each saved policy's identity. This diagnostic changes no policy.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import subprocess

from tools.assignment_cost_analysis import summarize_costs
from tools.frozen_cue_corpus_gate import read_replay
from tools.midi_lifecycle_analysis import read_events, summarize
from tools.portable_assignment_trace import compress_trace_window, digest, read_rows, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_midi_lane_trace import candidate_frames, raw_lane_history
from tools.portable_pending_string_trial import CONDITIONS
from tools.portable_routing_trace import outcome_window


CASES = (
    dict(label_index=17, midi_note=37, string_mask=1, start_sample=245017, end_sample=316800),
    dict(label_index=306, midi_note=42, string_mask=1, start_sample=5630617, end_sample=5702400),
    dict(label_index=335, midi_note=37, string_mask=1, start_sample=6283306, end_sample=6355200))


def window_for(label):
    return max(0, label['start_sample'] // 64 * 64 - 256), (label['end_sample'] // 64 + 10) * 64


def explain_frames(frames, assignments, label):
    """Keep complete observations in bulk evidence and a bounded diagnostic digest."""
    by_sample = {}
    for row in assignments:
        if int(row['observed']):
            by_sample.setdefault(int(row['sample']), []).append(row)
    counts, examples, transitions, previous = Counter(), [], [], None
    for frame in frames:
        sample = frame['sample']
        if not label['start_sample'] <= sample < label['end_sample']:
            continue
        peers = by_sample.get(sample, [])
        target = next((row for row in peers if int(row['note']) == label['midi_note']), None)
        state = frame['candidate_state'] or {}
        selected = state.get('selection') == 4
        active = bool(state.get('active', 0))
        preview = bool(target and int(target['allocation_preview']))
        ready = bool(target and not int(target['prior_active']) and
                     int(target['prior_attack_ticks']) + 1 >= int(target['attack_required']))
        valid = bool(target and int(target['valid']))
        routed = bool(frame['routing']['midi_after'])
        blocked = bool(frame['routing']['capacity_blocked'])
        counts.update(frames=1, selected=selected, active=active,
            selected_inactive=selected and not active, preview=preview,
            ready=ready, ready_infeasible=ready and not valid,
            ready_feasible=ready and valid, routed=routed, capacity_blocked=blocked)
        summary = dict(sample=sample, selected=selected, active=active, preview=preview,
            ready=ready, valid_assignment=valid, attack=state.get('attack'),
            release=state.get('release'), evidence_ticks=state.get('evidence_ticks'),
            assigned_mask=state.get('assigned_mask'), routing=frame['routing'],
            peers=[{key: int(row[key]) for key in ('note', 'prior_active', 'prior_midi',
                'prior_attack_ticks', 'attack_required', 'allocation_preview', 'playable',
                'prior_primary', 'dp_primary', 'final_mask', 'valid')}
                for row in peers])
        category = selected, active, preview, ready, valid, routed, blocked
        if category != previous:
            transitions.append(summary)
        if ready and not active and len(examples) < 12:
            examples.append(summary)
        previous = category
    return dict(counts=dict(counts), first_unactivated_ready_frames=examples,
                state_transition_count=len(transitions), first_state_transitions=transitions[:16]), transitions


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900,
        cases=None, conditions=None, window=None, diagnose=None,
        schema='m3_pending_string_reservation_trace_v1'):
    cases = CASES if cases is None else cases
    conditions = CONDITIONS[1:] if conditions is None else conditions
    window = window_for if window is None else window
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema=schema, state='running', final=False,
        stage='verify inputs', dataset='ordinary', settings=SETTINGS, cases=cases, runs={},
        runtime_rule_changed=False, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', live_readiness='not measured')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        references = json.loads(reference_path.read_text())['replay_references']
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
            input_manifest_sha256=digest(manifest_path), reference_checkpoint_sha256=digest(reference_path))
        for policy, flags in conditions:
            reference = references[policy]
            captures = None
            for label in cases:
                index, note = label['label_index'], label['midi_note']
                start, end = window(label)
                stem = f'{policy}-label{index}'
                destination = output / stem
                destination.mkdir()
                traces = {kind: destination / (kind + '.tsv')
                          for kind in ('candidate', 'assignment', 'outcome', 'midi-event')}
                command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
                command.extend(flags)
                for kind, path in traces.items():
                    command.extend(('--' + kind + '-trace', str(path)))
                command.extend(('--candidate-trace-note', str(note)))
                for kind in ('candidate', 'assignment'):
                    command.extend(('--' + kind + '-trace-start', str(start / 96000),
                                    '--' + kind + '-trace-end', str(end / 96000)))
                report.update(stage=stem, command=command)
                save()
                replay_path = destination / 'replay.tsv'
                with replay_path.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                    subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
                parsed = read_replay(replay_path)
                result = dict(policy=policy, label_index=index, tsv_sha256=digest(replay_path),
                              midi_sha256=digest(traces['midi-event']), output=parsed['output'])
                report['runs'][stem] = result
                result['saved_reference_bit_identical'] = all(
                    result[key] == reference[key] for key in ('tsv_sha256', 'midi_sha256', 'output'))
                if not result['saved_reference_bit_identical']:
                    raise ValueError(stem + ' differs from the saved output or raw MIDI')
                if 'outcome_sha256' in reference:
                    result['outcome_sha256'] = digest(traces['outcome'])
                    result['saved_outcome_bit_identical'] = (
                        result['outcome_sha256'] == reference['outcome_sha256'])
                    if not result['saved_outcome_bit_identical']:
                        raise ValueError(stem + ' differs from the saved complete outcome')
                with replay_path.open() as stream:
                    aggregate = next(csv.DictReader(stream, delimiter='\t'))
                samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
                if (rate != 96000 or samples != reference['sample_count'] or
                        rate != reference['sample_rate'] or not 0 <= start < end <= samples):
                    raise ValueError('Recorded annotation window or sample clock changed')
                annotation = next(row for row in parsed['labels'] if row['label_index'] == index)
                if any(annotation[key] != value for key, value in label.items()):
                    raise ValueError('Recorded annotation changed')
                events = read_events(traces['midi-event'], sample_count=samples,
                                     transition_count=int(aggregate['transitions']))
                lifecycle = summarize(events, parsed['labels'], sample_count=samples, sample_rate=rate)
                held = next(row for row in lifecycle['labels'] if row['label_index'] == index)
                if not lifecycle['coverage_valid'] or held != reference['held_labels'][str(index)]:
                    raise ValueError('Saved held-note measurement changed or pairing is invalid')
                outcomes = outcome_window(traces['outcome'], samples, start, end)
                frames = candidate_frames(read_rows(traces['candidate']), outcomes,
                                          note=note, start=start, end=end)
                assignments = read_rows(traces['assignment'])
                costs = summarize_costs(assignments, outcomes, note=note, start=start, end=end)
                diagnosis, transitions = explain_frames(frames, assignments, label)
                result.update(sample_count=samples, sample_rate=rate, held_label=held,
                    snapshot_label=annotation, window_start=start, window_end=end,
                    diagnosis=diagnosis, assignment_costs={key: value for key, value in costs.items()
                                                         if key != 'switches'})
                if diagnose is not None:
                    result['bounded_diagnosis'] = diagnose(assignments, frames, label)
                bulk = destination / 'observations.json.gz'
                with gzip.open(bulk, 'wt', encoding='utf-8') as stream:
                    json.dump(dict(frames=frames, assignment_costs=costs, transitions=transitions,
                        raw_lane_histories=[raw_lane_history(events, lane=lane, start=start, end=end)
                            for lane in sorted({event['voice_id'] for event in events})]), stream)
                result['observations'] = dict(file=bulk.name, sha256=digest(bulk))
                result['traces'] = {}
                for kind, path in traces.items():
                    result['traces'][kind] = compress_trace_window(path, start=start, end=end)
                    path.unlink()
                current = {kind: result['traces'][kind]['captured_raw_sha256']
                           for kind in ('outcome', 'midi-event')}
                if captures is not None and current != captures:
                    raise ValueError('Repeated policy captures changed complete MIDI or outcome')
                captures = current
                save()
        report.update(state='completed', final=True, stage='observations collected',
            saved_references_bit_identical=True, repeated_policy_streams_bit_identical=True,
            interpretation='Observations preserve the selected saved policies. Preview masks are '
                'assignment hints, not committed MIDI lanes. Held samples measure raw detector '
                'events, not tuner frame matches or delivered-host MIDI. The trial remains rejected.')
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
