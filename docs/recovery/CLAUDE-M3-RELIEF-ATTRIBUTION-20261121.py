#!/usr/bin/env python3
"""Attribution of the rejected upper-fretted-relief screen from the collected evidence files (saved files only: no audio, no dispatch, no replay)

  python3 -I CLAUDE-M3-RELIEF-ATTRIBUTION-20261121.py PROJECT_ROOT OUT.json

Inputs (run 44881108478, ordinary@512, evidence artifact collected by Codex, sha256 3b6993ea...):
  build/github-results/upper-fretted-relief-44881108478/evidence/ordinary-current-on-512.tsv           (+ -midi.tsv.gz)
  build/github-results/upper-fretted-relief-44881108478/evidence/ordinary-upper-fretted-relief-on-512.tsv (+ -midi.tsv.gz)
Why: the aggregate deltas (matched +13,412, wrong-string +7,810, gap +3,704) are net numbers; my earlier statement that the 63% share equals the DP's
existing lane accuracy was an association between different denominators (Codex's correction, 2026-11-21). The per-label sections and the raw MIDI let us
measure the lane the newly voiced notes actually received.

DEFINITION CHECK (done BEFORE this script, on both TSVs, reported here so the definitions are not post hoc): per-label `observed_note_lane_masks` is a
  histogram mask:frames over the label's `labeled` frames (sums equal `labeled` for all 499 labels). matched = frames whose mask equals the label's
  string_mask exactly (sums 145,400 and 158,812 = totals rows). false_wrong_string_voices = sum over labels of lane_k for k NOT in string_mask (92,638 and
  100,448 = totals rows). One (label, lane) pair has lane_k != frames with bit k set in the histogram (not investigated; lane_k is not used below).
  Frame = 64 samples (snapshots). Quiet/none = mask 0.

PREDECLARED BEFORE ANY ATTRIBUTION NUMBER WAS COMPUTED (descriptive, associations only, one dataset and block, annotation is not audibility):
 PART A (per-label lane classes, histogram-level, so ORDER WITHIN A LABEL IS NOT OBSERVED; only net class changes per label are exact).
  Classes per label, from the histogram and e = label string_mask: none (m == 0); exact (m == e); wrong_only (m != 0 and m & e == 0);
  mixed (m & e != 0 and m != e). Delta = RELIEF - CURRENT per label per class (the four deltas sum to 0 within a label).
  A1 reconciliation: summed class deltas against the totals-row deltas (matched, false_wrong_string_voices).
  A2 sign-pattern table: for each label with any nonzero delta, the tuple of signs (none, exact, wrong_only, mixed) -> label count and summed deltas per class.
  A3 lane correctness of newly rendered frames: rendered = labeled - none. Cohort N = labels with delta rendered > 0. In N: sum delta exact, wrong_only, mixed,
     delta rendered; exact share = sum delta exact / sum delta rendered. Sub-cohort N0 = labels with CURRENT rendered == 0 (all new frames are none->x, no
     reassignment possible): same quantities, plus label counts with RELIEF wrong_only == 0 ("all new frames exact"), RELIEF exact == 0 ("none exact"), else mixed.
  A4 decreases (lower bounds on frames that changed away): sum over labels of max(0, -delta exact), of max(0, -delta wrong_only), of max(0, -delta rendered),
     and the number of labels each applies to.
  A5 wrong-lane growth by (annotated lane, observed lane): for labels whose string_mask has exactly one bit a, sum of delta lane_k for k != a, grouped by a and k
     (the +7,810 is the sum over all labels and k not in e of delta lane_k, multi-bit labels reported as a separate row). Direction: share of that growth on a
     string index above a (lower fret) vs below.
  A6 band: the same exact/wrong_only/mixed/rendered deltas by label midi_note band (<48, 48-59, 60-71, 72-84, >84).
  A7 concentration: labels sorted by delta wrong_only; number of labels (of those with positive delta) needed to reach 50% and 90% of the positive total; top 10
     labels with note, e, CURRENT and RELIEF histograms. The same for delta exact.
  A8 labels 13 and 56: full histograms, string_flips and longest_correct_run_ms in both configurations.
 PART B (MIDI, per pitch, no lane information exists in the MIDI).
  Intervals: events in sequence order; on/off paired FIFO per (voice_id, note); an unmatched on closes at the recording end (samples in the totals row).
  Coverage of a pitch = union of its intervals over all voices. Added = RELIEF coverage minus CURRENT coverage; removed = the reverse, in samples.
  Label windows = [start_sample, end_sample) per label with that label's midi_note. Location of an added sample range:
    same_label  : inside a window of a label with the SAME pitch
    other_label : inside no same-pitch window, but inside a window of a label of another pitch
    gap         : inside no label window at all
  Within `gap` and `other_label`: kind = prolongation if the added range starts within 512 samples after the end of a CURRENT same-pitch span, else new_onset.
  Reported: added/removed samples by location and kind (+ range counts), NoteOn counts per config by location of the onset sample, and per pitch the top 10
  pitches by added gap samples. Reconciliation: my gap total is compared in prose with the report's +238,421 gap samples; any difference is reported, not forced.
  Retriggers: for each label, NoteOn events of its pitch with onset in its window, CURRENT vs RELIEF; labels with an increase, sorted by increase (top 15);
  labels 13 and 56 listed in full (on/off sample pairs in both configs).
 Nothing is tuned or thresholded except the stated 512-sample adjacency; no rule is proposed; the relief predicate stays frozen and rejected.

AMENDMENT 1 (added after the first run; the first-run numbers of PART A and PART B above are unchanged and stay in the output):
  First-run observation that prompted it: all 20 added `gap` ranges were labelled new_onset by the adjacency-to-CURRENT rule, yet gap NoteOns rose by only 3
  (517 -> 520), so the rule mislabels continuations of notes that began inside a label window (the piece is cut at the window end, so it is not adjacent to a
  CURRENT span). Also every MIDI voice_id looked like the string index (first CURRENT event: note 58, voice 6, label string 6), which would give the MIDI a lane.
  C1 voice_id check: per config and label, samples of the label's pitch sounding on voice k inside the label window vs lane_k * 64; report the number of labels
     where all eight lanes agree within 1,024 samples (two blocks), and the summed absolute difference. If it does not hold, C2 is not interpreted.
  C2 gap kind, version 2: for each added gap piece, look at the unsplit added segment S it belongs to: `continuation` if S.start < piece.start (the segment began
     earlier, in a label window), else `fresh`; fresh pieces are `prolongation` if within 512 samples after a CURRENT same-pitch span end, else `new_onset`.
     Reported in samples and piece counts, and the same for other_label pieces.
  C3 hand-offs: per config and label, the label pitch's spans inside its window sorted by start; a hand-off = consecutive spans that touch (next.start - prev.end
     <= 512) on a DIFFERENT voice; a re-attack = consecutive spans on any voice separated by more than 512 samples. Reported: totals per config; for the cohort N0
     (labels never rendered in CURRENT but rendered in RELIEF) in RELIEF and for all labels with rendered frames in CURRENT: hand-offs per 1,000 rendered frames;
     for labels 13 and 56 the hand-off count against string_flips; and, over labels whose NoteOn count rose, how much of the rise is hand-offs vs re-attacks.
  Not tested (stated so it is not read as a finding): whether wrong-note output that relief removed was replaced by relief-added genuine notes. Gross wrong-note
  coverage changed by +172,813 / -125,658 samples (net +47,155), more churn than the +454-frame net suggests.
"""
import collections, csv, gzip, json, sys

