#!/usr/bin/env python3
"""Independent read of the collected Basic Pitch comparison report (saved report.json only: no audio, no dispatch, no download, no replay).

  python3 -I CLAUDE-M3-BASIC-PITCH-READ-20261121.py REPORT.json OUT.json

Input: build/github-results/basic-pitch-comparison-44884737134/basic-pitch-result/report/report.json (schema m3_basic_pitch_comparison_v1).
Every number below is arithmetic on fields already in that report; nothing is re-scored and nothing is tuned.

PREDECLARED BEFORE ANY NUMBER WAS COMPUTED (descriptive; one run, one corpus; "present" = expected pitch occupied, pitch only, never string):
  1. Gate decomposition. Re-evaluate each clause of the frozen rule from the report's own deltas, per dataset:
       coverage gain >= +5 pp (ordinary only); extra_pitch_voice_samples delta <= 0; extra_gap_pitch_samples delta <= 0;
       exact_pitch_set_samples delta >= 0; all_expected_pitches_samples delta >= 0;
       no label with min(present delta, longest-hold delta) < 0.
     Report which clauses pass and the set of labels that violate the last one.
  2. Label losses (ordinary). Labels with present delta < 0 or longest-hold delta < 0: counts, summed sample loss, summed gain on gaining
     labels, labels whose Basic Pitch present duration is exactly 0 (a missed note) and their share of the loss. Losses by MIDI band
     (<48, 48-59, 60-71, 72+) with CURRENT and Basic Pitch coverage of annotated samples in that band. Loss size as a fraction of the label.
  3. Polyphony. Label -> number of distinct pitches in its annotation interval (report intervals[].distinct_pitch_count). Per count: labels,
     losing labels, CURRENT and Basic Pitch coverage of annotated samples, intervals with any all-expected-pitch time.
  4. Union arithmetic (report_only_union, never part of the verdict). Union minus Basic Pitch and union minus CURRENT for expected-pitch
     samples, extra-pitch samples during labels and gap extras. 'Pitch-sample share' = genuine / (genuine + extra), pitch-samples, not frames,
     as a ratio of two report fields: for Basic Pitch, CURRENT, the union, and the CURRENT-only increment (union minus Basic Pitch).
CURRENT here is the saved collision-enabled M3 CURRENT MIDI the report names (ordinary run 44835727027, extended-middle run 43736868711).
"""
import collections, json, sys

REPORT, OUT = sys.argv[1:3]


def band(n):
    return 'below48' if n < 48 else '48to59' if n < 60 else '60to71' if n < 72 else '72plus'


def gates(c):
    d = c['sample_deltas']
    lab = [r for r in c['label_deltas'] if min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0]
    return dict(
        coverage_gain_pp=c['pitch_coverage_gain_pp'],
        coverage_gain_ge_5pp=c['pitch_coverage_gain_pp'] >= 5,
        extra_voice_delta=d['extra_pitch_voice_samples'], extra_voice_ok=d['extra_pitch_voice_samples'] <= 0,
        gap_delta=c['extra_gap_pitch_samples_delta'], gap_ok=c['extra_gap_pitch_samples_delta'] <= 0,
        exact_set_delta=d['exact_pitch_set_samples'], exact_set_ok=d['exact_pitch_set_samples'] >= 0,
        all_expected_delta=d['all_expected_pitches_samples'], all_expected_ok=d['all_expected_pitches_samples'] >= 0,
        labels_violating_per_label_clause=len(lab), per_label_ok=not lab,
        report_no_pitch_safety_regression=c['no_pitch_safety_regression'])


def share(genuine, extra):
    return genuine / (genuine + extra) if genuine + extra else None


