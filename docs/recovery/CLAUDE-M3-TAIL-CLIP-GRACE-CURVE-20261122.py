"""Causal tail clip with a grace period: a curve on saved spans, not a candidate.  No audio, model run or job.

The tail-clip audit (CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121) found the strictly causal clip V2 (cut CURRENT's lower
span at the first overlapping A note-off, no revival) removes 7.5M false samples but loses 60 lower labels
(13.9% of lower present samples).  Mid-note A dropouts are the likely cost.  Here the cut is delayed by a grace
period g and cancelled if an A span of the same pitch is sounding at the cut time: at time e+g (e = the A note-off)
the tracker knows whether A re-attacked, so the rule is causal on A's own clock.  If cancelled, the search resumes at the
end of the A span that is sounding.  g = 0 is V2 (up to overlapping same-pitch A spans).

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; I give no clock time).
Already seen: the audit (V2 false 7,513,906; gap delta -225,325; 60 lower labels lose 1,808,214 samples), the
split report and the anatomy.  NOT seen: any grace result.  Fixed grid, one pass, no tuning: g in 0, 50, 100, 200,
300 ms.  CURRENT ordinary false (wrong + gap) = 11,429,794 and lower present 13,000,000-ish as in the audit.

Predictions, each can fail:
  T0  sanity: g = 0 reproduces the V2 false total (7,513,906) within 1% on the ordinary corpus.
  T1  at g = 200 ms, the number of lower labels that lose present samples is under half the g = 0 count.
  T2  at g = 200 ms, false output is still at least 25% below CURRENT (<= 8,572,345).
  T3  no grace in the grid passes the strict gate no_pitch_safety_regression on the ordinary corpus
      (it needs no lost label and a gap delta <= 0).
  T4  on extended-middle no grace loses any label.
Report the curve, whatever it shows.  Nothing here may be used to pick a threshold: the ordinary corpus is the
only corpus with a lower-band loss, so a choice would be tuned on its own evidence.  Pitch occupancy only: no lane,
unison, callback-deadline or live-host claim.

Usage: python3 -P -E CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122.py EVIDENCE_DIR
"""
import gzip
import importlib.util
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('audit', os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
tail = audit.tail
split = audit.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-GRACE-CURVE-20261122.json')
GRACES_MS = (0, 50, 100, 200, 300)


def clip_grace(current_spans, a_spans, grace):
    by_pitch = defaultdict(list)
    for left, right, note in a_spans:
        by_pitch[note].append((left, right))
    out = []
    for left, right, note in current_spans:
        if note >= split.SPLIT:
            continue
        spans = sorted(by_pitch.get(note, []))
        cut = right
        position = left
        while True:
            ends = sorted(e for s, e in spans if s < right and position < e < right)
            if not ends:
                break
            e = ends[0]
            when = e + grace
            if when >= right:
                break
            sounding = [(s, end) for s, end in spans if s <= when < end]
            if not sounding:
                cut = when
                break
            position = max(end for s, end in sounding)
        out.append((left, cut, note))
    return out


def run(evidence_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_tail_clip_grace_curve_v1', datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        clock = dict(sample_count=horizon, sample_rate=split.SAMPLE_RATE)
        labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
        current_spans = clip_spans(base['pitch_spans'], horizon)
        path = os.path.join(evidence_dir, name + '-bridge-events.json.gz')
        if os.path.getsize(path) != data['evidence']['bytes'] or split.sha(path) != data['evidence']['sha256']:
            raise ValueError(name + ': evidence differs from pin')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            a_spans = [tuple(s) for s in json.load(stream)['arm_spans']['A']]
        upper = [s for s in a_spans if s[2] >= split.SPLIT]
        current = score(current_spans, labels, **clock)
        cur = split.compact(current)
        cur_false = cur['wrong_pitch'] + cur['gap']
        rows = []
        for ms in GRACES_MS:
            grace = int(round(ms * split.SAMPLE_RATE / 1000))
            cand = score(clip_grace(current_spans, a_spans, grace) + upper, labels, **clock)
            c = split.compact(cand)
            cmp = compare(current, cand)
            summary = audit.summarize(audit.loss_rows(current, cand))
            lost = summary.get('total_loss_samples', 0)
            removed = cur_false - (c['wrong_pitch'] + c['gap'])
            rows.append(dict(grace_ms=ms, false=c['wrong_pitch'] + c['gap'], false_removed=removed,
                             gap_delta=cmp['extra_gap_pitch_samples_delta'], coverage_percent=c['coverage_percent'],
                             exact_pitch_set=c['exact_pitch_set'], strict_gate=bool(cmp['no_pitch_safety_regression']),
                             lower_labels_lost=summary.get('lower_labels_lost', 0), lower_present_lost=lost,
                             over_500ms=summary.get('over_500ms', 0),
                             false_removed_per_present_lost=None if not lost else round(removed / lost, 2)))
        result['datasets'][name] = dict(current_false=cur_false, current_present=cur['present'], curve=rows)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    for name, r in out['datasets'].items():
        print('==', name, 'CURRENT false', r['current_false'], 'present', r['current_present'])
        for row in r['curve']:
            print('  g', row['grace_ms'], 'ms |', {k: v for k, v in row.items() if k != 'grace_ms'})
