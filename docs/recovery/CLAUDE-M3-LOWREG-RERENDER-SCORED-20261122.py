"""The label-free re-render rule, scored through the real pitch-set scorer and per-label loss audit.  Saved trace and saved labels only.

No audio, model run or job.  CLAUDE-M3-LOWREG-RERENDER-HARM-20261122 counted gain and harm of the rule in voice-ticks.  Here the
same rules are applied to the saved v5 trace, the per-tick pitch sets are turned back into pitch spans (one tick = 64 samples),
and the spans go through `tools/pitch_detector_comparison.score` and `compare` against the labels, with the strict per-label
audit of the tail-clip work.  The control is the same reconstruction without the rule, so any trace-to-scorer difference
cancels; CURRENT's saved score is reported beside it as a reproduction check.

Rules, thetas and the label-free inputs are exactly those of CLAUDE-M3-LOWREG-RERENDER-HARM-20261122 (imported, not re-written).
Configs: rule A and rule B at theta 1.0, 1.5, 2, 3, 5, 10 over the whole trace, plus rule B at theta 1.5, 2 and 3 restricted to
the first half of the ticks and to the second half (split-half stability; the sweep is in-sample on one recording).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the tick-level harm table.  NOT seen: any scorer output of a rebuilt span set.  Predictions, each can fail:
  S0  the unmodified reconstruction reproduces CURRENT's saved ordinary score: coverage within 0.5 points of 39.99 and
      exact-pitch-set samples within 5% of 53,249.
  S1  rule B at theta 1.5 raises ordinary coverage by at least 1.5 points over the reconstruction.
  S2  `no_pitch_safety_regression` is FALSE for every config in the sweep.
  S3  rule B at theta 1.5 loses present samples on at least 5 labels.
  S4  rule B at theta 1.5 gains coverage in BOTH halves (each half alone adds a positive coverage change).
  S5  rule B at theta 3 raises coverage by at least 1.0 point.
Report the whole table whatever it shows.  One recording and one corpus; a sweep selected on the data it is scored on.  Pitch
occupancy at decision-tick resolution; no lane, unison, callback or live-host claim.  Nothing here selects a native rule.

Usage: python3 -P -E CLAUDE-M3-LOWREG-RERENDER-SCORED-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys

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

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-SCORED-20261122.json')
TICK = 64
THETAS = harm.THETAS
CONFIGS = [('CUR', None, 'all')] + [(r, t, 'all') for r in 'AB' for t in THETAS] + [
    ('B', t, h) for t in (1.5, 2.0, 3.0) for h in ('first', 'second')]


def name(config):
    rule, theta, half = config
    return 'CURRENT_rebuilt' if rule == 'CUR' else f'{rule}{theta:g}' + ('' if half == 'all' else f'_{half}')


class Tracker:
    def __init__(self):
        self.open, self.spans, self.prev = {}, [], None

    def step(self, sample, pitches):
        contiguous = self.prev is not None and sample - self.prev == TICK
        for pitch in list(self.open):
            start, last = self.open[pitch]
            if pitch in pitches and contiguous:
                self.open[pitch] = (start, sample)
            else:
                self.spans.append((start, last + TICK, pitch))
                del self.open[pitch]
        for pitch in pitches:
            if pitch not in self.open:
                self.open[pitch] = (sample, sample)
        self.prev = sample

    def finish(self):
        for pitch, (start, last) in self.open.items():
            self.spans.append((start, last + TICK, pitch))
        self.open = {}
        return self.spans


def run(path):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    base = baseline['datasets']['ordinary']
    horizon = report['datasets']['ordinary']['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    saved = split.compact(score(clip_spans(base['pitch_spans'], horizon), labels, **clock))
    trackers = {name(c): Tracker() for c in CONFIGS}
    total_ticks = 167026
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for index, line in enumerate(stream):
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            voices = frame['voices']
            rendered = {v[1] for v in voices}
            emitted = {v[0] for v in voices}
            cands = _candidates(frame)
            decisions = []          # (n, q*, ratio, own_direct) per lower voice with a replacement candidate
            for voice in voices:
                n = voice[1]
                if n >= split.SPLIT:
                    continue
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0:
                    continue
                best = None
                for q, row in cands.items():
                    if q == n or q in rendered:
                        continue
                    if rel_class(n - q) is None or not logged_without_labels(row, emitted):
                        continue
                    if best is None or row['fund_ratio'] > best[0]:
                        best = (row['fund_ratio'], q)
                if best is not None:
                    decisions.append((n, best[1], best[0] / max(own['fund_ratio'], 1e-6), own['direct']))
            half = 'first' if index < total_ticks // 2 else 'second'
            for config in CONFIGS:
                rule, theta, which = config
                pitches = set(rendered)
                if rule != 'CUR' and which in ('all', half):
                    for n, q, ratio, own_direct in decisions:
                        if ratio >= theta and (rule == 'A' or own_direct == 0):
                            pitches.discard(n)
                            pitches.add(q)
                trackers[name(config)].step(frame['sample'], pitches)
    results = {}
    reference = None
    for config in CONFIGS:
        key = name(config)
        spans = clip_spans(trackers[key].finish(), horizon)
        scored = score(spans, labels, **clock)
        if reference is None:
            reference = scored
        cur = split.compact(reference)
        row = split.compact(scored)
        entry = dict(score=row)
        if key != 'CURRENT_rebuilt':
            cmp = compare(reference, scored)
            summary = audit.summarize(audit.loss_rows(reference, scored))
            entry.update(coverage_gain_points=round(row['coverage_percent'] - cur['coverage_percent'], 3),
                         exact_set_ratio=round(row['exact_pitch_set'] / cur['exact_pitch_set'], 3) if cur['exact_pitch_set'] else None,
                         wrong_pitch_delta=row['wrong_pitch'] - cur['wrong_pitch'], gap_delta=row['gap'] - cur['gap'],
                         strict_gate=bool(cmp['no_pitch_safety_regression']), audit=summary)
        results[key] = entry
    out = dict(saved_current=saved, reproduction=dict(
        coverage_points_off=round(results['CURRENT_rebuilt']['score']['coverage_percent'] - saved['coverage_percent'], 3),
        exact_set_ratio=round(results['CURRENT_rebuilt']['score']['exact_pitch_set'] / saved['exact_pitch_set'], 3)
        if saved['exact_pitch_set'] else None), configs=results)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1)[:200])