def main():
    d = json.load(open(REPORT))
    rep = dict(report_schema=d['schema'], report_state=d['state'], screen=d['screen'])
    for name in ('ordinary', 'extended-middle'):
        rep[name] = dict(gates=gates(d['datasets'][name]['comparison']))

    ds = d['datasets']['ordinary']
    c = ds['comparison']
    L = c['label_deltas']
    lost_p = [r for r in L if r['present_samples_delta'] < 0]
    lost_l = [r for r in L if r['longest_present_samples_delta'] < 0]
    either = [r for r in L if min(r['present_samples_delta'], r['longest_present_samples_delta']) < 0]
    gain = [r for r in L if r['present_samples_delta'] > 0]
    loss_sum = sum(r['present_samples_delta'] for r in lost_p)
    zeroed = [r for r in lost_p if r['model_present_samples'] == 0]
    fr = sorted(-r['present_samples_delta'] / r['annotated_samples'] for r in lost_p)
    bands = {}
    for b in ('below48', '48to59', '60to71', '72plus'):
        rows = [r for r in L if band(r['midi_note']) == b]
        ann = sum(r['annotated_samples'] for r in rows)
        bands[b] = dict(labels=len(rows), annotated_samples=ann,
                        current_coverage=sum(r['current_present_samples'] for r in rows) / ann,
                        basic_pitch_coverage=sum(r['model_present_samples'] for r in rows) / ann,
                        labels_losing_present=sum(r['present_samples_delta'] < 0 for r in rows),
                        labels_losing_longest=sum(r['longest_present_samples_delta'] < 0 for r in rows),
                        labels_current_zero=sum(r['current_present_samples'] == 0 for r in rows),
                        labels_basic_pitch_zero=sum(r['model_present_samples'] == 0 for r in rows),
                        loss_samples=sum(min(0, r['present_samples_delta']) for r in rows),
                        gain_samples=sum(max(0, r['present_samples_delta']) for r in rows))
    rep['ordinary']['label_losses'] = dict(
        labels=len(L), losing_present=len(lost_p), losing_longest=len(lost_l), losing_either=len(either),
        gaining_present=len(gain), unchanged=sum(1 for r in L if r['present_samples_delta'] == 0 and r['longest_present_samples_delta'] == 0),
        summed_present_loss_samples=loss_sum, summed_longest_loss_samples=sum(r['longest_present_samples_delta'] for r in lost_l),
        summed_present_gain_samples=sum(r['present_samples_delta'] for r in gain),
        losing_labels_with_basic_pitch_zero=len(zeroed), zeroed_loss_samples=sum(r['present_samples_delta'] for r in zeroed),
        zeroed_share_of_loss=sum(r['present_samples_delta'] for r in zeroed) / loss_sum,
        loss_fraction_of_label=dict(median=fr[len(fr) // 2], p90=fr[int(len(fr) * .9)], max=fr[-1],
                                    under_5pct=sum(f < .05 for f in fr), under_20pct=sum(f < .2 for f in fr)),
        loss_seconds_at_96k=-loss_sum / 96000, bands=bands,
        worst=[dict(label=r['label_index'], note=r['midi_note'], annotated=r['annotated_samples'], current=r['current_present_samples'],
                    basic_pitch=r['model_present_samples']) for r in sorted(lost_p, key=lambda r: r['present_samples_delta'])[:8]])

    iv = ds['model']['pitch_sets']['intervals']
    lab2n = {li: i['distinct_pitch_count'] for i in iv for li in i['source_label_indices']}
    poly = collections.defaultdict(collections.Counter)
    for r in L:
        n = lab2n[r['label_index']]
        p = poly[n]
        p['labels'] += 1
        p['annotated'] += r['annotated_samples']
        p['current_present'] += r['current_present_samples']
        p['bp_present'] += r['model_present_samples']
        p['losing_labels'] += r['present_samples_delta'] < 0
        p['bp_zero_labels'] += r['model_present_samples'] == 0
    cnt = collections.Counter(); anyall = collections.Counter()
    for i in iv:
        cnt[i['distinct_pitch_count']] += 1
        anyall[i['distinct_pitch_count']] += i['all_expected_pitches_samples'] > 0
    rep['ordinary']['polyphony'] = {str(n): dict(
        labels=p['labels'], losing_labels=p['losing_labels'], basic_pitch_zero_labels=p['bp_zero_labels'],
        current_coverage=p['current_present'] / p['annotated'], basic_pitch_coverage=p['bp_present'] / p['annotated'],
        intervals=cnt[n], intervals_with_any_all_expected_time=anyall[n]) for n, p in sorted(poly.items())}

    for name in ('ordinary', 'extended-middle'):
        dd = d['datasets'][name]
        u = dd['report_only_union']['measurement']['pitch_sets']
        bp = dd['model']['pitch_sets']
        # CURRENT = union minus the report's own deltas of the BP-vs-CURRENT comparison
        sd = dd['comparison']['sample_deltas']
        cur_present = bp['totals']['present_pitch_samples'] - sd['present_pitch_samples']
        cur_extra = bp['totals']['extra_pitch_voice_samples'] - sd['extra_pitch_voice_samples']
        cur_gap = bp['unlabeled_gap_voice_samples'] - dd['comparison']['extra_gap_pitch_samples_delta']
        ut, bt = u['totals'], bp['totals']
        inc_gen = ut['present_pitch_samples'] - bt['present_pitch_samples']
        inc_extra = ut['extra_pitch_voice_samples'] - bt['extra_pitch_voice_samples']
        inc_gap = u['unlabeled_gap_voice_samples'] - bp['unlabeled_gap_voice_samples']
        rep[name]['union'] = dict(
            present=dict(current=cur_present, basic_pitch=bt['present_pitch_samples'], union=ut['present_pitch_samples']),
            extra_during_labels=dict(current=cur_extra, basic_pitch=bt['extra_pitch_voice_samples'], union=ut['extra_pitch_voice_samples']),
            gap_extras=dict(current=cur_gap, basic_pitch=bp['unlabeled_gap_voice_samples'], union=u['unlabeled_gap_voice_samples']),
            current_only_increment_over_basic_pitch=dict(genuine=inc_gen, extra=inc_extra, gap=inc_gap,
                                                         share_genuine_vs_extra=share(inc_gen, inc_extra)),
            pitch_sample_share_during_labels=dict(current=share(cur_present, cur_extra), basic_pitch=share(bt['present_pitch_samples'], bt['extra_pitch_voice_samples']),
                                                  union=share(ut['present_pitch_samples'], ut['extra_pitch_voice_samples'])),
            exact_pitch_set_samples=dict(current=bt['exact_pitch_set_samples'] - sd['exact_pitch_set_samples'], basic_pitch=bt['exact_pitch_set_samples'], union=ut['exact_pitch_set_samples']),
            all_expected_samples=dict(current=bt['all_expected_pitches_samples'] - sd['all_expected_pitches_samples'], basic_pitch=bt['all_expected_pitches_samples'], union=ut['all_expected_pitches_samples']),
            report_added_over_basic_pitch=dd['report_only_union']['added_present_pitch_samples_over_basic_pitch'])
    json.dump(rep, open(OUT, 'w'), indent=1)
    print(json.dumps(rep, indent=1))


main()
