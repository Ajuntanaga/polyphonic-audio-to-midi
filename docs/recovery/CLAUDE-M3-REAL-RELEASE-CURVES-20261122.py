"""Real-audio release curves on the saved ONNX stream tapes of run 45029161409.  Saved arrays only; no model, audio or job.

The plan, definitions and predictions H1-H4 / C1 are fixed in CLAUDE-M3-REAL-RELEASE-CURVES-PROPOSAL-20261122.md (commit 1f3ee7b) plus its
Amendment 1 (window end backed off 100 ms from a next same-pitch start), both written before any tape was read.  This script implements them.

Usage:
  python3 -P -E CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py --selftest
  python3 -P -E CLAUDE-M3-REAL-RELEASE-CURVES-20261122.py UNMODIFIED_DIR ADAPTED_DIR [OUT.json]
    each DIR holds ordinary-stream.npz, ordinary-events.json, extended-middle-stream.npz, extended-middle-events.json
"""
import gzip
import hashlib
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

MODEL_RATE, SOURCE_RATE, FRAME_HOP = 22050, 96000, 256
THRESHOLD = 0.3
RELEASE_RUN = 3
MIN_SPAN_MS, MIN_WINDOW_MS, MAX_WINDOW_MS, BACKOFF_MS = 100, 120, 1000, 100
PLATEAU = (-2, 0)          # frames g-2..g (registered)
EARLY_PLATEAU = (-10, -8)  # frames g-10..g-8 (post hoc)
FALL_FRACTION = 0.9
LONG_WINDOW_MS = 300
H1_SHARE, H1_ADAPTED_MEDIAN, H1_ORIGINAL_MEDIAN = 0.70, 0.9, 0.85
H2_SHARE, H2_MEDIAN_MS = 0.60, 2 * FRAME_HOP / MODEL_RATE * 1000
H3_SHARE = 0.60
H4_MARGIN_MS, H4_MIN_PAIRS = 20.0, 15
C1_POINTS = 20.0


def ms_samples(ms):
    return ms * SOURCE_RATE // 1000


def frame_at_or_before(sample):
    return (sample * MODEL_RATE) // (SOURCE_RATE * FRAME_HOP)


def frame_ms_after(frame, end_sample):
    return (FRAME_HOP * frame / MODEL_RATE - end_sample / SOURCE_RATE) * 1000


def union_by_pitch(labels):
    """Merge labels at the same MIDI note (any string) into non-overlapping spans, sorted."""
    by_note = {}
    for row in labels:
        by_note.setdefault(row['midi_note'], []).append((row['start_sample'], row['end_sample']))
    result = {}
    for note, spans in by_note.items():
        merged = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        result[note] = [tuple(x) for x in merged]
    return result


def label_ends(labels, horizon):
    """Every union-span end before the horizon, with its window and the number of other-pitch spans sounding at the end."""
    unions = union_by_pitch(labels)
    rows = []
    for note, spans in unions.items():
        for i, (start, end) in enumerate(spans):
            if end >= horizon:
                continue
            following = spans[i + 1][0] if i + 1 < len(spans) else None
            limit = horizon if following is None else following - ms_samples(BACKOFF_MS)
            window = min(limit, end + ms_samples(MAX_WINDOW_MS), horizon)
            others = sum(1 for n, s in unions.items() if n != note for a, b in s if a <= end < b)
            rows.append(dict(midi_note=note, start=start, end=end, window=window, others=others,
                             evaluable=(end - start >= ms_samples(MIN_SPAN_MS) and window - end >= ms_samples(MIN_WINDOW_MS))))
    return sorted(rows, key=lambda r: (r['end'], r['midi_note']))


