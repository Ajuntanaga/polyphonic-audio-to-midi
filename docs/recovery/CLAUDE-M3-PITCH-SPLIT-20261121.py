"""Fixed pitch-range partition, scored on saved spans only (no audio, no model, no job).

PRE-REGISTRATION, written 2026-11-21 ~02:00 PST, BEFORE any pitch-resolved arm span was opened.
What I had already seen: Codex's aggregates and label-weighted bands in the cached-bridge
report.json (run 44891340815), the baseline CURRENT report, and nothing at pitch resolution.

Candidate (frozen): hybrid H_X = CURRENT spans with MIDI < 60  +  arm X spans with MIDI >= 60.
60 is frozen. No per-label selection, no timing shift, no split sweep. Primary arm X = A (the
measured FIFO completion clock, the only arm that is causally deliverable). B (block availability)
and C (nominal stream grid) are diagnostic columns. F (saved upstream notes) is a NONCAUSAL
reference column only. Same two corpora, common horizon, same score()/compare() as the bridge.

Expectations declared in advance (each can fail):
 E1  ordinary H_A present_pitch_samples == 6690873+6292681+5408846+2949359 == 21,341,759
     (63.10% of 33,819,101): the label-weighted bands in the report add up exactly because no two
     ordinary labels share a pitch. Extended-middle H_A present == CURRENT == 2,021,510, because all
     six middle labels sit in 48-59.
 E2  By construction, per-label present/longest/segments/first-delay of every label < 60 equal
     CURRENT's and every label >= 60 equal A's. "Lower-band preservation" is therefore exact for
     those four fields and is NOT evidence about false output or exact pitch sets, which couple
     pitches. The check below confirms it rather than assuming it.
 E3  Extended-middle: the hybrid cannot gain on any label. Its wrong-pitch/gap samples exceed
     CURRENT's by exactly A's >=60 output on that recording (>= 0), and it forfeits A's middle-band
     improvement (A: wrong-pitch 261,056 vs CURRENT 528,259). So the middle corpus can only show a
     cost of the split, never a gain.
 E4  Ordinary false output: CURRENT emits almost nothing >= 60, so the hybrid's >=60 false output
     is A's. I expect H_A wrong-pitch samples to land BETWEEN A (3,008,188) and CURRENT (7,808,309)
     and nearer CURRENT, and H_A exact_pitch_set to land BELOW A's 882,053, because the split keeps
     CURRENT's below-60 wrong pitches that A removes.
 E5  Upper-band cost per unit gain: (extra + gap added at >=60 by A over CURRENT) / (present
     gained at >=60) is reported next to A's whole-band ratio (3,008,188+3,568,575)/18,583,289=0.354.
 E6  no_pitch_safety_regression is reported verbatim from compare(); I do not predict its value.
 Nothing here is promoted, installed or a release candidate. Pitch occupancy does not establish
 lane assignment, unison multiplicity, callback deadlines or live-host delivery.

Usage: python3 -I CLAUDE-M3-PITCH-SPLIT-20261121.py [EVIDENCE_DIR]
  without EVIDENCE_DIR: CURRENT-only self-test of the per-pitch decomposition against the report.
  with EVIDENCE_DIR (holding <name>-bridge-events.json.gz): the full split analysis, writing
  CLAUDE-M3-PITCH-SPLIT-20261121.json beside this file.
"""
import gzip
import hashlib
import json
import os
import statistics
import sys

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJ)
from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402

SPLIT = 60
REPORT = os.path.join(PROJ, 'build/github-results/basic-pitch-cached-44891340815/'
                      'basic-pitch-cached-result/report/report.json')
BASELINE = os.path.join(PROJ, 'docs/recovery/basic-pitch-baseline-20261121.json')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CLAUDE-M3-PITCH-SPLIT-20261121.json')
SAMPLE_RATE = 96000
MIN_NOTE_SAMPLES = 127.7 * SAMPLE_RATE / 1000  # upstream minimum_note_length
BANDS = (('lt60', 0, 59), ('ge60', 60, 127), ('below48', 0, 47), ('48to59', 48, 59),
         ('60to71', 60, 71), ('72plus', 72, 127))


