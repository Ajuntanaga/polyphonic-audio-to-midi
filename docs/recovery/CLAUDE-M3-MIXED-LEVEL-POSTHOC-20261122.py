"""Post hoc views of the mixed-level probe report (computed AFTER the registered verdicts were scored; none is a registered verdict).
Usage (repo root):  python3 docs/recovery/CLAUDE-M3-MIXED-LEVEL-POSTHOC-20261122.py REPORT.json OUT.json
Frame hop 256 samples at 22050 Hz = 11.61 ms; the cut is at the nominal time of frame 164; the profile covers frames 150..171."""
import json
import sys

import numpy as np

PITCHES, LEVELS, FRAMES = [52, 64, 76], [-80, -70, -60, -50, -40, -30], list(range(150, 172))


def main(report_path, out_path):
    report = json.load(open(report_path))
    T = {a: {w['id']: w for w in m['windows']} for a, m in report['models'].items()}
    out = dict(frame_ms=256 / 22050 * 1000, cut_profile={}, sustained_response={}, masking_by_pitch={}, dither_vs_zero={}, references={})
    for a in ('unmodified', 'adapted'):
        rows = {}
        for lv in LEVELS:
            profiles = [np.array(T[a]['zero|cut|m%d|L%d|none' % (m, lv)]['profile']) for m in PITCHES]
            mean = np.mean(profiles, axis=0)
            rows[str(lv)] = dict(mean_posterior={str(f): round(float(mean[FRAMES.index(f)]), 4) for f in range(164, 172)},
                                 pitches_below_0_3_by_frame_171=int(sum(p[-1] < 0.3 for p in profiles)))
        out['cut_profile'][a] = rows
        out['sustained_response'][a] = {str(m): [round(T[a]['zero|sustained|m%d|L%d|none' % (m, lv)]['response'], 4) for lv in LEVELS]
                                        for m in PITCHES}
    a = 'adapted'
    for m in PITCHES:
        row = {}
        for timing in ('through', 'ended'):
            for delta in (10, 20, 35):
                diffs = [T[a]['zero|sustained|m%d|L%d|%s+%d' % (m, lv, timing, delta)]['response']
                         - T[a]['zero|sustained|m%d|L%d|none' % (m, lv)]['response'] for lv in LEVELS if lv + delta <= -10]
                row['%s+%d' % (timing, delta)] = dict(mean_change=round(float(np.mean(diffs)), 4), cells=len(diffs))
        out['masking_by_pitch'][str(m)] = row
    differ = {}
    for i, w in T[a].items():
        if i.startswith('dither|') and w.get('response') is not None:
            if abs(w['response'] - T[a]['zero|' + i[len('dither|'):]]['response']) > 0.1:
                differ[i.split('|')[3]] = differ.get(i.split('|')[3], 0) + 1
    out['dither_vs_zero'] = dict(pairs_differing_by_more_than_0_1_by_probe_level=dict(sorted(differ.items())))
    out['references'] = {i: dict(max_note=round(w['max_note'], 4), active_bins=w['active_bins'], min_db=round(w['min_db'], 2),
                                 range_db=round(w['range_db'], 2)) for i, w in T[a].items() if '|ref|' in i}
    json.dump(out, open(out_path, 'w'), indent=1)
    print(json.dumps(out['cut_profile']['adapted']['-80']), json.dumps(out['dither_vs_zero']))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