def measure_end(note, row):
    """note: (N,88) tape.  Returns the registered per-arm measures for one label end."""
    column = note[:, row['midi_note'] - 21]
    g = frame_at_or_before(row['end'])
    last = min(frame_at_or_before(row['window']), len(column) - 1)
    if g + PLATEAU[0] < 0 or g + EARLY_PLATEAU[0] < 0 or g >= len(column):
        return None
    plateau = float(np.mean(column[g + PLATEAU[0]:g + PLATEAU[1] + 1]))
    early = float(np.mean(column[g + EARLY_PLATEAU[0]:g + EARLY_PLATEAU[1] + 1]))
    release = next((f for f in range(g + 1, last - 1) if (column[f:f + RELEASE_RUN] < THRESHOLD).all()), None)
    out = dict(plateau=plateau, early_plateau=early, detected=plateau >= THRESHOLD, last_frame=last)
    if release is None:
        out.update(censored=True, delay_ms=frame_ms_after(last, row['end']), release_frame=None)
    else:
        out.update(censored=False, delay_ms=frame_ms_after(release, row['end']), release_frame=release)
    start = next((f for f in range(g + 1, last + 1) if column[f] < FALL_FRACTION * plateau), None)
    out['fall_frames'] = None if (not out['detected'] or start is None or release is None) else release - start
    return out


def pair_direction(adapted, original):
    """+1 adapted later, -1 adapted earlier, 0 tie, None not evaluable (the probe's rule: only bounds that prove count)."""
    a, o = adapted, original
    if not a['censored'] and not o['censored']:
        return (a['delay_ms'] > o['delay_ms'] + 1e-9) - (a['delay_ms'] < o['delay_ms'] - 1e-9)
    if a['censored'] and not o['censored']:
        return 1 if a['delay_ms'] >= o['delay_ms'] - 1e-9 and a['delay_ms'] > o['delay_ms'] + 1e-9 else None
    if o['censored'] and not a['censored']:
        return -1 if o['delay_ms'] > a['delay_ms'] + 1e-9 else None
    return None


def sign_p(k, n):
    """Exact two-sided binomial p-value at p=0.5 (descriptive only)."""
    if n == 0:
        return None
    low = min(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(low + 1)) / 2 ** n)


def median(values):
    return float(np.median(values)) if len(values) else None


def share(count, total):
    return None if not total else count / total


