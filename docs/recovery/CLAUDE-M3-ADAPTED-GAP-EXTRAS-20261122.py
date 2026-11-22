"""Adapted gap extras: new attacks or longer continuations?  Plan and predictions G0-G6 are fixed in
CLAUDE-M3-ADAPTED-GAP-EXTRAS-PREREGISTRATION-20261122.md (commit 104b405), written before this script was run.

Saved data only: Codex's unmodified and adapted TensorFlow event files (run 45022134487) on the zero-compute availability clock, the labels,
CURRENT.  No audio, model run, job or native edit; nothing promoted; not a gate.

For each corpus: the adapted run's gap-voice samples (model span samples where no label is active) that the unmodified run does not cover at
the same pitch ("added"), split by the adapted span that contains them into
  carried in (the span covers the sample just before the gap began) -> same-pitch tail (a label of that pitch was active there) or other pitch,
  born in the gap (the span starts inside the gap) -> a post hoc sub-split: anticipation of the next label (same pitch, span reaches its start).
Overlap with the unmodified run: an unmodified span of the same pitch overlaps the adapted span at all.

Usage: python3 -P -E CLAUDE-M3-ADAPTED-GAP-EXTRAS-20261122.py [--selftest]   (no other arguments)
Writes CLAUDE-M3-ADAPTED-GAP-EXTRAS-20261122.json next to this file.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

spec = importlib.util.spec_from_file_location('ad', os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'))
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)
from tools.pitch_detector_comparison import score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTED-GAP-EXTRAS-20261122.json')
EVENTS = os.path.join(REPO, 'build', 'github-results', 'basic-pitch-adaptation-events-45022134487', 'collected', 'selected')


def merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def complement(merged, horizon):
    gaps, cursor = [], 0
    for a, b in merged:
        if a > cursor:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < horizon:
        gaps.append((cursor, horizon))
    return gaps


def subtract(seg, cover):
    """seg (a, b) minus a sorted merged interval list; returns the remaining pieces."""
    a, b = seg
    pieces = []
    for c, d in cover:
        if d <= a:
            continue
        if c >= b:
            break
        if c > a:
            pieces.append((a, c))
        a = max(a, d)
        if a >= b:
            break
    if a < b:
        pieces.append((a, b))
    return pieces


def by_pitch(spans):
    out = {}
    for l, r, p in spans:
        out.setdefault(p, []).append((l, r))
    return {p: merge(v) for p, v in out.items()}


def gap_segments(spans, gaps):
    """(span_left, gap_a, seg_l, seg_r, pitch) for every span piece inside a gap; carried = span_left < gap_a == seg_l."""
    rows = []
    for l, r, p in spans:
        for a, b in gaps:
            lo, hi = max(l, a), min(r, b)
            if lo < hi:
                rows.append((l, a, lo, hi, p))
    return rows


def analyse(spans_a, spans_u, labels, horizon, rate):
    """Classify the adapted run's gap samples that the unmodified run does not cover at the same pitch."""
    active = merge([(x['start_sample'], x['end_sample']) for x in labels])
    gaps = complement(active, horizon)
    cover_u, cover_a = by_pitch(spans_u), by_pitch(spans_a)
    seg_a, seg_u = gap_segments(spans_a, gaps), gap_segments(spans_u, gaps)
    gap_a = sum(r - l for _, _, l, r, _ in seg_a)
    gap_u = sum(r - l for _, _, l, r, _ in seg_u)
    removed = 0
    for _, _, l, r, p in seg_u:
        removed += sum(y - x for x, y in subtract((l, r), cover_a.get(p, [])))
    label_ends = sorted((x['end_sample'], x['midi_note']) for x in labels)
    label_starts = sorted((x['start_sample'], x['midi_note']) for x in labels)

    def tail_label(a, p):
        return any(x['midi_note'] == p and x['start_sample'] <= a - 1 < x['end_sample'] for x in labels)

    def anticipates(span_r, gap_end, p):
        return any(s == gap_end and note == p for s, note in label_starts) and span_r > gap_end

    classes = {}
    added_total = 0
    tails_added, tails_full = [], []
    span_index = {}
    for l, r, p in spans_a:
        span_index.setdefault(p, []).append((l, r))
    for span_l, gstart, lo, hi, p in seg_a:
        added = sum(y - x for x, y in subtract((lo, hi), cover_u.get(p, [])))
        if not added:
            continue
        # the adapted span that contains this gap piece (spans are unioned, so it is unique)
        span_r = next(r for l, r in span_index[p] if l <= lo < r)
        gap_b = next(b for a, b in gaps if a == gstart)
        carried = span_l < gstart == lo
        if carried:
            kind = 'carried_in_same_pitch_tail' if tail_label(gstart, p) else 'carried_in_other_pitch'
        else:
            kind = 'born_in_gap_anticipates_next_label' if anticipates(span_r, gap_b, p) else 'born_in_gap_other'
        overlap = any(u_l < span_r and u_r > span_l for u_l, u_r in cover_u.get(p, []))
        key = (kind, 'unmodified_also_has_note' if overlap else 'adapted_only_note')
        row = classes.setdefault(key, dict(segments=0, samples=0))
        row['segments'] += 1
        row['samples'] += added
        added_total += added
        if kind == 'carried_in_same_pitch_tail':
            tails_added.append(added * 1000 / rate)
            tails_full.append((hi - lo) * 1000 / rate)
    return dict(gap_voice_adapted=gap_a, gap_voice_unmodified=gap_u, added=added_total, removed=removed,
                net_change_pct=round(100 * (gap_a - gap_u) / max(1, gap_u), 1), classes=classes,
                tail_added_ms=_q(tails_added), tail_full_gap_segment_ms=_q(tails_full))