def merged(intervals):
    out = []
    for left, right in sorted(intervals):
        if out and left <= out[-1][1]:
            out[-1][1] = max(out[-1][1], right)
        else:
            out.append([left, right])
    return out


def length(items):
    return sum(r - l for l, r in items)


def inter(a, b):
    i = j = total = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        total += max(0, hi - lo)
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def decompose(spans, labels, horizon):
    """Per-pitch present / wrong-pitch / gap samples, additive over pitch, same definitions
    as _pitch_set_coverage (expected, present, extra_pitch_voice, unlabeled gap)."""
    expected, every = {}, []
    for row in labels:
        expected.setdefault(row['midi_note'], []).append((row['start_sample'], row['end_sample']))
        every.append((row['start_sample'], row['end_sample']))
    expected = {p: merged(v) for p, v in expected.items()}
    annotated = merged(every)
    active = {}
    for left, right, note in union_spans([tuple(s) for s in spans], sample_count=horizon):
        active.setdefault(note, []).append([left, right])
    rows = {}
    for p in sorted(set(expected) | set(active)):
        act, exp = active.get(p, []), expected.get(p, [])
        within = inter(act, annotated)
        present = inter(act, exp)
        rows[p] = dict(expected=length(exp), present=present, extra=within - present,
                       gap=length(act) - within)
    bands = {}
    for name, low, high in BANDS:
        keys = [p for p in rows if low <= p <= high]
        bands[name] = {k: sum(rows[p][k] for p in keys) for k in ('expected', 'present', 'extra', 'gap')}
    return dict(per_pitch={str(p): v for p, v in rows.items()}, bands=bands,
                totals={k: sum(r[k] for r in rows.values()) for k in ('expected', 'present', 'extra', 'gap')})


def check_decomposition(decomp, measurement, name):
    totals, pitch = decomp['totals'], measurement['pitch_sets']
    want = dict(expected=pitch['totals']['expected_pitch_samples'],
                present=pitch['totals']['present_pitch_samples'],
                extra=pitch['totals']['extra_pitch_voice_samples'],
                gap=pitch['unlabeled_gap_voice_samples'])
    if totals != want:
        raise ValueError(f'Per-pitch decomposition does not reproduce score() for {name}: {totals} vs {want}')
    return True


def lifecycle(spans, horizon):
    """Raw attack/release validity per band, from the raw (not unioned) span pairs."""
    result = {}
    for band, low, high in BANDS[:2]:
        rows = sorted((n, l, r) for l, r, n in map(tuple, spans) if low <= n <= high)
        durations = sorted(r - l for _, l, r in rows)
        overlaps = short_reattack = 0
        for (n0, l0, r0), (n1, l1, r1) in zip(rows, rows[1:]):
            if n0 == n1:
                overlaps += l1 < r0
                short_reattack += 0 <= l1 - r0 < MIN_NOTE_SAMPLES
        ms = lambda v: None if v is None else round(v * 1000 / SAMPLE_RATE, 2)
        q = lambda f: durations[min(len(durations) - 1, int(f * len(durations)))] if durations else None
        result[band] = dict(raw_spans=len(rows), pitches=len({n for n, _, _ in rows}),
            shortest_ms=ms(durations[0] if durations else None), p10_ms=ms(q(.1)),
            median_ms=ms(q(.5)), p90_ms=ms(q(.9)),
            spans_shorter_than_127_7ms=sum(d < MIN_NOTE_SAMPLES for d in durations),
            same_pitch_overlaps=overlaps, same_pitch_reattack_within_127_7ms=short_reattack,
            open_at_horizon=sum(r == horizon for _, _, r in rows))
    return result