PROJ, OUT = sys.argv[1:3]
csv.field_size_limit(10 ** 9)
D = PROJ + '/build/github-results/upper-fretted-relief-44881108478/evidence/'
CFG = {'cur': 'ordinary-current-on-512', 'rel': 'ordinary-upper-fretted-relief-on-512'}
CLS = ('none', 'exact', 'wrong_only', 'mixed')


def load(name):
    rows = list(csv.reader(open(D + name + '.tsv'), delimiter='\t'))
    tot = dict(zip(rows[0], rows[1]))
    h = rows[2]
    return tot, [dict(zip(h, r)) for r in rows[3:]]


def hist(s):
    out = {}
    for p in s.split(','):
        if p:
            m, f = p.split(':')
            out[int(m)] = int(f)
    return out


def classes(row):
    e = int(row['string_mask'])
    c = dict.fromkeys(CLS, 0)
    for m, f in hist(row['observed_note_lane_masks']).items():
        if m == 0:
            c['none'] += f
        elif m == e:
            c['exact'] += f
        elif not m & e:
            c['wrong_only'] += f
        else:
            c['mixed'] += f
    return c


def band(n):
    return '<48' if n < 48 else '48-59' if n < 60 else '60-71' if n < 72 else '72-84' if n <= 84 else '>84'


