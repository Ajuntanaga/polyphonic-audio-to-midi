"""Score Codex's original/adapted Basic Pitch events as the support of the CURRENT filter.  Saved data only.

The plan and the eight predictions R0-R7 are fixed in CLAUDE-M3-ADAPTED-SUPPORT-PREREGISTRATION-20261122.md (commit af50edc), written before
any event file existed.  This script only implements that plan: for each corpus, the support is (model spans union the native confirmation),
held forward D ms (D in {50, 220}), and the filter is CURRENT intersect support.  Model spans come from four sources: arm A (the saved ONNX
offline causal run), the unchanged-TensorFlow events, the adapted-TensorFlow events, and arm A union the adapted events.  Event files are the
`{dataset}-events.json` that tools/portable_basic_pitch_streaming.measure writes (a dict with `events`), turned into spans by
tools.basic_pitch_streaming.emission_spans on the measured emitted_ns clock, never the zero-compute one.

No audio, model run, job or native edit; nothing promoted.  This is not the adaptation's acceptance (Codex's frozen gates decide that), not a
tracking result, and says nothing about native deadlines, strings or live delivery.  A rejected adaptation is scored the same way.

Usage:
  python3 -P -E CLAUDE-M3-ADAPTED-SUPPORT-20261122.py --selftest
  python3 -P -E CLAUDE-M3-ADAPTED-SUPPORT-20261122.py ORD_ORIGINAL ORD_ADAPTED EXT_ORIGINAL EXT_ADAPTED   (events.json or .json.gz)
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

from tools.basic_pitch_cached_diagnosis import clip_labels, clip_spans, labels_from_measurement  # noqa: E402
from tools.basic_pitch_streaming import NS, emission_spans  # noqa: E402
from tools.native_neural_consensus import EVIDENCE_DIR, intersect_spans  # noqa: E402
from tools.pitch_detector_comparison import compare, score, union_spans  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dil = load('dil', 'CLAUDE-M3-SUPPORT-DILATION-20261122.py')
ce = dil.ce
OUT = os.path.join(HERE, 'CLAUDE-M3-ADAPTED-SUPPORT-20261122.json')
HOLDS_MS = [50, 220]
LOSER = 229   # largest arm-A loss on ordinary (pitch 42)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_events(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return json.load(stream)['events']


def spans_from_events(events, horizon):
    spans, audit = emission_spans(events, 'emitted_ns', horizon)
    return union_spans(spans, sample_count=horizon), audit


def events_from_spans(spans, rate):
    """Synthetic round trip for the self-test: one on/off pair per span at the exact emitted clock.
    emission_spans takes ceil(ns * rate / NS), so the inverse is floor(sample * NS / rate)."""
    rows = []
    for l, r, p in spans:
        rows.append((l * NS // rate, 1, 'on', p))
        rows.append((r * NS // rate, 0, 'off', p))
    rows.sort(key=lambda x: (x[0], x[1]))
    return [dict(kind=k, note=p, emitted_ns=t, available_ns=t) for t, _, k, p in rows]


def dataset_context(dataset):
    base = json.load(open(ce.BASELINE))['datasets'][dataset]
    rep = json.load(open(os.path.join(ce.CONSENSUS, 'report.json')))['datasets'][dataset]
    horizon = rep['common_support']['sample_count']
    rate = rep['common_support']['sample_rate']
    clock = dict(sample_count=horizon, sample_rate=rate)
    labels, _ = clip_labels(labels_from_measurement(base['measurement']), horizon)
    cur_spans = clip_spans(base['pitch_spans'], horizon)
    current = score(cur_spans, labels, **clock)
    if json.loads(json.dumps(current)) != rep['current']:
        raise SystemExit('CURRENT identity failed for ' + dataset)
    evidence = json.load(gzip.open(os.path.join(REPO, EVIDENCE_DIR, f'{dataset}-bridge-events.json.gz'), 'rt'))
    saved = json.load(gzip.open(os.path.join(ce.CONSENSUS, f'{dataset}-consensus-spans.json.gz'), 'rt'))
    return dict(horizon=horizon, rate=rate, clock=clock, labels=labels, cur_spans=cur_spans, current=current,
                arm_a=union_spans(evidence['arm_spans']['A'], sample_count=horizon),
                native=[tuple(x) for x in saved['native_confirmation']])


def score_filters(ctx, model_spans):
    horizon, rate, current = ctx['horizon'], ctx['rate'], ctx['current']
    ct, cg = current['pitch_sets']['totals'], current['pitch_sets']['unlabeled_gap_voice_samples']
    cur_false = ct['extra_pitch_voice_samples'] + cg
    support = union_spans([*model_spans, *ctx['native']], sample_count=horizon)
    rows = {}
    for d in HOLDS_MS:
        held = dil.dilate(support, int(d * rate / 1000), horizon)
        spans = union_spans(intersect_spans(ctx['cur_spans'], held, sample_count=horizon), sample_count=horizon)
        hybrid = score(spans, ctx['labels'], **ctx['clock'])
        cmp = compare(current, hybrid)
        t = hybrid['pitch_sets']['totals']
        gap = hybrid['pitch_sets']['unlabeled_gap_voice_samples']
        false = t['extra_pitch_voice_samples'] + gap
        losing = [r for r in cmp['label_deltas'] if r['present_samples_delta'] < 0 or r['longest_present_samples_delta'] < 0]
        lost = sum(-r['present_samples_delta'] for r in losing if r['present_samples_delta'] < 0)
        loser = next((r for r in cmp['label_deltas'] if r['label_index'] == LOSER), None)
        rows[d] = dict(
            coverage_pct=round(100 * t['present_pitch_samples'] / t['expected_pitch_samples'], 4),
            precision_pct=round(100 * t['present_pitch_samples'] / (t['present_pitch_samples'] + false), 2),
            present_delta=t['present_pitch_samples'] - ct['present_pitch_samples'],
            wrong_delta=t['extra_pitch_voice_samples'] - ct['extra_pitch_voice_samples'],
            wrong_removed_share=round(max(0, ct['extra_pitch_voice_samples'] - t['extra_pitch_voice_samples']) / max(1, ct['extra_pitch_voice_samples']), 4),
            gap_delta=gap - cg, false_change_pct_of_current=round(100 * (false - cur_false) / max(1, cur_false), 2),
            exact_set_delta=t['exact_pitch_set_samples'] - ct['exact_pitch_set_samples'],
            all_expected_delta=t['all_expected_pitches_samples'] - ct['all_expected_pitches_samples'],
            labels_losing_present_or_longest=len(losing), lost_share_of_current_present=round(lost / ct['present_pitch_samples'], 4),
            label_229_present_delta=loser['present_samples_delta'] if loser else None,
            no_pitch_safety_regression=cmp['no_pitch_safety_regression'])
    return rows


def run_dataset(dataset, original_path, adapted_path):
    ctx = dataset_context(dataset)
    horizon = ctx['horizon']
    out = dict(dataset=dataset, inputs={}, event_audit={}, sources={})
    sources = {'arm A': ctx['arm_a']}
    for tag, path in (('unchanged TF', original_path), ('adapted TF', adapted_path)):
        spans, audit = spans_from_events(read_events(path), horizon)
        sources[tag] = spans
        out['inputs'][tag] = dict(path=os.path.basename(path), sha256=sha256(path))
        out['event_audit'][tag] = audit
    sources['arm A union adapted TF'] = union_spans([*ctx['arm_a'], *sources['adapted TF']], sample_count=horizon)
    for name, spans in sources.items():
        out['sources'][name] = dict(runs=len(spans), filters=score_filters(ctx, spans))
    return out, ctx


def predictions(results, label_229_present):
    o, e = results['ordinary']['sources'], results['extended-middle']['sources']
    u, a, base = o['unchanged TF']['filters'][220], o['adapted TF']['filters'][220], o['arm A']['filters'][220]
    union = o['arm A union adapted TF']['filters'][220]

    def removed_half(row):
        return row['label_229_present_delta'] is not None and label_229_present and -row['label_229_present_delta'] >= 0.5 * label_229_present
    return {
        'R0 unchanged TF within a few labels of arm A': 4 <= u['labels_losing_present_or_longest'] <= 8 and 0.18 <= u['wrong_removed_share'] <= 0.26,
        'R1 adapted labels <= unchanged': a['labels_losing_present_or_longest'] <= u['labels_losing_present_or_longest'],
        'R2 adapted lost share <= unchanged': a['lost_share_of_current_present'] <= u['lost_share_of_current_present'],
        'R3 adapted removal >= unchanged': a['wrong_removed_share'] >= u['wrong_removed_share'],
        'R4 label 229 stays lost under both': removed_half(u) and removed_half(a),
        'R5 extended-middle D220 both safe, 0 labels': all(e[k]['filters'][220]['labels_losing_present_or_longest'] == 0 and e[k]['filters'][220]['no_pitch_safety_regression']
                                                             for k in ('unchanged TF', 'adapted TF')),
        'R6 adapted precision >= unchanged': a['precision_pct'] >= u['precision_pct'],
        'R7 arm A union adapted loses fewer labels than arm A': union['labels_losing_present_or_longest'] < base['labels_losing_present_or_longest'],
    }


def selftest():
    """The loader must reproduce arm A exactly from synthetic events, and the filter must reproduce the persistence-confirm L = inf row."""
    pers = json.load(open(os.path.join(HERE, 'CLAUDE-M3-PERSISTENCE-CONFIRM-20261122.json')))
    ok = True
    for dataset in ('ordinary', 'extended-middle'):
        ctx = dataset_context(dataset)
        events = events_from_spans(ctx['arm_a'], ctx['rate'])
        spans, audit = spans_from_events(events, ctx['horizon'])
        same = spans == ctx['arm_a']
        rows = score_filters(ctx, spans)
        for d in HOLDS_MS:
            ref = pers[dataset]['variants'][f'D{d} persist inf ms']
            for key in ('coverage_pct', 'precision_pct', 'present_delta', 'wrong_delta', 'gap_delta', 'exact_set_delta',
                        'wrong_removed_share', 'labels_losing_present_or_longest', 'lost_share_of_current_present'):
                if rows[d][key] != ref[key]:
                    ok = False
                    print('MISMATCH', dataset, d, key, rows[d][key], ref[key])
        print(dataset, 'round trip identical', same, 'pairing_valid', audit['pairing_valid'], 'D220 labels', rows[220]['labels_losing_present_or_longest'])
        ok = ok and same
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


def main(argv, out_path=OUT):
    ord_o, ord_a, ext_o, ext_a = argv
    results, ctxs = {}, {}
    for dataset, o, a in (('ordinary', ord_o, ord_a), ('extended-middle', ext_o, ext_a)):
        results[dataset], ctxs[dataset] = run_dataset(dataset, o, a)
    base_229 = None
    cur = ctxs['ordinary']['current']
    for lab in cur.get('labels', []) if isinstance(cur, dict) else []:
        if lab.get('label_index') == LOSER:
            base_229 = lab.get('present_samples')
    preds = predictions(results, base_229)
    results['predictions'] = preds
    with open(out_path, 'w') as stream:
        json.dump(results, stream, indent=1)
    for dataset in ('ordinary', 'extended-middle'):
        print(dataset, json.dumps(results[dataset]['inputs']))
        for name, row in results[dataset]['sources'].items():
            for d, f in row['filters'].items():
                print(f'  {name:26s} D{d}', json.dumps(f))
    for k, v in preds.items():
        print(('PASS ' if v else 'FAIL ') + k)


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        sys.exit(0 if selftest() else 1)
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