def _q(values):
    if not values:
        return None
    ordered = sorted(values)
    pick = lambda q: round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1)
    return dict(count=len(ordered), median_ms=pick(0.5), p90_ms=pick(0.9), max_ms=round(ordered[-1], 1))


def shares(result):
    added = max(1, result['added'])
    kinds = {}
    overlap = {}
    for (kind, ov), row in result['classes'].items():
        kinds[kind] = kinds.get(kind, 0) + row['samples']
        overlap.setdefault(kind, {})[ov] = row['samples']
    carried = sum(v for k, v in kinds.items() if k.startswith('carried'))
    carried_overlap = sum(row['samples'] for (k, ov), row in result['classes'].items() if k.startswith('carried') and ov == 'unmodified_also_has_note')
    return dict(
        by_kind_pct={k: round(100 * v / added, 1) for k, v in sorted(kinds.items())},
        carried_in_pct=round(100 * carried / added, 1),
        born_in_gap_pct=round(100 * (added - carried) / added, 1),
        carried_with_unmodified_note_pct=round(100 * carried_overlap / max(1, carried), 1),
        overlap_by_kind_samples=overlap)


def selftest():
    # Two labels (pitch 40 at 10-20, pitch 50 at 40-50) in a 60-sample horizon; gaps are 0-10, 20-40, 50-60.
    labels = [dict(start_sample=10, end_sample=20, midi_note=40), dict(start_sample=40, end_sample=50, midi_note=50)]
    unmod = [(10, 22, 40), (40, 50, 50)]
    adapt = [(10, 28, 40),     # same-pitch tail, unmodified had it ending at 22: 6 added samples (22-28), carried in, overlap
             (30, 36, 43),     # born in the gap, adapted-only: 6 samples
             (36, 52, 50),     # born in the gap at 36 and reaching the next label start at 40 (anticipates, 4 added), then a same-pitch tail 50-52 (2 added); unmodified has 40-50 so overlap
             (45, 60, 47)]     # starts inside a label (extra voice), carried into the 50-60 gap: 10 samples, other pitch, adapted-only
    res = analyse(adapt, unmod, labels, 60, 1000)
    cls = res['classes']
    assert res['gap_voice_adapted'] == 8 + 6 + (4 + 2) + 10 and res['gap_voice_unmodified'] == 2 and res['added'] == 6 + 6 + 6 + 10, res
    assert cls[('carried_in_same_pitch_tail', 'unmodified_also_has_note')] == dict(segments=2, samples=8), cls
    assert cls[('born_in_gap_other', 'adapted_only_note')] == dict(segments=1, samples=6), cls
    assert cls[('born_in_gap_anticipates_next_label', 'unmodified_also_has_note')] == dict(segments=1, samples=4), cls
    assert cls[('carried_in_other_pitch', 'adapted_only_note')] == dict(segments=1, samples=10), cls
    assert res['tail_added_ms']['count'] == 2 and res['tail_added_ms']['median_ms'] == 6.0 and res['removed'] == 0, res
    print('selftest ok')