def sgn(x):
    return '+' if x > 0 else '-' if x < 0 else '0'


def part_a():
    tc, rc = load(CFG['cur']); tr, rr = load(CFG['rel'])
    assert len(rc) == len(rr)
    rep = {}
    lab = []
    for a, b in zip(rc, rr):
        assert a['label_index'] == b['label_index'] and a['string_mask'] == b['string_mask'] and a['midi_note'] == b['midi_note']
        ca, cb = classes(a), classes(b)
        d = {k: cb[k] - ca[k] for k in CLS}
        lab.append(dict(i=int(a['label_index']), note=int(a['midi_note']), e=int(a['string_mask']), start=int(a['start_sample']), end=int(a['end_sample']),
                        labeled=int(a['labeled']), cur=ca, rel=cb, d=d, ra=a, rb=b))
    tot = lambda k: sum(l['d'][k] for l in lab)
    rep['A1_reconciliation'] = dict(
        delta_exact=tot('exact'), totals_delta_matched=int(tr['matched']) - int(tc['matched']),
        delta_wrong_only=tot('wrong_only'), delta_mixed=tot('mixed'), delta_none=tot('none'),
        delta_wrong_lane_voices=sum(int(l['rb']['lane_%d' % k]) - int(l['ra']['lane_%d' % k]) for l in lab for k in range(8) if not l['e'] >> k & 1),
        totals_delta_false_wrong_string=int(tr['false_wrong_string_voices']) - int(tc['false_wrong_string_voices']),
        totals_delta_gap_frames=int(tr['false_gap_voices']) - int(tc['false_gap_voices']),
        totals_delta_wrong_note=int(tr['false_wrong_note_voices']) - int(tc['false_wrong_note_voices']))
    pat = collections.defaultdict(lambda: collections.Counter())
    for l in lab:
        if any(l['d'].values()):
            key = ','.join('%s%s' % (k, sgn(l['d'][k])) for k in CLS if l['d'][k])
            P = pat[key]
            P['labels'] += 1
            for k in CLS:
                P['d_' + k] += l['d'][k]
    rep['A2_sign_patterns'] = {k: dict(v) for k, v in sorted(pat.items(), key=lambda kv: -kv[1]['labels'])}

    def cohort(sel):
        S = collections.Counter()
        allx = wo0 = mid = 0
        for l in sel:
            S['labels'] += 1
            for k in CLS:
                S['d_' + k] += l['d'][k]
            S['d_rendered'] += -l['d']['none']
            if l['rel']['wrong_only'] == 0 and l['rel']['mixed'] == 0:
                allx += 1
            elif l['rel']['exact'] == 0:
                wo0 += 1
            else:
                mid += 1
        out = dict(S)
        out['exact_share_of_new_rendered'] = round(S['d_exact'] / S['d_rendered'], 4) if S['d_rendered'] else None
        out['labels_all_new_frames_exact'] = allx
        out['labels_no_exact'] = wo0
        out['labels_mixed'] = mid
        return out
    N = [l for l in lab if -l['d']['none'] > 0]
    N0 = [l for l in lab if l['labeled'] - l['cur']['none'] == 0 and -l['d']['none'] > 0]
    rep['A3_new_rendered_cohort_N'] = cohort(N)
    rep['A3_never_rendered_before_N0'] = cohort(N0)
    rep['A4_decreases'] = dict(
        labels_exact_down=sum(1 for l in lab if l['d']['exact'] < 0), frames_exact_down=sum(-l['d']['exact'] for l in lab if l['d']['exact'] < 0),
        labels_wrong_only_down=sum(1 for l in lab if l['d']['wrong_only'] < 0), frames_wrong_only_down=sum(-l['d']['wrong_only'] for l in lab if l['d']['wrong_only'] < 0),
        labels_rendered_down=sum(1 for l in lab if l['d']['none'] > 0), frames_rendered_down=sum(l['d']['none'] for l in lab if l['d']['none'] > 0))
    conf = collections.defaultdict(int)
    for l in lab:
        e = l['e']
        for k in range(8):
            if e >> k & 1:
                continue
            dv = int(l['rb']['lane_%d' % k]) - int(l['ra']['lane_%d' % k])
            if dv == 0:
                continue
            key = ('annotated_%d' % (e.bit_length() - 1)) if e and not e & (e - 1) else 'multi_bit_label'
            conf['%s->observed_%d' % (key, k)] += dv
    rep['A5_wrong_lane_growth'] = dict(sorted(conf.items(), key=lambda kv: -abs(kv[1])))
    up = down = 0
    for l in lab:
        e = l['e']
        if not e or e & (e - 1):
            continue
        a = e.bit_length() - 1
        for k in range(8):
            if k == a:
                continue
            dv = int(l['rb']['lane_%d' % k]) - int(l['ra']['lane_%d' % k])
            if k > a:
                up += dv
            else:
                down += dv
    rep['A5_direction_single_lane_labels'] = dict(higher_string_index_than_annotated=up, lower_string_index_than_annotated=down)
    bands = collections.defaultdict(collections.Counter)
    for l in lab:
        B = bands[band(l['note'])]
        B['labels'] += 1
        for k in CLS:
            B['d_' + k] += l['d'][k]
    rep['A6_by_band'] = {k: dict(v) for k, v in sorted(bands.items())}

    def conc(key):
        pos = sorted((l for l in lab if l['d'][key] > 0), key=lambda l: -l['d'][key])
        total = sum(l['d'][key] for l in pos)
        out = dict(positive_labels=len(pos), positive_total=total)
        run = 0
        for n, l in enumerate(pos, 1):
            run += l['d'][key]
            if 'labels_for_50pct' not in out and run >= 0.5 * total:
                out['labels_for_50pct'] = n
            if 'labels_for_90pct' not in out and run >= 0.9 * total:
                out['labels_for_90pct'] = n
        out['top10'] = [dict(label=l['i'], note=l['note'], e=l['e'], delta=l['d'][key], cur=l['ra']['observed_note_lane_masks'],
                             rel=l['rb']['observed_note_lane_masks']) for l in pos[:10]]
        return out
    rep['A7_concentration_wrong_only'] = conc('wrong_only')
    rep['A7_concentration_exact'] = conc('exact')
    rep['A8_labels_13_56'] = {str(l['i']): dict(note=l['note'], e=l['e'], window=[l['start'], l['end']],
                                                cur=dict(hist=l['ra']['observed_note_lane_masks'], flips=l['ra']['string_flips'], longest_correct_ms=l['ra']['longest_correct_run_ms']),
                                                rel=dict(hist=l['rb']['observed_note_lane_masks'], flips=l['rb']['string_flips'], longest_correct_ms=l['rb']['longest_correct_run_ms']))
                              for l in lab if l['i'] in (13, 56)}
    return rep, lab, int(tc['samples'])


