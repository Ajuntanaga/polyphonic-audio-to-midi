"""Post hoc readings of the release probe (run 45031841272): direction counts and plateau levels.  Not registered; labelled post hoc in the note.

Usage: python3 CLAUDE-M3-RELEASE-PROBE-POSTHOC-20261122.py REPORT.json UNMODIFIED_OUTPUTS.npz ADAPTED_OUTPUTS.npz [OUT.json]
"""
import json
import sys

import numpy as np

FIRST = 21
PITCHES = (45, 52, 59, 66)
STEADY_FRAME = 78
EDGE = 165


def direction_counts(report):
    """Adapted minus unmodified release delay, over every (case, pitch) where both are active and uncensored."""
    earlier = later = equal = 0
    by_case = {}
    for case, rows in report['measurements']['unmodified'].items():
        for m, u in rows.items():
            a = report['measurements']['adapted'][case][m]
            if not (a['active'] and u['active']) or a['censored'] or u['censored']:
                continue
            d = a['delay_ms'] - u['delay_ms']
            by_case.setdefault(case, []).append(round(d, 1))
            earlier += d < -1e-6
            later += d > 1e-6
            equal += abs(d) <= 1e-6
    return dict(adapted_earlier=earlier, adapted_later=later, equal=equal, by_case=by_case,
                mean_difference_ms=round(float(np.mean([x for v in by_case.values() for x in v])), 2))


def plateaus(arrays):
    """Note probability at the played pitch on frame 78 of the sustained tone, and on the last two frames (edge)."""
    return {str(m): dict(frame78=round(float(arrays['%d_sustained_note' % m][STEADY_FRAME, m - FIRST]), 3),
                         last_frame=round(float(arrays['%d_sustained_note' % m][-1, m - FIRST]), 3)) for m in PITCHES}


def decay_shape(arrays, tau, midi):
    """Frames from the frame where the note first falls below 0.9 x its frame-78 value to the first frame below 0.3 (steepness of the fall)."""
    column = arrays['%d_decay_%s_note' % (midi, tau)][:, midi - FIRST]
    top = column[STEADY_FRAME]
    start = next((f for f in range(STEADY_FRAME + 1, 172) if column[f] < 0.9 * top), None)
    end = next((f for f in range(STEADY_FRAME + 1, 172) if column[f] < 0.3), None)
    return dict(start_frame=start, release_frame=end, fall_frames=None if start is None or end is None else end - start)


def main(report_path, unmodified_path, adapted_path, out=None):
    report = json.load(open(report_path))
    arrays = {name: np.load(path, allow_pickle=False) for name, path in (('unmodified', unmodified_path), ('adapted', adapted_path))}
    result = dict(direction=direction_counts(report),
                  plateau={name: plateaus(a) for name, a in arrays.items()},
                  fall={name: {str(tau): {str(m): decay_shape(a, tau, m) for m in PITCHES} for tau in (0.05, 0.1, 0.2, 0.4)}
                        for name, a in arrays.items()})
    text = json.dumps(result, indent=1)
    if out:
        open(out, 'w').write(text + '\n')
    print(text)


if __name__ == '__main__':
    main(*sys.argv[1:5])