def analyse(tapes, labels, horizon):
    """tapes: {'unmodified': (N,88), 'adapted': (N,88)}.  Returns the registered tables for one corpus."""
    ends = [r for r in label_ends(labels, horizon) if r['evaluable']]
    rows = []
    for r in ends:
        m = {arm: measure_end(note, r) for arm, note in tapes.items()}
        if any(v is None for v in m.values()):
            continue
        rows.append(dict(r, **{arm: v for arm, v in m.items()}))
    paired = [r for r in rows if r['unmodified']['detected'] and r['adapted']['detected']]
    result = dict(ends_total=len(label_ends(labels, horizon)), evaluable=len(rows), paired=len(paired),
                  detected_unmodified=sum(r['unmodified']['detected'] for r in rows),
                  detected_adapted=sum(r['adapted']['detected'] for r in rows))

    # H1: plateau
    higher = sum(r['adapted']['plateau'] > r['unmodified']['plateau'] for r in paired)
    lower = sum(r['adapted']['plateau'] < r['unmodified']['plateau'] for r in paired)
    result['H1'] = dict(adapted_higher=higher, adapted_lower=lower, share_higher=share(higher, higher + lower),
                        sign_p=sign_p(higher, higher + lower),
                        median_adapted=median([r['adapted']['plateau'] for r in paired]),
                        median_unmodified=median([r['unmodified']['plateau'] for r in paired]),
                        early_median_adapted=median([r['adapted']['early_plateau'] for r in paired]),
                        early_median_unmodified=median([r['unmodified']['early_plateau'] for r in paired]))
    h = result['H1']
    h['verdict'] = ('pass' if h['share_higher'] is not None and h['share_higher'] >= H1_SHARE and h['median_adapted'] >= H1_ADAPTED_MEDIAN
                    and h['median_unmodified'] <= H1_ORIGINAL_MEDIAN else 'miss')

    # H2: hold
    directions = [(pair_direction(r['adapted'], r['unmodified']), r) for r in paired]
    later = sum(d == 1 for d, _ in directions)
    earlier = sum(d == -1 for d, _ in directions)
    ties = sum(d == 0 for d, _ in directions)
    unevaluable = sum(d is None for d, _ in directions)
    uncensored = [r for r in paired if not r['adapted']['censored'] and not r['unmodified']['censored']]
    diffs = [r['adapted']['delay_ms'] - r['unmodified']['delay_ms'] for r in uncensored]
    result['H2'] = dict(adapted_later=later, adapted_earlier=earlier, tied=ties, not_evaluable=unevaluable,
                        share_later=share(later, later + earlier), sign_p=sign_p(later, later + earlier),
                        uncensored_pairs=len(uncensored), median_difference_ms=median(diffs),
                        censored_adapted=sum(r['adapted']['censored'] for r in paired),
                        censored_unmodified=sum(r['unmodified']['censored'] for r in paired))
    h = result['H2']
    h['verdict'] = ('pass' if h['share_later'] is not None and h['share_later'] >= H2_SHARE and h['median_difference_ms'] is not None
                    and h['median_difference_ms'] >= H2_MEDIAN_MS else 'miss')

    # H3: shape
    both = [r for r in paired if r['adapted']['fall_frames'] is not None and r['unmodified']['fall_frames'] is not None]
    shorter = sum(r['adapted']['fall_frames'] < r['unmodified']['fall_frames'] for r in both)
    longer = sum(r['adapted']['fall_frames'] > r['unmodified']['fall_frames'] for r in both)
    result['H3'] = dict(pairs_with_fall=len(both), adapted_shorter=shorter, adapted_longer=longer,
                        share_shorter=share(shorter, shorter + longer), sign_p=sign_p(shorter, shorter + longer),
                        median_fall_adapted=median([r['adapted']['fall_frames'] for r in both]),
                        median_fall_unmodified=median([r['unmodified']['fall_frames'] for r in both]))
    h = result['H3']
    h['verdict'] = 'pass' if h['share_shorter'] is not None and h['share_shorter'] >= H3_SHARE else 'miss'

    # H4: polyphony
    def group_median(selector):
        values = [r['adapted']['delay_ms'] - r['unmodified']['delay_ms'] for r in uncensored if selector(r['others'])]
        return len(values), median(values)
    n0, m0 = group_median(lambda k: k == 0)
    n12, m12 = group_median(lambda k: 1 <= k <= 2)
    n3, m3 = group_median(lambda k: k >= 3)
    result['H4'] = dict(group_0=dict(pairs=n0, median_ms=m0), group_1_2=dict(pairs=n12, median_ms=m12), group_3_plus=dict(pairs=n3, median_ms=m3))
    h = result['H4']
    if n0 < H4_MIN_PAIRS or n3 < H4_MIN_PAIRS:
        h['verdict'] = 'not evaluated'
    else:
        h['verdict'] = 'pass' if m3 - m0 >= H4_MARGIN_MS else 'miss'
        h['difference_ms'] = m3 - m0

    # C1: censored share among long windows (all evaluable ends; paired-only shown as extra)
    long_rows = [r for r in rows if r['window'] - r['end'] >= ms_samples(LONG_WINDOW_MS)]
    long_paired = [r for r in paired if r['window'] - r['end'] >= ms_samples(LONG_WINDOW_MS)]
    cu = share(sum(r['unmodified']['censored'] for r in long_rows), len(long_rows))
    ca = share(sum(r['adapted']['censored'] for r in long_rows), len(long_rows))
    result['C1'] = dict(ends=len(long_rows), censored_share_unmodified=cu, censored_share_adapted=ca,
                        points=None if cu is None else 100 * (ca - cu),
                        paired_ends=len(long_paired),
                        paired_censored_unmodified=share(sum(r['unmodified']['censored'] for r in long_paired), len(long_paired)),
                        paired_censored_adapted=share(sum(r['adapted']['censored'] for r in long_paired), len(long_paired)))
    result['C1']['verdict'] = 'pass' if result['C1']['points'] is not None and result['C1']['points'] >= C1_POINTS else 'miss'
    return result, rows


