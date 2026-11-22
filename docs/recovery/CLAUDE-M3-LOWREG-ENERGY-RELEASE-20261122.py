"""Tick-level bound: release a lower-band voice once its fundamental energy has stayed below a fraction of its own peak.  Saved trace only.

No audio, model run or job.  Follows CLAUDE-M3-LOWREG-ENERGY-DECAY-20261122, which found that
R = fund_energy / (running maximum of fund_energy since the voice appeared) separates tail from true ticks much better
than I predicted: R < 0.1 flags 41% of selected tail ticks and 2.5% of selected true ticks (22% vs 1.5% where a direct
fundamental peak exists, the part the unsupported-run rule cannot reach).  Here the question is the one that matters for
the strict gate: per label, how much true output would a release rule on R destroy, and how much tail does it remove?

Rule E(thr, T): a lower-band voice (rendered note below 60) is suppressed once it has had at least T consecutive decision
ticks with energy_observed == 1 and R < thr, whether or not the candidate is selected; it returns when R >= thr, or
the energy is not observed, or the voice disappears.  The running peak resets only when the voice is absent for a tick
(no re-onset reset: a re-plucked voice that stays present keeps its old peak, which can only make this rule release
earlier, so true loss here is an upper bound on that account).
Grid, fixed and reported whole: thr in 0.05, 0.1, 0.25 and T in 1 tick (about 0.7 ms), 50 ms, 100 ms.
Also, for comparison and as the one union reported: R1(50 ms) = selected with direct == 0 for 50 ms (the unsupported
rule), and U = R1(50 ms) OR E(0.1, 50 ms).  The union is descriptive, not a chosen rule.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the energy-decay grid (selected-tick flag rates) and the earlier bounds.  NOT seen: any suppression
count, per-label loss or union count.  Predictions, each can fail:
  X1  E(0.1, 50 ms) suppresses at least 20% of the lower-band tail ticks.
  X2  E(0.1, 50 ms) loses true ticks on at least 1 label (the strict per-label gate fails), but fewer labels than
      R1(50 ms) (8 in the earlier bound).
  X3  E(0.05, 100 ms) loses true ticks on at most 5 labels.
  X4  at every grid point with any true loss, (tail + other) suppressed ticks per suppressed true tick are at least 10.
  X5  the union U suppresses at least 5 percentage points more of the tail ticks than the larger of R1(50 ms) and
      E(0.1, 50 ms) alone.
Report the grid whatever it shows.  One recording; nothing here selects a threshold.  Pitch occupancy at decision-tick
resolution; no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('tailstate', os.path.join(HERE, 'CLAUDE-M3-LOWREG-TAIL-STATE-20261122.py'))
tailstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tailstate)
split = tailstate.split
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122.json')
TICK_MS = tailstate.TICK_MS
TAIL_TICKS = tailstate.TAIL_TICKS
THRS = (0.05, 0.1, 0.25)
TICKS = {'1t': 1, '50ms': int(round(50 / TICK_MS)), '100ms': int(round(100 / TICK_MS))}
RULES = [('E', thr, tn) for thr in THRS for tn in TICKS] + [('R1', None, '50ms'), ('U', 0.1, '50ms')]


def name(rule):
    kind, thr, tn = rule
    return '%s(%s,%s)' % (kind, thr, tn) if thr is not None else '%s(%s)' % (kind, tn)


def run(path):
    last_label = {}
    peak = {}
    run_e = {}        # (thr, tn-free) per note: consecutive ticks with R < thr, one counter per thr
    run_r1 = defaultdict(int)
    state = {}
    sup = {name(r): Counter() for r in RULES}
    lost = {name(r): Counter() for r in RULES}
    label_ticks = Counter()
    label_note = {}
    base = Counter()
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick = frame['tick']
            active = {}
            for idx, note, _mask in frame['labels']:
                active.setdefault(note, idx)
                last_label[note] = tick
                label_note[idx] = note
            lows = [v for v in frame['voices'] if v[1] < split.SPLIT]
            present = {v[1] for v in lows}
            for note in [n for n in list(peak) if n not in present]:
                del peak[note]
            for note in [n for n in list(state) if n not in present]:
                del state[note]
                run_r1.pop(note, None)
            if not lows:
                continue
            cands = _candidates(frame)
            for voice in lows:
                note = voice[1]
                if note in active:
                    kind = 'true'
                    label_ticks[active[note]] += 1
                elif tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    kind = 'other'
                base[kind] += 1
                cand = cands.get(voice[0])
                runs = state.setdefault(note, {thr: 0 for thr in THRS})
                if cand is not None and cand.get('energy_observed') == 1:
                    energy = cand['fund_energy']
                    peak[note] = max(peak.get(note, 0.0), energy)
                    ratio = energy / peak[note] if peak[note] > 0 else 1.0
                    for thr in THRS:
                        runs[thr] = runs[thr] + 1 if ratio < thr else 0
                else:
                    for thr in THRS:
                        runs[thr] = 0
                unsupported = cand is not None and cand['selection'] != 0 and cand['direct'] == 0
                run_r1[note] = run_r1[note] + 1 if unsupported else 0
                for rule in RULES:
                    kindr, thr, tn = rule
                    need = TICKS[tn]
                    if kindr == 'E':
                        hit = runs[thr] >= need
                    elif kindr == 'R1':
                        hit = run_r1[note] >= need
                    else:
                        hit = runs[thr] >= need or run_r1[note] >= need
                    if hit:
                        key = name(rule)
                        sup[key][kind] += 1
                        if kind == 'true':
                            lost[key][active[note]] += 1
    grid = {}
    for rule in RULES:
        key = name(rule)
        s = sup[key]
        removed = s['tail'] + s['other']
        lost_labels = lost[key]
        top = sorted(lost_labels.items(), key=lambda kv: -kv[1])[:5]
        grid[key] = dict(
            tail_suppressed_ticks=s['tail'], tail_suppressed_share=round(s['tail'] / base['tail'], 3),
            other_suppressed_ticks=s['other'], approx_false_samples_removed=(s['tail'] + s['other']) * 64,
            true_suppressed_ticks=s['true'], true_suppressed_ms=round(s['true'] * TICK_MS, 1),
            removed_per_true_lost=None if not s['true'] else round(removed / s['true'], 1),
            labels_with_loss=len(lost_labels),
            labels_losing_over_100ms=sum(1 for v in lost_labels.values() if v * TICK_MS > 100),
            worst_labels=[dict(label_index=i, midi=label_note[i], lost_ms=round(v * TICK_MS, 1),
                               label_ms_with_voice=round(label_ticks[i] * TICK_MS, 1)) for i, v in top])
    out = dict(base_ticks=dict(base), grid=grid)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
