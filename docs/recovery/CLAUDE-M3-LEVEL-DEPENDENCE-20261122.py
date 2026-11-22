"""POST HOC (not registered): does presence at the label end depend on how loud the note is?

Uses only the committed ends file (groups from the saved tapes of run 45029161409) and the committed level curves of the registered
audio-level read (run 45034800737).  Nothing is re-measured, no audio is opened.
`pre` is the level of [E-80 ms, E) at the pitch's first harmonics (dB re full scale).
Usage: python3 CLAUDE-M3-LEVEL-DEPENDENCE-20261122.py ENDS.json CURVES.json.gz [OUT.json]
"""
import gzip
import json
import sys

PRE_INDEX = 12                                   # END_GRID j = -8
LEVEL_BINS = [(-200, -70), (-70, -60), (-60, -50), (-50, -40), (-40, 0)]
PITCH_BANDS = [(0, 48), (48, 60), (60, 72), (72, 100)]
MIN_N = 5


def auc(positive, negative):
    """P(a random positive end is louder than a random negative end), ties count half."""
    if not positive or not negative:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return round(wins / (len(positive) * len(negative)), 3)


def present(group, arm):
    return group in ('both', 'adapted_only') if arm == 'adapted' else group in ('both', 'original_only')


def rate(rows, arm):
    return round(sum(present(r['group'], arm) for r in rows) / len(rows), 3)


def analyse(ends_path, curves_path):
    ends = json.load(open(ends_path))
    curves = json.load(gzip.open(curves_path, 'rt'))
    by_index = {r['idx']: r for r in curves['corpora']['ordinary']['ends']}
    rows = []
    for e in ends['corpora']['ordinary']['ends']:
        level = by_index[e['idx']]['end_levels'][PRE_INDEX]
        if level is not None:
            rows.append(dict(group=e['group'], midi=e['midi_note'], pre=level))
    out = dict(n=len(rows), by_level=[], by_pitch=[], by_pitch_and_level=[], auc={})
    for lo, hi in LEVEL_BINS:
        sel = [r for r in rows if lo <= r['pre'] < hi]
        if sel:
            out['by_level'].append(dict(pre_db=[lo, hi], n=len(sel), adapted=rate(sel, 'adapted'), original=rate(sel, 'original')))
    for lo, hi in PITCH_BANDS:
        sel = [r for r in rows if lo <= r['midi'] < hi]
        if sel:
            out['by_pitch'].append(dict(midi=[lo, hi], n=len(sel), adapted=rate(sel, 'adapted'), original=rate(sel, 'original'),
                                        median_pre=sorted(r['pre'] for r in sel)[len(sel) // 2]))
        for a, b in LEVEL_BINS:
            cell = [r for r in sel if a <= r['pre'] < b]
            if len(cell) >= MIN_N:
                out['by_pitch_and_level'].append(dict(midi=[lo, hi], pre_db=[a, b], n=len(cell), adapted=rate(cell, 'adapted'), original=rate(cell, 'original')))
    for arm in ('adapted', 'original'):
        pos = [r for r in rows if present(r['group'], arm)]
        neg = [r for r in rows if not present(r['group'], arm)]
        block = dict(level_all=auc([r['pre'] for r in pos], [r['pre'] for r in neg]),
                     lower_pitch_all=auc([-r['midi'] for r in pos], [-r['midi'] for r in neg]))
        for lo, hi in PITCH_BANDS:
            p = [r['pre'] for r in pos if lo <= r['midi'] < hi]
            n = [r['pre'] for r in neg if lo <= r['midi'] < hi]
            block['level_within_midi_%d_%d' % (lo, hi)] = dict(n_present=len(p), n_absent=len(n), auc=auc(p, n))
        out['auc'][arm] = block
    return out


if __name__ == '__main__':
    result = analyse(sys.argv[1], sys.argv[2])
    text = json.dumps(result, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w').write(text + '\n')
    print(text)
