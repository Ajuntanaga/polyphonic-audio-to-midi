"""Held-out check of the frozen low-register re-render gates on a corpus they were not chosen on.  Saved trace and saved spans only.

No audio, model run or job.  The rule B(1.5) and the six gates below were fixed on the ORDINARY corpus by
CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122 and CLAUDE-M3-LOWREG-RERENDER-LOSERS-20261122 (the three `o_band_score` gates and the
`o_release` gate are the ones that note rescored; the 0.108358 gate was picked post hoc from its screen).  This script applies exactly
those gates, with exactly those thresholds, to another corpus' v5 trace and scores each by editing CURRENT's saved pitch spans
(`tools/pitch_detector_comparison.score`, the same exact-output plumbing and the same optimistic immediate-replacement assumption).
Nothing is refit: no threshold, gate or rule is changed for the corpus under test.  Labels classify fires after the fact only.

Registered in CLAUDE-M3-LOWREG-HELDOUT-PREREGISTRATION-20261122.md (committed before the extended-middle trace was opened).
Run on `ordinary` first as a regression test of this script: it must reproduce the ordinary pool (16,822 fires) and the gate
fire counts of the losers note (11,847 / 7,809 / 5,047 / 3,365 / 1,683).

Usage: python3 -P -E CLAUDE-M3-LOWREG-HELDOUT-20261122.py DATASET TRACE.tsv.gz OUT.json
       DATASET is `ordinary` or `extended-middle`.
"""
import bisect
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('losers', os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-LOSERS-20261122.py'))
losers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(losers)
em, split, audit = losers.em, losers.split, losers.audit
TICK, SR = em.TICK, split.SAMPLE_RATE

# Frozen on the ordinary corpus; thresholds are the unrounded quantile values printed by the losers note's gate strings.
GATES = [
    ('B1.5 ungated', lambda d: True),
    ('o_release >= 12', lambda d: d['o_release'] >= 12),
    ('exclude rel=octave', lambda d: d['rel'] != 'octave'),
    ('o_band_score <= 0.174142', lambda d: d['o_band_score'] <= 0.174142),
    ('o_band_score <= 0.108358', lambda d: d['o_band_score'] <= 0.108358),
    ('o_band_score <= 0.0615331', lambda d: d['o_band_score'] <= 0.0615331),
]
ORDINARY_SAVED = dict(present=13525345, exact_pitch_set=53249, wrong_pitch=7808309, gap=3621485)


def run(dataset, path, out):
    report = json.load(open(split.REPORT))
    base = json.load(open(split.BASELINE))['datasets'][dataset]
    horizon = report['datasets'][dataset]['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=SR)
    labels, _ = em.clip_labels(em.labels_from_measurement(base['measurement']), horizon)
    base_spans = em.clip_spans(base['pitch_spans'], horizon)
    reference = em.score(base_spans, labels, **clock)
    saved = split.compact(reference)

    occ = defaultdict(list)
    for left, right, pitch in base_spans:
        occ[pitch].append((left, right))
    for pitch in occ:
        occ[pitch].sort()

    def occupied(pitch, sample):
        iv = occ.get(pitch)
        if not iv:
            return False
        i = bisect.bisect_right(iv, (sample, 10 ** 12)) - 1
        return i >= 0 and iv[i][0] <= sample < iv[i][1]

    by_pitch = defaultdict(list)
    for r in labels:
        by_pitch[r['midi_note']].append((r['start_sample'], r['end_sample'], r['label_index']))

    def find_label(pitch, sample):
        for left, right, idx in by_pitch.get(pitch, ()):
            if left <= sample < right:
                return idx
        return None

    info = {r['label_index']: r for r in labels}

    def evaluate(fires):
        removals, additions = defaultdict(list), defaultdict(list)
        for d in fires:
            start = d['sample'] - (TICK - 1)
            removals[d['n']].append((start, start + TICK))
            additions[d['q']].append((start, start + TICK))
        spans = em.clip_spans(em.edit(base_spans, removals, additions), horizon)
        scored = em.score(spans, labels, **clock)
        row = split.compact(scored)
        cmp = em.compare(reference, scored)
        lost = [r for r in cmp['label_changes'] if min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0]
        return dict(
            fires=len(fires), coverage_percent=row['coverage_percent'],
            coverage_gain_points=round(row['coverage_percent'] - saved['coverage_percent'], 3),
            exact_pitch_set=row['exact_pitch_set'], exact_set_ratio=round(row['exact_pitch_set'] / max(1, saved['exact_pitch_set']), 3),
            wrong_pitch_delta=row['wrong_pitch'] - saved['wrong_pitch'], gap_delta=row['gap'] - saved['gap'],
            strict_gate=bool(cmp['no_pitch_safety_regression']), labels_losing=len(lost),
            lost_labels=[dict(label_index=r['label_index'], midi=r['midi_note'],
                              present_delta_ms=round(r['present_samples_delta'] * 1000 / SR, 2),
                              longest_delta_ms=round(r['longest_present_samples_delta'] * 1000 / SR, 2)) for r in lost],
            audit=audit.summarize(audit.loss_rows(reference, scored)))

    # M0: an edit with no removals and no additions must reproduce the unedited score exactly.
    rebuilt = split.compact(em.score(em.clip_spans(em.edit(base_spans, {}, {}), horizon), labels, **clock))
    m0 = dict(rebuilt_equals_saved=rebuilt == saved, saved=saved)
    if dataset == 'ordinary':
        m0['matches_registered_ordinary_constants'] = all(saved[k] == v for k, v in ORDINARY_SAVED.items())

    decisions = losers.collect(path, occupied, find_label)
    pool = [d for d in decisions if d['ratio'] >= 1.5]
    agree = sum((d['n_label'] is not None) == d['n_active_frame'] for d in pool)

    def klass(d):
        a, b = d['n_label'] is not None, d['q_label'] is not None
        return 'harm' if a and not b else 'swap' if a and b else 'good' if b else 'null'

    results = []
    for name, keep in GATES:
        fires = [d for d in pool if keep(d)]
        ev = evaluate(fires)
        ev['gate'] = name
        ev['classes'] = dict(Counter(klass(d) for d in fires))
        ev['removal_fires_by_label'] = dict(sorted(Counter(d['n_label'] for d in fires if d['n_label'] is not None).items()))
        ev['addition_fires_by_label'] = dict(sorted(Counter(d['q_label'] for d in fires if d['q_label'] is not None).items()))
        ev['relation_classes'] = dict(Counter(d['rel'] for d in fires))
        results.append(ev)
    result = dict(
        dataset=dataset, trace=os.path.basename(path), m0=m0, saved_current=saved, labels=len(labels),
        label_pitches={str(r['label_index']): r['midi_note'] for r in labels}, decisions_total=len(decisions),
        pool_b15=len(pool), p0_label_lookup_agreement=round(agree / max(1, len(pool)), 5),
        pool_relation_classes=dict(Counter(d['rel'] for d in pool)),
        pool_voice_kinds=dict(Counter(d['kind'] for d in pool)), gates=results)
    with open(out, 'w') as stream:
        json.dump(result, stream, indent=1, default=str)
    return result


if __name__ == '__main__':
    r = run(sys.argv[1], sys.argv[2], sys.argv[3])
    print(json.dumps(dict(dataset=r['dataset'], m0=r['m0']['rebuilt_equals_saved'], pool=r['pool_b15'],
                          agree=r['p0_label_lookup_agreement'], saved=r['saved_current']), indent=1))
    for g in r['gates']:
        print(f"{g['gate']:28s} fires {g['fires']:6d}  cov {g['coverage_gain_points']:+7.3f}  exact x{g['exact_set_ratio']:<6}"
              f"  wrong {g['wrong_pitch_delta']:>9d}  gap {g['gap_delta']:>6d}  labels losing {g['labels_losing']:3d}  strict {g['strict_gate']}")
