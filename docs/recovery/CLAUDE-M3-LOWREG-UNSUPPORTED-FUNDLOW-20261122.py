"""Second tick-level bound: release a lower-band voice after T ms of selected, no-direct-peak AND low-fundamental-share ticks.  Saved trace only.

No audio, model run or job.  This is a conjunction of the rule in CLAUDE-M3-LOWREG-UNSUPPORTED-RUN-20261122 with the
fund_ratio < 0.2 flag from CLAUDE-M3-LOWREG-TAIL-STATE-20261122, and it was chosen AFTER the first bound was run:
that run lost exactly one label (index 150, MIDI 43, 494 of 736 ms at T = 200 ms) whose voice has direct == 0 on
97% of its ticks but a fundamental share mostly 0.3 to 0.7.  So this rule is shaped by one label of this recording;
it is in-sample for that label and its result on this corpus is NOT evidence that it generalizes.  Every suppressed
set here is a subset of the first rule's, so its true-tick loss can only be smaller; what the run measures is how much
tail is left.  The saved trace is ordinary / CURRENT ON only (no extended-middle trace was saved), so the only
held-out check is a future native job.

Rule R2(T): a lower-band voice is suppressed while it has had at least T consecutive decision ticks that are selected
with direct == 0 and fund_ratio < 0.2; it returns when any of the three stops holding or the voice disappears.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the tail-state result, the first bound, and the state of label 150 (sampled every 46th tick).  NOT seen:
any R2 count.  Same grid, 50, 100, 200, 400 ms.  Predictions, each can fail:
  V1  at T = 200 ms, R2 suppresses at least 5% of the lower-band tail ticks (the first rule: 10.6%).
  V2  at T = 200 ms and at 400 ms, no label loses more than 100 ms of true ticks.
  V3  at every T with any true loss, suppressed (tail + other) ticks per suppressed true tick are at least 100.
  V4  at T = 100 ms, R2 suppresses at least 8% of the lower-band tail ticks.
Pitch occupancy at decision-tick resolution; no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-UNSUPPORTED-FUNDLOW-20261122.py TRACE.tsv.gz
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

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-UNSUPPORTED-FUNDLOW-20261122.json')
TICK_MS = tailstate.TICK_MS
TAIL_TICKS = tailstate.TAIL_TICKS
GRID_MS = (50, 100, 200, 400)
GRID = {ms: int(round(ms / TICK_MS)) for ms in GRID_MS}


def run(path):
    last_label = {}
    run_len = {ms: defaultdict(int) for ms in GRID_MS}
    sup = {ms: Counter() for ms in GRID_MS}
    lost = {ms: Counter() for ms in GRID_MS}
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
            for ms in GRID_MS:                      # a voice that vanished loses its run
                for note in [n for n in run_len[ms] if n not in present]:
                    run_len[ms][note] = 0
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
                unsupported = (cand is not None and cand['selection'] != 0 and cand['direct'] == 0
                               and cand['fund_ratio'] < 0.2)
                for ms in GRID_MS:
                    run_len[ms][note] = run_len[ms][note] + 1 if unsupported else 0
                    if run_len[ms][note] >= GRID[ms]:
                        sup[ms][kind] += 1
                        if kind == 'true':
                            lost[ms][active[note]] += 1
    curve = {}
    for ms in GRID_MS:
        s = sup[ms]
        removed = s['tail'] + s['other']
        lost_labels = lost[ms]
        over100 = sum(1 for v in lost_labels.values() if v * TICK_MS > 100)
        top = sorted(lost_labels.items(), key=lambda kv: -kv[1])[:6]
        curve[str(ms)] = dict(
            tail_suppressed_ticks=s['tail'], tail_suppressed_share=round(s['tail'] / base['tail'], 3),
            other_suppressed_ticks=s['other'], true_suppressed_ticks=s['true'],
            true_suppressed_ms=round(s['true'] * TICK_MS, 1),
            removed_per_true_lost=None if not s['true'] else round(removed / s['true'], 2),
            labels_with_loss=len(lost_labels), labels_losing_over_100ms=over100,
            worst_labels=[dict(label_index=i, midi=label_note[i], lost_ms=round(v * TICK_MS, 1),
                               label_ms_with_voice=round(label_ticks[i] * TICK_MS, 1)) for i, v in top])
    out = dict(base_ticks=dict(base), labels_with_a_lower_voice=len(label_ticks), curve=curve)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    return out


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=1))
