"""POST HOC supplement to the restart-evidence census (ordinary recording).  NOT pre-registered.

Written and run after the census result (CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json, pre-registration commit d3b51a6) showed that no candidate cue is informative.  Descriptive only:
no prediction, no policy, no threshold, nothing tuned, nothing promoted.  Saved data only: the census JSON and the saved labels; no audio, model run, job or native edit.

1. Timing separability.  For each cue, the restart delay after the end of the first marked run (infinite when the span never restarts) for the 21 positive spans against the 224 negative
   spans: medians among the restarted and a threshold-free AUC (the probability that a positive restarts earlier than a negative; 0.5 = no separation).  The first same-pitch label start
   of a positive span lies a median of about 1 ms from its run end, so the delay is also the latency after the re-strike.  Because most negatives never restart (infinite delay) and
   nearly every positive does, that AUC mixes "restarts at all" with "restarts sooner"; part 1b therefore also reports, among the spans that do restart, the probability that a positive
   restarts LATER than a negative.
2. What the negative spans are.  For each negative span, how its pitch relates to the labels that sound at the same time in its removed part (a harmonic of a lower sounding note, a
   subharmonic of a higher one, another relation, or no concurrent label), by span count and by removed-part samples.  Harmonic offsets are the semitone distances of partials 2..10
   (12, 19, 24, 28, 31, 34, 36, 38, 40).  Every other label that overlaps the removed part counts as concurrent, so this is permissive and has no chance baseline: it is context, not a test.
3. The negative spans' own history.  A negative span is an overhang when a same-pitch label overlaps its kept part [span start, cut) (the note was real and the output ran on past its
   label end) and unlabelled when no same-pitch label touches the span at all.  Counted by span and by removed-part samples, with the gap from the last same-pitch label end to the cut,
   and the restart counts of L, E, A, M and AM by class.

Disclosure: this script was run three times, all after the census result and all post hoc.  The first run printed parts 1 and 2; part 3 was then added and the JSON regenerated, and part
1b (the among-restarted AUC) was added and the JSON regenerated again.  Each regeneration was compared key by key with the run before it: every number the earlier run produced was
reproduced exactly (the script is deterministic).

Usage: python3 -P -E CLAUDE-M3-RESTART-EVIDENCE-POSTHOC-20261122.py --run
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
CENSUS = os.path.join(HERE, 'CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json')
OUT = os.path.join(HERE, 'CLAUDE-M3-RESTART-EVIDENCE-POSTHOC-20261122.json')
INF = 10 ** 12
HARMONIC = {12, 19, 24, 28, 31, 34, 36, 38, 40}
CANDIDATE_CUES = ('L', 'E', 'A', 'M', 'AM')


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def auc(pos, neg):
    total = 0.0
    for a in pos:
        for b in neg:
            total += 1.0 if a < b else (0.5 if a == b else 0.0)
    return total / (len(pos) * len(neg))


def auc_later(pos, neg):
    """Among spans that restart at all (finite delay): P(a positive restarts LATER than a negative), ties half."""
    p = [v for v in pos if v < INF]
    n = [v for v in neg if v < INF]
    if not p or not n:
        return None
    return auc([-v for v in p], [-v for v in n])


def quantile(values, fraction):
    finite = sorted(v for v in values if v < INF)
    return finite[min(len(finite) - 1, int(fraction * len(finite)))] if finite else None


def main():
    census = json.load(open(CENSUS))
    ad = load('ad', 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.py')
    ctx = ad.dataset_context('ordinary')
    labels = ctx['labels']
    rate = census['datasets']['ordinary']['rate']
    ms = lambda x: None if x is None else round(x * 1000 / rate, 2)
    spans = census['datasets']['ordinary']['truncated_spans']
    pos = [t for t in spans if t['cls'] == 'positive']
    neg = [t for t in spans if t['cls'] == 'negative']
    timing = {}
    for cue in CANDIDATE_CUES:
        dp = [(t['restart'][cue] - t['run_end']) if t['restart'][cue] is not None else INF for t in pos]
        dn = [(t['restart'][cue] - t['run_end']) if t['restart'][cue] is not None else INF for t in neg]
        al = auc_later(dp, dn)
        timing[cue] = dict(auc_positive_earlier=round(auc(dp, dn), 4), auc_positive_later_among_restarted=None if al is None else round(al, 4),
                           positives=dict(restarted=sum(d < INF for d in dp), median_ms=ms(quantile(dp, .5)), p25_ms=ms(quantile(dp, .25)), p75_ms=ms(quantile(dp, .75)), at_run_end=sum(d == 0 for d in dp)),
                           negatives=dict(restarted=sum(d < INF for d in dn), median_ms=ms(quantile(dn, .5)), p25_ms=ms(quantile(dn, .25)), p75_ms=ms(quantile(dn, .75)), at_run_end=sum(d == 0 for d in dn)))
    gap = sorted(t['first_label_start_in_removed'] - t['run_end'] for t in pos)
    relation = dict(harmonic_of_sounding_lower_note=dict(spans=0, samples=0), subharmonic_of_sounding_higher_note=dict(spans=0, samples=0),
                    other_relation_only=dict(spans=0, samples=0), no_concurrent_label=dict(spans=0, samples=0))
    detail = []
    own_class = dict(overhang_of_labelled_note=dict(spans=0, samples=0), unlabelled_span=dict(spans=0, samples=0))
    lag_to_cut = []
    for t in neg:
        p, lo, hi = t['pitch'], t['cut'], t['span'][1]
        same = [lab for lab in labels if lab['midi_note'] == p and lab['start_sample'] < lo and lab['end_sample'] > t['span'][0]]
        own = 'overhang_of_labelled_note' if same else 'unlabelled_span'
        own_class[own]['spans'] += 1
        own_class[own]['samples'] += hi - lo
        if same:
            lag_to_cut.append(lo - max(lab['end_sample'] for lab in same))
        concurrent = {}
        for lab in labels:
            a, b = max(lab['start_sample'], lo), min(lab['end_sample'], hi)
            if a < b and lab['midi_note'] != p:
                concurrent[lab['midi_note']] = concurrent.get(lab['midi_note'], 0) + (b - a)
        has_harm = any((p - q) in HARMONIC for q in concurrent)
        has_sub = any((q - p) in HARMONIC for q in concurrent)
        key = 'harmonic_of_sounding_lower_note' if has_harm else 'subharmonic_of_sounding_higher_note' if has_sub else 'other_relation_only' if concurrent else 'no_concurrent_label'
        relation[key]['spans'] += 1
        relation[key]['samples'] += hi - lo
        detail.append(dict(pitch=p, cut=lo, end=hi, relation=key, own=own, concurrent=sorted(concurrent)))
    total_samples = sum(v['samples'] for v in relation.values())
    for v in relation.values():
        v['share_of_spans'] = round(v['spans'] / len(neg), 4)
        v['share_of_removed_samples'] = round(v['samples'] / total_samples, 4)
    restarted_by_relation = {}
    for cue in ('L', 'E', 'A'):
        table = {}
        for t, d in zip(neg, detail):
            row = table.setdefault(d['relation'], [0, 0])
            row[0] += 1
            row[1] += int(t['restart'][cue] is not None)
        restarted_by_relation[cue] = {k: dict(spans=v[0], restarted=v[1]) for k, v in table.items()}
    for v in own_class.values():
        v['share_of_spans'] = round(v['spans'] / len(neg), 4)
        v['share_of_removed_samples'] = round(v['samples'] / total_samples, 4)
    restarted_by_own = {}
    for cue in ('L', 'E', 'A', 'M', 'AM'):
        table = {}
        for t, d in zip(neg, detail):
            row = table.setdefault(d['own'], [0, 0])
            row[0] += 1
            row[1] += int(t['restart'][cue] is not None)
        restarted_by_own[cue] = {k: dict(spans=v[0], restarted=v[1]) for k, v in table.items()}
    lag_sorted = sorted(lag_to_cut)
    lag_summary = dict(n=len(lag_sorted), min_ms=ms(lag_sorted[0]), p25_ms=ms(lag_sorted[len(lag_sorted) // 4]), median_ms=ms(lag_sorted[len(lag_sorted) // 2]),
                       p75_ms=ms(lag_sorted[(3 * len(lag_sorted)) // 4]), max_ms=ms(lag_sorted[-1]))
    out = dict(schema='m3_restart_evidence_posthoc_v2', post_hoc=True, census_sha256_note='read from CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json',
               positive_spans=len(pos), negative_spans=len(neg), first_label_start_minus_run_end_ms=dict(min=ms(gap[0]), median=ms(gap[len(gap) // 2]), max=ms(gap[-1])),
               timing=timing, negative_relation_to_concurrent_labels=relation, negative_restarted_by_relation=restarted_by_relation,
               negative_own_history=own_class, negative_restarted_by_own_history=restarted_by_own, overhang_label_end_to_cut_ms=lag_summary, negative_detail=detail)
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    print('first label start minus run end (ms)', out['first_label_start_minus_run_end_ms'])
    for cue, v in timing.items():
        print(cue, json.dumps(v))
    print('negative spans by relation to concurrent labels', json.dumps(relation))
    print('negatives restarted by relation', json.dumps(restarted_by_relation))
    print('negative own history', json.dumps(own_class))
    print('negatives restarted by own history', json.dumps(restarted_by_own))
    print('overhang: last same-pitch label end to cut (ms)', json.dumps(lag_summary))


if __name__ == '__main__':
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
