"""Observe complete changed assignments in the rejected retained-spectral trial.

One ON replay must reproduce the saved trial byte for byte before attribution.
Ordinary and constrained solutions share that ON history; they are not an OFF
counterfactual. Labels annotate observations afterward, never detector decisions.
"""
import argparse
import csv
from datetime import datetime, timezone
from itertools import groupby
import json
from pathlib import Path
import re
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import compress_trace_window, digest, read_rows, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for
from tools.portable_retained_spectral_trial import FLAG


FIELDS = ('sample', 'tick', 'note', 'selected_count', 'ordinal', 'ordinary_valid',
          'ordinary_primary', 'retained_primary', 'pin_mask', 'playable',
          'prior_active', 'prior_committed', 'prior_primary', 'prior_mask',
          'prior_midi', 'prior_spectral', 'final_primary', 'final_mask', 'rendered_mask')
LIMITATION = ('Both proposed assignments share the ON history. Counts describe '
             'immediate primary choices, not OFF counterfactual durations or gains. '
             'Final rendered masks can differ from the primary assignment. '
             'Labels only annotate the completed capture.')


def changed(row):
    return bool(row['ordinary_valid'] and
                row['ordinary_primary'] != row['retained_primary'])


def unpinned_incumbent(row):
    return bool(not row['pin_mask'] and row['prior_active'] and row['prior_committed'])


def read_decisions(path, stderr_path, sample_count):
    raw = read_rows(path)
    if not raw or any(set(row) != set(FIELDS) for row in raw):
        raise ValueError('Missing or malformed retained assignment trace')
    rows = [{key: int(row[key]) for key in FIELDS} for row in raw]
    metadata = re.findall(r'assignment_trace rows=(\d+) cap=(\d+) truncated=(\d+) '
                          r'sampled_frames=(\d+) decimation=(\d+)', stderr_path.read_text())
    if len(metadata) != 1:
        raise ValueError('Missing or repeated trace coverage metadata')
    count, cap, truncated, sampled, decimation = map(int, metadata[0])
    if count != len(rows) or cap != 500000 or count > cap or truncated or decimation != 1:
        raise ValueError('Incomplete retained assignment trace')
    groups, last_sample, last_tick = [], -1, -1
    for (sample, tick), members in groupby(rows, lambda row: (row['sample'], row['tick'])):
        peers = list(members)
        selected = peers[0]['selected_count']
        valid = peers[0]['ordinary_valid']
        if not (last_sample < sample < sample_count and last_tick < tick and tick > 0):
            raise ValueError('Invalid decision clock or sample bounds')
        if (selected not in (2, 3, 4) or len(peers) != selected or
                {row['ordinal'] for row in peers} != set(range(selected)) or
                len({row['note'] for row in peers}) != selected or
                any(row['selected_count'] != selected or row['ordinary_valid'] != valid
                    for row in peers)):
            raise ValueError('Incomplete or duplicate selected peers')
        for row in peers:
            if (not 0 <= row['note'] <= 127 or any(row[key] not in (0, 1)
                    for key in ('ordinary_valid', 'prior_active', 'prior_committed')) or
                    any(not 0 <= row[key] <= 255 for key in ('pin_mask', 'playable',
                        'prior_mask', 'prior_midi', 'prior_spectral', 'final_mask', 'rendered_mask'))):
                raise ValueError('Invalid note, flag or string mask')
            for key in ('prior_primary', 'final_primary'):
                if row[key] not in (*range(8), 255):
                    raise ValueError('Invalid prior or final primary')
            primary, ordinary, pin = (row[key] for key in
                                      ('retained_primary', 'ordinary_primary', 'pin_mask'))
            if (primary not in range(8) or not row['playable'] & (1 << primary) or
                    (valid and (ordinary not in range(8) or
                                not row['playable'] & (1 << ordinary))) or
                    (not valid and ordinary != 255)):
                raise ValueError('Invalid proposed assignment')
            if pin and (pin.bit_count() != 1 or pin != 1 << primary):
                raise ValueError('Invalid or unsatisfied retained pin')
        if (len({row['retained_primary'] for row in peers}) != selected or
                (valid and len({row['ordinary_primary'] for row in peers}) != selected) or
                not any(row['pin_mask'] for row in peers) or
                (valid and not any(changed(row) for row in peers))):
            raise ValueError('Trace does not describe a complete changed allocation')
        groups.append(sorted(peers, key=lambda row: row['ordinal']))
        last_sample, last_tick = sample, tick
    if not len(groups) <= sampled <= sample_count:
        raise ValueError('Invalid sampled frame coverage')
    return groups, dict(rows=count, cap=cap, truncated=False,
                        sampled_frames=sampled, decimation=decimation)


