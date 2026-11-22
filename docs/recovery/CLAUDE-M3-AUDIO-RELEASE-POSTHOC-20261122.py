"""POST HOC (not registered): how many label ends are followed by exact digital silence, and who rings.

Reads the same pinned ends file and the saved curves of the registered read; nothing is re-measured and no audio is opened.
A level at the floor (<= -179 dB) means the 80 ms window holds only zero samples: the projection of any nonzero 16-bit sample
on a harmonic is orders of magnitude above 1e-9.  Usage: python3 CLAUDE-M3-AUDIO-RELEASE-POSTHOC-20261122.py ENDS.json CURVES.json OUT.json
"""
import json
import math
import sys

FLOOR_DB = -179.0
RING_DB = -6.0
END_J0 = 20          # END_GRID starts at j = -20, so j = 0 (window [E, E+80 ms)) is index 20
PRE_INDEX = 12       # j = -8, window [E-80 ms, E)
GROUPS = ('both', 'adapted_only', 'original_only', 'neither')


def fisher_one_sided(a, n1, b, n2):
    """P(X >= a) where a of n1 and b of n2 are 'ring' and the total number of ring ends is fixed (hypergeometric tail)."""
    k, n = a + b, n1 + n2
    return sum(math.comb(n1, i) * math.comb(n2, k - i) for i in range(a, min(n1, k) + 1)) / math.comb(n, k)


def block(rows):
    n = len(rows)
    silent = sum(r['after'] <= FLOOR_DB for r in rows)
    ring = sum(r['after'] - r['pre'] >= RING_DB for r in rows)
    return dict(n=n, silent=silent, ring=ring, between=n - silent - ring)


def first_silent_j(levels):
    """Smallest j (10 ms steps from the label end) such that every window start from j through 0 is at the floor, or None."""
    j = 0
    while j > -20 and levels[END_J0 + j - 1] is not None and levels[END_J0 + j - 1] <= FLOOR_DB:
        j -= 1
    return j


def analyse(ends_path, curves_path):
    ends = json.load(open(ends_path))
    curves = json.load(open(curves_path))
    out = {}
    for corpus, spec in ends['corpora'].items():
        by_index = {r['idx']: r for r in curves['corpora'][corpus]['ends']}
        usable = []
        cut = {}
        for e in spec['ends']:
            levels = by_index[e['idx']]['end_levels']
            after, pre = levels[END_J0], levels[PRE_INDEX]
            window_ok = e['end'] + int(0.080 * 96000) <= e['window']
            if after is None or pre is None or not window_ok:
                continue
            usable.append(dict(group=e['group'], contested=e['contested_end'], after=after, pre=pre))
            if after <= FLOOR_DB:
                key = str(first_silent_j(levels))
                cut[key] = cut.get(key, 0) + 1
        strata = {'all': usable, 'uncontested': [r for r in usable if not r['contested']]}
        result = {name: {g: block([r for r in rows if r['group'] == g]) for g in GROUPS} for name, rows in strata.items()}
        for name in strata:
            a, b = result[name]['adapted_only'], result[name]['neither']
            if a['n'] and b['n']:
                result[name]['fisher_ring_adapted_only_over_neither'] = dict(
                    adapted_only=[a['ring'], a['n']], neither=[b['ring'], b['n']],
                    p_one_sided=round(fisher_one_sided(a['ring'], a['n'], b['ring'], b['n']), 4))
        result['first_silent_window_start_j_counts'] = dict(sorted(cut.items(), key=lambda kv: int(kv[0])))
        out[corpus] = result
    return out


if __name__ == '__main__':
    ends_path, curves_path = sys.argv[1], sys.argv[2]
    result = analyse(ends_path, curves_path)
    text = json.dumps(result, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], 'w').write(text + '\n')
    print(text)