def midi_intervals(name, end):
    ev = []
    for line in gzip.open(D + name + '-midi.tsv.gz', 'rt'):
        if line.startswith('#') or line.startswith('sample'):
            continue
        s, kind, note, vel, vid, seq = line.split('\t')[:6]
        ev.append((int(seq), int(s), kind, int(note), int(vid)))
    ev.sort()
    open_on = collections.defaultdict(list)
    spans = collections.defaultdict(list)
    onsets = []
    for _, s, kind, note, vid in ev:
        if kind == 'on':
            open_on[(vid, note)].append(s)
            onsets.append((s, note, vid))
        else:
            q = open_on[(vid, note)]
            if q:
                spans[note].append((q.pop(0), s, vid))
    for (vid, note), q in open_on.items():
        for s in q:
            spans[note].append((s, end, vid))
    return spans, onsets


def merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(A, B):
    """A minus B for sorted merged lists of [a, b)."""
    out = []
    j = 0
    for a, b in A:
        cur = a
        while j < len(B) and B[j][1] <= cur:
            j += 1
        k = j
        while k < len(B) and B[k][0] < b:
            if B[k][0] > cur:
                out.append([cur, B[k][0]])
            cur = max(cur, B[k][1])
            k += 1
        if cur < b:
            out.append([cur, b])
    return out


