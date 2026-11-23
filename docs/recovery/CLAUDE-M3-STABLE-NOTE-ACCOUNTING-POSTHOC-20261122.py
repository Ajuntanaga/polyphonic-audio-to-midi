#!/usr/bin/env python3
"""POST HOC addendum to CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.py (committed in 87c6d9b): does the NoteOn accounting identity hold on all 14 datasets of the
VST3-component corpus run, and does it test the window grouping of the main script?
Written after the main result was committed and after I had run the identity ad hoc on the corpus report and seen its outcome (exact on 12 datasets with every label
counted once; exact on synthetic-four only once labels are grouped into windows; still 415 NoteOns too many on constructed after grouping).  Descriptive only: no
predictions, no verdict, and nothing here is a gate, a parameter, an exemption or a change to the stable-note path.  Saved data only: it reads the corpus report and
imports the main script's functions; no audio, model run, job, download or native code.

The identity: every NoteOn is exactly one of (a) inside a label of its pitch, (b) a wrong-note onset or (c) a gap onset, so
    in-label NoteOns + wrong-note onsets + gap onsets = the lifecycle's NoteOns
where the lifecycle's NoteOns come from the native runs' accepted callbacks: events = NoteOns + NoteOffs, and the notes still open at end of file have no NoteOff, so
NoteOns = (events + open at EOF) / 2 (only when no NoteOff arrives without a NoteOn).  The ordinary recording satisfies it exactly (main result, item 3).  Overlapping
same-pitch labels count one NoteOn once per label, so a dataset with such labels overshoots when every label counts, and is exact only if the grouping of labels into
windows is right.  The residual lifecycle - (in-label + wrong + gap) is negative exactly when NoteOns are counted more than once.
The same identity also gives a grouping-free count: lifecycle NoteOns - wrong-note onsets - gap onsets = the NoteOns that sit inside at least one same-pitch label,
each counted once, with no inference about which labels share a window (`implied_distinct_in_label`).

Revision note.  This script was run once with parts 1 and 2 only (the identity per dataset, the exact-dataset pooling and the grouping-free totals); that first output
was moved aside, not published.  After seeing it I printed constructed's window rows with a throwaway script (not kept) and found that its higher-pitch windows are
sets of four labels with equal NoteOn counts but label lengths that differ by far more than the 96 samples the grouping tolerates.  I then added part 3 (`unmerged`:
the single-label windows that still carry NoteOns, and whether a neighbouring window of the same pitch has the same counts) and re-ran.  Part 3 is a description of the
residual; it is not a new grouping rule, nothing here changes the grouping in the main script, and no number from the first output changed.

Usage: python3 -I CLAUDE-M3-STABLE-NOTE-ACCOUNTING-POSTHOC-20261122.py [--selftest | --run]     (--run refuses to overwrite its JSON)
"""
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, 'CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.py')
MAIN_JSON = os.path.join(HERE, 'CLAUDE-M3-STABLE-NOTE-LEDGER-CHECK-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-STABLE-NOTE-ACCOUNTING-POSTHOC-20261122.json')


