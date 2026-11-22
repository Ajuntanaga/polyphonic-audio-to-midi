"""POST HOC (not registered): is a quiet note at its label end quiet because it decayed, or quiet from the start?

Written after Part C of CLAUDE-M3-LEVEL-CONDITIONED-PARTC-PREREGISTRATION-20261122.md missed its own separability condition (C3), which left
C1 and C2 not evaluable.  Uses the same saved tapes and committed curves; whole-note drop = level just after the onset ([S+20 ms, S+100 ms),
start grid index 22) minus `pre` ([E-80 ms, E)).  Descriptive; no verdict, no bar.
Usage: python3 CLAUDE-M3-LEVEL-CONDITIONED-POSTHOC-20261122.py ENDS.json CURVES.json.gz UNMODIFIED_DIR ADAPTED_DIR OUT.json
"""
import gzip
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ONSET_INDEX = 22
BINS = ((-200, -60), (-60, -50), (-50, -40), (-40, 0))
DROP_CUTS = (6.0, 12.0)


def load_main():
    spec = importlib.util.spec_from_file_location('cond', os.path.join(HERE, 'CLAUDE-M3-LEVEL-CONDITIONED-20261122.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv):
    ends_path, curves_path, unmodified_dir, adapted_dir, out_path = argv
    cond = load_main()
    rc = cond.load_rc()
    ends = json.load(open(ends_path))
    curves = json.load(gzip.open(curves_path, 'rt'))
    tapes = {arm: cond.load_tape(d)[0] for arm, d in (('unmodified', unmodified_dir), ('adapted', adapted_dir))}
    rows = cond.build_rows(ends, curves, tapes, rc)
    by_index = {r['idx']: r for r in curves['corpora']['ordinary']['ends']}
    result = dict(note='post hoc, descriptive; no verdicts', onset_grid_index=ONSET_INDEX, arms={})
    for arm in ('adapted', 'unmodified'):
        pop = []
        for r in rows:
            start_level = by_index[r['idx']]['start_levels'][ONSET_INDEX]
            if r['span_ok'] and r[arm + '_early'] and r[arm + '_present'] is not None and start_level is not None:
                pop.append(dict(pre=r['pre'], total_drop=start_level - r['pre'], present=r[arm + '_present'], contested=r['contested'],
                                start_level=start_level))
        drops = sorted(p['total_drop'] for p in pop)
        block = dict(population=len(pop), spearman_pre_total_drop=round(cond.spearman([p['pre'] for p in pop], [p['total_drop'] for p in pop]), 3),
                     total_drop_db=dict(min=round(drops[0], 1), p10=round(drops[len(drops) // 10], 1), median=round(drops[len(drops) // 2], 1),
                                        p90=round(drops[9 * len(drops) // 10], 1), max=round(drops[-1], 1)),
                     share_drop_above={str(c): round(sum(d >= c for d in drops) / len(drops), 3) for c in DROP_CUTS},
                     by_pre_and_drop=[])
        for lo, hi in BINS:
            cell = [p for p in pop if lo <= p['pre'] < hi]
            for a, b, name in ((-1e9, DROP_CUTS[0], 'drop<6'), (DROP_CUTS[0], DROP_CUTS[1], '6<=drop<12'), (DROP_CUTS[1], 1e9, 'drop>=12')):
                sel = [p for p in cell if a <= p['total_drop'] < b]
                block['by_pre_and_drop'].append(dict(pre_db=[lo, hi], drop=name, n=len(sel),
                                                     present=None if not sel else round(sum(p['present'] for p in sel) / len(sel), 3)))
        result['arms'][arm] = block
    with open(out_path, 'w') as handle:
        json.dump(result, handle, indent=1)
        handle.write('\n')
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    if len(sys.argv) != 6:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
