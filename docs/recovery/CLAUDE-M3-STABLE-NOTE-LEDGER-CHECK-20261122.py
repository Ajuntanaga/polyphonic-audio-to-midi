#!/usr/bin/env python3
"""Independent re-derivation of the saved per-label claims about the default-off stable-note identity path.
Codex's claims: RESUME.md (stable note identity bounded screen, ledger run 44079653692) and the later VST3 component corpus run 44245557161.
Saved data only: three small JSON reports already in build/github-results.  No audio, model run, job, download, native code or edit of Codex's files.

Registration status: NOT pre-registered.  I recomputed the headline numbers inline before writing this script, and looked at the per-label rows of six datasets
(ordinary, extended-middle, physical-long, extended-highmid, extended-high, physical-four) while deciding what to check.  Parts A and B are a verification of
someone else's claims (the result is reproduces / does not reproduce); part C is POST HOC and descriptive, with no prediction, no verdict and nothing that is a
candidate, a gate or a change to the stable-note path.

A.  The ordinary-recording claims in RESUME.md (target label 17, 79 / 148 / 0 label counts, callbacks 11,851 -> 8,623 through 1,614 pairs, onset counts), checked
    against the per-label rows of the ledger report; the report against the collected verdict's hash; the ledger's rows against the later VST3 component run's rows;
    and the identity  in-label NoteOns + wrong-note onsets + gap onsets = all NoteOns  against the lifecycle count and the pair count.
B.  The label-level gates (no pitch loss, no shorter hold, no NoteOn growth) recomputed from the rows of all 14 datasets of the corpus run, and compared with
    the report's own gate booleans; labels that had a NoteOn inside them before and none after (the only label-level sign of a lost attack the rows can show).
C.  POST HOC: where the remaining in-label NoteOns are (by the label's baseline count), how much of each bucket the path removed, and a lower bound for the
    NoteOns that must overlap another same-pitch note inside their label (a note shorter than one 64-sample decision cannot exist, so more NoteOns than fit
    outside the longest hold must overlap).  Each is reported label-weighted and per inferred window (see the revision note).

Revision note (disclosed): this script was run once before the revision below, and its first output was moved aside, not published.  That first run weighted every
label equally.  Looking at its output I found that labels annotated once per string (the four-string and unison datasets) carry identical rows, so the same NoteOn
events are counted once per label in the totals and in part C.  The rows carry no start or end sample, so that is an inference from the rows, not a measurement.  I
therefore added `window_groups` (see its docstring) and report the totals, the lost-last-NoteOn labels and part C both label-weighted (the way the ledger and the
gates count) and per inferred window.  Nothing in part A and no per-label gate depends on the grouping.  The outcome data seen before the revision: the label-weighted
totals and pooled bucket table of the first run, and the rows of the six datasets listed above.  The ordinary recording is a control: its accounting identity is
exact, so no NoteOn is counted twice there, and the grouping must merge nothing in it.  A later edit (before anything was committed) only added output fields: the rows
of the labels that lost every in-label NoteOn, and the count of labels where the pitch is present but no NoteOn falls inside; no number that was already printed changed.

Usage: python3 -I CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.py [--selftest | --run]     (--run refuses to overwrite its JSON)
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(ROOT, 'build', 'github-results')
LEDGER = os.path.join(RESULTS, 'stable-note-identity-ledger-44079653692', 'stable-note-identity-ledger', 'report.json')
VERDICT = os.path.join(RESULTS, 'stable-note-identity-ledger-44079653692', 'collected-verdict.json')
CORPUS = os.path.join(RESULTS, 'vst3-stable-note-corpus-44245557161', 'vst3-stable-note-corpus', 'report.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.json')

MIN_NOTE_SAMPLES = 64          # one decision; the lifecycle's shortest closed note is 64 samples
SAMPLE_RATE = 96000
BUCKETS = ((0, 0), (1, 1), (2, 5), (6, 20), (21, 50), (51, 100), (101, None))

# The ordinary-recording claims as written in RESUME.md (stable note identity bounded screen paragraph), copied here so the comparison is explicit.
CLAIMED = dict(target_label=17, target_note=37, target_string_mask=1, target_start=245017, target_end=316800, target_label_samples=71783,
               target_present=65857, target_note_ons_before=156, target_note_ons_after=109, target_reduction_percent=30.1282,
               target_hold_before=5184, target_hold_after=5824, target_hold_ms_before=54.0, target_hold_ms_after=60.6667, target_present_percent=91.7446,
               labels=499, labels_longer_hold=79, labels_fewer_note_ons=148, label_regressions=0,
               callbacks_before=11851, callbacks_after=8623, pairs=1614, suppressed_events=3228,
               wrong_note_voice_samples=8222039, gap_voice_samples=3761781, wrong_note_onsets_before=1200, wrong_note_onsets_after=928,
               gap_onsets_before=517, gap_onsets_after=323, open_note_at_eof=44)


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path) as f:
        return json.load(f)


def compare(before, after):
    """Per-label comparison of two ledgers that describe the same labels in the same order."""
    out = dict(labels=len(before), regress=[], longer=[], fewer=[], lost_last_attack=[], present_changed=[], before_on=0, after_on=0, present_labels=0)
    if len(before) != len(after):
        raise ValueError('different label counts')
    for b, a in zip(before, after):
        if any(b[k] != a[k] for k in ('label_index', 'midi_note', 'label_samples')):
            raise ValueError('label identity differs between the two ledgers')
        i = b['label_index']
        if (a['pitch_present_samples'] < b['pitch_present_samples'] or a['longest_sink_hold_samples'] < b['longest_sink_hold_samples']
                or a['note_ons_inside_label'] > b['note_ons_inside_label']):
            out['regress'].append(i)
        if a['longest_sink_hold_samples'] > b['longest_sink_hold_samples']:
            out['longer'].append(i)
        if a['note_ons_inside_label'] < b['note_ons_inside_label']:
            out['fewer'].append(i)
        if b['note_ons_inside_label'] >= 1 and a['note_ons_inside_label'] == 0:
            out['lost_last_attack'].append(i)
        if a['pitch_present_samples'] != b['pitch_present_samples']:
            out['present_changed'].append(i)
        out['before_on'] += b['note_ons_inside_label']
        out['after_on'] += a['note_ons_inside_label']
        out['present_labels'] += 1 if b['pitch_present_samples'] > 0 else 0
    return out


def bucket_name(n):
    for lo, hi in BUCKETS:
        if n >= lo and (hi is None or n <= hi):
            return str(lo) if lo == hi else f'{lo}-{hi}' if hi is not None else f'>{lo - 1}'
    raise ValueError(n)


def bucket_table(pairs):
    """pairs: iterable of (note_ons_before, note_ons_after) per label."""
    names = [bucket_name(lo) for lo, _ in BUCKETS]
    t = {n: dict(labels=0, before=0, after=0) for n in names}
    for nb, na in pairs:
        r = t[bucket_name(nb)]
        r['labels'] += 1
        r['before'] += nb
        r['after'] += na
    for r in t.values():
        r['removed'] = r['before'] - r['after']
        r['removed_share'] = r['removed'] / r['before'] if r['before'] else None
    return t


def overlap_excess(note_ons, label_samples, longest_hold):
    """Lower bound for the NoteOns that must overlap another same-pitch note inside the label.
    Outside the longest hold there are label_samples - longest_hold samples, which fit at most that // 64 further notes of at least 64 samples each; the longest
    hold itself accounts for at most one of the NoteOns.  Anything beyond that is a note that began while another same-pitch note was sounding."""
    room = max(label_samples - longest_hold, 0) // MIN_NOTE_SAMPLES
    return max(note_ons - 1 - room, 0)


GROUP_TOLERANCE = 96           # samples (1 ms at 96 kHz)


def _alike(x, y, tolerance):
    return (x['midi_note'] == y['midi_note'] and x['note_ons_inside_label'] == y['note_ons_inside_label']
            and all(abs(x[k] - y[k]) <= tolerance for k in ('label_samples', 'longest_sink_hold_samples', 'pitch_present_samples')))


def window_groups(before, after, tolerance=GROUP_TOLERANCE):
    """Group labels that are very probably one annotated window labelled once per string (the four-string and unison datasets).
    The rows carry no start or end sample, so this is an inference from the rows, not a measurement: consecutive labels of one pitch with at least one NoteOn
    before, whose NoteOn counts are equal and whose length, longest hold and pitch-present samples are within `tolerance` samples of the group's first label, in
    both modes.  Labels with no NoteOn before stay alone (they carry nothing to double-count).  Returns lists of positions into the rows."""
    groups = []
    for i, (b, a) in enumerate(zip(before, after)):
        if groups and b['note_ons_inside_label'] >= 1:
            j = groups[-1][0]
            if _alike(b, before[j], tolerance) and _alike(a, after[j], tolerance):
                groups[-1].append(i)
                continue
        groups.append([i])
    return groups


def distinct_rows(before, after):
    """One representative row (the first label of each inferred window) per window, in both modes, plus the groups."""
    g = window_groups(before, after)
    return [before[x[0]] for x in g], [after[x[0]] for x in g], g


def concentration(before, after):
    """Where the remaining NoteOns are, and the provable same-pitch overlap bound, for one list of rows (labels, or inferred windows)."""
    total_after = sum(a['note_ons_inside_label'] for a in after)
    heavy_after = sum(a['note_ons_inside_label'] for a in after if a['note_ons_inside_label'] >= 21)
    top = max(after, key=lambda a: a['note_ons_inside_label'])
    ex_before = ex_after = 0
    rows = []
    for b, a in zip(before, after):
        eb = overlap_excess(b['note_ons_inside_label'], b['label_samples'], b['longest_sink_hold_samples'])
        ea = overlap_excess(a['note_ons_inside_label'], a['label_samples'], a['longest_sink_hold_samples'])
        ex_before += eb
        ex_after += ea
        if eb or ea:
            rows.append(dict(label=a['label_index'], midi_note=a['midi_note'], label_ms=1000 * a['label_samples'] / SAMPLE_RATE,
                             note_ons_before=b['note_ons_inside_label'], note_ons_after=a['note_ons_inside_label'],
                             hold_before_ms=1000 * b['longest_sink_hold_samples'] / SAMPLE_RATE, hold_after_ms=1000 * a['longest_sink_hold_samples'] / SAMPLE_RATE,
                             overlap_excess_before=eb, overlap_excess_after=ea))
    return dict(note_ons_after=total_after, in_labels_with_21_or_more=heavy_after,
                share_in_labels_with_21_or_more=heavy_after / total_after if total_after else None,
                heaviest_label=dict(label=top['label_index'], note_ons_after=top['note_ons_inside_label'],
                                    share=top['note_ons_inside_label'] / total_after if total_after else None),
                overlap_excess_before=ex_before, overlap_excess_after=ex_after, overlap_rows=rows)


def check_claims(derived, claimed):
    return {k: dict(claimed=claimed[k], derived=derived.get(k), match=_close(claimed[k], derived.get(k))) for k in claimed}


def _close(claimed, derived):
    if derived is None:
        return False
    if isinstance(claimed, float):
        return abs(claimed - derived) <= 5e-5 * max(1.0, abs(claimed))
    return claimed == derived


def accounting(in_label_on, wrong_onsets, gap_onsets, lifecycle_note_ons):
    return dict(in_label=in_label_on, wrong_note_onsets=wrong_onsets, gap_onsets=gap_onsets, sum=in_label_on + wrong_onsets + gap_onsets,
                lifecycle_note_ons=lifecycle_note_ons, equal=in_label_on + wrong_onsets + gap_onsets == lifecycle_note_ons)


def unit_checks():
    def row(i, n, hold, present=100, length=1000, note=40):
        return dict(label_index=i, midi_note=note, label_samples=length, pitch_present_samples=present, longest_sink_hold_samples=hold, note_ons_inside_label=n)
    before = [row(0, 5, 100), row(1, 3, 100), row(2, 1, 100), row(3, 4, 100), row(4, 0, 0, present=0), row(5, 6, 100)]
    after = [row(0, 3, 150), row(1, 4, 100),          # label 1: NoteOn growth is a regression
             row(2, 0, 100),                          # label 2: lost its last attack (also a decrease)
             row(3, 4, 90),                           # label 3: shorter hold is a regression
             row(4, 0, 0, present=0), row(5, 6, 100, present=90)]   # label 5: pitch loss is a regression
    c = compare(before, after)
    ok = [c['regress'] == [1, 3, 5], c['longer'] == [0], c['fewer'] == [0, 2], c['lost_last_attack'] == [2], c['present_changed'] == [5],
          c['before_on'] == 19 and c['after_on'] == 17, c['present_labels'] == 5]
    bad = False
    try:
        compare(before[:2], [row(0, 1, 1, note=41), row(1, 1, 1)])
    except ValueError:
        bad = True
    ok.append(bad)
    ok.append([bucket_name(n) for n in (0, 1, 2, 5, 6, 20, 21, 50, 51, 100, 101, 400)] == ['0', '1', '2-5', '2-5', '6-20', '6-20', '21-50', '21-50', '51-100', '51-100', '>100', '>100'])
    t = bucket_table([(0, 0), (1, 1), (30, 20), (30, 30), (200, 150)])
    ok.append(t['21-50']['labels'] == 2 and t['21-50']['removed'] == 10 and abs(t['21-50']['removed_share'] - 1 / 6) < 1e-12 and t['0']['removed_share'] is None
              and t['>100']['removed'] == 50)
    ok.append(overlap_excess(251, 345600, 341059) == 180)                     # extended-middle label 2: 4,541 samples outside the longest hold fit 70 notes
    ok.append(overlap_excess(1, 1000, 0) == 0 and overlap_excess(3, 640, 0) == 0 and overlap_excess(12, 640, 0) == 1 and overlap_excess(5, 500, 600) == 4)
    ok.append(accounting(4209, 1200, 517, 5926)['equal'] and not accounting(4209, 1200, 518, 5926)['equal'])
    cl = check_claims({'a': 1, 'b': 2.00001, 'c': 3}, {'a': 1, 'b': 2.0, 'c': 4})
    ok.append(cl['a']['match'] and cl['b']['match'] and not cl['c']['match'])
    ok.append(not check_claims({}, {'a': 1})['a']['match'])
    cc = concentration([row(0, 30, 100), row(1, 5, 0)], [row(0, 22, 100), row(1, 5, 0)])      # label 0: room (1000 - 100) // 64 = 14; excess 30-1-14 = 15 before, 22-1-14 = 7 after
    ok.append(cc['note_ons_after'] == 27 and cc['in_labels_with_21_or_more'] == 22 and abs(cc['share_in_labels_with_21_or_more'] - 22 / 27) < 1e-12
              and cc['heaviest_label']['label'] == 0 and cc['overlap_excess_before'] == 15 and cc['overlap_excess_after'] == 7 and len(cc['overlap_rows']) == 1)
    wb = [row(0, 4, 100, present=900),                                   # label 0 and label 1: same pitch, NoteOns, and length / hold / present within 96 samples: one window
          row(1, 4, 150, present=900, length=1050),
          row(2, 4, 100, present=900, length=1200),                      # 200 samples longer than label 0: its own window
          row(3, 4, 100, present=900, note=41),                          # another pitch
          row(4, 0, 0, present=0, note=41), row(5, 0, 0, present=0, note=41),   # no NoteOn before: never grouped
          row(6, 3, 100, present=900, note=42), row(7, 4, 100, present=900, note=42),   # different NoteOn counts
          row(8, 4, 300, present=900, note=42)]                          # same NoteOns as label 7 but a hold 200 samples longer: its own window
    ok.append(window_groups(wb, wb) == [[0, 1], [2], [3], [4], [5], [6], [7], [8]])
    wa = [dict(x) for x in wb]
    wa[1]['note_ons_inside_label'] = 3                                   # the two modes disagree about label 1: not the same window
    ok.append(window_groups(wb, wa) == [[0], [1], [2], [3], [4], [5], [6], [7], [8]])
    four = [row(i, 4, 1585, present=2000, length=2299 + i, note=51) for i in range(4)]
    db, da, g = distinct_rows(four, four)
    ok.append(g == [[0, 1, 2, 3]] and len(db) == 1 and db[0]['label_index'] == 0 and da[0]['label_index'] == 0 and window_groups([], []) == [])
    return ok


def ordinary_claims(ledger, verdict):
    """The numbers the RESUME paragraph states, derived from the ledger report's per-label rows and counters."""
    A = ledger['ledgers']['per_voice']['labels']
    S = ledger['ledgers']['stable_note']['labels']
    c = compare(A, S)
    tgt = ledger['target_label']
    i = tgt['label_index']
    a, s = A[i], S[i]
    native_s, native_a = ledger['ledgers']['stable_note']['native'], ledger['ledgers']['per_voice']['native']
    safety_a, safety_s = ledger['ledgers']['per_voice']['pitch_safety'], ledger['ledgers']['stable_note']['pitch_safety']
    derived = dict(target_label=i, target_note=tgt['midi_note'], target_string_mask=tgt['string_mask'], target_start=tgt['start_sample'], target_end=tgt['end_sample'],
                   target_label_samples=a['label_samples'], target_present=a['pitch_present_samples'],
                   target_note_ons_before=a['note_ons_inside_label'], target_note_ons_after=s['note_ons_inside_label'],
                   target_reduction_percent=100 * (a['note_ons_inside_label'] - s['note_ons_inside_label']) / a['note_ons_inside_label'],
                   target_hold_before=a['longest_sink_hold_samples'], target_hold_after=s['longest_sink_hold_samples'],
                   target_hold_ms_before=1000 * a['longest_sink_hold_samples'] / SAMPLE_RATE, target_hold_ms_after=1000 * s['longest_sink_hold_samples'] / SAMPLE_RATE,
                   target_present_percent=100 * a['pitch_present_samples'] / a['label_samples'],
                   labels=c['labels'], labels_longer_hold=len(c['longer']), labels_fewer_note_ons=len(c['fewer']), label_regressions=len(c['regress']),
                   callbacks_before=native_a['source_callbacks'], callbacks_after=native_s['source_callbacks'], pairs=native_s['transferred_pairs'],
                   suppressed_events=native_s['suppressed_source_events'],
                   wrong_note_voice_samples=safety_s['false_wrong_note_voice_samples'], gap_voice_samples=safety_s['false_gap_voice_samples'],
                   wrong_note_onsets_before=safety_a['false_wrong_note_onsets'], wrong_note_onsets_after=safety_s['false_wrong_note_onsets'],
                   gap_onsets_before=safety_a['false_gap_onsets'], gap_onsets_after=safety_s['false_gap_onsets'],
                   open_note_at_eof=ledger['ledgers']['stable_note']['open_pitches_at_eof'][0])
    extra = dict(
        target_row_matches_verdict=verdict['target']['before'] == a and verdict['target']['after'] == s,
        target_matches_report_target=ledger['ledgers']['stable_note']['target'] == s,
        pitch_present_equal_in_every_label=not c['present_changed'],
        labels_that_lost_their_last_note_on=c['lost_last_attack'],
        open_eof_both_modes_equal=ledger['ledgers']['per_voice']['open_pitches_at_eof'] == ledger['ledgers']['stable_note']['open_pitches_at_eof'],
        pairs_times_two_equals_suppressed=2 * native_s['transferred_pairs'] == native_s['suppressed_source_events'],
        callbacks_after_equal_before_minus_suppressed=native_a['source_callbacks'] - native_s['suppressed_source_events'] == native_s['source_callbacks'],
        pairing_errors=(native_a['callback_pairing_errors'], native_s['callback_pairing_errors']),
        verdict_decision=verdict['decision'], report_decision=ledger['decision'])
    return derived, c, extra


