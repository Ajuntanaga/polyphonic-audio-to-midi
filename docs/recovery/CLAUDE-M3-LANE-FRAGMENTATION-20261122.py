"""What do the extra note runs of the filter-plus-rescue lane cost, and does a short forward hold of the lane remove them?  Saved data only.

No audio, model run, job or native edit; nothing promoted.  CLAUDE-M3-SUPPORT-RESCUE-COMBINED-20261122 (commit 4d47d9d, ordinary) found that
the supported rescue lane (native >= 60 confirmation plus rescue candidates that arm A also reports) on top of the filtered CURRENT adds
+47.5 / +59.7 / +91.9% more output runs than CURRENT at D = 220 (c = 1.0 / 0.5 / 0.25) and +60 / +71 / +100% at D = 50, and the note said that
a real emitter would turn each extra run into an extra note-on.  The lane spans are one block per completed 512-sample callback with no
coasting, so a lane that flickers makes many short runs.  This script asks whether holding the LANE spans forward h ms after they end
(causal; extends forward only; only the lane is held, never CURRENT's own spans) merges the flicker, what that costs in precision and gap
voice-samples, and how many of the remaining runs are short (under 50 ms and under 100 ms).  The rescue spans are saved to the build folder
(not committed) so later scripts need not re-read the trace.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the combined-result run counts above.  NOT seen: any hold of the lane, any run-length distribution, the short-run share of
CURRENT's own spans or of the lane's.  Grid fixed before the run, not tuned: h in {0, 30, 60, 120} ms; two base variants taken from the
combined result: (a) D = 220 with the supported lane at c = 0.5, (b) D = 50 with the supported lane at c = 0.25.  Predictions, each can fail:
  H0  identity: h = 0 reproduces the combined result (a: coverage 48.797%, runs +59.66%; b: coverage 51.260%, runs +100.19%).
  H1  output runs fall (non-increasing) as h grows, for both base variants.
  H2  at h = 120 the run count of (a) is below +30% over CURRENT's.
  H3  precision falls (non-increasing) as h grows, for both.
  H4  at h = 120 the gap-voice delta of (a) is still <= 0 and its wrong-pitch delta is still <= 0.
  H5  the share of runs shorter than 50 ms is larger in the lane's own spans (supported c = 0.5, h = 0) than in CURRENT's spans.
  H6  coverage rises with h by less than 1.5 pp between h = 0 and h = 120 (the flicker is mostly short gaps inside already-detected notes).
  H7  the number of labels losing present or longest hold is unchanged by h (the lane adds only pitches >= 60 and the losses are elsewhere).
Report everything whatever it shows.  One recording, one corpus, in-sample for design (the grid was fixed before the run); the trace is a
diagnostic writer's record; descriptive counts; no lane, unison, string, callback or live-host claim; no native implementation of any gate or
lane exists, and a real one would change which spans appear; a run is a maximal same-pitch span, not a scored MIDI note-on; not a built output.

Usage: python3 -P -E CLAUDE-M3-LANE-FRAGMENTATION-20261122.py TRACE.tsv.gz
"""
import gzip
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.candidate_outcome_analysis import _candidates, _frame  # noqa: E402
from tools.native_neural_consensus import EVIDENCE_DIR, confirmation_spans, intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
rf = load('rf', 'CLAUDE-M3-NATIVE-RESCUE-FRONTIER-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-LANE-FRAGMENTATION-20261122.json')
CACHE_DIR = os.path.join(REPO, 'build', 'recovery', 'm3-rescue-spans-20261122')
CACHE = os.path.join(CACHE_DIR, 'ordinary-rescue-spans.json.gz')
CUTS = [math.inf, 1.0, 0.5, 0.25]
HOLDS_MS = [0, 30, 60, 120]
FLOOR = 60
BASES = [('a', 220, 0.5), ('b', 50, 0.25)]