def shift_spans(spans, delta, horizon):
    return [(l + delta, min(r + delta, horizon), p) for l, r, p in spans if l + delta < horizon]


def offset_to_arm_a(spans_u, arm_a):
    """Median onset shift (samples) of the saved arm A relative to the unmodified event spans, pairing by (pitch, onset) order."""
    uu = sorted(spans_u, key=lambda s: (s[2], s[0]))
    aa = sorted(arm_a, key=lambda s: (s[2], s[0]))
    if len(uu) != len(aa) or any(x[2] != y[2] for x, y in zip(uu, aa)):
        return None
    deltas = sorted(y[0] - x[0] for x, y in zip(uu, aa))
    return deltas[len(deltas) // 2]


def finish(res):
    res['shares'] = shares(res)
    res['classes'] = {f'{k}|{ov}': v for (k, ov), v in sorted(res['classes'].items())}
    return res


def main():
    out = {'clock': 'available_ns', 'events_dir': 'build/github-results/basic-pitch-adaptation-events-45022134487/collected/selected'}
    for dataset in ('ordinary', 'extended-middle'):
        ctx = ad.dataset_context(dataset)
        horizon, rate, labels = ctx['horizon'], ctx['rate'], ctx['labels']
        spans = {}
        for run in ('unmodified', 'adapted'):
            events = ad.read_events(os.path.join(EVENTS, run + '_tensorflow', dataset + '-events.json'))
            spans[run], _ = ad.spans_from_events(events, horizon, 'available_ns')
        res = analyse(spans['adapted'], spans['unmodified'], labels, horizon, rate)
        check = {run: score(spans[run], labels, **ctx['clock'])['pitch_sets']['unlabeled_gap_voice_samples'] for run in spans}
        offset = offset_to_arm_a(spans['unmodified'], ctx['arm_a'])
        res['g0'] = dict(unmodified_equals_arm_a=sorted(spans['unmodified']) == sorted(ctx['arm_a']),
                         same_run_count_and_pitches=offset is not None, arm_a_later_by_samples=offset,
                         arm_a_later_by_ms=None if offset is None else round(offset * 1000 / rate, 2),
                         scorer_gap_voice=check, recomputed_gap_voice=dict(unmodified=res['gap_voice_unmodified'], adapted=res['gap_voice_adapted']))
        out[dataset] = finish(res)
        if offset:
            # POST HOC: both runs moved onto the arm A clock (the clock every earlier scoring used) by the constant offset
            aligned = analyse(shift_spans(spans['adapted'], offset, horizon), shift_spans(spans['unmodified'], offset, horizon), labels, horizon, rate)
            out[dataset]['post_hoc_aligned_to_arm_a_clock'] = finish(aligned)
        print(dataset, json.dumps({k: v for k, v in out[dataset].items() if k != 'post_hoc_aligned_to_arm_a_clock'}, indent=1))
        if offset:
            print(dataset, 'POST HOC aligned', json.dumps(out[dataset]['post_hoc_aligned_to_arm_a_clock'], indent=1))
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        selftest()
    elif len(sys.argv) != 1:
        raise SystemExit(__doc__)
    else:
        main()