def main(run):
    ok = unit_checks()
    print('unit checks', ok)
    if not all(ok):
        raise SystemExit('unit checks failed')
    if not run:
        return
    if os.path.exists(OUT):
        raise SystemExit('output exists; refusing to overwrite')
    ledger, verdict, corpus = load(LEDGER), load(VERDICT), load(CORPUS)

    # ---- A. the ordinary-recording claims
    derived, cmp_ord, extra = ordinary_claims(ledger, verdict)
    claims = check_claims(derived, CLAIMED)
    identity = dict(ledger_sha256=sha(LEDGER), verdict_report_sha256=verdict['report_sha256'], report_matches_verdict=sha(LEDGER) == verdict['report_sha256'],
                    corpus_sha256=sha(CORPUS), ledger_rows_equal_corpus_ordinary_rows=dict(
                        per_voice_vs_before=ledger['ledgers']['per_voice']['labels'] == corpus['datasets']['ordinary']['comparisons']['before']['labels'],
                        stable_note_vs_after=ledger['ledgers']['stable_note']['labels'] == corpus['datasets']['ordinary']['comparisons']['after']['labels']),
                    corpus_safety_equals_ledger_safety=dict(
                        before=corpus['datasets']['ordinary']['comparisons']['before']['safety'] == ledger['ledgers']['per_voice']['pitch_safety'],
                        after=corpus['datasets']['ordinary']['comparisons']['after']['safety'] == ledger['ledgers']['stable_note']['pitch_safety']))
    life = ledger['runs']['current-on']['physical_lifecycle']
    acc_before = accounting(cmp_ord['before_on'], ledger['ledgers']['per_voice']['pitch_safety']['false_wrong_note_onsets'],
                            ledger['ledgers']['per_voice']['pitch_safety']['false_gap_onsets'], life['note_ons'])
    acc_after = accounting(cmp_ord['after_on'], ledger['ledgers']['stable_note']['pitch_safety']['false_wrong_note_onsets'],
                           ledger['ledgers']['stable_note']['pitch_safety']['false_gap_onsets'], life['note_ons'] - ledger['ledgers']['stable_note']['native']['transferred_pairs'])
    acc = dict(per_voice=acc_before, stable_note=acc_after, note_ons_plus_note_offs=life['note_ons'] + life['note_offs'],
               input_events=ledger['ledgers']['per_voice']['native']['input_events'],
               removed_in_label=cmp_ord['before_on'] - cmp_ord['after_on'],
               removed_wrong_note=acc_before['wrong_note_onsets'] - acc_after['wrong_note_onsets'], removed_gap=acc_before['gap_onsets'] - acc_after['gap_onsets'],
               removed_equals_pairs=(cmp_ord['before_on'] - cmp_ord['after_on']) + (acc_before['wrong_note_onsets'] - acc_after['wrong_note_onsets'])
               + (acc_before['gap_onsets'] - acc_after['gap_onsets']) == ledger['ledgers']['stable_note']['native']['transferred_pairs'])

    # ---- B. the 14 datasets of the corpus run, from the rows
    datasets = {}
    delta_mismatches = 0
    for name, ds in corpus['datasets'].items():
        comp = ds['comparisons']
        B, A = comp['before']['labels'], comp['after']['labels']
        c = compare(B, A)
        for b, a, d in zip(B, A, comp['label_changes']):
            if not (d['label_index'] == b['label_index'] and d['pitch_present_delta'] == a['pitch_present_samples'] - b['pitch_present_samples']
                    and d['longest_hold_delta'] == a['longest_sink_hold_samples'] - b['longest_sink_hold_samples']
                    and d['note_on_delta'] == a['note_ons_inside_label'] - b['note_ons_inside_label']):
                delta_mismatches += 1
        g = comp['gates']
        no_pitch_loss = not [1 for b, a in zip(B, A) if a['pitch_present_samples'] < b['pitch_present_samples']]
        no_shorter_hold = not [1 for b, a in zip(B, A) if a['longest_sink_hold_samples'] < b['longest_sink_hold_samples']]
        no_note_on_growth = not [1 for b, a in zip(B, A) if a['note_ons_inside_label'] > b['note_ons_inside_label']]
        Bd, Ad, groups = distinct_rows(B, A)
        cd = compare(Bd, Ad)
        by_first = {B[x[0]]['label_index']: x for x in groups}
        distinct = dict(windows=len(groups), labels_merged_into_windows=len(B) - len(groups), largest_window_in_labels=max((len(x) for x in groups), default=0),
                        windows_with_more_than_one_label=sum(1 for x in groups if len(x) > 1),
                        note_ons_before=cd['before_on'], note_ons_after=cd['after_on'], removed=cd['before_on'] - cd['after_on'],
                        removed_share=(cd['before_on'] - cd['after_on']) / cd['before_on'] if cd['before_on'] else None,
                        lost_last_attack_windows=[dict(first_label=i, labels=[B[p]['label_index'] for p in by_first[i]]) for i in cd['lost_last_attack']],
                        regressions=len(cd['regress']))
        lost_rows = [dict(label=b['label_index'], midi_note=b['midi_note'], label_ms=1000 * b['label_samples'] / SAMPLE_RATE,
                          note_ons_before=b['note_ons_inside_label'], note_ons_after=a['note_ons_inside_label'],
                          hold_before_ms=1000 * b['longest_sink_hold_samples'] / SAMPLE_RATE, hold_after_ms=1000 * a['longest_sink_hold_samples'] / SAMPLE_RATE,
                          hold_after_is_whole_label=a['longest_sink_hold_samples'] == a['label_samples'],
                          present_before=b['pitch_present_samples'], present_after=a['pitch_present_samples'])
                     for b, a in zip(B, A) if b['note_ons_inside_label'] >= 1 and a['note_ons_inside_label'] == 0]
        # labels where the pitch is present but no NoteOn falls inside the label: an earlier note covers it (carry-over), the baseline already has some
        silent_before = sum(1 for b in B if b['pitch_present_samples'] > 0 and b['note_ons_inside_label'] == 0)
        silent_after = sum(1 for a in A if a['pitch_present_samples'] > 0 and a['note_ons_inside_label'] == 0)
        datasets[name] = dict(labels=c['labels'], present_labels=c['present_labels'], note_ons_before=c['before_on'], note_ons_after=c['after_on'], distinct_windows=distinct,
                              lost_last_attack_rows=lost_rows, pitch_present_without_note_on_before=silent_before, pitch_present_without_note_on_after=silent_after,
                              removed=c['before_on'] - c['after_on'], removed_share=(c['before_on'] - c['after_on']) / c['before_on'] if c['before_on'] else None,
                              labels_fewer=len(c['fewer']), labels_longer_hold=len(c['longer']), regressions=len(c['regress']),
                              pitch_present_changed=len(c['present_changed']), lost_last_attack=c['lost_last_attack'],
                              report_gates=g, report_gate_pass=comp['gate_pass'],
                              rows_agree_with_report_label_gates=(no_pitch_loss == bool(g['no_label_pitch_loss']) and no_shorter_hold == bool(g['no_shorter_label_holds'])
                                                                  and no_note_on_growth == bool(g['no_label_attack_growth'])),
                              dataset_gate_pass=ds['gate_pass'],
                              open_notes_equal=comp['before']['open_notes_at_eof'] == comp['after']['open_notes_at_eof'])
    totals = dict(datasets=len(datasets), labels=sum(d['labels'] for d in datasets.values()), note_ons_before=sum(d['note_ons_before'] for d in datasets.values()),
                  note_ons_after=sum(d['note_ons_after'] for d in datasets.values()), regressions=sum(d['regressions'] for d in datasets.values()),
                  lost_last_attack_labels=sum(len(d['lost_last_attack']) for d in datasets.values()),
                  label_changes_mismatching_rows=delta_mismatches,
                  corpus_decision=corpus['decision'], corpus_gate_pass=corpus['corpus_gate_pass'],
                  datasets_failing_gate=[n for n, d in datasets.items() if not d['dataset_gate_pass']],
                  acoustic_repluck_preservation=corpus['acoustic_repluck_preservation'], physical_string_assignment=corpus['physical_string_assignment'])
    totals['removed'] = totals['note_ons_before'] - totals['note_ons_after']
    totals['removed_share'] = totals['removed'] / totals['note_ons_before']
    dd = [d['distinct_windows'] for d in datasets.values()]
    dtot = dict(windows=sum(d['windows'] for d in dd), labels_merged_into_windows=sum(d['labels_merged_into_windows'] for d in dd),
                note_ons_before=sum(d['note_ons_before'] for d in dd), note_ons_after=sum(d['note_ons_after'] for d in dd),
                lost_last_attack_windows=sum(len(d['lost_last_attack_windows']) for d in dd),
                datasets_with_merged_labels=[n for n, d in datasets.items() if d['distinct_windows']['labels_merged_into_windows']],
                control_ordinary_labels_merged=datasets['ordinary']['distinct_windows']['labels_merged_into_windows'])
    dtot['removed'] = dtot['note_ons_before'] - dtot['note_ons_after']
    dtot['removed_share'] = dtot['removed'] / dtot['note_ons_before']
    totals['distinct_windows'] = dtot

    # ---- C. POST HOC descriptive, label-weighted and per inferred window
    per_dataset_c, pooled_label_pairs, pooled_window_pairs, overlap_rows = {}, [], [], []
    for name, ds in corpus['datasets'].items():
        B, A = ds['comparisons']['before']['labels'], ds['comparisons']['after']['labels']
        Bd, Ad, groups = distinct_rows(B, A)
        by_first = {B[x[0]]['label_index']: x for x in groups}
        pooled_label_pairs += [(b['note_ons_inside_label'], a['note_ons_inside_label']) for b, a in zip(B, A)]
        pooled_window_pairs += [(b['note_ons_inside_label'], a['note_ons_inside_label']) for b, a in zip(Bd, Ad)]
        lw, dw = concentration(B, A), concentration(Bd, Ad)
        lw.pop('overlap_rows')
        for r in dw.pop('overlap_rows'):
            overlap_rows.append(dict(dataset=name, labels_in_window=[B[p]['label_index'] for p in by_first[r['label']]], **r))
        per_dataset_c[name] = dict(label_weighted=lw, per_window=dw)
    overlap_rows.sort(key=lambda r: -r['overlap_excess_after'])

    def pooled_block(pairs, key):
        return dict(pooled_buckets=bucket_table(pairs), pooled_note_ons_after=sum(a for _, a in pairs),
                    pooled_after_in_labels_with_21_or_more=sum(a for _, a in pairs if a >= 21),
                    pooled_overlap_excess_before=sum(d[key]['overlap_excess_before'] for d in per_dataset_c.values()),
                    pooled_overlap_excess_after=sum(d[key]['overlap_excess_after'] for d in per_dataset_c.values()))
    post_hoc = dict(min_note_samples=MIN_NOTE_SAMPLES, group_tolerance_samples=GROUP_TOLERANCE,
                    label_weighted=pooled_block(pooled_label_pairs, 'label_weighted'), per_window=pooled_block(pooled_window_pairs, 'per_window'),
                    per_dataset=per_dataset_c, overlap_rows=overlap_rows)
    # ordinary-only view of the same buckets, for the recording the claims are about
    ordinary_pairs = [(b['note_ons_inside_label'], a['note_ons_inside_label']) for b, a in zip(ledger['ledgers']['per_voice']['labels'], ledger['ledgers']['stable_note']['labels'])]
    post_hoc['ordinary_buckets'] = bucket_table(ordinary_pairs)

    out = dict(schema='m3_stable_note_ledger_check_v1', registered=False, post_hoc_parts=['C'], derived_from=dict(ledger=os.path.relpath(LEDGER, ROOT), verdict=os.path.relpath(VERDICT, ROOT), corpus=os.path.relpath(CORPUS, ROOT)),
               identity=identity, claims=claims, claims_all_match=all(v['match'] for v in claims.values()), extra_checks=extra, accounting=acc,
               corpus=dict(datasets=datasets, totals=totals), post_hoc=post_hoc)
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', os.path.basename(OUT))


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--selftest'
    if arg not in ('--selftest', '--run'):
        raise SystemExit(__doc__)
    main(arg == '--run')
