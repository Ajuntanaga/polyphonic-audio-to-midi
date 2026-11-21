#!/usr/bin/env python3
"""Lane confusion and persistence of the existing DP on rendered upper notes (saved v5 table only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-DP-LANE-CONFUSION-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Follows CLAUDE-M3-DP-LANE-RULE-CHECK-20261120.py, which found that the existing DP gives rendered upper notes the annotated lane in 4,150 of 6,753
frames (61.5%), never gives string 5 the right lane (0 of 559) and almost never string 7 (4 of 897). This asks whether those lane errors are persistent
per note (a biased lane preference) or flipping (noise), and which lane the DP chooses instead.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one CURRENT configuration, annotation is not audibility):
  Population R as in the rule check: (tick, voice) with outcome in {0,2}, rendered note 61..84, not a quiet tick.
  Confusion: for outcome-2 voices, count (annotated lane set of the label, assigned string); for outcome-0 voices the annotated lane equals the assigned one.
  Runs: a run = maximal consecutive ticks in which the same (label id, rendered note) is rendered. For each run: ticks, number of distinct assigned strings,
    number of lane switches, whether the FIRST assigned lane of the run is in the annotated mask, whether the run's modal lane is. Reported:
    runs, ticks, share of ticks whose run never switches lane, ticks with outcome 0 under (a) the DP as it is, (b) "first lane of the run held for the run"
    (causal onset-lock), (c) "modal lane of the run" (an oracle that uses the future: reported only as an upper bound for any persistence-only rule).
  All counts are over frames; nothing is tuned or thresholded.
  AMENDMENT (added after the first run, which was tick-weighted and dominated by a few long runs; the first-run numbers are kept as run):
    run-weighted secondary counts: runs whose every tick is in the annotated mask, runs with none, runs mixed; runs whose first lane is annotated;
    and the five longest runs with (label id, note, ticks, distinct lanes, annotated mask, fraction of ticks in mask). Still nothing tuned.
"""
import collections, json, sys

PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main():
    conf = collections.Counter()
    open_runs = {}                      # (lid, note) -> dict(last_tick, lanes list, mask)
    done = []

    def close(key):
        done.append(open_runs.pop(key))

    for fr in m.load_new(TABLE):
        seen = set()
        if not fr['quiet']:
            lab = {}
            for (lid, note, mask) in fr['labels']:
                lab.setdefault(note, (lid, mask))
            for v in fr['voices']:
                det, ren, s, out = v[0], v[1], v[2], v[3]
                if out not in (0, 2) or not 61 <= ren <= 84 or ren not in lab:
                    continue
                lid, mask = lab[ren]
                if out == 2:
                    conf[(''.join(str(b) for b in range(8) if mask >> b & 1) or '-', s)] += 1
                key = (lid, ren)
                seen.add(key)
                r = open_runs.get(key)
                if r is not None and r['last'] == fr['tick'] - 1:
                    r['lanes'].append(s); r['last'] = fr['tick']
                else:
                    if r is not None:
                        close(key)
                    open_runs[key] = dict(last=fr['tick'], lanes=[s], mask=mask, lid=lid, note=ren)
        for key in [k for k, r in open_runs.items() if r['last'] != fr['tick'] and k not in seen]:
            close(key)
    for key in list(open_runs):
        close(key)
    ticks = sum(len(r['lanes']) for r in done)
    never = sum(len(r['lanes']) for r in done if len(set(r['lanes'])) == 1)
    asis = sum(sum(1 for s in r['lanes'] if r['mask'] >> s & 1) for r in done)
    first = sum(len(r['lanes']) for r in done if r['mask'] >> r['lanes'][0] & 1)
    modal = 0
    for r in done:
        lane = collections.Counter(r['lanes']).most_common(1)[0][0]
        modal += len(r['lanes']) if r['mask'] >> lane & 1 else 0
    allok = sum(1 for r in done if all(r['mask'] >> x & 1 for x in r['lanes']))
    none_ok = sum(1 for r in done if not any(r['mask'] >> x & 1 for x in r['lanes']))
    first_ok = sum(1 for r in done if r['mask'] >> r['lanes'][0] & 1)
    longest = sorted(done, key=lambda r: -len(r['lanes']))[:5]
    switches = sum(sum(1 for a, b in zip(r['lanes'], r['lanes'][1:]) if a != b) for r in done)
    lens = sorted(len(r['lanes']) for r in done)
    rep = dict(runs=len(done), ticks=ticks, ticks_in_runs_with_no_lane_switch=never, lane_switches=switches,
               run_length_median=lens[len(lens) // 2] if lens else None, run_length_max=lens[-1] if lens else None,
               outcome0_ticks_as_is=asis, outcome0_ticks_if_first_lane_held=first, outcome0_ticks_if_modal_lane_oracle=modal,
               runs_all_ticks_in_mask=allok, runs_no_tick_in_mask=none_ok, runs_mixed=len(done) - allok - none_ok, runs_first_lane_in_mask=first_ok,
               longest_runs=[dict(label=r['lid'], note=r['note'], ticks=len(r['lanes']), lanes=sorted(set(r['lanes'])), mask=r['mask'],
                                  frac_in_mask=round(sum(1 for x in r['lanes'] if r['mask'] >> x & 1) / len(r['lanes']), 3)) for r in longest],
               confusion_outcome2={'annotated=%s|assigned=%d' % k: v for k, v in sorted(conf.items(), key=lambda kv: -kv[1])})
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


main()
