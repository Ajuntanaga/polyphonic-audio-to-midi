#!/usr/bin/env python3
"""Does any saved per-string field see the annotated lane, string by string? (saved v5 table only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-LANE-SIGNAL-BY-STRING-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Follows CLAUDE-M3-DP-LANE-CONFUSION-20261120.py: the existing DP never gave string 5 a correct lane on a rendered upper note (0 of 559), annotated-5
notes went to strings 6, 7 or 4, and 82% of wrong lanes sit on a higher string index (lower fret) than annotated. This asks whether the per-string fields
the trace already carries distinguish the annotated lane at all, per annotated string.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (descriptive, associations only, one CURRENT configuration, annotation is not audibility):
  Population G = (tick, genuine label note n) with 61 <= n <= 84, label string mask with exactly one bit a (lane), not a quiet tick, a candidate row for n
    with energy_observed != 0. Selection state is NOT conditioned on (rendered, evicted and below-threshold frames all count), so this is the lane
    information in the evidence itself, not in the DP's output.
  For each annotated lane a (3..7), over G:
    frames; lane a in playable_mask; in cal_mask; in selector_option_mask; in selector_positive_mask; in fine_mask; in committed_mask (counts);
    the distribution of best_string when cal_mask != 0 (counts per string and 'none'); and the share of those frames where best_string == a.
  No rule is proposed from this and nothing is thresholded; it only says whether per-string evidence for the annotated lane exists in the saved fields.
"""
import collections, json, sys

PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

FIELDS = ('playable_mask', 'cal_mask', 'selector_option_mask', 'selector_positive_mask', 'fine_mask', 'committed_mask')


def main():
    lane = collections.defaultdict(collections.Counter)
    best = collections.defaultdict(collections.Counter)
    for fr in m.load_new(TABLE):
        if fr['quiet']:
            continue
        lab = {}
        for (lid, note, mask) in fr['labels']:
            lab.setdefault(note, mask)
        for note, mask in lab.items():
            if not 61 <= note <= 84 or mask == 0 or mask & (mask - 1):
                continue
            c = fr['rows'].get(note)
            if c is None or c.get('energy_observed') == 0:
                continue
            a = mask.bit_length() - 1
            L = lane[a]
            L['frames'] += 1
            for f in FIELDS:
                L['in_' + f] += 1 if c.get(f, 0) >> a & 1 else 0
            if c['cal_mask'] != 0:
                best[a][c['best_string']] += 1
            else:
                best[a]['none'] += 1
    rep = {}
    for a in sorted(lane):
        b = best[a]
        n_cal = sum(v for k, v in b.items() if k != 'none')
        rep['annotated_lane_%d' % a] = dict(lane[a], best_string_distribution={str(k): v for k, v in sorted(b.items(), key=lambda kv: str(kv[0]))},
                                            best_string_equals_annotated=b.get(a, 0), best_string_defined=n_cal)
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


main()