def load_events(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt') as handle:
        return json.load(handle)['events']


def mapping_check(directory, corpus):
    """C0a/C0b: frame clock and decoder replay reproduce the saved events exactly."""
    from tools.basic_pitch_streaming import ForwardDecoder
    tape = np.load(os.path.join(directory, corpus + '-stream.npz'), allow_pickle=False)
    note, onset, frames = tape['note'], tape['onset'], tape['frames']
    c0a = bool((frames[:, 0] == np.arange(len(frames))).all() and (frames[:, 1] == FRAME_HOP * frames[:, 0]).all()
               and note.shape == onset.shape == (len(frames), 88))
    events_path = os.path.join(directory, corpus + '-events.json')
    if not os.path.exists(events_path):
        return dict(c0a=c0a, c0b=None, note='events file absent'), note
    saved = [(e['kind'], e['note'], e['frame']) for e in load_events(events_path)]
    decoder, replay = ForwardDecoder(), []
    for i in range(len(frames)):
        replay.extend((e['kind'], e['note'], e['frame']) for e in decoder.consume(note[i], onset[i], int(frames[i, 0])))
    return dict(c0a=c0a, c0b=replay == saved, frames=int(len(frames)), saved_events=len(saved), replay_events=len(replay)), note


def sha12(path):
    h = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:12]


