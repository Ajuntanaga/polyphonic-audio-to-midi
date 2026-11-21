#!/usr/bin/env python3
"""Lane and fragmentation analysis of the relief-eligible population (saved v5 table only: no audio, no dispatch, no replay).

  python3 -I CLAUDE-M3-RELIEF-LANE-ANALYSIS-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz OUT.json

Why: the rejected relief screen (run 44881108478) gained 811,886 correct-lane and 436,106 wrong-lane voice-samples of annotated pitch
(their sum is exactly the pitch-presence gain of 1,247,992), so about 35% of the recovered pitch sat on a non-annotated lane. This asks
what the saved table says about that, without tuning anything.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one current-on configuration, annotation is not audibility):
  Population E = frames (tick, genuine label note n, 61 <= n <= 84) with a candidate row, selection code 3 (DP-evicted), the note NOT
    rendered that tick, and the frozen relief predicate evaluated with the same rendered-lower-parent proxy the v5 verdict used:
    P = rendered voice notes below n; relief iff P is non-empty and no c in P has n-c in {12,19,24,28,31,36}.
    (Proxy, not the causal previous-active parent. The v5 verdict counted about 13.6k such genuine frames.)
  Strings: bit s of every mask is string s with open note 32+4*s (0..7). A = the label's annotated string mask; labels with mask 0 are
    excluded and counted. fret(s) = n - open(s).
  playable = row.playable_mask. used = row.selector_used_mask (strings taken by the winning DP state, i.e. what the DP had when it evicted
    the candidate). free = playable & ~used.
  L_dp = the free string with the lowest fret (highest string index): the lane the existing per-fret cost would give the note. no_free_lane
    when free is empty. hit_dp = L_dp in A.
  Availability: annotated_playable = A & playable != 0; annotated_free = A & free != 0.
  Calibration lane: B = row.best_string, usable only when row.cal_mask != 0 and B is in playable; margin = best_cal - second_cal; hit_cal =
    B in A. Reported over fixed margin bins (<=0.02, 0.02-0.05, 0.05-0.10, 0.10-0.20, >0.20, and no calibration); no cut is chosen.
  Fragmentation: runs of consecutive ticks of E within one label; reported overall and for labels 13 and 56 (the two labels whose NoteOns
    went 0 -> 12 and 0 -> 11 in the screen).
  Nothing here is tuned or thresholded; any rule it suggests would need its own predeclaration and a separately authorized screen.
"""
import collections, json, sys

PROJ, TABLE, OUT = sys.argv[1:4]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

RELATED = {12, 19, 24, 28, 31, 36}
OPEN = [32 + 4 * s for s in range(8)]
MARGIN_BINS = (0.02, 0.05, 0.10, 0.20)
MARGIN_NAMES = ('<=0.02', '0.02-0.05', '0.05-0.10', '0.10-0.20', '>0.20')


def bits(mask):
    return [s for s in range(8) if mask >> s & 1]


def margin_bin(x):
    for e, nme in zip(MARGIN_BINS, MARGIN_NAMES):
        if x <= e:
            return nme
    return MARGIN_NAMES[-1]