def label_summary(current, other, hybrid):
    """Per-label outcomes of the hybrid, lower (<60) and upper (>=60) labels kept apart."""
    out = {}
    for side, keep in (('lower_lt60', lambda n: n < SPLIT), ('upper_ge60', lambda n: n >= SPLIT)):
        idx = [i for i, row in enumerate(current['labels']) if keep(row['midi_note'])]
        def tally(ref, cand):
            d = [cand['labels'][i]['present_samples'] - ref['labels'][i]['present_samples'] for i in idx]
            return dict(gained=sum(v > 0 for v in d), lost=sum(v < 0 for v in d), unchanged=sum(v == 0 for v in d))
        zero = lambda m: sum(m['labels'][i]['present_samples'] == 0 and m['labels'][i]['annotated_samples'] > 0 for i in idx)
        delays = lambda m: [m['labels'][i]['first_present_delay_samples'] for i in idx
                            if m['labels'][i]['first_present_delay_samples'] is not None]
        med = lambda v: None if not v else round(statistics.median(v) * 1000 / SAMPLE_RATE, 2)
        out[side] = dict(labels=len(idx),
            annotated_samples=sum(current['labels'][i]['annotated_samples'] for i in idx),
            present=dict(current=sum(current['labels'][i]['present_samples'] for i in idx),
                         arm=sum(other['labels'][i]['present_samples'] for i in idx),
                         hybrid=sum(hybrid['labels'][i]['present_samples'] for i in idx)),
            hybrid_vs_current=tally(current, hybrid), hybrid_vs_arm=tally(other, hybrid),
            labels_with_zero_present=dict(current=zero(current), arm=zero(other), hybrid=zero(hybrid)),
            median_first_present_delay_ms=dict(current=med(delays(current)), arm=med(delays(other)),
                                               hybrid=med(delays(hybrid))))
    return out


def compact(m):
    t = m['pitch_sets']['totals']
    return dict(present=t['present_pitch_samples'], expected=t['expected_pitch_samples'],
                coverage_percent=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
                exact_pitch_set=t['exact_pitch_set_samples'], wrong_pitch=t['extra_pitch_voice_samples'],
                gap=m['pitch_sets']['unlabeled_gap_voice_samples'])


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        h.update(stream.read())
    return h.hexdigest()


