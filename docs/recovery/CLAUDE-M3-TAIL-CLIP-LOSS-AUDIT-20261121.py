"""Audit of the tail-clip result: what the 31+5 lost labels lose, and how causal the rule is.  Saved spans only.

DECLARED AS AN AUDIT, NOT A CANDIDATE.  Written 2026-11-21 ~00:35 PST AFTER the tail-clip result
(CLAUDE-M3-TAIL-CLIP-CANDIDATE-20261121) was seen: ordinary lower band clipped 199 of 517 CURRENT spans,
H_T false output 8,257,342 vs CURRENT 11,429,794, gap delta +162,357, 31 lower + 5 upper labels lose present.
Nothing here may be used to pick a threshold.  Two questions:

 Q1  How big are the per-label losses?  Guess (can fail): median loss per lost lower label above 50 ms, i.e.
     real mid-note A dropouts and not one-frame boundary noise; at least one label loses over 500 ms.
 Q2  The primary rule ends a CURRENT span at the LATEST end of the overlapping A spans.  A real tracker at an
     A note-off does not know whether A will re-attack later inside the same CURRENT span, so that rule peeks
     ahead whenever a clipped span overlaps two or more A spans.  How often, and what does the strictly
     causal variant V2 (cut at the FIRST A note-off that falls inside the CURRENT span, no revival) cost?
     Guess (can fail): fewer than 20% of clipped spans have 2+ overlapping A spans, and V2 removes less false
     output and loses more present than the primary rule.

The V2 rule is reported once as a bound.  It is not tuned, not swept, not recommended on this evidence alone.
Pitch occupancy only: no lane, unison, callback-deadline or live-host claim.

Usage: python3 -I CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121.py EVIDENCE_DIR
"""
import gzip
import importlib.util
import json
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('tail', os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-CANDIDATE-20261121.py'))
tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail)
split = tail.split
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score  # noqa: E402

OUT = os.path.join(HERE, 'CLAUDE-M3-TAIL-CLIP-LOSS-AUDIT-20261121.json')
MS = lambda v: round(v * 1000 / split.SAMPLE_RATE, 1)


def clip_first(current_spans, a_spans):
    """V2: end at the first overlapping A note-off strictly inside (left, right)."""
    by_pitch = defaultdict(list)
    for left, right, note in a_spans:
        by_pitch[note].append((left, right))
    out = []
    for left, right, note in current_spans:
        if note >= split.SPLIT:
            continue
        ends = [e for s, e in by_pitch.get(note, []) if s < right and left < e < right]
        out.append((left, min(ends) if ends else right, note))
    return out


def loss_rows(current, candidate):
    rows = []
    for a, b in zip(current['labels'], candidate['labels']):
        delta = b['present_samples'] - a['present_samples']
        if delta < 0 or b['longest_present_samples'] < a['longest_present_samples']:
            rows.append(dict(midi=a['midi_note'], start=a['start_sample'], annotated=a['annotated_samples'],
                             present_loss=-delta, present_current=a['present_samples'],
                             longest_loss=a['longest_present_samples'] - b['longest_present_samples']))
    return rows


def summarize(rows):
    lower = [r for r in rows if r['midi'] < split.SPLIT and r['present_loss'] > 0]
    losses = sorted(r['present_loss'] for r in lower)
    if not losses:
        return dict(lower_labels_lost=0)
    pick = lambda q: MS(losses[min(len(losses) - 1, int(q * len(losses)))])
    return dict(lower_labels_lost=len(lower), total_loss_samples=sum(losses), total_loss_ms=MS(sum(losses)),
                loss_ms=dict(min=MS(losses[0]), p25=pick(.25), median=MS(statistics.median(losses)), p75=pick(.75),
                             max=MS(losses[-1])),
                under_20ms=sum(l < .02 * split.SAMPLE_RATE for l in losses),
                over_500ms=sum(l > .5 * split.SAMPLE_RATE for l in losses),
                share_of_label_lost=round(statistics.median(
                    r['present_loss'] / max(1, r['present_current']) for r in lower), 3),
                by_pitch={str(m): sum(1 for r in lower if r['midi'] == m) for m in sorted({r['midi'] for r in lower})},
                longest_only=sum(1 for r in rows if r['midi'] < split.SPLIT and r['present_loss'] <= 0))


def run(evidence_dir):
    report = json.load(open(split.REPORT))
    baseline = json.load(open(split.BASELINE))
    result = dict(schema='claude_m3_tail_clip_audit_v1', datasets={})
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
        primary_lower, counts = tail.clip_lower(current_spans, a_spans)
        v2_lower = clip_first(current_spans, a_spans)
        primary = score(primary_lower + upper, labels, **clock)
        v2 = score(v2_lower + upper, labels, **clock)
        # look-ahead audit: how many CURRENT lower spans overlap 2+ A spans of their pitch, and how many of the
        # clipped ones.
        by_pitch = defaultdict(list)
        for s, e, p in a_spans:
            by_pitch[p].append((s, e))
        multi = clipped_multi = clipped = 0
        for left, right, note in current_spans:
            if note >= split.SPLIT:
                continue
            ov = [(s, e) for s, e in by_pitch.get(note, []) if s < right and e > left]
            if len(ov) >= 2:
                multi += 1
            if ov and max(e for _, e in ov) < right:
                clipped += 1
                clipped_multi += len(ov) >= 2
        row = dict(horizon=horizon, lower_spans=counts['lower_spans'], clipped=clipped, clipped_multi=clipped_multi,
                   multi_overlap_spans=multi,
                   primary=dict(compact=split.compact(primary), false=split.compact(primary)['wrong_pitch'] + split.compact(primary)['gap'],
                                summary=summarize(loss_rows(current, primary)),
                                gap_delta=compare(current, primary)['extra_gap_pitch_samples_delta']),
                   v2=dict(compact=split.compact(v2), false=split.compact(v2)['wrong_pitch'] + split.compact(v2)['gap'],
                           summary=summarize(loss_rows(current, v2)),
                           gap_delta=compare(current, v2)['extra_gap_pitch_samples_delta']),
                   top_primary_losses=sorted(loss_rows(current, primary), key=lambda r: -r['present_loss'])[:8])
        result['datasets'][name] = row
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    for name, row in out['datasets'].items():
        print('==', name, '| lower spans', row['lower_spans'], 'clipped', row['clipped'],
              'of which 2+ A overlaps', row['clipped_multi'], '| any 2+ overlap', row['multi_overlap_spans'])
        for key in ('primary', 'v2'):
            v = row[key]
            print(' ', key, 'false', v['false'], 'gap delta', v['gap_delta'], 'present', v['compact']['present'])
            print('    ', json.dumps(v['summary']))
        print('  top primary losses:', [(r['midi'], MS(r['present_loss']), MS(r['annotated'])) for r in row['top_primary_losses']])