def main():
    tot = collections.Counter()
    by_band = collections.defaultdict(collections.Counter)
    cal_bins = collections.defaultdict(collections.Counter)
    ann_size = collections.Counter()
    lane_conf = collections.Counter()           # (annotated lowest-fret lane == L_dp) breakdown by annotated string
    dp_lane_hist = collections.Counter()
    ann_lane_hist = collections.Counter()
    runs_state = {}                              # lid -> (last_tick, run_len)
    runs = collections.defaultdict(list)         # lid -> run lengths
    frames_by_label = collections.Counter()
    for fr in m.load_new(TABLE):
        voice_notes = {v[1] for v in fr['voices']}
        lab = {}
        for (lid, note, mask) in fr['labels']:
            lab.setdefault(note, (lid, mask))
        for note, (lid, mask) in lab.items():
            if not 61 <= note <= 84:
                continue
            c = fr['rows'].get(note)
            if c is None or note in voice_notes or fr['quiet'] or c['selection'] != 3 or c.get('energy_observed') == 0:
                continue
            P = [v for v in voice_notes if v < note]
            if not P or any((note - v) in RELATED for v in P):
                continue
            if mask == 0:
                tot['label_mask_zero_excluded'] += 1
                continue
            band = '61-71' if note <= 71 else '72-84'
            tot['E_frames'] += 1; by_band[band]['E'] += 1
            frames_by_label[lid] += 1
            st = runs_state.get(lid)
            if st and st[0] == fr['tick'] - 1:
                runs_state[lid] = (fr['tick'], st[1] + 1)
            else:
                if st: runs[lid].append(st[1])
                runs_state[lid] = (fr['tick'], 1)
            A, play, used = mask, c['playable_mask'], c['selector_used_mask']
            free = play & ~used
            ann_size[len(bits(A))] += 1
            by_band[band]['annotated_playable'] += 1 if A & play else 0
            by_band[band]['annotated_free'] += 1 if A & free else 0
            if free == 0:
                by_band[band]['no_free_lane'] += 1
            else:
                L = max(bits(free))
                dp_lane_hist[L] += 1
                hit = bool(A >> L & 1)
                by_band[band]['hit_dp'] += 1 if hit else 0
                for s in bits(A):
                    ann_lane_hist[s] += 1
                lane_conf[('hit' if hit else 'miss', 'annotated_free' if A & free else 'annotated_not_free')] += 1
            B = c['best_string']
            if c['cal_mask'] != 0 and play >> B & 1:
                bn = margin_bin(c['best_cal'] - c['second_cal'])
                cal_bins[bn]['n'] += 1
                cal_bins[bn]['hit_cal'] += 1 if (A >> B & 1) else 0
                # the calibration pick restricted to what was actually free, to be comparable with L_dp
                cal_bins[bn]['cal_in_free'] += 1 if (free >> B & 1) else 0
                if free:
                    cal_bins[bn]['hit_dp_same_frames'] += 1 if (A >> max(bits(free)) & 1) else 0
                    cal_bins[bn]['n_free'] += 1
            else:
                cal_bins['no_calibration']['n'] += 1
                if free:
                    cal_bins['no_calibration']['hit_dp_same_frames'] += 1 if (A >> max(bits(free)) & 1) else 0
                    cal_bins['no_calibration']['n_free'] += 1
    for lid, (t, n) in runs_state.items():
        runs[lid].append(n)
    all_runs = [n for v in runs.values() for n in v]
    all_runs.sort()
    q = lambda p: all_runs[min(len(all_runs) - 1, int(p * len(all_runs)))] if all_runs else None
    rep = dict(counts=dict(tot),
               by_band={b: dict(v) for b, v in by_band.items()},
               annotated_string_count=dict(ann_size),
               dp_lane_hist=dict(sorted(dp_lane_hist.items())), annotated_lane_hist=dict(sorted(ann_lane_hist.items())),
               hit_vs_free=dict(('%s|%s' % k, v) for k, v in lane_conf.items()),
               calibration_by_margin={k: dict(v) for k, v in cal_bins.items()},
               fragmentation=dict(runs=len(all_runs), frames=sum(all_runs), run_len_quantiles=dict(
                   min=all_runs[0] if all_runs else None, p25=q(0.25), median=q(0.5), p75=q(0.75), max=all_runs[-1] if all_runs else None),
                   runs_of_one_tick=sum(1 for n in all_runs if n == 1), runs_of_at_most_4_ticks=sum(1 for n in all_runs if n <= 4),
                   label13=dict(frames=frames_by_label.get(13, 0), runs=sorted(runs.get(13, []))[:60]),
                   label56=dict(frames=frames_by_label.get(56, 0), runs=sorted(runs.get(56, []))[:60])))
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


main()
