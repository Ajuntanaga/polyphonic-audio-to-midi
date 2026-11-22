"""What does the native tracker do with the upper register?  Saved v5 trace and saved spans only.

CURRENT covers MIDI 60-71 at 5.8% and 72+ at 0.0% of the labelled time (0 of 78 labels at 72+ ever present), while Basic Pitch arm A
places 65.6% of both bands; about 41% of all expected pitch-samples are at 60 and above.  The detector's configured range reaches MIDI 84,
so the 72+ gap is not a range cap.  This script asks where the labelled upper notes are lost inside the native selection chain, using the
trace's per-tick candidate dispositions (selection codes: 0 quiet, 1 below_threshold, 2 spectral_rejected, 3 dp_evicted, 4 selected,
5 coasting), and whether the rejected true candidates look different from the rejected ghost candidates.  No audio, model run or job;
nothing is selected, promoted or installed.

Definitions (same as the lower-register ghost-separation scripts, for comparability): a tick is 'true' for a note if a label of that pitch
is active at the tick; 'ghost' if no label of that pitch is active and none ended within the last 1.5 s (TAIL_TICKS); everything else is
skipped.  Quiet ticks (quiet == 1) carry no candidate decisions and are counted apart.  The v5 trace is the detector's own stream on the
ordinary corpus (167,025 decision rows).  The candidate list per tick holds about a dozen pitches, not only selected ones.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the CURRENT/Basic Pitch band coverage table; that the configured highest note is 84; and a three-label peek (a 78 label held a
candidate for pitch 78 on all 1,626 of its ticks, a 83 label on all 504; one sample row, tick 4001, shows codes 1, 3, 4, 5 present in one
list).  NOT seen: any census of codes by band, any per-label fate, any separation statistic for the upper band.
Predictions, each can fail:
  F0  the label pitch is in the candidate list at >= 95% of non-quiet true ticks in every band.
  F1  at 72+, fewer than 10% of non-quiet true ticks carry code 4 or 5.
  F2  at 72+, code 1 (below_threshold) is the most frequent code among non-quiet true ticks.
  F3  at 72+, code 3 (dp_evicted) is under 20% of non-quiet true ticks.
  F4  at 72+, the best single-feature AUC between true and ghost candidates that were rejected (codes 1-3) is above 0.90.
  F5  that best AUC at 72+ exceeds the best at 60-71 by at least 0.03.
  F6  fewer than 20 of the 78 labels at 72+ reach code 4 or 5 on any tick.
  F7  the quiet share of true ticks at 72+ is within 5 points of that at 60-71.
  F8  for the best 72+ feature at a ghost false-positive rate of 1% or less, the recovered true ticks outnumber the admitted ghost ticks.
Report everything whatever it shows.  Ticks inside one note are strongly correlated and bands/labels are few: descriptive tick-level
numbers, no confidence interval, in-sample.  One recording and one corpus.  This does not establish lane or unison behaviour, callback
deadlines, or a rule worth building.

POST-HOC EXTENSION (added after the first run's census and separation tables had been read; its outputs are labelled post-hoc, and the
predictions above were not changed): per-band quantiles of score_ratio, fund_ratio and band_score for below_threshold true and ghost
candidates, and the share of below_threshold true ticks within a factor of the threshold, plus each label's best score_ratio over its
non-quiet ticks.  Motive: the first run showed that 96.6% of the 72+ true ticks sit at code 1, so the question became how far below the
threshold they sit.

Usage: python3 -P -E CLAUDE-M3-UPPER-FATE-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import os
import sys
from array import array
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gs = load('gs', 'CLAUDE-M3-LOWREG-GHOST-SEPARATION-20261122.py')
BASELINE = os.path.join(REPO, 'docs/recovery/basic-pitch-baseline-20261121.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-UPPER-FATE-20261122.json')
HORIZON = 10681922
TAIL_TICKS = gs.TAIL_TICKS
BANDS = [(48, 60, '48-59'), (60, 72, '60-71'), (72, 200, '72+')]
CODE_NAMES = {0: 'quiet', 1: 'below_threshold', 2: 'spectral_rejected', 3: 'dp_evicted', 4: 'selected', 5: 'coasting'}
PROGRESS = {1: 1, 2: 2, 3: 3, 5: 4, 4: 5}
FEATS = ['direct', 'local', 'evidence_ticks', 'evidence_gap', 'fund_ratio', 'band_fund', 'band_score', 'score_ratio', 'fund_energy',
         'score_energy', 'age', 'attack', 'release', 'onset', 'selector_pool_member', 'selector_raw_score',
         'selector_best_adjusted_score', 'best_cal']
MAX_ROWS = 2500000  # rows per store; float32 storage, first-N if ever reached (recorded in the output)


def band_of(note):
    for lo, hi, name in BANDS:
        if lo <= note < hi:
            return name
    return None


def operating_points(true, ghost, sign):
    """Threshold at ghost FPR <= 1% and <= 0.1% (direction sign: +1 means high value = true-like)."""
    t = sign * np.asarray(true, dtype=float)
    g = sign * np.asarray(ghost, dtype=float)
    out = {}
    for label, fpr in (('fpr_1pct', 0.01), ('fpr_0.1pct', 0.001)):
        cut = np.quantile(g, 1.0 - fpr)
        kept_t, kept_g = int(np.sum(t > cut)), int(np.sum(g > cut))
        out[label] = dict(true_recovered=kept_t, true_share=round(kept_t / len(t), 4), ghost_admitted=kept_g,
                          tick_precision=round(kept_t / (kept_t + kept_g), 4) if kept_t + kept_g else None)
    return out


def run(path):
    base = json.load(open(BASELINE))['datasets']['ordinary']
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), HORIZON)
    cur_spans = clip_spans(base['pitch_spans'], HORIZON)
    spans_by = defaultdict(list)
    for left, right, pitch in cur_spans:
        spans_by[pitch].append((left, right))
    for pitch in spans_by:
        spans_by[pitch].sort()

    def emitted(label):
        iv = spans_by.get(label['midi_note'], [])
        i = bisect.bisect_right(iv, (label['start_sample'], 10 ** 12)) - 1
        for j in range(max(0, i), len(iv)):
            if iv[j][0] >= label['end_sample']:
                break
            if iv[j][1] > label['start_sample']:
                return True
        return False

    label_by_index = {r['label_index']: r for r in labels}
    unknown_label_ids = set()
    codes = {(b, k): Counter() for _, _, b in BANDS for k in ('true', 'ghost')}
    quiet_true = Counter()
    all_true = Counter()
    rows = {(b, k): array('f') for _, _, b in BANDS for k in ('true', 'ghost')}
    rows_below = {(b, k): array('f') for _, _, b in BANDS for k in ('true', 'ghost')}
    width = len(FEATS)
    best = {}
    label_max_ratio = {}
    last_label = {}
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick = frame['tick']
            active = {row[1]: row[0] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            if frame['quiet']:
                for note in active:
                    band = band_of(note)
                    if band:
                        quiet_true[band] += 1
                        all_true[band] += 1
                continue
            cands = _candidates(frame)
            for note, idx in active.items():
                band = band_of(note)
                if not band:
                    continue
                all_true[band] += 1
                if idx not in label_by_index:
                    unknown_label_ids.add(idx)
                cand = cands.get(note)
                code = 'none' if cand is None else cand['selection']
                codes[(band, 'true')][code] += 1
                if cand is not None:
                    label_max_ratio[idx] = max(label_max_ratio.get(idx, 0.0), cand['score_ratio'])
                if cand is not None and code in PROGRESS:
                    prev = best.get(idx, 0)
                    if PROGRESS[code] > prev:
                        best[idx] = PROGRESS[code]
                if cand is not None and code in (1, 2, 3) and len(rows[(band, 'true')]) < MAX_ROWS * width:
                    vec = [cand[f] for f in FEATS]
                    rows[(band, 'true')].extend(vec)
                    if code == 1:
                        rows_below[(band, 'true')].extend(vec)
            for note, cand in cands.items():
                band = band_of(note)
                if not band or note in active or tick - last_label.get(note, -10 ** 9) <= TAIL_TICKS:
                    continue
                code = cand['selection']
                codes[(band, 'ghost')][code] += 1
                if code in (1, 2, 3) and len(rows[(band, 'ghost')]) < MAX_ROWS * width:
                    vec = [cand[f] for f in FEATS]
                    rows[(band, 'ghost')].extend(vec)
                    if code == 1:
                        rows_below[(band, 'ghost')].extend(vec)

    result = dict(bands={}, unknown_label_ids_in_trace=sorted(unknown_label_ids)[:20], horizon=HORIZON)
    for _, _, band in BANDS:
        info = {}
        nq_true = sum(codes[(band, 'true')].values())
        info['true_ticks_total'] = all_true[band]
        info['true_ticks_quiet'] = quiet_true[band]
        info['quiet_share_of_true'] = round(quiet_true[band] / all_true[band], 4) if all_true[band] else None
        info['true_nonquiet_ticks'] = nq_true
        info['true_code_share'] = {(CODE_NAMES.get(k, k)): round(v / nq_true, 4) for k, v in sorted(codes[(band, 'true')].items(), key=str)}
        ng = sum(codes[(band, 'ghost')].values())
        info['ghost_ticks'] = ng
        info['ghost_code_share'] = {(CODE_NAMES.get(k, k)): round(v / ng, 4) for k, v in sorted(codes[(band, 'ghost')].items(), key=str)}
        in_band = [r for r in labels if band_of(r['midi_note']) == band]
        fate = Counter()
        for r in in_band:
            fate[best.get(r['label_index'], 0)] += 1
        info['labels'] = len(in_band)
        stage = {0: 'never_a_nonquiet_candidate', 1: 'below_threshold', 2: 'spectral_rejected', 3: 'dp_evicted', 4: 'coasting', 5: 'selected'}
        info['label_best_stage'] = {stage[k]: v for k, v in sorted(fate.items())}
        info['labels_reaching_selected_or_coasting'] = sum(v for k, v in fate.items() if k >= 4)
        info['labels_emitted_by_current'] = sum(1 for r in in_band if emitted(r))
        sep = {}
        for tag, store in (('rejected_codes_1_to_3', rows), ('below_threshold_only', rows_below)):
            tt = np.frombuffer(store[(band, 'true')], dtype=np.float32).reshape(-1, width).astype(float)
            gg = np.frombuffer(store[(band, 'ghost')], dtype=np.float32).reshape(-1, width).astype(float)
            sep[tag] = dict(n_true=len(tt), n_ghost=len(gg), truncated=bool(len(tt) >= MAX_ROWS or len(gg) >= MAX_ROWS), features={})
            if len(tt) < 50 or len(gg) < 50:
                continue
            for i, name in enumerate(FEATS):
                stats = gs.auc_and_tpr(gg[:, i], tt[:, i])  # ghost > true direction chosen >= 0.5
                if stats:
                    sign = -1.0 if stats['ghost_high'] else 1.0  # direction in which high = true-like
                    stats['operating'] = operating_points(tt[:, i], gg[:, i], sign)
                    sep[tag]['features'][name] = stats
        info['separation'] = sep
        # post-hoc: how far below the threshold
        post = {}
        for k in ('true', 'ghost'):
            arr = np.frombuffer(rows_below[(band, k)], dtype=np.float32).reshape(-1, width)
            if len(arr) < 50:
                continue
            q = {}
            for name in ('score_ratio', 'fund_ratio', 'band_score', 'fund_energy'):
                col = arr[:, FEATS.index(name)].astype(float)
                q[name] = {str(p): float(np.quantile(col, p / 100)) for p in (5, 25, 50, 75, 95)}
            col = arr[:, FEATS.index('score_ratio')].astype(float)
            q['share_score_ratio_ge'] = {str(x): round(float(np.mean(col >= x)), 4) for x in (0.1, 0.25, 0.5, 0.8)}
            post[k] = q
        mx = np.asarray([label_max_ratio.get(r['label_index'], 0.0) for r in in_band], dtype=float)
        post['label_best_score_ratio'] = {str(p): round(float(np.quantile(mx, p / 100)), 4) for p in (10, 25, 50, 75, 90)}
        post['labels_best_score_ratio_ge'] = {str(x): int(np.sum(mx >= x)) for x in (0.1, 0.25, 0.5, 0.8, 1.0)}
        info['post_hoc_distance_to_threshold'] = post
        result['bands'][band] = info
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


def summarize(result):
    for band, info in result['bands'].items():
        print('==', band, 'labels', info['labels'], 'reach sel/coast', info['labels_reaching_selected_or_coasting'],
              'CURRENT emitted', info['labels_emitted_by_current'], 'best stage', info['label_best_stage'])
        print('  true ticks', info['true_ticks_total'], 'quiet share', info['quiet_share_of_true'], 'code share', info['true_code_share'])
        print('  ghost ticks', info['ghost_ticks'], 'code share', info['ghost_code_share'])
        for tag, sep in info['separation'].items():
            feats = sep['features']
            top = sorted(feats.items(), key=lambda kv: -kv[1]['auc'])[:4]
            print('  ', tag, 'n_true', sep['n_true'], 'n_ghost', sep['n_ghost'])
            for name, s in top:
                print('     ', name, 'auc', s['auc'], 'ghost_high', s['ghost_high'], json.dumps(s['operating']))


if __name__ == '__main__':
    summarize(run(sys.argv[1]))