def rescue_spans(path, horizon):
    if os.path.exists(CACHE):
        saved = json.load(gzip.open(CACHE, 'rt'))
        return {float(k) if k != 'inf' else math.inf: [tuple(x) for x in v] for k, v in saved.items()}
    obs = {c: [] for c in CUTS}
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for line in stream:
            frame = _frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            cands = {} if frame['quiet'] else _candidates(frame)
            for c in CUTS:
                obs[c].append((frame['sample'], rf.lane_notes(cands, c) if cands else set()))
    out = {}
    for c in CUTS:
        spans, _ = confirmation_spans(obs[c], sample_count=horizon, block_size=512)
        out[c] = union_spans(spans, sample_count=horizon)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with gzip.open(CACHE, 'wt') as stream:
        json.dump({('inf' if c == math.inf else str(c)): [list(s) for s in v] for c, v in out.items()}, stream)
    return out


def run_stats(spans, short_samples):
    n = len(spans)
    short = sum(1 for l, r, _ in spans if r - l < short_samples)
    return n, short


def run(path):
    base = json.load(open(ce.BASELINE))['datasets']['ordinary']
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets']['ordinary']
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed')
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, 'ordinary-bridge-events.json.gz'), 'rt'))
    arm_a = evidence['arm_spans']['A']
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, 'ordinary-consensus-spans.json.gz'), 'rt'))
    native = [tuple(x) for x in saved['native_confirmation']]
    native60 = union_spans([s for s in native if s[2] >= FLOOR], sample_count=horizon)
    arm_a60 = union_spans([s for s in arm_a if s[2] >= FLOOR], sample_count=horizon)
    support_an = union_spans([*arm_a, *native], sample_count=horizon)
    rescue = rescue_spans(path, horizon)
    s50, s100 = int(0.05 * rate), int(0.1 * rate)
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_u = union_spans(cur_spans, sample_count=horizon)
    cur_runs, cur_short50 = len(cur_u), run_stats(cur_u, s50)[1]
    cur_short100 = run_stats(cur_u, s100)[1]
    result = dict(horizon=horizon, current_runs=cur_runs,
                  current_short_share_50ms=round(cur_short50 / cur_runs, 4), current_short_share_100ms=round(cur_short100 / cur_runs, 4),
                  lane_spans_runs={}, variants={})
    for c in CUTS:
        n, sh = run_stats(rescue[c], s50)
        result['lane_spans_runs'][str(c)] = dict(runs=n, short_share_50ms=round(sh / n, 4) if n else 0.0)

    def supported(c, d):
        held_a = dil.dilate(arm_a60, int(d * rate / 1000), horizon)
        return union_spans([*native60, *intersect_spans(rescue[c], held_a, sample_count=horizon)], sample_count=horizon)

    sup_lane = supported(0.5, 220)
    n, sh = run_stats(sup_lane, s50)
    result['lane_spans_runs']['supported c=0.5 D=220 (lane only)'] = dict(runs=n, short_share_50ms=round(sh / n, 4))
    for tag, d, c in BASES:
        filt = intersect_spans(cur_spans, dil.dilate(support_an, int(d * rate / 1000), horizon), sample_count=horizon)
        lane0 = supported(c, d)
        for h in HOLDS_MS:
            lane = dil.dilate(lane0, int(h * rate / 1000), horizon) if h else lane0
            spans = union_spans([*filt, *lane], sample_count=horizon)
            hybrid = score(spans, labels, **clock)
            cmp = compare(current, hybrid)
            t = hybrid['pitch_sets']['totals']
            gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
            false = t['extra_pitch_voice_samples'] + gap
            losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
            n, s50n = run_stats(spans, s50)
            s100n = run_stats(spans, s100)[1]
            result['variants'][f'{tag}: D{d} supported c={c}, lane hold {h} ms'] = dict(
                coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
                precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
                wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'], gap_delta=gap - cg,
                exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
                all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
                false_change_pct_of_current=round(100 * (false - (ct['extra_pitch_voice_samples'] + cg)) / (ct['extra_pitch_voice_samples'] + cg), 2),
                labels_losing_present_or_longest=len(losing),
                runs=n, runs_vs_current_pct=round(100 * (n - cur_runs) / cur_runs, 2),
                runs_under_50ms=s50n, runs_under_100ms=s100n,
                short50_share=round(s50n / n, 4), short100_share=round(s100n / n, 4),
                no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    print('current_runs', out['current_runs'], 'short share 50/100 ms', out['current_short_share_50ms'], out['current_short_share_100ms'])
    print('lane spans', json.dumps(out['lane_spans_runs']))
    for name, row in out['variants'].items():
        print(name, json.dumps(row))
