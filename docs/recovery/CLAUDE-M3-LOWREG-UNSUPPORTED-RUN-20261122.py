"""Tick-level bound: release a lower-band voice after T ms of selected-without-direct-fundamental ticks.  Saved trace only.

No audio, model run or job.  Follows CLAUDE-M3-LOWREG-TAIL-STATE-20261122, which found that 81% of lower-band tail
ticks are SELECTED ticks (re-selection keeps the voice alive), and that direct == 0 (no direct fundamental peak)
holds on 63% of selected tail ticks against 8.8% of selected true ticks, the only single flag to pass the S4 bar
(that prediction failed: I expected none to).  Codex's rejected sustain-renewal trials used a related but different
rule on the installed tracker (support = direct peak OR candidate evidence, release grace restart); this script asks
the tick-level question directly and can only bound, not predict, a native result: a real release changes later
detector state, which a replay on a trace cannot reproduce.

Rule R(T): for each lower-band voice (rendered note below 60), count consecutive decision ticks on which its candidate
is selected with direct == 0.  While that count is at least T ticks the voice is suppressed (as if released); it
returns the moment direct != 0 again or the voice disappears.  Tick classes as in the tail-state script (true, tail,
other).  Per label (a label index from the trace's active-label column): ticks of the voice's pitch suppressed while
that label is active.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the tail-state result (above).  NOT seen: any suppression count.  Fixed grid T in 50, 100, 200, 400 ms.
Predictions, each can fail:
  U1  at T = 200 ms, at least 40% of the lower-band tail ticks are suppressed.
  U2  at T = 200 ms, at least 10 labels lose some true ticks (the strict per-label gate fails; Codex's label 364
      lost its whole hold under the related trial).
  U3  at T = 400 ms, at least 3 labels still lose over 100 ms of true ticks.
  U4  at every T, suppressed (tail + other) ticks per suppressed true tick are at least 3.
Report the curve whatever it shows.  Nothing here may choose a threshold: one corpus, one recording; a choice would be
tuned on its own evidence.  Pitch occupancy at decision-tick resolution; no lane, unison, callback or live-host claim.

Usage: python3 -P -E CLAUDE-M3-LOWREG-UNSUPPORTED-RUN-20261122.py TRACE.tsv.gz
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

OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-UNSUPPORTED-RUN-20261122.json')
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
                unsupported = cand is not None and cand['selection'] != 0 and cand['direct'] == 0
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