def run(evidence_dir):
    report = json.load(open(REPORT))
    baseline = json.load(open(BASELINE))
    result = dict(schema='claude_m3_pitch_split_v1', split=SPLIT, evidence_dir_given=bool(evidence_dir),
                  report_sha256=sha(REPORT), datasets={})
    for name, data in report['datasets'].items():
        base = baseline['datasets'][name]
        horizon = data['common_support']['sample_count']
        clock = dict(sample_count=horizon, sample_rate=SAMPLE_RATE)
        labels, clipping = clip_labels(labels_from_measurement(base['measurement']), horizon)
        current_spans = clip_spans(base['pitch_spans'], horizon)
        current = score(current_spans, labels, **clock)
        if current != data['current_measurement']:
            raise ValueError(name + ': CURRENT does not reproduce the bridge report')
        row = dict(horizon=horizon, current_reproduces_report=True,
                   current_decomposition_matches_score=check_decomposition(
                       decompose(current_spans, labels, horizon), current, name + ' CURRENT'))
        result['datasets'][name] = row
        if not evidence_dir:
            continue
        path = os.path.join(evidence_dir, name + '-bridge-events.json.gz')
        pin = data['evidence']
        if os.path.getsize(path) != pin['bytes'] or sha(path) != pin['sha256']:
            raise ValueError(name + ': evidence file differs from the report pin')
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            evidence = json.load(stream)
        if evidence['common_horizon'] != horizon:
            raise ValueError(name + ': horizon differs')
        arms = {arm: [tuple(s) for s in spans] for arm, spans in evidence['arm_spans'].items()}
        measured = {arm: score(spans, labels, **clock) for arm, spans in arms.items()}
        row['arm_spans_reproduce_report'] = {arm: measured[arm] == data['measurements'][arm] for arm in measured}
        if not all(row['arm_spans_reproduce_report'].values()):
            raise ValueError(name + ': evidence spans do not reproduce the report: ' + str(row['arm_spans_reproduce_report']))
        hybrids, scores = {}, {'CURRENT': current}
        for arm in 'ABCF':
            hybrids[arm] = ([s for s in current_spans if s[2] < SPLIT] + [s for s in arms[arm] if s[2] >= SPLIT])
            scores[arm], scores['H_' + arm] = measured[arm], score(hybrids[arm], labels, **clock)
        row['compact'] = {k: compact(v) for k, v in scores.items()}
        row['decomposition'] = {}
        for key, spans in (('CURRENT', current_spans), ('A', arms['A']), ('H_A', hybrids['A'])):
            d = decompose(spans, labels, horizon)
            check_decomposition(d, scores[key], name + ' ' + key)
            row['decomposition'][key] = dict(bands=d['bands'], per_pitch=d['per_pitch'])
        up = lambda k: row['decomposition'][k]['bands']['ge60']
        gained = up('A')['present'] - up('CURRENT')['present']
        added = (up('A')['extra'] + up('A')['gap']) - (up('CURRENT')['extra'] + up('CURRENT')['gap'])
        a_total = scores['A']['pitch_sets']
        row['upper_band_cost'] = dict(present_gained=gained, wrong_plus_gap_added=added,
            added_per_gained=None if not gained else round(added / gained, 4),
            arm_A_whole_band_ratio=round((a_total['totals']['extra_pitch_voice_samples']
                + a_total['unlabeled_gap_voice_samples']) / a_total['totals']['present_pitch_samples'], 4))
        row['compare_hybrid_to_current'] = {arm: {k: v for k, v in compare(current, scores['H_' + arm]).items()
                                                  if k not in ('label_deltas', 'label_changes')}
                                            for arm in 'ABCF'}
        row['compare_hybrid_to_A'] = {k: v for k, v in compare(measured['A'], scores['H_A']).items()
                                      if k not in ('label_deltas', 'label_changes')}
        row['labels'] = label_summary(current, measured['A'], scores['H_A'])
        row['per_label_H_A'] = [dict(label_index=c['label_index'], midi_note=c['midi_note'],
            annotated=c['annotated_samples'], current=c['present_samples'], A=a['present_samples'],
            hybrid=h['present_samples'], hybrid_longest=h['longest_present_samples'],
            hybrid_segments=h['present_segments'], hybrid_first_delay=h['first_present_delay_samples'])
            for c, a, h in zip(current['labels'], measured['A']['labels'], scores['H_A']['labels'])]
        row['lower_labels_identical_to_current'] = all(
            h['present_samples'] == c['present_samples'] and h['longest_present_samples'] == c['longest_present_samples']
            and h['present_segments'] == c['present_segments']
            and h['first_present_delay_samples'] == c['first_present_delay_samples']
            for c, h in zip(current['labels'], scores['H_A']['labels']) if c['midi_note'] < SPLIT)
        row['upper_labels_identical_to_A'] = all(
            h['present_samples'] == a['present_samples'] and h['longest_present_samples'] == a['longest_present_samples']
            and h['present_segments'] == a['present_segments']
            and h['first_present_delay_samples'] == a['first_present_delay_samples']
            for a, h in zip(measured['A']['labels'], scores['H_A']['labels']) if a['midi_note'] >= SPLIT)
        row['lifecycle'] = dict(CURRENT_raw=lifecycle(base['pitch_spans'] if False else current_spans, horizon),
                                A_raw=lifecycle(arms['A'], horizon), event_audit_A=data['event_audits']['A'])
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1] if len(sys.argv) > 1 else None)
    for name, row in out['datasets'].items():
        print(name, 'horizon', row['horizon'], 'CURRENT reproduces report:', row['current_reproduces_report'],
              '| per-pitch decomposition == score():', row['current_decomposition_matches_score'])
        if 'compact' in row:
            for key, value in row['compact'].items():
                print('  %-8s' % key, value)
