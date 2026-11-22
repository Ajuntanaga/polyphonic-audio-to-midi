"""One candidate from the measured failure: clip CURRENT's lower-band overhang with A's note-off.

PRE-REGISTRATION, written 2026-11-21 ~00:20 PST (day 11-22 UTC) BEFORE this script was run.
Seen already: the frozen split report and the anatomy result (CLAUDE-M3-SPLIT-FALSE-OUTPUT-ANATOMY):
CURRENT's lower band emits 11,067,777 false samples of which 6,425,872 (58.1%) are overhang past the
last overlapping same-pitch label end (194 spans, mean 345 ms, median 295 ms, p10 171 ms); A's lower
band overhang is mean 126 ms.  Not seen: any score of the rule below.

Rule (frozen, parameter-free, label-free, causal):
  H_T = for MIDI >= 60: A's spans, unchanged (the same upper band as the frozen split);
        for MIDI <  60: each CURRENT span (l, r, p).  If some A span of the same pitch overlaps it,
        end it at the LATEST end of those overlapping A spans when that end is earlier than r (A's own
        note-off, on A's measured FIFO completion clock, so it is available no sooner than that time).
        If no A span of that pitch overlaps it, leave it untouched (A never confirmed it; no basis to
        clip).  A span is never lengthened and never started earlier or later.
  No threshold, no timing shift, no per-label choice, no sweep.  Same score()/compare() as the split.

Expectations declared in advance, each can fail:
  T1  Lower-band false output (extra+gap) falls below CURRENT's 11,067,777, enough that ordinary
      wrong+gap for H_T total is BELOW CURRENT's 11,429,794 (the false-growth gate the split failed).
      I put this at roughly 60%: A's overlapping note-off is much earlier than CURRENT's on average,
      but only 42% of CURRENT's lower spans have an A overlap I have not yet counted.
  T2  Some lower labels LOSE present samples (strict per-label gate fails), because A ends notes
      early where CURRENT held on.  I put this at 80%.
  T3  Extended-middle: no lower label loses, and wrong+gap do not rise above the split's 623,474.
  T4  Upper band is identical to the split's (by construction).
The result is reported as measured.  If T1 holds and T2 fails, that is a safety-positive, label-
positive saved-span result with the usual caveats; if T1 fails the rule is dead and I will not tune it.

Nothing here is promoted, installed or a release candidate.  Pitch occupancy does not establish lane
assignment, unison multiplicity, callback deadlines or live-host delivery.

Usage: python3 -I CLAUDE-M3-TAIL-CLIP-CANDIDATE-20261121.py EVIDENCE_DIR
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('split', os.path.join(HERE, 'CLAUDE-M3-PITCH-SPLIT-20261121.py'))
split = importlib.util.module_from_spec(spec)
spec.loader.exec_module(split)
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-CANDIDATE-20261121.json')


def clip_lower(current_spans, a_spans):
    by_pitch = defaultdict(list)
    for left, right, note in a_spans:
        by_pitch[note].append((left, right))
    out, counts = [], dict(lower_spans=0, with_A_overlap=0, clipped=0, clipped_samples=0)
    for left, right, note in current_spans:
        if note >= split.SPLIT:
            continue
        counts['lower_spans'] += 1
        overlapping = [end for start, end in by_pitch.get(note, []) if start < right and end > left]
        end = right
        if overlapping:
            counts['with_A_overlap'] += 1
            if max(overlapping) < right:
                end = max(overlapping)
                counts['clipped'] += 1
                counts['clipped_samples'] += right - end
        out.append((left, end, note))
    return out, counts


def run(evidence_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    frozen = json.load(open(os.path.join(HERE, '..', '..', 'build/github-results/basic-pitch-cached-44891340815/'
                                         'claude-pitch-split/report.json')))
    result = dict(schema='claude_m3_tail_clip_v1', datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
        labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
        current_spans = clip_spans(base['pitch_spans'], horizon)
        path = os.path.join(evidence_dir, name + '-bridge-events.json.gz')
        if os.path.getsize(path) != data['evidence']['bytes'] or split.sha(path) != data['evidence']['sha256']:
            raise ValueError(name + ': evidence differs from pin')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            a_spans = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
        current = score(current_spans, labels, **clock)
        arm_a = score(a_spans, labels, **clock)
        if split.compact(current) != frozen['datasets'][name]['compact']['CURRENT'] \
                or split.compact(arm_a) != frozen['datasets'][name]['compact']['A']:
            raise ValueError(name + ': CURRENT or A does not reproduce the frozen split report')
        lower, counts = clip_lower(current_spans, a_spans)
        split_spans = [s for s in current_spans if s[2] < split.SPLIT] + [s for s in a_spans if s[2] >= split.SPLIT]
        h_split = score(split_spans, labels, **clock)
        h_tail = score(lower + [s for s in a_spans if s[2] >= split.SPLIT], labels, **clock)
        if split.compact(h_split) != frozen['datasets'][name]['compact']['H_A']:
            raise ValueError(name + ': split hybrid does not reproduce the frozen report')
        decomp = split.decompose(lower + [s for s in a_spans if s[2] >= split.SPLIT], labels, horizon)
        split.check_decomposition(decomp, h_tail, name + ' H_T')
        cmp_cur = compare(current, h_tail)
        result['datasets'][name] = dict(
            horizon=horizon, clip_counts=counts,
            compact={'CURRENT': split.compact(current), 'H_split': split.compact(h_split),
                     'H_T': split.compact(h_tail)},
            bands=decomp['bands'],
            hybrid_tail_vs_current={k: v for k, v in cmp_cur.items() if k not in ('label_deltas', 'label_changes')},
            labels=split.label_summary(current, arm_a, h_tail),
            false_total=dict(CURRENT=split.compact(current)['wrong_pitch'] + split.compact(current)['gap'],
                             H_split=split.compact(h_split)['wrong_pitch'] + split.compact(h_split)['gap'],
                             H_T=split.compact(h_tail)['wrong_pitch'] + split.compact(h_tail)['gap']))
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    for name, row in out['datasets'].items():
        print('==', name, 'horizon', row['horizon'], row['clip_counts'])
        for key, value in row['compact'].items():
            print('  %-8s' % key, value)
        print('  false total (wrong+gap):', row['false_total'])
        lower = row['labels']['lower_lt60']
        print('  lower labels vs CURRENT:', lower['hybrid_vs_current'], '| present', lower['present'])
        print('  upper labels vs CURRENT:', row['labels']['upper_ge60']['hybrid_vs_current'])
        print('  no_pitch_safety_regression:', row['hybrid_tail_vs_current']['no_pitch_safety_regression'],
              '| exact-set delta', row['hybrid_tail_vs_current']['sample_deltas']['exact_pitch_set_samples'])