def load_module(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(unmodified_dir, adapted_dir, out=None):
    support = load_module('asup', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py')
    report = dict(pins={}, mapping={}, corpora={})
    for corpus in ('ordinary', 'extended-middle'):
        tapes = {}
        for arm, directory in (('unmodified', unmodified_dir), ('adapted', adapted_dir)):
            check, note = mapping_check(directory, corpus)
            report['mapping'][arm + '/' + corpus] = check
            report['pins'][arm + '/' + corpus] = {f: sha12(os.path.join(directory, corpus + f)) for f in ('-stream.npz', '-events.json')
                                                  if os.path.exists(os.path.join(directory, corpus + f))}
            if not check['c0a'] or check['c0b'] is False:
                print(json.dumps(report, indent=1))
                raise SystemExit('Mapping check failed for %s/%s: no curve is read' % (arm, corpus))
            tapes[arm] = note
        ctx = support.dataset_context(corpus)
        result, rows = analyse(tapes, ctx['labels'], ctx['horizon'])
        result['tape_frames'] = {a: int(len(n)) for a, n in tapes.items()}
        result['horizon_samples'] = ctx['horizon']
        report['corpora'][corpus] = result
    text = json.dumps(report, indent=1)
    if out:
        open(out, 'w').write(text + '\n')
    print(text)


def selftest():
    """Definition checks on constructed tapes."""
    import tempfile

    n = 400
    SAMPLES_PER_FRAME = FRAME_HOP * SOURCE_RATE / MODEL_RATE          # 1114.557...

    def sample_of(frame):
        return math.ceil(frame * SAMPLES_PER_FRAME)

    # Frame and time conventions.
    for k in (0, 1, 10, 164, 399):
        assert frame_at_or_before(sample_of(k)) == k, k
        if k:
            assert frame_at_or_before(sample_of(k) - 1) == k - 1, k
        assert 0 <= frame_ms_after(k, sample_of(k)) * -1 < 0.011, k

    # Union and ends: strings at one pitch merge; a next start backs the window off 100 ms; others counts other pitches sounding at the end.
    labels = [dict(midi_note=40, start_sample=0, end_sample=19200), dict(midi_note=40, start_sample=9600, end_sample=28800),
              dict(midi_note=40, start_sample=96000, end_sample=120000), dict(midi_note=52, start_sample=5000, end_sample=60000)]
    unions = union_by_pitch(labels)
    assert unions[40] == [(0, 28800), (96000, 120000)] and unions[52] == [(5000, 60000)]
    ends = {(r['midi_note'], r['end']): r for r in label_ends(labels, horizon=200000)}
    first = ends[(40, 28800)]
    assert first['window'] == 96000 - ms_samples(BACKOFF_MS) and first['others'] == 1 and first['evaluable']
    assert ends[(52, 60000)]['others'] == 0 and ends[(52, 60000)]['window'] == 60000 + ms_samples(MAX_WINDOW_MS)   # 1000 ms cap
    last = ends[(40, 120000)]
    assert last['window'] == min(120000 + ms_samples(MAX_WINDOW_MS), 200000) and last['others'] == 0   # the horizon caps it
    assert not [r for r in label_ends(labels, horizon=120000) if r['end'] == 120000]      # an end at the horizon is not an end
    short = label_ends([dict(midi_note=40, start_sample=0, end_sample=9000)], horizon=200000)[0]
    assert not short['evaluable']                                                          # 93.75 ms long
    tight = label_ends([dict(midi_note=40, start_sample=0, end_sample=48000), dict(midi_note=40, start_sample=48000 + 20000, end_sample=90000)], 200000)[0]
    assert not tight['evaluable']                                                          # next start 208 ms away: window 108 ms

    # measure_end: a plateau, a linear fall, release run of three.
    note = np.zeros((n, 88), dtype=np.float32)
    column = note[:, 19]
    column[:100] = 0.9
    column[100:120] = np.linspace(0.9, 0, 20)
    end = sample_of(100) + 1
    row = dict(midi_note=40, start=sample_of(20), end=end, window=end + ms_samples(1000), others=0)
    m = measure_end(note, row)
    g = frame_at_or_before(end)
    assert g == 100 and abs(m['plateau'] - 0.9) < 1e-6 or g == 100
    expected = next(f for f in range(g + 1, 140) if (column[f:f + 3] < THRESHOLD).all())
    assert m['release_frame'] == expected and not m['censored'] and m['detected']
    assert abs(m['delay_ms'] - frame_ms_after(expected, end)) < 1e-9
    fall_start = next(f for f in range(g + 1, 140) if column[f] < FALL_FRACTION * m['plateau'])
    assert m['fall_frames'] == expected - fall_start

    # Censored: the tape never falls inside the window.
    note2 = np.zeros((n, 88), dtype=np.float32)
    note2[:, 19] = 0.9
    c = measure_end(note2, row)
    assert c['censored'] and c['release_frame'] is None and abs(c['delay_ms'] - frame_ms_after(c['last_frame'], end)) < 1e-9

    # Two frames below the threshold then back up is not a release; three is.
    note3 = np.zeros((n, 88), dtype=np.float32)
    note3[:, 19] = 0.9
    note3[110:112, 19] = 0.0
    assert measure_end(note3, row)['censored']
    note3[110:113, 19] = 0.0
    assert measure_end(note3, row)['release_frame'] == 110
    # Not detected at the end: low plateau, release is immediate, fall undefined.
    low = np.zeros((n, 88), dtype=np.float32)
    d = measure_end(low, row)
    assert not d['detected'] and d['fall_frames'] is None and d['release_frame'] == g + 1

    # Pair direction: only proving bounds count.
    u = dict(censored=False, delay_ms=100.0)
    assert pair_direction(dict(censored=False, delay_ms=150.0), u) == 1
    assert pair_direction(dict(censored=False, delay_ms=50.0), u) == -1
    assert pair_direction(dict(censored=False, delay_ms=100.0), u) == 0
    assert pair_direction(dict(censored=True, delay_ms=500.0), u) == 1
    assert pair_direction(dict(censored=True, delay_ms=50.0), u) is None
    assert pair_direction(dict(censored=False, delay_ms=50.0), dict(censored=True, delay_ms=500.0)) == -1
    assert pair_direction(dict(censored=False, delay_ms=600.0), dict(censored=True, delay_ms=500.0)) is None
    assert pair_direction(dict(censored=True, delay_ms=500.0), dict(censored=True, delay_ms=500.0)) is None

    # sign test.
    assert abs(sign_p(10, 10) - 2 / 1024) < 1e-12 and sign_p(5, 10) == 1.0 and sign_p(0, 0) is None

    # End to end: adapted sits higher, releases later (frame 73 against 59 after the start) and falls faster.
    rng_labels, orig, adap = [], np.zeros((4000, 88), dtype=np.float32), np.zeros((4000, 88), dtype=np.float32)
    for i in range(30):
        pitch = 40 + (i % 3) * 5
        t0 = 100 + i * 120
        rng_labels.append(dict(midi_note=pitch, start_sample=sample_of(t0), end_sample=sample_of(t0 + 40), string_mask=0, label_index=i))
        c = pitch - 21
        orig[t0:t0 + 40, c] = 0.8
        orig[t0 + 40:t0 + 40 + 30, c] = np.linspace(0.8, 0.0, 30)        # slow fall
        adap[t0:t0 + 70, c] = 0.99                                         # holds well past the original's release, saturated
        adap[t0 + 70:t0 + 74, c] = np.linspace(0.99, 0.0, 4)              # then falls in about 3 frames
    out, rows = analyse(dict(unmodified=orig, adapted=adap), rng_labels, horizon=sample_of(4000))
    assert out['evaluable'] == 30 and out['paired'] == 30, out
    assert out['H1']['verdict'] == 'pass' and out['H1']['share_higher'] == 1.0
    assert out['H2']['adapted_later'] == 30 and out['H2']['verdict'] == 'pass'
    assert out['H3']['verdict'] == 'pass' and out['H3']['adapted_shorter'] == 30
    assert out['H4']['verdict'] == 'not evaluated' and out['H4']['group_0']['pairs'] == 30
    assert out['C1']['ends'] == 30 and out['C1']['points'] == 0.0 and out['C1']['verdict'] == 'miss'   # nothing censored in 1000 ms windows
    out2, _ = analyse(dict(unmodified=adap, adapted=orig), rng_labels, horizon=sample_of(4000))
    assert out2['H2']['adapted_earlier'] == 30 and out2['H2']['verdict'] == 'miss' and out2['H1']['verdict'] == 'miss'

    # Mapping check: a decoder-consistent tape passes; a changed event list fails; a shifted frame clock fails.
    from tools.basic_pitch_streaming import ForwardDecoder
    frames = np.array([(i, FRAME_HOP * i, 0, 0) for i in range(60)], dtype=np.int64)
    nt = np.zeros((60, 88), dtype=np.float32)
    on = np.zeros((60, 88), dtype=np.float32)
    nt[10:30, 5] = 0.9
    on[10, 5] = 0.9
    dec, events = ForwardDecoder(), []
    for i in range(60):
        events.extend(dec.consume(nt[i], on[i], i))
    assert [e['kind'] for e in events] == ['on', 'off']
    with tempfile.TemporaryDirectory() as tmp:
        np.savez_compressed(os.path.join(tmp, 'x-stream.npz'), note=nt, onset=on, frames=frames, timing=np.zeros((1, 9), dtype=np.int64))
        json.dump(dict(events=events), open(os.path.join(tmp, 'x-events.json'), 'w'))
        check, _ = mapping_check(tmp, 'x')
        assert check['c0a'] and check['c0b'] is True and check['replay_events'] == 2, check
        json.dump(dict(events=events[:1]), open(os.path.join(tmp, 'x-events.json'), 'w'))
        assert mapping_check(tmp, 'x')[0]['c0b'] is False
        shifted = frames.copy()
        shifted[:, 1] += 1
        np.savez_compressed(os.path.join(tmp, 'x-stream.npz'), note=nt, onset=on, frames=shifted, timing=np.zeros((1, 9), dtype=np.int64))
        assert mapping_check(tmp, 'x')[0]['c0a'] is False
    print('selftest ok')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--selftest']:
        selftest()
    else:
        run(*sys.argv[1:4])
