#!/usr/bin/env python3
"""Per-label reconciliation of the relief-eligible population E against the realized relief screen (saved files only: no audio, no dispatch, no replay).

  python3 -I CLAUDE-M3-RELIEF-RECONCILE-20261120.py PROJECT_ROOT V5_TABLE.tsv.gz REPORT.json OUT.json

Why: my lane analysis (CLAUDE-M3-RELIEF-LANE-ANALYSIS-20261120.py) predicted that a min-fret free lane matches the annotation in about 5% of
the 14,038 relief-eligible frames, while the screen realized 13,412 correct-lane matched frames and +7,810 wrong-string frames on the same
ordinary dataset. This checks, per label, whether E and the realized gain describe the same notes, so the contradiction is located and not
explained away.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (exploratory, associations only, one dataset, the rendered-parent proxy, annotation is not audibility):
  E_label[lid] = the number of frames of population E of the lane analysis for that label (same definition, imported from its docstring:
    genuine note 61..84, candidate selection code 3, not rendered, not quiet, energy observed, rendered-lower-parent proxy relief predicate,
    label mask != 0). Taken from the v5 table (CURRENT, collision on).
  Realized[lid] = comparison.snapshot.changed_labels[label_index == lid].matched_delta from the screen's report.json.
  Mapping check: lid in the v5 table is trusted as report label_index only if (midi_note, string_mask) agree for EVERY changed label present in
    both; otherwise the mapping is reported as unverified and no per-label comparison is stated.
  Reported: sums of both; how many changed labels have E_label == 0; how many labels have E_label > 0 and Realized == 0 (or <= 0);
    Realized/E_label ratio histogram on labels with both positive; the labels with the largest |Realized - E_label|; and the E_label total on
    labels with Realized <= 0. Nothing is thresholded or tuned.
"""
import collections, json, sys

PROJ, TABLE, REPORT, OUT = sys.argv[1:5]
sys.argv = [sys.argv[0], PROJ]
import importlib.util
spec = importlib.util.spec_from_file_location('m3an', PROJ + '/docs/recovery/CLAUDE-M3-OBSERVATION-ANALYSIS-20261120.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

RELATED = {12, 19, 24, 28, 31, 36}


def main():
    rep = json.load(open(REPORT))
    changed = rep['datasets']['ordinary']['comparison']['snapshot']['changed_labels']
    e_frames = collections.Counter()
    label_meta = {}                       # lid -> (note, mask)
    unmatched_mask_zero = 0
    for fr in m.load_new(TABLE):
        voice_notes = {v[1] for v in fr['voices']}
        lab = {}
        for (lid, note, mask) in fr['labels']:
            label_meta.setdefault(lid, (note, mask))
            lab.setdefault(note, (lid, mask))
        for note, (lid, mask) in lab.items():
            if not 61 <= note <= 84:
                continue
            c = fr['rows'].get(note)
            if c is None or note in voice_notes or fr['quiet'] or c['selection'] != 3 or c.get('energy_observed') == 0:
                continue
            P = [v for v in voice_notes if v < note]
            if not P or any((note - v) in RELATED for v in P):
                continue
            if mask == 0:
                unmatched_mask_zero += 1
                continue
            e_frames[lid] += 1
    # mapping check
    bad = []
    present = 0
    for r in changed:
        lid = r['label_index']
        if lid in label_meta:
            present += 1
            if label_meta[lid] != (r['midi_note'], r['string_mask']):
                bad.append((lid, label_meta[lid], (r['midi_note'], r['string_mask'])))
    mapping_ok = present > 0 and not bad
    out = dict(changed_labels=len(changed), present_in_v5_table=present, mapping_mismatches=bad[:20], mapping_verified=mapping_ok,
               e_total=sum(e_frames.values()), e_labels=len(e_frames), realized_total=sum(r['matched_delta'] for r in changed),
               realized_positive_total=sum(r['matched_delta'] for r in changed if r['matched_delta'] > 0),
               realized_negative_total=sum(r['matched_delta'] for r in changed if r['matched_delta'] < 0))
    if mapping_ok:
        real = {r['label_index']: r['matched_delta'] for r in changed}
        both = [l for l in e_frames if l in real and real[l] > 0]
        out['changed_labels_with_E_zero'] = sorted(l for l in real if e_frames.get(l, 0) == 0)
        out['changed_labels_with_E_zero_realized_positive_total'] = sum(real[l] for l in real if e_frames.get(l, 0) == 0 and real[l] > 0)
        out['E_positive_labels_not_in_changed'] = sorted(l for l in e_frames if l not in real)
        out['E_total_on_labels_not_in_changed'] = sum(e_frames[l] for l in e_frames if l not in real)
        out['E_positive_labels_realized_nonpositive'] = {str(l): [e_frames[l], real[l]] for l in e_frames if l in real and real[l] <= 0}
        bins = collections.Counter()
        for l in both:
            q = real[l] / e_frames[l]
            bins['<=0.5' if q <= 0.5 else '0.5-0.9' if q <= 0.9 else '0.9-1.1' if q <= 1.1 else '>1.1'] += 1
        out['ratio_histogram_labels_both_positive'] = dict(bins)
        rows = sorted(((abs(real.get(l, 0) - e_frames.get(l, 0)), l) for l in set(real) | set(e_frames)), reverse=True)[:15]
        out['largest_gaps'] = [dict(label=l, note=label_meta.get(l, (None, None))[0], E=e_frames.get(l, 0), realized=real.get(l, 0)) for _, l in rows]
        out['sum_min'] = sum(min(e_frames.get(l, 0), max(real.get(l, 0), 0)) for l in set(real) | set(e_frames))
    json.dump(out, open(OUT, 'w'), indent=1, default=str)
    print(json.dumps(out, indent=1, default=str))


main()
