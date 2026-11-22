"""Independent recomputation of the headline numbers in Codex's adaptation report (run 45016827324) from its four saved event files.

Why: a handoff claim is worth more once someone else has reproduced it.  This rebuilds, with the committed scorer and a different code path
from the one that produced the report (emission_spans on the saved events, then tools.pitch_detector_comparison.score/compare), the paired
unchanged-TF versus adapted-TF comparison on both corpora and both clocks, at the FULL recording length the report used (spec sample_count, not
the consensus common horizon), and prints every figure next to the value the report states.  Read-only, saved data, no audio, no model, no job.

Compared per corpus and clock: both arms' coverage, the paired exact-set percentages (exact-set samples over annotated samples), the sample
deltas (present, all-expected, exact set, extra pitch voice, and the unlabeled gap voice, which the report names extra_gap_pitch_samples_delta),
the number of labels losing present time and losing longest hold, the number of labels changed either way, the label count losing present
time per register band, and the no_pitch_safety_regression flag.  A first run with three different definitions on my side (exact set over
expected samples, extra plus gap, a band count of present-or-longest) differed from the report only in those three fields; the arithmetic
showed each was a naming or denominator difference, and this version uses the report's labelled meaning.

Usage: python3 -P -E CLAUDE-M3-ADAPTATION-VERIFY-20261122.py REPORT_JSON ORD_ORIGINAL ORD_ADAPTED EXT_ORIGINAL EXT_ADAPTED
Writes CLAUDE-M3-ADAPTATION-VERIFY-20261122.json next to this file.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ad', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'))
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTATION-VERIFY-20261122.json')
BANDS = {'below48': (0, 48), '48to59': (48, 60), '60to71': (60, 72), '72plus': (72, 200)}


def full_context(dataset, spec_sizes):
    base = json.load(open(ad.ce.BASELINE))['datasets'][dataset]
    horizon, rate = spec_sizes['sample_count'], spec_sizes['sample_rate']
    labels, _ = ad.clip_labels(ad.labels_from_measurement(base['measurement']), horizon)
    return dict(horizon=horizon, clock=dict(sample_count=horizon, sample_rate=rate), labels=labels)


def paired(ctx, original, adapted, clock_name):
    spans = {}
    for tag, events in (('original', original), ('adapted', adapted)):
        spans[tag] = ad.spans_from_events(events, ctx['horizon'], clock_name)[0]
    scored = {tag: score(s, ctx['labels'], **ctx['clock']) for tag, s in spans.items()}
    cmp = compare(scored['original'], scored['adapted'])
    t0, t1 = scored['original']['pitch_sets']['totals'], scored['adapted']['pitch_sets']['totals']
    g0 = scored['original']['pitch_sets']['unlabeled_gap_voice_samples']
    g1 = scored['adapted']['pitch_sets']['unlabeled_gap_voice_samples']
    rows = cmp['label_deltas']
    by = {lab['label_index']: lab['midi_note'] for lab in ctx['labels']}
    lost = {name: sum(1 for r in rows if lo <= by[r['label_index']] < hi and r['present_samples_delta'] < 0)
            for name, (lo, hi) in BANDS.items()}
    pct = lambda n, d: 100.0 * n / d
    return dict(
        original_coverage_percent=pct(t0['present_pitch_samples'], t0['expected_pitch_samples']),
        adapted_coverage_percent=pct(t1['present_pitch_samples'], t1['expected_pitch_samples']),
        original_exact_set_percent=pct(t0['exact_pitch_set_samples'], t0['annotated_samples']),
        adapted_exact_set_percent=pct(t1['exact_pitch_set_samples'], t1['annotated_samples']),
        present_delta=t1['present_pitch_samples'] - t0['present_pitch_samples'],
        all_expected_delta=t1['all_expected_pitches_samples'] - t0['all_expected_pitches_samples'],
        exact_set_delta=t1['exact_pitch_set_samples'] - t0['exact_pitch_set_samples'],
        extra_voice_delta=t1['extra_pitch_voice_samples'] - t0['extra_pitch_voice_samples'],
        gap_voice_delta=g1 - g0,
        labels_losing_present=sum(1 for r in rows if r['present_samples_delta'] < 0),
        labels_losing_longest=sum(1 for r in rows if r['longest_present_samples_delta'] < 0),
        labels_changed=sum(1 for r in rows if r['present_samples_delta'] or r['longest_present_samples_delta']),
        lost_labels_by_band=lost,
        no_pitch_safety_regression=cmp['no_pitch_safety_regression'])


def reported(block):
    sd = block['sample_deltas']
    rows = block['label_deltas']
    return dict(
        original_coverage_percent=block['current_pitch_coverage_percent'], adapted_coverage_percent=block['model_pitch_coverage_percent'],
        original_exact_set_percent=block['current_exact_pitch_set_percent'], adapted_exact_set_percent=block['model_exact_pitch_set_percent'],
        present_delta=sd['present_pitch_samples'], all_expected_delta=sd['all_expected_pitches_samples'],
        exact_set_delta=sd['exact_pitch_set_samples'], extra_voice_delta=sd['extra_pitch_voice_samples'],
        gap_voice_delta=block['extra_gap_pitch_samples_delta'],
        labels_losing_present=sum(1 for r in rows if r['present_samples_delta'] < 0),
        labels_losing_longest=sum(1 for r in rows if r['longest_present_samples_delta'] < 0),
        labels_changed=len(block['label_changes']),
        lost_labels_by_band={k: v['lost_labels'] for k, v in block['label_bands'].items()},
        no_pitch_safety_regression=block['no_pitch_safety_regression'])


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def main(report_path, ord_o, ord_a, ext_o, ext_a):
    report = json.load(open(report_path))
    paths = {'ordinary': (ord_o, ord_a), 'extended-middle': (ext_o, ext_a)}
    out, mismatches = {}, []
    for dataset, (po, pa) in paths.items():
        ctx = full_context(dataset, report['specification']['datasets'][dataset])
        original, adapted = ad.read_events(po), ad.read_events(pa)
        for clock_name, key in (('emitted_ns', 'adaptation_primary'), ('available_ns', 'adaptation_zero_compute_diagnostic')):
            mine = paired(ctx, original, adapted, clock_name)
            theirs = reported(report['datasets'][dataset][key])
            diffs = {k: dict(mine=mine[k], report=theirs[k]) for k in mine if not same(mine[k], theirs[k])}
            out[f'{dataset}/{clock_name}'] = dict(recomputed=mine, reported=theirs, differences=diffs)
            mismatches.extend(f'{dataset}/{clock_name}/{k}' for k in diffs)
            print(dataset, clock_name, 'fields', len(mine), 'differences', len(diffs))
            for k, v in diffs.items():
                print('   DIFF', k, json.dumps(v))
    out['all_match'] = not mismatches
    out['mismatches'] = mismatches
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('ALL MATCH' if not mismatches else 'MISMATCHES: ' + ', '.join(mismatches))


if __name__ == '__main__':
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