def overlap_len(segs, wins):
    """Total length of segs inside union(wins) (both merged)."""
    t = 0
    for a, b in segs:
        for c, d in wins:
            if d <= a:
                continue
            if c >= b:
                break
            t += min(b, d) - max(a, c)
    return t


def split_by(segs, wins):
    """Return (inside, outside) pieces of segs against merged windows."""
    return subtract(segs, subtract(segs, wins)), subtract(segs, wins)


def part_b(lab, end):
    sc, oc = midi_intervals(CFG['cur'], end)
    sr, orl = midi_intervals(CFG['rel'], end)
    same = collections.defaultdict(list)
    anyw = []
    for l in lab:
        same[l['note']].append((l['start'], l['end']))
        anyw.append((l['start'], l['end']))
    anyw = merge(anyw)
    samew = {n: merge(v) for n, v in same.items()}
    res = dict(added=collections.Counter(), removed=collections.Counter(), ranges=collections.Counter())
    per_pitch_gap = collections.Counter()
    for note in sorted(set(sc) | set(sr)):
        cur = merge([[a, b] for a, b, _ in sc.get(note, [])])
        rel = merge([[a, b] for a, b, _ in sr.get(note, [])])
        for tag, segs in (('added', subtract(rel, cur)), ('removed', subtract(cur, rel))):
            in_same, rest = split_by(segs, samew.get(note, []))
            in_any, in_gap = split_by(rest, anyw)
            for loc, ss in (('same_label', in_same), ('other_label', in_any), ('gap', in_gap)):
                for a, b in ss:
                    kind = 'prolongation' if any(0 <= a - c[1] <= 512 for c in cur) else 'new_onset'
                    if tag == 'removed':
                        kind = 'n/a'
                    res[tag]['%s|%s' % (loc, kind) if loc != 'same_label' else loc] += b - a
                    res['ranges']['%s|%s|%s' % (tag, loc, kind)] += 1
                    if tag == 'added' and loc == 'gap':
                        per_pitch_gap[note] += b - a
    onset_loc = {}
    for tag, ons in (('cur', oc), ('rel', orl)):
        C = collections.Counter()
        for s, note, vid in ons:
            if any(a <= s < b for a, b in samew.get(note, [])):
                C['same_label'] += 1
            elif any(a <= s < b for a, b in anyw):
                C['other_label'] += 1
            else:
                C['gap'] += 1
        onset_loc[tag] = dict(C, total=len(ons))
    retrig = []
    for l in lab:
        a, b = l['start'], l['end']
        nc = sum(1 for s, n, v in oc if n == l['note'] and a <= s < b)
        nr = sum(1 for s, n, v in orl if n == l['note'] and a <= s < b)
        retrig.append((nr - nc, l['i'], l['note'], nc, nr))
    retrig.sort(reverse=True)
    full = {}
    for i in (13, 56):
        l = next(x for x in lab if x['i'] == i)
        full[str(i)] = dict(note=l['note'], window=[l['start'], l['end']],
                            cur=[(a, b, v) for a, b, v in sc.get(l['note'], []) if a < l['end'] and b > l['start']],
                            rel=[(a, b, v) for a, b, v in sr.get(l['note'], []) if a < l['end'] and b > l['start']])
    return dict(added_samples=dict(res['added']), removed_samples=dict(res['removed']), range_counts=dict(res['ranges']),
                total_added=sum(res['added'].values()), total_removed=sum(res['removed'].values()),
                added_gap_samples_total=sum(v for k, v in res['added'].items() if k.startswith('gap')),
                onsets_by_location=onset_loc,
                top_pitches_by_added_gap_samples=per_pitch_gap.most_common(10),
                labels_with_noteon_increase=sum(1 for r in retrig if r[0] > 0), labels_with_noteon_decrease=sum(1 for r in retrig if r[0] < 0),
                top15_noteon_increase=[dict(label=i, note=n, cur=c, rel=r, delta=d) for d, i, n, c, r in retrig[:15]],
                labels_13_56_intervals=full)