def load_main():
    spec = importlib.util.spec_from_file_location('stable_note_check', MAIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def lifecycle(runs, prefix):
    """NoteOn count from one family of native runs (`per_voice` or `stable_note`); every run of the family must agree on events, open notes and pairs."""
    seen = {}
    for key, r in runs.items():
        if key.startswith(prefix):
            cb = r['callbacks']
            seen[key] = (cb['observed_events'], len(cb['note_ons_open_at_eof']), r['native']['transferred_pairs'], cb['counts']['off_without_raw_on'])
    if not seen:
        raise ValueError('no runs for ' + prefix)
    if len(set(seen.values())) != 1:
        raise ValueError('runs of one family disagree: ' + repr(sorted(set(seen.values()))))
    events, opened, pairs, orphans = next(iter(seen.values()))
    if orphans or (events + opened) % 2:
        raise ValueError('a NoteOff without a NoteOn, or odd parity: the NoteOn count is not (events + open) / 2')
    return dict(runs=len(seen), events=events, open_at_eof=opened, pairs=pairs, note_ons=(events + opened) // 2)


def residual(lifecycle_note_ons, in_label, wrong_onsets, gap_onsets):
    """Negative when NoteOns are counted more than once, positive when some NoteOn is in none of the three classes."""
    return lifecycle_note_ons - (in_label + wrong_onsets + gap_onsets)


def unmerged_single_windows(before, after, groups):
    """Windows made of a single label that carry at least one NoteOn before the path, with whether the window next to it (either side) has the same pitch and the same
    NoteOn counts in both modes.  A description of what the length-based grouping left alone; it merges nothing and is not a rule."""
    rows = []
    for k, g in enumerate(groups):
        i = g[0]
        if len(g) != 1 or before[i]['note_ons_inside_label'] < 1:
            continue
        same = False
        for n in (k - 1, k + 1):
            if 0 <= n < len(groups):
                j = groups[n][0]
                same = same or (before[j]['midi_note'] == before[i]['midi_note']
                                and before[j]['note_ons_inside_label'] == before[i]['note_ons_inside_label']
                                and after[j]['note_ons_inside_label'] == after[i]['note_ons_inside_label'])
        rows.append(dict(label=before[i]['label_index'], midi_note=before[i]['midi_note'], label_samples=before[i]['label_samples'],
                         note_ons_before=before[i]['note_ons_inside_label'], note_ons_after=after[i]['note_ons_inside_label'],
                         neighbour_same_pitch_equal_counts=same))
    return rows


def unit_checks():
    def lab(i, pitch, length, nb, hold=10, present=10):
        return dict(label_index=i, midi_note=pitch, label_samples=length, note_ons_inside_label=nb, longest_sink_hold_samples=hold, pitch_present_samples=present)

    def run(events, opened, pairs=0, orphans=0):
        return dict(callbacks=dict(observed_events=events, note_ons_open_at_eof=[0] * opened, counts=dict(off_without_raw_on=orphans)), native=dict(transferred_pairs=pairs))
    ok = []
    lc = lifecycle({'per_voice-a': run(11851, 1), 'per_voice-b': run(11851, 1), 'stable_note-a': run(8623, 1, 1614)}, 'per_voice')
    ok.append(lc['note_ons'] == 5926 and lc['runs'] == 2 and lc['pairs'] == 0)
    ok.append(lifecycle({'per_voice-a': run(11851, 1), 'stable_note-a': run(8623, 1, 1614)}, 'stable_note')['note_ons'] == 4312)
    bad = []
    for runs in ({'per_voice-a': run(10, 0), 'per_voice-b': run(12, 0)},          # the runs of one family disagree
                 {'per_voice-a': run(11, 0)},                                      # odd parity
                 {'per_voice-a': run(10, 0, orphans=1)},                           # a NoteOff without a NoteOn
                 {'stable_note-a': run(10, 0)}):                                   # no run of the requested family
        try:
            lifecycle(runs, 'per_voice')
            bad.append(False)
        except ValueError:
            bad.append(True)
    ok.append(all(bad))
    ok.append(residual(5926, 4209, 1200, 517) == 0 and residual(100, 120, 5, 1) == -26 and residual(100, 90, 5, 1) == 4)
    # the description of unmerged single-label windows: labels 0,1 are one window (same length), 2 is a shorter copy of it, 3 is another pitch, 4 has no NoteOn
    B = [lab(0, 60, 1000, 3), lab(1, 60, 1000, 3), lab(2, 60, 400, 3), lab(3, 61, 1000, 1), lab(4, 62, 1000, 0)]
    A = [lab(0, 60, 1000, 2), lab(1, 60, 1000, 2), lab(2, 60, 400, 2), lab(3, 61, 1000, 1), lab(4, 62, 1000, 0)]
    g = load_main().window_groups(B, A)
    u = unmerged_single_windows(B, A, g)
    ok.append(g == [[0, 1], [2], [3], [4]])
    ok.append([(r['label'], r['neighbour_same_pitch_equal_counts']) for r in u] == [(2, True), (3, False)])
    return ok


def main(run):
    ok = unit_checks()
    print('unit checks', ok)
    if not all(ok):
        raise SystemExit('unit checks failed')
    if not run:
        return
    if os.path.exists(OUT):
        raise SystemExit('output exists; refusing to overwrite')
    chk = load_main()
    corpus = chk.load(chk.CORPUS)
    per_dataset, exact_names = {}, []
    pairs, excess_before, excess_after = [], 0, 0
    for name, ds in corpus['datasets'].items():
        c = ds['comparisons']
        B, A = c['before']['labels'], c['after']['labels']
        Bd, Ad, groups = chk.distinct_rows(B, A)
        lb, la = lifecycle(ds['runs'], 'per_voice'), lifecycle(ds['runs'], 'stable_note')
        sb, sa = c['before']['safety'], c['after']['safety']
        label_before, label_after = sum(r['note_ons_inside_label'] for r in B), sum(r['note_ons_inside_label'] for r in A)
        window_before, window_after = sum(r['note_ons_inside_label'] for r in Bd), sum(r['note_ons_inside_label'] for r in Ad)
        rec = dict(labels=len(B), windows=len(groups), pairs=la['pairs'], runs_per_family=(lb['runs'], la['runs']),
                   events_before=lb['events'], events_after=la['events'], open_at_eof=(lb['open_at_eof'], la['open_at_eof']),
                   note_ons_before=lb['note_ons'], note_ons_after=la['note_ons'],
                   removed_equals_pairs=lb['note_ons'] - la['note_ons'] == la['pairs'] and lb['events'] - la['events'] == 2 * la['pairs'],
                   wrong_note_onsets=(sb['false_wrong_note_onsets'], sa['false_wrong_note_onsets']), gap_onsets=(sb['false_gap_onsets'], sa['false_gap_onsets']),
                   in_label_every_label_counted=(label_before, label_after), in_label_each_window_counted_once=(window_before, window_after),
                   residual_every_label_counted=(residual(lb['note_ons'], label_before, sb['false_wrong_note_onsets'], sb['false_gap_onsets']),
                                                 residual(la['note_ons'], label_after, sa['false_wrong_note_onsets'], sa['false_gap_onsets'])),
                   residual_each_window_once=(residual(lb['note_ons'], window_before, sb['false_wrong_note_onsets'], sb['false_gap_onsets']),
                                              residual(la['note_ons'], window_after, sa['false_wrong_note_onsets'], sa['false_gap_onsets'])),
                   implied_distinct_in_label=(lb['note_ons'] - sb['false_wrong_note_onsets'] - sb['false_gap_onsets'],
                                              la['note_ons'] - sa['false_wrong_note_onsets'] - sa['false_gap_onsets']))
        rec['exact_every_label_counted'] = rec['residual_every_label_counted'] == (0, 0)
        rec['exact_each_window_once'] = rec['residual_each_window_once'] == (0, 0)
        ib, ia = rec['implied_distinct_in_label']
        rec['implied_removed_share'] = (ib - ia) / ib if ib else None
        sizes = {}
        for grp in groups:
            sizes[len(grp)] = sizes.get(len(grp), 0) + 1
        rec['window_size_histogram'] = {str(k): v for k, v in sorted(sizes.items())}
        singles = unmerged_single_windows(B, A, groups)
        rec['unmerged'] = dict(single_label_windows_with_note_ons=len(singles),
                               note_ons_before=sum(r['note_ons_before'] for r in singles), note_ons_after=sum(r['note_ons_after'] for r in singles),
                               with_same_pitch_equal_count_neighbour=sum(1 for r in singles if r['neighbour_same_pitch_equal_counts']))
        if not rec['exact_each_window_once']:
            rec['unmerged']['rows'] = singles
        per_dataset[name] = rec
        if rec['exact_each_window_once']:
            exact_names.append(name)
            pairs += [(b['note_ons_inside_label'], a['note_ons_inside_label']) for b, a in zip(Bd, Ad)]
            cc = chk.concentration(Bd, Ad)
            excess_before += cc['overlap_excess_before']
            excess_after += cc['overlap_excess_after']
    pooled_before, pooled_after = sum(b for b, _ in pairs), sum(a for _, a in pairs)
    implied_before = sum(r['implied_distinct_in_label'][0] for r in per_dataset.values())
    implied_after = sum(r['implied_distinct_in_label'][1] for r in per_dataset.values())
    summary = dict(
        datasets=len(per_dataset),
        exact_every_label_counted=[n for n, r in per_dataset.items() if r['exact_every_label_counted']],
        exact_each_window_once=exact_names,
        not_exact_each_window_once=[n for n, r in per_dataset.items() if not r['exact_each_window_once']],
        every_removed_pair_accounted=all(r['removed_equals_pairs'] for r in per_dataset.values()),
        implied_distinct_in_label_note_ons=dict(before=implied_before, after=implied_after, removed=implied_before - implied_after,
                                                removed_share=(implied_before - implied_after) / implied_before),
        exact_subset=dict(datasets=len(exact_names), windows=len(pairs), note_ons_before=pooled_before, note_ons_after=pooled_after,
                          removed_share=(pooled_before - pooled_after) / pooled_before, buckets=chk.bucket_table(pairs),
                          after_in_windows_with_21_or_more=sum(a for _, a in pairs if a >= 21),
                          overlap_excess_before=excess_before, overlap_excess_after=excess_after))
    out = dict(schema='m3_stable_note_accounting_posthoc_v1', post_hoc=True, per_dataset=per_dataset, summary=summary,
               main_script_sha256=sha(MAIN), main_json_sha256=sha(MAIN_JSON), corpus_sha256=sha(chk.CORPUS))
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=1)
    print('wrote', os.path.basename(OUT))


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--selftest'
    if arg not in ('--selftest', '--run'):
        raise SystemExit(__doc__)
    main(arg == '--run')
