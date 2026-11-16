"""Compare retained tuning/competition cues and MIDI on GitHub, without replay."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from tools import ordinary_harmonic_attribution as attribution


SCREENS = ('tuning', 'competition')
CURRENT, TRIAL = attribution.CURRENT, attribution.TRIAL


def observation_key(row):
    return row['available_sample'], row['candidate_note']


def compare_parent_inputs(left, right):
    """Fitted frequencies are outputs; saved phase and parent identity are inputs."""
    before, after = left.get('base_pitches', []), right.get('base_pitches', [])
    if len(before) != len(after):
        raise ValueError('Causal parent count differs')
    both_fitted = all(row.get('parent_tuning', {}).get('status') == 'fitted'
                      for row in (left, right))
    differences = []
    for old, new in zip(before, after):
        fitted = both_fitted and old.get('phase_valid') is False
        fields = set(old) | set(new)
        if fitted:
            fields.discard('frequency_hz')
        if any(old.get(field) != new.get(field) for field in fields):
            raise ValueError('Causal parent identity or saved phase differs')
        if fitted and old['frequency_hz'] != new['frequency_hz']:
            hz = old['frequency_hz'], new['frequency_hz']
            if not all(math.isfinite(value) and value > 0 for value in hz):
                raise ValueError('Invalid fitted parent frequency')
            differences.append(dict(note=old['note'], tuning_hz=hz[0], competition_hz=hz[1],
                                    difference_cents=1200 * math.log2(hz[1] / hz[0])))
    return differences


def match_observations(before, after):
    """Require the same frozen observations; competition may only withhold cues."""
    indexed = []
    for rows in (before, after):
        mapping = {}
        for row in rows:
            key = observation_key(row)
            baseline = row['baseline_state_sample']
            if key in mapping or (baseline is not None and baseline > key[0] - 960):
                raise ValueError('Duplicate or noncausal paired observation')
            mapping[key] = row
        indexed.append(mapping)
    old, new = indexed
    if old.keys() != new.keys():
        raise ValueError('Frozen observation identities differ')
    withheld, fit_differences = [], []
    for key in sorted(old):
        left, right = old[key], new[key]
        for field in ('window_start_sample', 'baseline_state_sample'):
            if left[field] != right[field]:
                raise ValueError(f'Causal observation {key} differs at {field}: '
                                 f'{left[field]!r} != {right[field]!r}')
        if left['status'] != right['original_status']:
            raise ValueError(f'Original decision {key} differs: '
                             f'{left["status"]!r} != {right["original_status"]!r}')
        differences = compare_parent_inputs(left, right)
        if differences:
            fit_differences.append(dict(available_sample=key[0], candidate_note=key[1],
                                        parents=differences))
        if right['admitted'] and not left['admitted']:
            raise ValueError('Competition added an admission')
        if left['admitted'] and not right['admitted']:
            if right['status'] != 'lower_competition_withheld':
                raise ValueError('Unexpected reason for withholding')
            withheld.append(right)
    return old, new, withheld, fit_differences


def require_shared_reference(screens):
    left, right = (screens[name] for name in SCREENS)
    for field in ('sample_count', 'sample_rate', 'labels'):
        if left[field] != right[field]:
            raise ValueError('Shared reference differs: ' + field)
    if left['events'][CURRENT] != right['events'][CURRENT]:
        raise ValueError('Shared current MIDI differs')
    if (left['saved']['runs'][CURRENT]['midi_trace']['raw_sha256'] !=
            right['saved']['runs'][CURRENT]['midi_trace']['raw_sha256']):
        raise ValueError('Shared current MIDI bytes differ')
    if left['saved']['input_manifest_sha256'] != right['saved']['input_manifest_sha256']:
        raise ValueError('Shared input manifest differs')
    if (left['saved']['runs'][CURRENT]['outcome_sha256'] !=
            right['saved']['runs'][CURRENT]['outcome_sha256']):
        raise ValueError('Shared causal detector outcome differs')


def expected_pitch_intervals(labels, start, end, note):
    """Classify cue duration by annotation pitch, without inventing a string lane."""
    relevant = [row for row in labels if row['start_sample'] < end and row['end_sample'] > start]
    edges = sorted({start, end} | {max(start, row['start_sample']) for row in relevant}
                   | {min(end, row['end_sample']) for row in relevant})
    counts = Counter()
    for left, right in zip(edges, edges[1:]):
        active = [row for row in relevant if row['start_sample'] <= left < row['end_sample']]
        kind = ('expected_pitch' if any(row['midi_note'] == note for row in active)
                else 'other_labeled_pitch' if active else 'unlabeled_gap')
        counts[kind] += right - left
    return dict(counts)


def overlap(left, right, start, end):
    return max(0, min(right, end) - max(left, start))


def paired_analysis(screens, focus_labels, focus_cue):
    require_shared_reference(screens)
    old, new, withheld, fit_differences = match_observations(
        *(screens[name]['observations'] for name in SCREENS))
    labels = screens['tuning']['labels']
    count = screens['tuning']['sample_count']
    reproduction, screen_changes = {}, {}
    for name, screen in screens.items():
        result, changes, counts = attribution.compare(screen['events'], labels, count,
                                                       screen['context'], focus_labels)
        attribution.reproduce_metrics(screen['saved'], result, counts)
        reproduction[name] = result
        screen_changes[name] = changes
    pair, changes, _ = attribution.compare(
        {CURRENT: screens['tuning']['events'][TRIAL], TRIAL: screens['competition']['events'][TRIAL]},
        labels, count, screens['competition']['context'], focus_labels)
    for row in changes:
        # Generic compare uses CURRENT/TRIAL; report explicitly maps these aliases.
        row['tuning_cue_at_original_onset'] = screens['tuning']['context'].preceding(
            row['original_onset_sample'], row['note'])
        row['tuning_cue_at_span_start'] = screens['tuning']['context'].preceding(
            row['start_sample'], row['note'])
    rows = []
    for decision in withheld:
        start = decision['available_sample'] + 1
        end = min(start + 1024, count)
        note = decision['candidate_note']
        associated = []
        for change in changes:
            shared = overlap(change['start_sample'], change['end_sample'], start, end)
            if change['note'] == note and shared:
                associated.append(dict(sign=change['sign'], classification=change['classification'],
                    voice_id=change['voice_id'], overlap_voice_samples=shared,
                    start_sample=change['start_sample'], end_sample=change['end_sample']))
        rows.append(dict(start_sample=start, end_sample=end, note=note,
            withholding_lower_note=decision['withholding_lower_note'],
            annotation_pitch_samples=expected_pitch_intervals(labels, start, end, note),
            overlapping_same_pitch_output_changes=associated, decision=decision))
    expected_count = screens['competition']['saved']['cue_generation']['statuses'].get(
        'lower_competition_withheld', 0)
    if len(rows) != expected_count:
        raise ValueError('Withheld count differs from screen')
    key = focus_cue['available_sample'], focus_cue['candidate_note']
    if key not in old:
        raise ValueError('Known false-note cue absent')
    largest = {}
    for name in SCREENS:
        largest[name] = sorted([row for row in screen_changes[name]
            if row['sign'] == 1 and row['note'] == focus_cue['candidate_note']
            and row['classification'] == 'false_wrong_note'],
            key=lambda row: (-row['voice_samples'], row['start_sample']))[:3]
    observed_lowers = Counter()
    if largest['tuning']:
        span = largest['tuning'][0]
        for decision in new.values():
            if (decision['candidate_note'] == focus_cue['candidate_note'] and
                    span['start_sample'] - 1024 <= decision['available_sample'] < span['end_sample']):
                for lower in decision['lower_comparisons']:
                    observed_lowers[(lower['lower']['note'], lower['independent_lower_support']['status'])] += 1
    by_pair = Counter((row['note'], row['withholding_lower_note']) for row in rows)
    pair['change_totals'] = {kind: dict(
        added=sum(row['voice_samples'] for row in changes if row['sign'] == 1 and row['classification'] == kind),
        removed=sum(row['voice_samples'] for row in changes if row['sign'] == -1 and row['classification'] == kind))
        for kind in attribution.KINDS}
    target = labels[focus_labels[0]]
    target_decisions = [row for row in new.values() if row['candidate_note'] == target['midi_note']
        and target['start_sample'] <= row['available_sample'] + 1 < target['end_sample']]
    result = dict(shared_current_identity_pass=True, saved_metric_reproduction_pass=True,
        shared_input_manifest_and_causal_outcome_pass=True, original_decision_statuses_identical=True,
        fitted_parent_output_differences=dict(observations=len(fit_differences),
            maximum_absolute_cents=max((abs(parent['difference_cents']) for row in fit_differences
                for parent in row['parents']), default=0.), rows=fit_differences),
        observations=len(old), cue_counts={name: len(screens[name]['cues']) for name in SCREENS},
        withheld_count=len(rows), withheld_by_upper_lower=[dict(upper=upper, lower=lower, count=n)
            for (upper, lower), n in sorted(by_pair.items())],
        withheld_annotation_pitch_samples=dict(sum((Counter(row['annotation_pitch_samples']) for row in rows), Counter())),
        withheld_with_overlapping_output_changes=sum(bool(row['overlapping_same_pitch_output_changes']) for row in rows),
        per_screen_vs_current=reproduction, competition_vs_tuning=pair,
        pair_mode_aliases={CURRENT: 'tuning', TRIAL: 'competition'},
        known_false_note=dict(tuning_decision=old[key], competition_decision=new[key],
            largest_added_wrong_note_spans=largest,
            lower_support_during_tuning_false_span=[dict(lower=lower, status=status, count=n)
                for (lower, status), n in sorted(observed_lowers.items())]),
        target=dict(label=target, competition_decision_statuses=dict(Counter(row['status'] for row in target_decisions)),
                    admitted_cues=sum(row['admitted'] for row in target_decisions)))
    return result, rows, changes


def analyze(reference_path, archives, output):
    reference = json.loads(reference_path.read_text())
    if reference['schema'] != 'm3_ordinary_harmonic_competition_attribution_references_v1':
        raise ValueError('Unexpected paired attribution reference')
    screens = {name: attribution.load_screen(reference['screens'][name], *archives[name]) for name in SCREENS}
    result, withheld, changes = paired_analysis(screens, reference['focus_labels'], reference['focus_cue'])
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (('withheld-cues', withheld), ('paired-output-changes', changes)):
        (output / (name + '.json')).write_text(json.dumps(rows, indent=2, allow_nan=False) + '\n')
    result.update(schema='m3_ordinary_harmonic_competition_attribution_v1', state='completed', final=True,
        finished_at=datetime.now(timezone.utc).isoformat(),
        source_commit=os.environ.get('SOURCE_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
        retained_sources=reference, sample_count=screens['tuning']['sample_count'],
        sample_rate=screens['tuning']['sample_rate'], native_replays=0, audio_processed=False,
        installed_output_changed=False, promotion_accepted=False,
        interpretation='Cue duration counts overlapping candidate windows, not unique audio duration. '
        'Cue pitch annotation does not test string assignment. Output durations are voice-samples; '
        'exact held durations count overlapping label-samples. Gap outputs are extra notes, not missing notes. '
        'Cue/output overlaps are associations, not proof of native branch selection. '
        'Fitted parent frequencies are computed outputs; any differences are reported separately '
        'from identical frozen detector input and original decision status. '
        'The competition and tuning trials remain rejected; no new note quality, timing, allocation, buffer '
        'or host measurement is performed.')
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(state='completed', withheld=len(withheld),
                          saved_metric_reproduction_pass=True, native_replays=0)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    for name in SCREENS:
        parser.add_argument('--' + name + '-small', type=Path, required=True)
        parser.add_argument('--' + name + '-bulk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.reference, {name: (getattr(args, name + '_small'), getattr(args, name + '_bulk'))
                             for name in SCREENS}, args.output)


if __name__ == '__main__':
    main()
