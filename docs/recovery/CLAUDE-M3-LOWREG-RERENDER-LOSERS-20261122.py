"""Which labels does the label-free re-render rule B(1.5) lose, where in the label, and does any one detector-side condition separate the losing fires from the gaining ones?  Saved trace and saved spans only.

No audio, model run or job.  Builds on CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122 (same saved spans, same label-free rule, same
edit-and-score plumbing; its helpers are imported, not copied).  That note found that rule B(1.5) (a lower voice with `direct == 0`
is re-rendered as the related unrendered pitch q* with the largest fundamental share when q*'s share is at least 1.5 times the
voice's own) gains 1.58 coverage points on CURRENT's exact output but 36 labels lose some present samples (784 ms in all), so the
strict per-label gate fails.  Here every fire of the rule is kept with its detector-side features and attributed to the label (if
any) whose pitch it removes and the label (if any) whose pitch it adds.

Definitions (labels are used only to classify fires after the fact, never to decide one):
  harm fire    the removed pitch n has an active label at the tick's sample (the removal cuts that label's present samples).
  good fire    n has no active label and q* has one (the addition can only add present samples to q*'s label).
  swap fire    both have active labels.  null fire: neither does.
A rule can only keep the strict per-label gate if it fires on no harm or swap fire whose removal is not covered by another voice.

PRE-REGISTRATION, written 2026-11-22 BEFORE this script was run (file mtimes are the record; no clock time given).
Already seen: the aggregate B1.5 result, its 36 losing labels' count, bands (27 below MIDI 48, 9 in 48-59), total 784 ms,
median 6.3 ms, max 268.7 ms, and the B1 fire shares from the tick-level harm table (17.1% of B1 fires on a true voice).  NOT
seen: which labels lose, where in the label, the fire classes, any fire-level feature comparison, any gate.
Predictions, each can fail:
  P0  the pool of fires with ratio >= 1.5 has exactly 16,822 members (the EMITTED count) and the label lookup agrees with the
      trace's own active-label set at the tick for at least 99.9% of them (plumbing).
  L1  harm fires (n has an active label) are at most 25% of B1.5 fires.
  L2  good fires (n none, q* active) are at least 40% of B1.5 fires.
  L3  at least 60% of harm fires lie in the second half of their label's annotated duration.
  L4  no single listed feature separates harm fires from good fires with AUC >= 0.85.
  L5  no single-feature one-sided threshold gate (deciles of the B1.5 fire values, both directions, three relation-class
      exclusions: octave, fifth (twelfth-like), near) that keeps at least 1.0 coverage point passes the strict per-label gate when rescored.
Report the whole table whatever it shows.  One recording, one corpus, in-sample throughout; the optimistic immediate-replacement
assumption of the EMITTED note applies.  No lane, unison, callback or live-host claim.  Nothing here selects a native rule.

Usage: python3 -P -E CLAUDE-M3-LOWREG-RERENDER-LOSERS-20261122.py TRACE.tsv.gz
"""
import bisect
import gzip
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
spec = importlib.util.spec_from_file_location('em', os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-EMITTED-20261122.py'))
em = importlib.util.module_from_spec(spec)
spec.loader.exec_module(em)
split, audit = em.split, em.audit
OUT = os.path.join(HERE, 'CLAUDE-M3-LOWREG-RERENDER-LOSERS-20261122.json')
TICK, TAIL_TICKS = em.TICK, em.TAIL_TICKS
SR = split.SAMPLE_RATE
OWN = ('fund_ratio', 'local', 'evidence', 'evidence_ticks', 'evidence_gap', 'band_fund', 'band_score', 'score_ratio',
       'fund_energy', 'attack', 'release', 'age', 'selection')
QF = ('fund_ratio', 'direct', 'local', 'evidence', 'evidence_ticks', 'band_fund', 'band_score', 'score_ratio',
      'fund_energy', 'attack', 'age', 'selection')
FEATURES = ['o_' + f for f in OWN] + ['v_age', 'ratio', 'dist'] + ['q_' + f for f in QF]
BAD_DIRECTION = None


def auc(pos, neg):
    """AUC of pos > neg, direction chosen to be >= 0.5; returns (auc, pos_high)."""
    g, t = np.asarray(pos, float), np.asarray(neg, float)
    if len(g) == 0 or len(t) == 0:
        return None
    values = np.concatenate([g, t])
    order = np.argsort(values, kind='mergesort')
    ranks = np.empty(len(values))
    s = values[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    a = (ranks[:len(g)].sum() - len(g) * (len(g) + 1) / 2.0) / (len(g) * len(t))
    return (round(float(max(a, 1 - a)), 3), bool(a >= 0.5))


def collect(path, occupied, find_label):
    decisions = []
    last_label = {}
    total_ticks = 167026
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        stream.readline()
        stream.readline()
        for index, line in enumerate(stream):
            frame = em._frame('\t'.join(line.rstrip('\n').split('\t')[:8]))
            tick, sample = frame['tick'], frame['sample']
            active = {row[1] for row in frame['labels']}
            for note in active:
                last_label[note] = tick
            voices = frame['voices']
            lows = [v for v in voices if v[1] < split.SPLIT]
            if not lows:
                continue
            cands = em._candidates(frame)
            rendered = {v[1] for v in voices}
            emitted_notes = {v[0] for v in voices}
            for voice in lows:
                n = voice[1]
                own = cands.get(voice[0])
                if own is None or own['selection'] == 0 or not occupied(n, sample):
                    continue
                best = None
                for q, row in cands.items():
                    if q == n or q in rendered:
                        continue
                    if em.rel_class(n - q) is None or not em.logged_without_labels(row, emitted_notes):
                        continue
                    if best is None or row['fund_ratio'] > best[0]:
                        best = (row['fund_ratio'], q, row)
                if best is None or own['direct'] != 0:
                    continue
                ratio = best[0] / max(own['fund_ratio'], 1e-6)
                if ratio < 1.0:
                    continue
                q, qrow = best[1], best[2]
                if n in active:
                    kind = 'true'
                elif tick - last_label.get(n, -10 ** 9) <= TAIL_TICKS:
                    kind = 'tail'
                else:
                    kind = 'ghost'
                d = dict(sample=sample, index=index, half='first' if index < total_ticks // 2 else 'second',
                         n=n, q=q, ratio=ratio, kind=kind, rel=em.rel_class(n - q)[1], dist=abs(n - q),
                         n_label=find_label(n, sample), q_label=find_label(q, sample), n_active_frame=n in active,
                         v_age=voice[4])
                for f in OWN:
                    d['o_' + f] = own[f]
                for f in QF:
                    d['q_' + f] = qrow[f]
                decisions.append(d)
    return decisions


def run(path):
    report = json.load(open(split.REPORT))
    base = json.load(open(split.BASELINE))['datasets']['ordinary']
    horizon = report['datasets']['ordinary']['common_support']['sample_count']
    clock = dict(sample_count=horizon, sample_rate=SR)
    labels, _ = em.clip_labels(em.labels_from_measurement(base['measurement']), horizon)
    base_spans = em.clip_spans(base['pitch_spans'], horizon)
    saved = split.compact(em.score(base_spans, labels, **clock))
    reference = em.score(base_spans, labels, **clock)
    occ = defaultdict(list)
    for left, right, pitch in base_spans:
        occ[pitch].append((left, right))
    for pitch in occ:
        occ[pitch].sort()

    def occupied(pitch, sample):
        iv = occ.get(pitch)
        if not iv:
            return False
        i = bisect.bisect_right(iv, (sample, 10 ** 12)) - 1
        return i >= 0 and iv[i][0] <= sample < iv[i][1]

    by_pitch = defaultdict(list)
    for r in labels:
        by_pitch[r['midi_note']].append((r['start_sample'], r['end_sample'], r['label_index']))

    def find_label(pitch, sample):
        for left, right, idx in by_pitch.get(pitch, ()):
            if left <= sample < right:
                return idx
        return None

    decisions = collect(path, occupied, find_label)
    pool = [d for d in decisions if d['ratio'] >= 1.5]
    agree = sum((d['n_label'] is not None) == d['n_active_frame'] for d in pool)
    info = {r['label_index']: r for r in labels}

    def evaluate(fires):
        removals, additions = defaultdict(list), defaultdict(list)
        for d in fires:
            start = d['sample'] - (TICK - 1)
            removals[d['n']].append((start, start + TICK))
            additions[d['q']].append((start, start + TICK))
        spans = em.clip_spans(em.edit(base_spans, removals, additions), horizon)
        scored = em.score(spans, labels, **clock)
        row = split.compact(scored)
        cmp = em.compare(reference, scored)
        return dict(
            fired=len(fires), score=row, coverage_gain_points=round(row['coverage_percent'] - saved['coverage_percent'], 3),
            exact_set_ratio=round(row['exact_pitch_set'] / saved['exact_pitch_set'], 3),
            wrong_pitch_delta=row['wrong_pitch'] - saved['wrong_pitch'], gap_delta=row['gap'] - saved['gap'],
            strict_gate=bool(cmp['no_pitch_safety_regression']),
            labels_losing=sum(min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0
                              for r in cmp['label_changes']),
            audit=audit.summarize(audit.loss_rows(reference, scored))), cmp

    base_eval, cmp = evaluate(pool)
    deltas = {r['label_index']: r for r in cmp['label_changes']}

    # ---- fire classes
    def klass(d):
        a, b = d['n_label'] is not None, d['q_label'] is not None
        return 'harm' if a and not b else 'swap' if a and b else 'good' if b else 'null'
    classes = Counter(klass(d) for d in pool)
    by_kind = Counter((d['kind'], klass(d)) for d in pool)
    harm = [d for d in pool if d['n_label'] is not None]
    pos = []
    for d in harm:
        r = info[d['n_label']]
        pos.append((d['sample'] - r['start_sample']) / max(1, r['end_sample'] - r['start_sample']))
    to_end_ms = [(info[d['n_label']]['end_sample'] - d['sample']) * 1000.0 / SR for d in harm]
    second_half = sum(p >= 0.5 for p in pos) / max(1, len(pos))
    last_quarter = sum(p >= 0.75 for p in pos) / max(1, len(pos))
    within_100ms = sum(t <= 100 for t in to_end_ms) / max(1, len(to_end_ms))

    # ---- per losing label
    loss = {}
    for idx, r in deltas.items():
        if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0:
            loss[idx] = r
    per_label = []
    for idx, r in sorted(loss.items(), key=lambda kv: kv[1]['present_samples_delta']):
        mine = [d for d in harm if d['n_label'] == idx]
        gain_in = [d for d in pool if d['q_label'] == idx]
        per_label.append(dict(
            label_index=idx, midi=r['midi_note'], start_ms=round(r['start_sample'] * 1000 / SR, 1),
            annotated_ms=round(r['annotated_samples'] * 1000 / SR, 1),
            present_delta_ms=round(r['present_samples_delta'] * 1000 / SR, 2),
            longest_delta_ms=round(r['longest_present_samples_delta'] * 1000 / SR, 2),
            current_present_ms=round(r['current_present_samples'] * 1000 / SR, 1),
            removal_fires=len(mine), addition_fires=len(gain_in),
            median_position=round(float(np.median([(d['sample'] - info[idx]['start_sample']) /
                                                   max(1, info[idx]['end_sample'] - info[idx]['start_sample'])
                                                   for d in mine])), 3) if mine else None,
            median_own_fund_ratio=round(float(np.median([d['o_fund_ratio'] for d in mine])), 3) if mine else None,
            median_q_fund_ratio=round(float(np.median([d['q_fund_ratio'] for d in mine])), 3) if mine else None,
            median_ratio=round(float(np.median([d['ratio'] for d in mine])), 2) if mine else None))
    gaining = [r for r in deltas.values() if r['present_samples_delta'] > 0]
    gain_summary = dict(labels_gaining=len(gaining),
                        total_gain_ms=round(sum(r['present_samples_delta'] for r in gaining) * 1000 / SR, 1))

    # ---- fire-level separation: harm vs good
    good = [d for d in pool if klass(d) == 'good']
    sep = {}
    for f in FEATURES:
        sep[f] = auc([d[f] for d in harm], [d[f] for d in good])
    sep['rel_octave_share'] = dict(
        harm=round(sum(d['rel'] == 'octave' for d in harm) / max(1, len(harm)), 3),
        good=round(sum(d['rel'] == 'octave' for d in good) / max(1, len(good)), 3))
    sel = dict(harm_selection=dict(Counter(d['o_selection'] for d in harm)),
               good_selection=dict(Counter(d['o_selection'] for d in good)))

    # ---- one-sided single-feature gates
    gates = []
    values = {f: np.array([d[f] for d in pool], float) for f in FEATURES}
    for f in FEATURES:
        for t in np.unique(np.quantile(values[f], [i / 10 for i in range(1, 10)])):
            for side in ('ge', 'le'):
                keep = [d for d in pool if (d[f] >= t if side == 'ge' else d[f] <= t)]
                gates.append((f'{f} {side} {float(t):.6g}', keep))
    for rel in ('octave', 'fifth', 'near'):
        gates.append((f'exclude rel={rel}', [d for d in pool if d['rel'] != rel]))
    # relation labels from rel_class: report which strings exist
    rels = Counter(d['rel'] for d in pool)

    def summarize_gate(desc, keep):
        rm = {d['n_label'] for d in keep if d['n_label'] is not None}
        return dict(gate=desc, fires=len(keep), harm_swap_labels=len(rm),
                    harm_swap_fires=sum(d['n_label'] is not None for d in keep),
                    good_fires=sum(klass(d) == 'good' for d in keep))
    screen = [summarize_gate(desc, keep) for desc, keep in gates]
    order = sorted(range(len(gates)), key=lambda i: (screen[i]['harm_swap_labels'] != 0,
                                                     -(screen[i]['good_fires'] - screen[i]['harm_swap_fires'])
                                                     if screen[i]['harm_swap_labels'] else -screen[i]['good_fires']))
    zero = [i for i in order if screen[i]['harm_swap_labels'] == 0]
    rest = sorted((i for i in range(len(gates)) if screen[i]['harm_swap_labels'] != 0),
                  key=lambda i: -(screen[i]['good_fires'] - 3 * screen[i]['harm_swap_fires']))
    chosen = zero[:12] + rest[:12]
    chosen += [i for i, (desc, _) in enumerate(gates) if desc.startswith('exclude rel=') and i not in chosen]
    # POST HOC (added after the first results were read): also rescore the gates that leave at most 3 harm/swap labels.
    low = sorted((i for i in range(len(gates)) if screen[i]['harm_swap_labels'] <= 3 and i not in chosen),
                 key=lambda i: (screen[i]['harm_swap_labels'], -screen[i]['good_fires']))
    chosen += low[:12]
    rescored = []
    for i in chosen:
        ev, _ = evaluate(gates[i][1])
        rescored.append(dict(screen[i], coverage_gain_points=ev['coverage_gain_points'], strict_gate=ev['strict_gate'],
                             exact_set_ratio=ev['exact_set_ratio'], wrong_pitch_delta=ev['wrong_pitch_delta'],
                             gap_delta=ev['gap_delta'], labels_losing=ev['labels_losing'],
                             loss_ms=ev['audit'].get('total_loss_ms', 0)))
    # POST HOC: the gate with the fewest residual harm/swap labels (then the most good fires), on each half of the ticks.
    best_i = min(range(len(gates)), key=lambda i: (screen[i]['harm_swap_labels'], -screen[i]['good_fires']))
    halves = {}
    for half in ('first', 'second'):
        keep = [d for d in gates[best_i][1] if d['half'] == half]
        ev, _ = evaluate(keep)
        halves[half] = dict(fires=len(keep), harm_swap_labels=summarize_gate('', keep)['harm_swap_labels'],
                            coverage_gain_points=ev['coverage_gain_points'], strict_gate=ev['strict_gate'],
                            exact_set_ratio=ev['exact_set_ratio'], wrong_pitch_delta=ev['wrong_pitch_delta'],
                            gap_delta=ev['gap_delta'], labels_losing=ev['labels_losing'],
                            loss_ms=ev['audit'].get('total_loss_ms', 0))
    result = dict(
        posthoc_best_gate=dict(gate=gates[best_i][0], halves=halves),
        saved_current=saved,
        decisions_total=len(decisions), pool_b15=len(pool), p0_label_lookup_agreement=round(agree / max(1, len(pool)), 5),
        rule_b15_rescored=base_eval, fire_classes=dict(classes),
        fire_class_by_voice_kind={f'{k}_{c}': v for (k, c), v in sorted(by_kind.items())},
        harm_fire_position=dict(count=len(harm), second_half_share=round(second_half, 3),
                                last_quarter_share=round(last_quarter, 3),
                                within_100ms_of_label_end_share=round(within_100ms, 3),
                                median_ms_to_label_end=round(float(np.median(to_end_ms)), 1) if to_end_ms else None),
        harm_vs_good_separation=sep, own_selection_code=sel, relation_classes=dict(rels),
        gain_summary=gain_summary, losing_labels=per_label, gate_screen_size=len(gates),
        zero_residual_gates=sum(1 for s in screen if s['harm_swap_labels'] == 0),
        gate_screen=screen,
        rescored_gates=rescored)
    with open(OUT, 'w') as stream:
        json.dump(result, stream, indent=1, default=str)
    return result


if __name__ == '__main__':
    out = run(sys.argv[1])
    print(json.dumps({k: out[k] for k in ('pool_b15', 'p0_label_lookup_agreement', 'fire_classes', 'harm_fire_position',
                                          'gain_summary', 'zero_residual_gates')}, indent=1))
