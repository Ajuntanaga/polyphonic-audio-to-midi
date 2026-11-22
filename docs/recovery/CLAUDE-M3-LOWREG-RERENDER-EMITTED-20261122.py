"""The label-free re-render rule applied only to EMITTED voices, scored by editing CURRENT's exact saved spans.  Saved trace and saved spans only.

No audio, model run or job.  The first scored run (CLAUDE-M3-LOWREG-RERENDER-SCORED-20261122) rebuilt spans from every voice in the
v5 trace and failed its own reproduction check: the unmodified rebuild scored 44.98% coverage against CURRENT's saved 39.99%.  The
cause, found afterwards, is that the trace's `voices` field is the detector's rendered voice list, which includes voices that have
not reached MIDI: of 452,094 lower (rendered note below 60) voice-ticks, 70,916 are not occupied in CURRENT's saved pitch spans,
and 62,562 of those have age 0 (a single-tick flicker); voices of age 16 or more are occupied 99%.  A rule that "replaces" a
non-emitted voice removes nothing CURRENT outputs and adds a pitch, and the earlier control counted that voice as false output.

Here the control is CURRENT's own saved pitch-occupancy spans (exact).  A rule fires on a lower voice-tick only if that voice's
rendered pitch is occupied in those spans at the tick's sample (the voice is actually being output).  A fired tick removes the
pitch over that tick's 64 samples (sample-63 to sample, inclusive) and adds q* over the same samples; the edited per-pitch
intervals are unioned and scored by `tools/pitch_detector_comparison.score` with the per-label loss audit.  The replacement is
assumed to be emitted at once: no onset-confirmation delay, hold or minimum duration is modelled, so this is an optimistic bound
on what a native implementation could deliver, not a prediction of one.

Rule A(theta) and rule B(theta), the label-free inputs (the writer's inclusion filter, `fund_ratio`, `direct`) and the sweep are
those of CLAUDE-M3-LOWREG-RERENDER-HARM-20261122.  Configs: A and B at theta 1, 1.5, 2, 3, 5, 10; B at 1.5, 2, 3 restricted to the
first half and to the second half of the ticks.  The sweep is in-sample on one recording.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the first scored table (trace-voice rebuild; B1.5 +2.478 points, strict gate false everywhere) and the
emitted-or-not tally by age.  NOT seen: any score of an edited saved-span set, nor how the ghost class splits by emission.
Predictions, each can fail:
  M0  an edit with no removals and no additions reproduces CURRENT's saved score exactly (13,525,345 present, 53,249
      exact-set, 7,808,309 wrong, 3,621,485 gap), so the interval-edit plumbing is lossless.
  M1  rule B at theta 1.5 now has a coverage gain that is positive but smaller than the first run's +2.478 points.
  M2  rule B at theta 1.5 still gains at least 1.0 point.
  M3  `no_pitch_safety_regression` is false for every config.
  M4  rule B at theta 1.5 gains coverage in both halves.
  M5  at least 40% of the ghost class (lower voice-ticks with no same-pitch label now or within 1.5 s; 92,957 in the earlier
      notes) is NOT occupied in CURRENT's saved spans.
Report the whole table whatever it shows.  One recording and one corpus; pitch occupancy at decision-tick resolution; no lane,
unison, callback or live-host claim.  Nothing here selects a native rule, and a coverage gain from an optimistic edit of saved
output is not the strict gate and not a native result.

Usage: python3 -P -E CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('harm', os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-HARM-20261122.py'))
harm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harm)
spec = importlib.util.spec_from_file_location('oracle', os.path.join(HERE, 'CLAUDE-M3-LOWREG-ORACLE-SUBSTITUTION-20261122.py'))
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
audit, split = oracle.audit, oracle.split
elig, rel_class = harm.elig, harm.rel_class
logged_without_labels = elig.logged_without_labels
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122.json')
TICK = 64
TAIL_TICKS = harm.TAIL_TICKS
THETAS = harm.THETAS
CONFIGS = [(r, t, 'all') for r in 'AB' for t in THETAS] + [(('B'), t, h) for t in (1.5, 2.0, 3.0) for h in ('first', 'second')]


def name(config):
    rule, theta, half = config
    return f'{rule}{theta:g}' + ('' if half == 'all' else f'_{half}')


def merge(intervals):
    out = []
    for left, right in sorted(intervals):
        if out and left <= out[-1][1]:
            out[-1][1] = max(out[-1][1], right)
        else:
            out.append([left, right])
    return out


def subtract(base, cut):
    """base, cut: merged sorted [l, r] lists; returns base minus cut."""
    out, j = [], 0
    for left, right in base:
        cur = left
        while j < len(cut) and cut[j][1] <= cur:
            j += 1
        k = j
        while k < len(cut) and cut[k][0] < right:
            if cut[k][0] > cur:
                out.append([cur, cut[k][0]])
            cur = max(cur, cut[k][1])
            k += 1
        if cur < right:
            out.append([cur, right])
    return out


def edit(base_spans, removals, additions):
    by = defaultdict(list)
    for left, right, pitch in base_spans:
        by[pitch].append([left, right])
    spans = []
    for pitch in sorted(set(by) | set(additions)):
        merged = merge(by.get(pitch, []))
        merged = subtract(merged, merge(removals.get(pitch, [])))
        merged = merge([tuple(i) for i in merged] + [tuple(i) for i in additions.get(pitch, [])])
        spans.extend((left, right, pitch) for left, right in merged)
    return spans


def run(path):
    report = json.load(open(split.REPORT))
    base = json.load(open(split.BASELINE))['datasets']['ordinary']
    horizon = report['datasets']['ordinary']['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    base_spans = clip_spans(base['pitch_spans'], horizon)
    saved = split.compact(score(base_spans, labels, **clock))
    reference = score(base_spans, labels, **clock)
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

    last_label = {}
    kinds = Counter()             # (kind, emitted) over lower voice-ticks with a non-quiet candidate
    removals = {name(c): defaultdict(list) for c in CONFIGS}
    additions = {name(c): defaultdict(list) for c in CONFIGS}
    fired = Counter()
    total_ticks = 167026
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for index, line in enumerate(stream):
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick, sample = frame['tick'], frame['sample']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            voices = frame['voices']
            lows = [v for v in voices if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = _candidates(frame)
            rendered = {v[1] for v in voices}
            emitted_notes = {v[0] for v in voices}
            half = 'first' if index < total_ticks // 2 else 'second'
            decisions = []
            for voice in lows:
                n = voice[1]
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0:
                    continue
                if n in active:
                    kind = 'true'
                elif tick - last_label.get(n, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    kind = 'ghost'
                is_out = occupied(n, sample)
                kinds[(kind, is_out)] += 1
                if not is_out:
                    continue
                best = None
                for q, row in cands.items():
                    if q == n or q in rendered:
                        continue
                    if rel_class(n - q) is None or not logged_without_labels(row, emitted_notes):
                        continue
                    if best is None or row['fund_ratio'] > best[0]:
                        best = (row['fund_ratio'], q)
                if best is not None:
                    decisions.append((n, best[1], best[0] / max(own['fund_ratio'], 1e-6), own['direct']))
            if not decisions:
                continue
            start = sample - (TICK - 1)
            for config in CONFIGS:
                rule, theta, which = config
                if which not in ('all', half):
                    continue
                key = name(config)
                for n, q, ratio, own_direct in decisions:
                    if ratio >= theta and (rule == 'A' or own_direct == 0):
                        removals[key][n].append((start, start + TICK))
                        additions[key][q].append((start, start + TICK))
                        fired[key] += 1
    results = {}
    for config in CONFIGS:
        key = name(config)
        spans = clip_spans(edit(base_spans, removals[key], additions[key]), horizon)
        scored = score(spans, labels, **clock)
        row = split.compact(scored)
        cmp = compare(reference, scored)
        results[key] = dict(
            fired_voice_ticks=fired[key], score=row,
            coverage_gain_points=round(row['coverage_percent'] - saved['coverage_percent'], 3),
            exact_set_ratio=round(row['exact_pitch_set'] / saved['exact_pitch_set'], 3),
            wrong_pitch_delta=row['wrong_pitch'] - saved['wrong_pitch'], gap_delta=row['gap'] - saved['gap'],
            strict_gate=bool(cmp['no_pitch_safety_regression']), audit=audit.summarize(audit.loss_rows(reference, scored)),
            gate_clauses=dict(
                extra_pitch_voice_delta=cmp['sample_deltas']['extra_pitch_voice_samples'],
                gap_delta=cmp['extra_gap_pitch_samples_delta'],
                exact_set_delta=cmp['sample_deltas']['exact_pitch_set_samples'],
                all_expected_delta=cmp['sample_deltas']['all_expected_pitches_samples'],
                labels_changed=len(cmp['label_changes']),
                labels_losing_present_or_longest=sum(
                    min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0 for r in cmp['label_changes']),
                lost_labels_by_band={k: v['lost_labels'] for k, v in cmp['label_bands'].items()}))
    ghost_total = kinds[('ghost', True)] + kinds[('ghost', False)]
    out = dict(saved_current=saved,
               lower_voice_ticks_by_kind_and_emission={f'{k}_{"emitted" if e else "not_emitted"}': kinds[(k, e)]
                                                       for k in ('true', 'tail', 'ghost') for e in (True, False)},
               ghost_not_emitted_share=round(kinds[('ghost', False)] / ghost_total, 3) if ghost_total else None,
               configs=results)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1)[:300])
