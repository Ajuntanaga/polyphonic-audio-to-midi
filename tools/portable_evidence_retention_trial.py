"""Cloud-only OFF/ON screen of direct evidence retention through energy dips.

Both replays cover the full ordinary recording. Labels select retained diagnosis
windows only; they never change audio, detector settings or the runtime rule.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from tools.candidate_outcome_analysis import HEADER, _candidates, _frame
from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_assignment_trace import (compress_trace_window, digest, read_rows,
                                             select_labels, trace_sample_bounds, verify_inputs)
from tools.portable_corpus_replay import SETTINGS, command_for


def summarize_target(rows, events, label):
    """Separate preview matches, logical activity and captured MIDI transitions.

    ``events=None`` means MIDI was not captured. Snapshot associations describe
    note-ons only: a note-off's old output may be absent from its new snapshot.
    """
    start, end, note = (label[key] for key in ('start_sample', 'end_sample', 'midi_note'))
    expected = set(range(((start + 1 + 63) // 64) * 64 - 1, end, 64))
    seen = set()
    counts = dict(present=0, selected=0, active=0, direct=0,
                  selected_direct_inactive_zero_evidence=0)
    maxima = dict(evidence_ticks=0, attack_ticks=0)
    snapshots = dict(matched=0, matched_with_active_source=0,
                     matched_inactive_preview_only=0, matched_source_unknown=0,
                     rendered_note_with_active_source_any_string=0)
    on_sources = {}
    columns = HEADER.rstrip('\n').split('\t')
    for row in rows:
        sample = int(row['sample'])
        if not start <= sample < end:
            continue
        if sample not in expected or sample in seen or int(row['tick']) * 64 - 1 != sample:
            raise ValueError('Outcome trace clock or duplicate mismatch')
        seen.add(sample)
        frame = _frame('\t'.join(row[column] for column in columns))
        if (label['label_index'], note, label['string_mask']) not in frame['labels']:
            raise ValueError('Target label differs from outcome trace')
        entries = _candidates(frame)
        rendered = [voice for voice in frame['voices'] if voice[1] == note]
        active_sources = [voice for voice in rendered
                          if voice[0] in entries and entries[voice[0]]['active']]
        on_sources[sample] = {}
        for voice in active_sources:
            on_sources[sample].setdefault(voice[2], set()).add(voice[0])
        snapshots['rendered_note_with_active_source_any_string'] += bool(active_sources)
        if label['label_index'] in frame['matched']:
            snapshots['matched'] += 1
            if active_sources:
                snapshots['matched_with_active_source'] += 1
            elif not rendered or any(voice[0] not in entries for voice in rendered):
                snapshots['matched_source_unknown'] += 1
            else:
                snapshots['matched_inactive_preview_only'] += 1
        fields = entries.get(note)
        if fields is None:
            continue
        selected, active, direct = fields['selection'] == 4, bool(fields['active']), bool(fields['direct'])
        evidence, attack = fields['evidence_ticks'], fields['attack']
        counts['present'] += 1
        counts['selected'] += selected
        counts['active'] += active
        counts['direct'] += direct
        counts['selected_direct_inactive_zero_evidence'] += selected and direct and not active and not evidence
        maxima['evidence_ticks'] = max(maxima['evidence_ticks'], evidence)
        maxima['attack_ticks'] = max(maxima['attack_ticks'], attack)
    if seen != expected:
        raise ValueError('Incomplete outcome trace for target label')
    transitions = []
    for row in events if events is not None else ():
        if row['kind'] not in ('on', 'off'):
            raise ValueError('Unknown MIDI event kind')
        if int(row['note']) == note and start <= int(row['sample']) < end:
            transition = dict(sample=int(row['sample']), kind=row['kind'],
                              voice_id=int(row['voice_id']))
            if row['kind'] == 'on':
                sources = sorted(on_sources.get(transition['sample'], {}).get(transition['voice_id'], ()))
                transition['matching_snapshot_active_source_notes'] = sources
                transition['snapshot_source_status'] = ('unique' if len(sources) == 1 else
                                                        'ambiguous' if sources else 'unknown')
            transitions.append(transition)
    return dict(label=label, frames=len(seen), counts=counts, maxima=maxima,
                snapshot_counts=snapshots,
                midi_event_capture='not measured' if events is None else 'provided',
                midi_events_during_label=transitions,
                interpretation='Candidate state is after lifecycle processing. MIDI events are '
                               'actual transitions. The voice cents_valid field is pitch-bend '
                               'validity, not MIDI activity. Matches can include inactive tuner '
                               'previews. Active-source snapshots do not prove held MIDI; note-on '
                               'source associations require a unique active logical source at the '
                               'same sample, emitted note and lane. Neither establishes physical '
                               'string identity or freedom from stuck notes.')


def summarize_calibrated_output(rows, outcomes, events, note):
    """Join the executed stage to later snapshots without attributing later MIDI.

    Stage transition counts identify this candidate's calibrated-output work.
    Events at the same tick can also include later assignment/lifecycle work.
    """
    outcomes = {int(row['sample']): row for row in outcomes}
    events_at = {}
    for row in events:
        events_at.setdefault(int(row['sample']), []).append(dict(
            kind=row['kind'], note=int(row['note']), voice_id=int(row['voice_id'])))
    seen, reasons, changes, transitions = set(), Counter(), Counter(), []
    int_fields = ('tick', 'eligibility_failures', 'age', 'min_age', 'selected_count',
                  'member_mask', 'output_before', 'output_after', 'midi_before',
                  'midi_after', 'target_before', 'target_after', 'ticks_before',
                  'ticks_after', 'projected_note', 'changed', 'trusted',
                  'collision_note', 'collision_kind', 'transitions_added')
    for row in rows:
        sample, tick = int(row['sample']), int(row['tick'])
        if (sample not in outcomes or sample in seen or tick * 64 - 1 != sample
                or int(row['note']) != note):
            raise ValueError('Calibrated-output trace clock, candidate or coverage mismatch')
        seen.add(sample)
        observed, reason = int(row['cal_observed']), row['cal_reason']
        if observed and (int(row['cal_tick']) != tick or reason == 'not_observed'):
            raise ValueError('Stale calibrated-output stage observation')
        if not observed and reason != 'not_observed':
            raise ValueError('Unobserved calibrated-output stage has a reason')
        reasons[reason] += 1
        stage = {key: int(row['cal_' + key]) for key in int_fields}
        stage.update(observed=bool(observed), reason=reason,
                     phase_cents=row['cal_phase_cents'],
                     projected_error_cents=row['cal_projected_error_cents'])
        changed = observed and (stage['output_before'] != stage['output_after']
                                or stage['midi_before'] != stage['midi_after'])
        if changed:
            changes[reason] += 1
        actual = events_at.get(sample, [])
        if changed or stage['transitions_added'] or any(
                event['note'] in (note, note + 1) for event in actual):
            transitions.append(dict(sample=sample, stage=stage,
                midi_events_at_same_tick=actual,
                later_snapshot_voices=outcomes[sample]['voices']))
    if seen != set(outcomes):
        raise ValueError('Incomplete calibrated-output candidate capture')
    return dict(candidate_note=note, frames=len(seen), reasons=dict(reasons),
                output_change_reasons=dict(changes), transitions=transitions,
                interpretation='Stage fields record the executed calibrated-output branch '
                    'before later assignment/lifecycle work. Same-tick MIDI events are '
                    'actual global events, not automatically attributable to this stage. '
                    'An ineligible tick clears pending consensus but does not itself '
                    'revert an emitted projection. This is baseline diagnosis, not a '
                    'runtime improvement or host/MIDI acceptance.')


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900,
        calibrated_output_trace=False):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_direct_evidence_retention_trial_v1', state='running', final=False,
                  stage='verify inputs', dataset='ordinary', settings=SETTINGS,
                  installed_output_changed=False, promotion_accepted=False,
                  native_timing='not measured', live_readiness='not measured')
    if calibrated_output_trace:
        report['schema'] = 'm3_calibrated_output_trace_v1'
        report['runtime_rule_changed'] = False

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    def replay(command, stem):
        report.update(stage=stem, command=command)
        save()
        path = output / (stem + '.tsv')
        started = time.monotonic()
        with path.open('x') as stdout, (output / (stem + '.stderr')).open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
        parsed = read_replay(path)
        report.setdefault('runs', {})[stem] = dict(elapsed_seconds=time.monotonic() - started,
            tsv_sha256=digest(path), output=parsed['output'],
            exact_matches_by_string_count=parsed['exact_matches_by_string_count'])
        return path, parsed

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
                      input_manifest_sha256=digest(manifest_path),
                      reference_report_sha256=digest(reference_path))
        command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
        reference_file, before = replay(command, 'reference-off')
        reference = json.loads(reference_path.read_text())['runs']['reference-off']
        identity = (digest(reference_file) == reference['tsv_sha256']
                    and before['output'] == reference['output'])
        report['off_reference_bit_identical'] = identity
        if not identity:
            raise ValueError('OFF reference differs from the retained ordinary baseline')
        label = select_labels(before['labels'], note=42, label_index=55)[0]
        with reference_file.open() as stream:
            aggregate = next(csv.DictReader(stream, delimiter='\t'))
        samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
        start, end = trace_sample_bounds([label], samples)
        traces = {kind: output / (kind + '.tsv') for kind in ('candidate', 'outcome', 'midi-event')}
        if not calibrated_output_trace:
            command.append('--diagnostic-direct-evidence-retention')
        for kind, path in traces.items():
            command.extend(('--' + kind + '-trace', str(path)))
        candidate_note = 41 if calibrated_output_trace else 42
        command.extend(('--candidate-trace-note', str(candidate_note), '--candidate-trace-start', str(start / rate),
                        '--candidate-trace-end', str(end / rate)))
        after_file, after = replay(command, 'traced-off' if calibrated_output_trace else 'trial-on')
        comparison = compare_replays(before, after)
        report.update(comparison=comparison, sample_rate=rate, sample_count=samples,
                      target_before=label, target_after=after['labels'][55],
                      full_recording_screen_pass=comparison['gate_pass'],
                      labeled_match_gain=comparison['delta']['matched'] > 0)
        if calibrated_output_trace:
            report['trace_output_bit_identical'] = digest(reference_file) == digest(after_file)
            report['trace_semantic_identity'] = before == after
            if not report['trace_output_bit_identical'] or not report['trace_semantic_identity']:
                raise ValueError('Traced OFF replay differs from untraced OFF replay')
        # Stream the full capture once; retain the small target window in memory.
        window = []
        with traces['outcome'].open(newline='') as stream:
            rows = csv.DictReader((line for line in stream if not line.startswith('#')), delimiter='\t')
            expected_sample = 63
            for row in rows:
                sample = int(row['sample'])
                if sample != expected_sample or int(row['tick']) * 64 - 1 != sample:
                    raise ValueError('Incomplete or reordered full outcome capture')
                expected_sample += 64
                if start <= sample < end:
                    window.append(row)
            if expected_sample != 63 + (samples // 64) * 64:
                raise ValueError('Incomplete full outcome capture')
        events = read_rows(traces['midi-event'])
        report['target_lifecycle'] = summarize_target(window, events, after['labels'][55])
        if calibrated_output_trace:
            report['calibrated_output'] = summarize_calibrated_output(
                read_rows(traces['candidate']), window, events, candidate_note)
        report['traces'] = {}
        for kind, path in traces.items():
            report['traces'][kind] = compress_trace_window(path, start=start, end=end)
            path.unlink()
        report.update(state='completed', final=True, stage='offline screen collected',
                      decision='unchanged baseline; diagnostic collected' if calibrated_output_trace else
                               'eligible for wider validation' if comparison['gate_pass'] and
                               comparison['delta']['matched'] > 0 else 'rejected')
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
    parser.add_argument('--calibrated-output-trace', action='store_true',
                        help='Capture the unchanged OFF calibrated-output branch for logical note 41')
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds, calibrated_output_trace=args.calibrated_output_trace)


if __name__ == '__main__':
    main()
