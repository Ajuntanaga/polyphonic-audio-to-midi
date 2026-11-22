"""POST HOC cross-check: Codex's published native joint-reset screen (run 45075475603) against the restart-evidence census.  Saved data only; no model, audio, job or native edit.

Inputs, read and never written: the census JSON (CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json, pre-registered in commit d3b51a6 and run once), the native report that Codex collected
once (build/github-results/joint-rapid-reset-45075475603/report/joint-rapid-reset/report/report.json, SHA-256 3bedd04b...), and the pinned ordinary v5 trace (through the rapid-mute check
module) for the marked runs.  Questions: (1) are the labels the native reset hurt the re-struck labels of the census, the 23 labels the rapid-mute cut loses; (2) where does each
re-struck label's first note sample fall relative to the marked run it follows (inside it, just after it, or later); (3) do the two scorers agree (index and present-sample checks)?

Disclosure: this script's first run printed an index check that required a census loss under cue M to equal the native present total for every fully missed label; that was a wrong test
(M loses only labels 42 and 70 whole), so the check was replaced by the four below and the nearest-run analysis (2) was added before anything was committed.  Numbers common to both
versions were identical.

Usage: python3 -P -E CLAUDE-M3-NATIVE-RESET-CROSSCHECK-20261122.py --run
"""
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
CENSUS = os.path.join(HERE, 'CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json')
NATIVE = os.path.join(ROOT, 'build/github-results/joint-rapid-reset-45075475603/report/joint-rapid-reset/report/report.json')
NATIVE_SHA = '3bedd04bd9b1cccc60faed718fcbdbf15e855d86a8d968b6aeb6fe3237773b8a'
OUT = os.path.join(HERE, 'CLAUDE-M3-NATIVE-RESET-CROSSCHECK-20261122.json')
CUES = ('L', 'E', 'A', 'M', 'AM')
EARLY_MS = 25


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    raw = open(NATIVE, 'rb').read()
    if hashlib.sha256(raw).hexdigest() != NATIVE_SHA:
        raise SystemExit('native report hash differs from the published pin')
    native, census = json.loads(raw), json.load(open(CENSUS))
    ad, rm = load('ad', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py'), load('rm', 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py')
    ctx = ad.dataset_context('ordinary')
    last, _ = rm.read_quiet('ordinary')
    runs = [(int(a), int(b)) for a, b in rm.marked_runs(last, ctx['horizon'])]
    cmp_ = native['datasets']['ordinary']['comparison']
    cen = census['datasets']['ordinary']
    rate = cen['rate']
    ms = lambda samples: round(samples * 1000 / rate, 2)
    by = {r['label_index']: r for r in cmp_['pitch']['label_deltas']}
    pos = cen['positive_labels']
    lost = {i: r['current_present_samples'] - r['model_present_samples'] for i, r in by.items() if r['current_present_samples'] > r['model_present_samples']}
    gained = {i: r['model_present_samples'] - r['current_present_samples'] for i, r in by.items() if r['model_present_samples'] > r['current_present_samples']}
    budgets = {k: sorted(f['label_index'] for f in v['failures']) for k, v in cmp_['label_budgets'].items()}
    pitch_fail = budgets['pitch_present_samples']
    full = sorted(f['label_index'] for f in cmp_['label_budgets']['pitch_present_samples']['failures'] if f['after'] == 0)
    table = {}
    for i in pos:
        lab, spans, s = by[i], census['datasets']['ordinary']['truncated_spans'], by[i]['start_sample']
        span = next((t for t in spans if t['cls'] == 'positive' and t['pitch'] == lab['midi_note'] and lab['start_sample'] < t['span'][1] and lab['end_sample'] > t['cut']), None)
        before = [r for r in runs if r[0] <= s]
        run = before[-1] if before else None
        offset = None if run is None else s - run[1]           # negative: the label starts inside the run, that far before its end
        where = None if run is None else ('inside_run' if offset < 0 else 'within_25ms_after_run_end' if offset <= EARLY_MS * rate // 1000 else 'later_than_25ms_after_run_end')
        table[str(i)] = dict(midi=lab['midi_note'], present=lab['current_present_samples'], native_lost=lost.get(i, 0), native_fully_missed=i in full,
                             census_total_loss={c: cen['census'][c]['positive_label_loss_samples'][str(i)] for c in CUES},
                             start_minus_first_run_end_of_span_ms=None if span is None else ms(s - span['run_end']),
                             nearest_preceding_run_end_offset_ms=None if offset is None else ms(offset), where=where)
    tally = {}
    for key, group in (('lost_natively', [i for i in pos if i in lost]), ('not_lost_natively', [i for i in pos if i not in lost]), ('fully_missed_natively', full)):
        row = tally.setdefault(key, {})
        for i in group:
            row[table[str(i)]['where']] = row.get(table[str(i)]['where'], 0) + 1
    newly_missed_pairs = [(i, c) for c in CUES for i in cen['census'][c]['new_missed_vs_mask']]
    checks = dict(
        aggregate_current_present_equal=sum(r['current_present_samples'] for r in by.values()) == cen['variants']['CURRENT']['present'],
        every_positive_maps_to_a_positive_span_of_the_same_pitch=all(table[str(i)]['start_minus_first_run_end_of_span_ms'] is not None for i in pos),
        census_loss_never_exceeds_native_present=all(table[str(i)]['census_total_loss'][c] <= table[str(i)]['present'] for i in pos for c in CUES),
        census_newly_missed_loss_equals_native_present=all(table[str(i)]['census_total_loss'][c] == table[str(i)]['present'] for i, c in newly_missed_pairs),
        newly_missed_pairs_checked=len(newly_missed_pairs))
    out = dict(schema='m3_native_reset_crosscheck_v2', post_hoc=True, native_report_sha256=NATIVE_SHA, census_json_sha256=hashlib.sha256(open(CENSUS, 'rb').read()).hexdigest(),
               native=dict(labels_losing_present=sorted(lost), labels_gaining_present=len(gained), present_lost_total=sum(lost.values()), present_gained_total=sum(gained.values()),
                           budget_failures=budgets, fully_missed=full),
               census_positive_labels=pos,
               overlap=dict(budget_failures_that_are_positives=sorted(set(pitch_fail) & set(pos)), budget_failures_not_positives=sorted(set(pitch_fail) - set(pos)),
                            fully_missed_that_are_positives=sorted(set(full) & set(pos)), positives_lost_natively=sorted(set(lost) & set(pos)),
                            positives_not_lost_natively=sorted(set(pos) - set(lost)), losing_labels_not_positives=sorted(set(lost) - set(pos))),
               checks=checks, positive_label_position_vs_nearest_preceding_marked_run=tally, positive_label_table=table)
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('native: labels losing present', len(lost), 'gaining', len(gained), '| samples lost', sum(lost.values()), 'gained', sum(gained.values()))
    print('native pitch-present budget failures', pitch_fail, '| fully missed', full)
    print('overlap', json.dumps(out['overlap']))
    print('checks', json.dumps(checks))
    print('positive labels by position of the label start relative to the nearest preceding marked run', json.dumps(tally))
    print('label | midi | present | native lost | census total loss L E A M AM | start - first run end of span (ms) | start - nearest preceding run end (ms) | where')
    for i in pos:
        t = table[str(i)]
        print(i, t['midi'], t['present'], t['native_lost'], [t['census_total_loss'][c] for c in CUES], t['start_minus_first_run_end_of_span_ms'], t['nearest_preceding_run_end_offset_ms'], t['where'])


if __name__ == '__main__':
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