def summarize(groups, labels, comparison):
    rows = [row for group in groups for row in group]
    totals = dict(changed_decisions=len(groups), selected_note_observations=len(rows),
        ordinary_invalid_decisions=sum(not group[0]['ordinary_valid'] for group in groups),
        pinned_note_observations=sum(bool(row['pin_mask']) for row in rows),
        changed_primary_observations=sum(changed(row) for row in rows),
        changed_unpinned_active_committed_observations=sum(
            changed(row) and unpinned_incumbent(row) for row in rows))
    changes = {row['label_index']: row for row in comparison['changed_labels']}
    lost = comparison['lost_labels']
    if not lost or len(set(lost)) != len(lost):
        raise ValueError('Expected recorded passage losses')
    results = []
    for index in lost:
        label, saved = labels[index], changes[index]
        if (saved['matched_delta'] >= 0 or label['matched'] != saved['current_matched'] or
                any(label[key] != saved[key] for key in ('label_index', 'midi_note',
                                                       'string_mask', 'labeled'))):
            raise ValueError('Recorded lost label changed')
        counts = dict(selected_at_changed_decisions=0, ordinary_expected_to_other=0,
            ordinary_other_to_expected=0, expected_to_other_unpinned_incumbent=0,
            final_render_contains_expected=0, final_render_exact_expected=0)
        examples = []
        for peers in groups:
            if not label['start_sample'] <= peers[0]['sample'] < label['end_sample']:
                continue
            row = next((row for row in peers if row['note'] == label['midi_note']), None)
            if row is None:
                continue
            counts['selected_at_changed_decisions'] += 1
            expected = label['string_mask']
            ordinary_matches = bool(row['ordinary_valid'] and
                                    expected & (1 << row['ordinary_primary']))
            retained_matches = bool(expected & (1 << row['retained_primary']))
            loss = ordinary_matches and not retained_matches
            gain = row['ordinary_valid'] and not ordinary_matches and retained_matches
            counts['ordinary_expected_to_other'] += loss
            counts['ordinary_other_to_expected'] += bool(gain)
            counts['expected_to_other_unpinned_incumbent'] += loss and unpinned_incumbent(row)
            counts['final_render_contains_expected'] += row['rendered_mask'] & expected == expected
            counts['final_render_exact_expected'] += row['rendered_mask'] == expected
            if loss and len(examples) < 3:
                examples.append(dict(sample=row['sample'], tick=row['tick'], selected_peers=peers))
        results.append(dict(label=label, recorded_trial_change=saved,
                            observations=counts, expected_to_other_examples=examples))
    focus = min(results, key=lambda item: item['recorded_trial_change']['matched_delta'])
    return dict(totals=totals, lost_labels=results,
                largest_recorded_loss_label=focus['label']['label_index'], interpretation=LIMITATION)


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_retained_spectral_diagnosis_v1', state='running', final=False,
        stage='verify inputs', dataset='ordinary', settings=SETTINGS,
        runtime_rule_changed=False, installed_output_changed=False, promotion_accepted=False,
        decision='rejected trial remains rejected', native_timing='not measured',
        live_readiness='not measured', interpretation=LIMITATION)

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        reference = json.loads(reference_path.read_text())
        expected = reference['runs']['trial-on']
        verify_inputs(corpus, manifest, 'ordinary')
        report.update(source=manifest.get('source', {}), binary_sha256=digest(binary),
            input_manifest_sha256=digest(manifest_path), reference_report_sha256=digest(reference_path))
        trace_path, replay_path = output / 'retained-assignment.tsv', output / 'replay.tsv'
        stderr_path = output / 'replay.stderr'
        command = command_for(binary, corpus, 'ordinary', 'off', 512, None)
        command.extend((FLAG, '--retained-assignment-trace', str(trace_path)))
        report.update(stage='traced ON replay', command=command)
        save()
        started = time.monotonic()
        with replay_path.open('x') as stdout, stderr_path.open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=timeout)
        parsed = read_replay(replay_path)
        report.update(elapsed_seconds=time.monotonic() - started,
            tsv_sha256=digest(replay_path), output=parsed['output'])
        identity = (report['tsv_sha256'] == expected['tsv_sha256'] and
                    report['output'] == expected['output'])
        report['rejected_on_trial_bit_identical'] = identity
        if not identity:
            raise ValueError('Traced ON replay differs from the rejected trial')
        with replay_path.open() as stream:
            aggregate = next(csv.DictReader(stream, delimiter='\t'))
        samples, rate = int(aggregate['samples']), int(aggregate['sample_rate'])
        if samples <= 0 or rate != 96000:
            raise ValueError('Invalid recorded sample clock')
        groups, coverage = read_decisions(trace_path, stderr_path, samples)
        diagnosis = summarize(groups, parsed['labels'], reference['comparison'])
        archive = compress_trace_window(trace_path, start=0, end=samples)
        archive['scope'] = 'all changed decisions, all selected peers, complete recording'
        trace_path.unlink()
        report.update(state='completed', final=True, stage='diagnostic collected',
            sample_count=samples, sample_rate=rate, coverage=coverage,
            diagnosis=diagnosis, trace=archive)
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
