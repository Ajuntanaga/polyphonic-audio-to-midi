"""Trace a recorded lane replacement without changing the selected runtime policy.

Complete replays observe each candidate with the existing recorder. They must
preserve historical output and identical MIDI/outcome captures. The collision
ON profile also requires complete-stream identity with the original ON trial.
Only the short conflict window and its preceding raw note-ons are retained.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.candidate_outcome_analysis import HEADER, _candidates, _frame
from tools.frozen_cue_corpus_gate import read_replay
from tools.midi_lifecycle_analysis import read_events
from tools.portable_assignment_trace import compress_trace_window, digest, read_rows, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_evidence_retention_trial import summarize_calibrated_output
from tools.portable_routing_trace import ROUTING_FIELDS, outcome_window


WINDOW = (202752, 204288)
NOTES = (47, 48)
LANE = 0
TARGET_EVENTS = (
    dict(sample=203519, kind='on', note=47, voice_id=0, sequence=45),
    dict(sample=203583, kind='off', note=48, voice_id=0, sequence=46))
COLLISION_WINDOW = (286720, 289280)
COLLISION_TARGET_EVENTS = (
    dict(sample=287743, kind='on', note=37, voice_id=0, sequence=430),
    dict(sample=287807, kind='on', note=54, voice_id=1, sequence=432),
    dict(sample=288255, kind='off', note=37, voice_id=0, sequence=433),
    dict(sample=288255, kind='on', note=37, voice_id=1, sequence=434))
COASTING_OWNER_WINDOW = (1147904, 1150464)
COASTING_OWNER_TARGET_EVENTS = (
    dict(sample=1149183, kind='on', note=36, voice_id=0, sequence=2152),
    dict(sample=1149183, kind='on', note=37, voice_id=0, sequence=2153))


def trace_profile(profile):
    if profile == 'reference-off':
        return dict(window=WINDOW, notes=NOTES, lane=LANE, targets=TARGET_EVENTS,
                    reference_key='reference-off', flags=())
    if profile == 'spectral-collision-on':
        return dict(window=COLLISION_WINDOW, notes=(37, 54, 57), lane=1,
                    targets=COLLISION_TARGET_EVENTS, reference_key='trial-on',
                    flags=('--diagnostic-spectral-lane-collision',))
    if profile == 'coasting-owner-on':
        return dict(window=COASTING_OWNER_WINDOW, notes=(36, 37), lane=0,
                    targets=COASTING_OWNER_TARGET_EVENTS, reference_key='trial-on',
                    flags=('--diagnostic-spectral-lane-collision',))
    raise ValueError('Unknown MIDI lane trace profile')


def raw_lane_history(events, *, lane, start, end):
    """Keep overlapping raw onsets; never replace an old pitch with a new one.

    These outstanding transitions are not proof of host-delivered ownership.
    Repeated same-pitch onsets stay separate; an off pairs with the oldest.
    """
    active, retained, prior = [], [], None
    for event in events:
        if event['sample'] >= end:
            break
        if event['sample'] >= start and prior is None:
            prior = list(active)
        if event['voice_id'] != lane:
            continue
        before = list(active)
        matching = [i for i, opened in enumerate(active) if opened['note'] == event['note']]
        if event['kind'] == 'on':
            active.append(event)
            ambiguity = len(matching) > 0
        else:
            ambiguity = len(matching) != 1
            if matching:
                active.pop(matching[0])
        if event['sample'] >= start:
            retained.append(dict(event=event, unreleased_raw_note_ons_before=before,
                                 unreleased_raw_note_ons_after=list(active),
                                 same_pitch_pairing_ambiguous=ambiguity))
    return dict(voice_id=lane, unreleased_raw_note_ons_at_window_start=prior
                if prior is not None else list(active), events=retained,
                interpretation='Raw detector order before the host ledger. Overlapping '
                'pitches remain distinct; repeated same-pitch pairing is flagged. '
                'This is not delivered MIDI ownership or a held-duration acceptance gate.')


def candidate_frames(rows, outcomes, *, note, start, end):
    expected = set(range(((start + 64) // 64) * 64 - 1, end, 64))
    snapshots = {int(row['sample']): row for row in outcomes}
    if set(snapshots) != expected or len(snapshots) != len(outcomes):
        raise ValueError('Incomplete or duplicate lane outcome window')
    result, seen = [], set()
    columns = HEADER.rstrip('\n').split('\t')
    for row in rows:
        sample, tick = int(row['sample']), int(row['tick'])
        if (sample not in expected or sample in seen or tick * 64 - 1 != sample
                or int(row['note']) != note or int(snapshots[sample]['tick']) != tick):
            raise ValueError('Invalid lane candidate clock, note or duplicate')
        seen.add(sample)
        routing = {field: int(row['route_' + field]) for field in ROUTING_FIELDS}
        observed = routing['render_observed'] or routing['continuity_observed']
        if routing['tick'] != (tick if observed else 0):
            raise ValueError('Stale routing stage observation')
        frame = _frame('\t'.join(snapshots[sample][column] for column in columns))
        states = _candidates(frame)
        result.append(dict(sample=sample, tick=tick, routing=routing,
            tracking={key: int(row[key]) for key in
                      ('selection', 'active', 'assigned_mask', 'rescue_mask', 'selector_mask')},
            selected_or_coasting=row['selected_or_coasting'],
            labels=frame['labels'], matched_labels=sorted(frame['matched']),
            voices=frame['voices'], candidate_state=states.get(note)))
    if seen != expected:
        raise ValueError('Incomplete lane candidate window')
    return result


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900,
        profile='reference-off'):
    selected = trace_profile(profile)
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    start, end = selected['window']
    mode = 'on' if selected['flags'] else 'off'
    report = dict(schema='m3_midi_lane_trace_v1', state='running', final=False,
        stage='verify inputs', dataset='ordinary', settings=SETTINGS,
        profile=profile, diagnostic_flags=selected['flags'],
        reference_key=selected['reference_key'], voice_id=selected['lane'],
        candidate_notes=selected['notes'], window_start=start, window_end=end,
        target_events=selected['targets'], runtime_rule_changed=False,
        installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', live_readiness='not measured', runs={})

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference_report = json.loads(reference_path.read_text())
        reference = reference_report['runs'][selected['reference_key']]
        expected_captures = None
        if selected['flags']:
            if reference_report.get('policy_name') != 'spectral-lane-collision':
                raise ValueError('Collision ON profile requires the saved collision trial')
            if (profile == 'coasting-owner-on'
                    and reference_report.get('trial_revision') != 'coasting_owner_hold'):
                raise ValueError('Coasting owner profile requires the saved coasting owner trial')
            expected_captures = {kind: reference['traces'][kind]['captured_raw_sha256']
                                 for kind in ('outcome', 'midi-event')}
            if any(len(value) != 64 or any(c not in '0123456789abcdef' for c in value)
                   for value in expected_captures.values()):
                raise ValueError('Invalid historical complete-stream digest')
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
                      input_manifest_sha256=digest(manifest_path),
                      reference_report_sha256=digest(reference_path))
        captures = None
        for note in selected['notes']:
            stem = f'candidate-{note}-{mode}'
            destination = output / stem
            destination.mkdir()
            traces = {kind: destination / (kind + '.tsv')
                      for kind in ('candidate', 'outcome', 'midi-event')}
            command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
            command.extend(selected['flags'])
            for kind, path in traces.items():
                command.extend(('--' + kind + '-trace', str(path)))
            command.extend(('--candidate-trace-note', str(note),
                '--candidate-trace-start', str(start / 96000),
                '--candidate-trace-end', str(end / 96000)))
            report.update(stage=stem, command=command)
            save()
            replay_path = destination / 'replay.tsv'
            started = time.monotonic()
            with replay_path.open('x') as stdout, (destination / 'replay.stderr').open('x') as stderr:
                subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
            parsed = read_replay(replay_path)
            result = dict(elapsed_seconds=time.monotonic() - started,
                          tsv_sha256=digest(replay_path), output=parsed['output'])
            result['reference_bit_identical'] = (result['tsv_sha256'] == reference['tsv_sha256']
                                                and result['output'] == reference['output'])
            report['runs'][stem] = result
            if not result['reference_bit_identical']:
                raise ValueError(stem + f' differs from the historical {mode.upper()} replay')
            with replay_path.open() as stream:
                aggregate = next(csv.DictReader(stream, delimiter='\t'))
            samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
            if rate != 96000 or not 0 <= start < end <= samples:
                raise ValueError('Recorded conflict window or sample clock changed')
            events = read_events(traces['midi-event'], sample_count=samples,
                                 transition_count=int(aggregate['transitions']))
            for target in selected['targets']:
                if sum(all(event[key] == value for key, value in target.items())
                       for event in events) != 1:
                    raise ValueError('Recorded conflict event changed or disappeared')
            outcomes = outcome_window(traces['outcome'], samples, start, end)
            candidates = read_rows(traces['candidate'])
            result.update(sample_rate=rate, sample_count=samples,
                frames=candidate_frames(candidates, outcomes, note=note, start=start, end=end),
                calibrated_output=summarize_calibrated_output(candidates, outcomes, events, note),
                raw_lane_history=raw_lane_history(events, lane=selected['lane'], start=start, end=end))
            result['traces'] = {}
            for kind, path in traces.items():
                result['traces'][kind] = compress_trace_window(path, start=start, end=end)
                path.unlink()
            current = {kind: result['traces'][kind]['captured_raw_sha256']
                       for kind in ('outcome', 'midi-event')}
            if expected_captures is not None:
                result['reference_complete_streams_bit_identical'] = current == expected_captures
                if not result['reference_complete_streams_bit_identical']:
                    raise ValueError('Complete MIDI or outcome stream differs from the historical ON trial')
            if captures is not None and current != captures:
                raise ValueError('Candidate captures changed the complete MIDI or outcome stream')
            captures = current
            save()
        report.update(state='completed', final=True, stage='conflict window collected',
            complete_midi_and_outcome_identical=True,
            reference_complete_streams_bit_identical=True if expected_captures else None,
            decision=f'unchanged; recorded {mode.upper()} lane conflict reproduced',
            interpretation='Routing and calibrated-output fields identify observed stages, '
            'not an unconditional emission call-site. Unobserved stages are not measured '
            'zeros. Full replay identity is required for every candidate observation; '
            'the selected OFF or ON policy is unchanged. No installed score or live '
            'acceptance changes.')
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
    parser.add_argument('--profile', choices=('reference-off', 'spectral-collision-on',
                                              'coasting-owner-on'),
                        default='reference-off')
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds, profile=args.profile)


if __name__ == '__main__':
    main()
