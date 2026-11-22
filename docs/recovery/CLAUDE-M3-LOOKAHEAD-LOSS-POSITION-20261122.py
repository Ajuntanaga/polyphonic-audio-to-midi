"""POST HOC (not registered): where inside a label does the shorter lookahead (readout 166) lose frame-level presence?

Written after Part A of CLAUDE-M3-LEVEL-CONDITIONED-PREREGISTRATION-20261122.md showed label-end presence nearly unchanged on silent-after
ends while Codex's whole-label presence fell 4.6 pp.  Frame-level posterior >= 0.3 at the label pitch (tape, not decoder events); the 428
evaluable ordinary labels of the committed ends file; control164 and candidate166 tapes of run 45036257574.  Descriptive, no verdict.
Usage: python3 CLAUDE-M3-LOOKAHEAD-LOSS-POSITION-20261122.py ENDS.json CONTROL_DIR CANDIDATE_DIR OUT.json
"""
import json
import os
import sys

import numpy as np

HOP, MODEL_RATE, SOURCE_RATE, THRESHOLD = 256, 22050, 96000, 0.3
START_BINS = ((0, 50), (50, 100), (100, 200), (200, 400))      # ms after the label start
END_BINS = ((0, 50), (50, 100), (100, 200))                    # ms before the label end


def tape(directory):
    return np.load(os.path.join(directory, 'ordinary-stream.npz'), allow_pickle=False)['note']


def main(ends_path, control_dir, candidate_dir, out_path):
    ends = json.load(open(ends_path))['corpora']['ordinary']['ends']
    control, candidate = tape(control_dir), tape(candidate_dir)
    rows = {'start': {b: [0, 0, 0, 0] for b in START_BINS}, 'end': {b: [0, 0, 0, 0] for b in END_BINS}, 'middle': {'all': [0, 0, 0, 0]},
            'whole': {'all': [0, 0, 0, 0]}}

    def add(cell, c, k):
        cell[0] += 1
        cell[1] += c
        cell[2] += k
        cell[3] += (c != k)

    for e in ends:
        lo = -(-e['start'] * MODEL_RATE // (SOURCE_RATE * HOP))
        hi = (e['end'] * MODEL_RATE) // (SOURCE_RATE * HOP)
        hi = min(hi, len(control) - 1)
        column = e['midi_note'] - 21
        for f in range(lo, hi + 1):
            c, k = bool(control[f, column] >= THRESHOLD), bool(candidate[f, column] >= THRESHOLD)
            t = f * HOP / MODEL_RATE
            since_start, until_end = (t - e['start'] / SOURCE_RATE) * 1000, (e['end'] / SOURCE_RATE - t) * 1000
            add(rows['whole']['all'], c, k)
            for b in START_BINS:
                if b[0] <= since_start < b[1]:
                    add(rows['start'][b], c, k)
            for b in END_BINS:
                if b[0] <= until_end < b[1]:
                    add(rows['end'][b], c, k)
            if since_start >= START_BINS[-1][1] and until_end >= END_BINS[-1][1]:
                add(rows['middle']['all'], c, k)
    out = dict(note='post hoc, descriptive; frames with posterior >= 0.3 at the label pitch; positions overlap for short labels', labels=len(ends))
    for group, cells in rows.items():
        out[group] = [dict(bin_ms=list(b) if isinstance(b, tuple) else b, frames=n, control_pct=round(100 * c / n, 2), candidate_pct=round(100 * k / n, 2),
                           change_pp=round(100 * (k - c) / n, 2), frames_that_differ=d) for b, (n, c, k, d) in cells.items() if n]
    with open(out_path, 'w') as handle:
        json.dump(out, handle, indent=1)
        handle.write('\n')
    for group in ('whole', 'start', 'middle', 'end'):
        for row in out[group]:
            print(group, row)


if __name__ == '__main__':
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