def part_c(lab, end):
    sc, oc = midi_intervals(CFG['cur'], end)
    sr, orl = midi_intervals(CFG['rel'], end)
    out = {}

    def lane_samples(spans, l):
        v = collections.Counter()
        for a, b, vid in spans.get(l['note'], []):
            o = min(b, l['end']) - max(a, l['start'])
            if o > 0:
                v[vid] += o
        return v
    chk = {}
    for tag, spans, key in (('cur', sc, 'ra'), ('rel', sr, 'rb')):
        ok = 0; diff = 0
        for l in lab:
            v = lane_samples(spans, l)
            good = True
            for k in range(8):
                d = abs(v.get(k, 0) - int(l[key]['lane_%d' % k]) * 64)
                diff += d
                if d > 1024:
                    good = False
            ok += 1 if good else 0
        chk[tag] = dict(labels=len(lab), labels_all_lanes_within_1024=ok, summed_abs_diff_samples=diff)
    out['C1_voice_id_vs_lane'] = chk
    # C2 gap/other kind v2
    same = collections.defaultdict(list)
    anyw = []
    for l in lab:
        same[l['note']].append((l['start'], l['end']))
        anyw.append((l['start'], l['end']))
    anyw = merge(anyw)
    samew = {n: merge(v) for n, v in same.items()}
    C = collections.Counter(); N = collections.Counter()
    for note in sorted(set(sc) | set(sr)):
        cur = merge([[a, b] for a, b, _ in sc.get(note, [])])
        rel = merge([[a, b] for a, b, _ in sr.get(note, [])])
        for S in subtract(rel, cur):
            in_same, rest = split_by([S], samew.get(note, []))
            in_any, in_gap = split_by(rest, anyw)
            for loc, ss in (('other_label', in_any), ('gap', in_gap)):
                for a, b in ss:
                    if S[0] < a:
                        kind = 'continuation_of_segment_begun_earlier'
                    elif any(0 <= a - c[1] <= 512 for c in cur):
                        kind = 'fresh_prolongation_of_current_span'
                    else:
                        kind = 'fresh_new_onset'
                    C['%s|%s' % (loc, kind)] += b - a
                    N['%s|%s' % (loc, kind)] += 1
    out['C2_kind_v2_samples'] = dict(C)
    out['C2_kind_v2_pieces'] = dict(N)
    # C3 hand-offs
    def handoffs(spans, l):
        ss = sorted((a, b, v) for a, b, v in spans.get(l['note'], []) if a < l['end'] and b > l['start'])
        h = r = 0
        for x, y in zip(ss, ss[1:]):
            gap = y[0] - x[1]
            if gap <= 512 and y[2] != x[2]:
                h += 1
            elif gap > 512:
                r += 1
        return h, r, len(ss)
    H = {}
    for tag, spans in (('cur', sc), ('rel', sr)):
        H[tag] = {l['i']: handoffs(spans, l) for l in lab}
    out['C3_totals'] = {t: dict(handoffs=sum(v[0] for v in H[t].values()), reattacks=sum(v[1] for v in H[t].values()), spans=sum(v[2] for v in H[t].values())) for t in H}
    n0 = [l for l in lab if l['labeled'] - l['cur']['none'] == 0 and -l['d']['none'] > 0]
    cur_rendered = [l for l in lab if l['labeled'] - l['cur']['none'] > 0]
    fr = lambda ls, c: sum(l['labeled'] - l[c]['none'] for l in ls)
    out['C3_rate_per_1000_rendered_frames'] = dict(
        relief_on_N0=dict(labels=len(n0), rendered_frames=fr(n0, 'rel'), handoffs=sum(H['rel'][l['i']][0] for l in n0), reattacks=sum(H['rel'][l['i']][1] for l in n0)),
        current_on_rendered_labels=dict(labels=len(cur_rendered), rendered_frames=fr(cur_rendered, 'cur'), handoffs=sum(H['cur'][l['i']][0] for l in cur_rendered), reattacks=sum(H['cur'][l['i']][1] for l in cur_rendered)),
        relief_on_labels_rendered_in_current=dict(labels=len(cur_rendered), rendered_frames=fr(cur_rendered, 'rel'), handoffs=sum(H['rel'][l['i']][0] for l in cur_rendered), reattacks=sum(H['rel'][l['i']][1] for l in cur_rendered)))
    for k, v in list(out['C3_rate_per_1000_rendered_frames'].items()):
        v['handoffs_per_1000_frames'] = round(1000 * v['handoffs'] / v['rendered_frames'], 2) if v['rendered_frames'] else None
        v['reattacks_per_1000_frames'] = round(1000 * v['reattacks'] / v['rendered_frames'], 2) if v['rendered_frames'] else None
    out['C3_labels_13_56'] = {str(i): dict(handoffs_rel=H['rel'][i][0], reattacks_rel=H['rel'][i][1], spans_rel=H['rel'][i][2], handoffs_cur=H['cur'][i][0],
                                           string_flips_rel=int(next(l for l in lab if l['i'] == i)['rb']['string_flips'])) for i in (13, 56)}
    rise_h = rise_r = rise_on = 0
    for l in lab:
        nc = sum(1 for s_, n, v in oc if n == l['note'] and l['start'] <= s_ < l['end'])
        nr = sum(1 for s_, n, v in orl if n == l['note'] and l['start'] <= s_ < l['end'])
        if nr > nc:
            rise_on += nr - nc
            rise_h += H['rel'][l['i']][0] - H['cur'][l['i']][0]
            rise_r += H['rel'][l['i']][1] - H['cur'][l['i']][1]
    out['C3_noteon_rise_labels'] = dict(noteon_rise=rise_on, handoff_rise=rise_h, reattack_rise=rise_r)
    return out


def main():
    a, lab, end = part_a()
    rep = dict(PART_A=a, PART_B=part_b(lab, end), PART_C=part_c(lab, end))
    json.dump(rep, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(rep, indent=1, default=str))


main()
