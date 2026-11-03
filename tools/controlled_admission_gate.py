"""Score the intended low note separately from controlled-mixture totals."""
from __future__ import annotations

import csv
from pathlib import Path


CASES = ('solo', 'octave_-12dB', 'octave_0dB', 'nearby_-12dB', 'nearby_0dB')
FIELDS = ('matched', 'false_wrong_note_voices', 'false_wrong_string_voices',
          'false_gap_voices', 'false_positive_voices')
TARGET_FIELDS = ('label_index', 'start_sample', 'end_sample', 'midi_note',
                 'string_mask', 'calibration_pass', 'labeled', 'matched')
GATE_VERSION = 'target-note-v2'


def _count(value):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError('expected a nonnegative integer count')
    return int(value)


def _target(row):
    result = {key: _count(row[key]) for key in TARGET_FIELDS}
    if (result['midi_note'] != 36 or result['string_mask'] != 1
            or result['end_sample'] <= result['start_sample']
            or result['labeled'] == 0 or result['matched'] > result['labeled']):
        raise ValueError('invalid target identity, span or counts')
    return result


def read_target_detail(path):
    """Read exactly one MIDI-36/string-mask-1 row from --label-details TSV."""
    csv.field_size_limit(8 * 1024 * 1024)
    with Path(path).open(newline='') as stream:
        rows = csv.reader(stream, delimiter='\t')
        header = next((row for row in rows if row and row[0] == 'label_index'), None)
        if (header is None or len(set(header)) != len(header)
                or not set(TARGET_FIELDS).issubset(header)):
            raise ValueError('missing or malformed label-details header')
        targets = []
        for row in rows:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError('malformed label-details row')
            detail = dict(zip(header, row))
            if (_count(detail['midi_note']), _count(detail['string_mask'])) == (36, 1):
                targets.append(_target(detail))
        if len(targets) != 1:
            raise ValueError('expected exactly one target label')
        return targets[0]


def evaluate_admission(datasets):
    """Fail closed without paired target evidence; totals cannot mask its loss."""
    if set(datasets) != set(CASES):
        raise ValueError('expected all five controlled cases')
    results = {}
    for case in CASES:
        item = datasets[case]
        if item.get('control_identical') is not True:
            raise ValueError(f'{case}: changed or missing control')
        off, on = (item['replays'][mode] for mode in ('off', 'on'))
        if any('target' not in replay for replay in (off, on)):
            raise ValueError(f'{case}: missing target details')
        targets = [_target(replay['target']) for replay in (off, on)]
        if any(targets[0][key] != targets[1][key]
               for key in TARGET_FIELDS if key != 'matched'):
            raise ValueError(f'{case}: target identity or label accounting changed')
        totals = [{key: _count(replay['output'][key]) for key in ('labeled', *FIELDS)}
                  for replay in (off, on)]
        if totals[0]['labeled'] != totals[1]['labeled']:
            raise ValueError(f'{case}: aggregate label accounting changed')
        for target, total in zip(targets, totals):
            other_labeled = total['labeled'] - target['labeled']
            other_matched = total['matched'] - target['matched']
            if not 0 <= other_matched <= other_labeled:
                raise ValueError(f'{case}: target and aggregate counts disagree')
        delta = {key: totals[1][key] - totals[0][key] for key in FIELDS}
        target_delta = targets[1]['matched'] - targets[0]['matched']
        results[case] = dict(delta=delta, target_matched_delta=target_delta,
                             gate_pass=target_delta >= 0 and delta['matched'] >= 0
                             and all(delta[key] <= 0 for key in FIELDS[1:]))
    regressions = [case for case in CASES if not results[case]['gate_pass']]
    target_improved = results['nearby_0dB']['target_matched_delta'] > 0
    accepted = not regressions and target_improved
    return dict(gate_version=GATE_VERSION, cases=results, regressions=regressions,
                target_improved=target_improved,
                aggregate_match_improved=results['nearby_0dB']['delta']['matched'] > 0,
                accepted_for_corpus_screen=accepted,
                verdict='advance to corpus screen' if accepted else 'rejected')
