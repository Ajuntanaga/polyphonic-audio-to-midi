"""Report-only ranking diagnosis of saved training activities; no audio or fit."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def counts(activity, truth, cutoff):
    pred = activity >= cutoff
    return dict(examples=len(truth), expected=int(truth.sum()),
        true_positive=int((pred & truth).sum()),
        false_positive=int((pred & ~truth).sum()),
        false_negative=int((~pred & truth).sum()),
        complete_sets=int((pred == truth).all(axis=1).sum()))


def quantiles(values):
    if not len(values):
        return None
    return dict(zip(('min', 'p10', 'median', 'p90', 'max'),
                    np.quantile(values, [0, .1, .5, .9, 1]).tolist()))


def diagnose(activity, truth, plan, cutoff, note_low=32):
    activity, truth = np.asarray(activity), np.asarray(truth)
    if (activity.ndim != 2 or truth.dtype != np.dtype(bool) or
            activity.shape != truth.shape or len(plan) != len(truth) or
            not np.isfinite(activity).all() or (activity < 0).any() or
            (activity > 1).any() or not np.isfinite(cutoff) or cutoff <= 0):
        raise ValueError('Invalid saved arrays or cutoff')
    examples, targets = [], []
    usage = Counter()
    for i, (scores, y, row) in enumerate(zip(activity, truth, plan)):
        if row['example'] != i or row['role'] != 'train':
            raise ValueError('Plan ordering or role mismatch')
        components = row['components']
        by_note = defaultdict(list)
        for c in components:
            by_note[c['note']].append(c)
            usage[c['source_key']] += 1
        if set(by_note) != set((np.flatnonzero(y)+note_low).tolist()):
            raise ValueError('Plan targets differ from saved targets')
        n = int(y.sum())
        if n == 0:
            continue
        if y.all():
            raise ValueError('No false-pitch comparison available')
        false_max = float(scores[~y].max())
        weakest = float(scores[y].min())
        margin = weakest - false_max
        pred = scores >= cutoff
        examples.append(dict(example=i, distinct_pitches=n, components=len(components),
            duplicate_pitch=len(components) > n, weakest_true=weakest,
            strongest_false=false_max, margin=margin,
            strict_separation=margin > 0, exact_tie=margin == 0,
            false_above_weakest=margin < 0,
            frozen_complete=bool(np.array_equal(pred, y))))
        max_gain = max(c['gain_db'] for c in components)
        for j in np.flatnonzero(y):
            note = int(j)+note_low
            score = float(scores[j])
            targets.append(dict(example=i, note=note, distinct_pitches=n,
                relative_scheduled_gain_db=max(c['gain_db'] for c in by_note[note])-max_gain,
                duplicate_pitch=len(by_note[note]) > 1, score=score,
                strongest_false=false_max, above_all_false=score > false_max,
                tied_with_strongest_false=score == false_max,
                below_strongest_false=score < false_max,
                false_pitches_above=int((scores[~y] > score).sum()),
                false_pitches_equal=int((scores[~y] == score).sum()),
                frozen_detected=bool(pred[j]), zero_activity=score == 0))

    def target_summary(rows):
        return dict(expected=len(rows), detected=sum(r['frozen_detected'] for r in rows),
            zero_activity=sum(r['zero_activity'] for r in rows),
            above_all_false=sum(r['above_all_false'] for r in rows),
            tied_with_strongest_false=sum(r['tied_with_strongest_false'] for r in rows),
            below_strongest_false=sum(r['below_strongest_false'] for r in rows),
            score_quantiles=quantiles([r['score'] for r in rows]),
            false_pitches_above_quantiles=quantiles([r['false_pitches_above'] for r in rows]))

    def example_summary(rows):
        return dict(examples=len(rows), strict_separation=sum(r['strict_separation'] for r in rows),
            exact_tie=sum(r['exact_tie'] for r in rows),
            false_above_weakest=sum(r['false_above_weakest'] for r in rows),
            frozen_complete=sum(r['frozen_complete'] for r in rows),
            strict_separation_but_frozen_incomplete=sum(r['strict_separation'] and not
                                                       r['frozen_complete'] for r in rows),
            margin_quantiles=quantiles([r['margin'] for r in rows]))

    summary = dict(frozen=counts(activity, truth, cutoff),
        nonsilent=example_summary(examples), targets=target_summary(targets),
        frozen_missed_targets=target_summary([r for r in targets if not r['frozen_detected']]),
        by_distinct_pitch_count={}, by_relative_scheduled_gain_db={},
        by_duplicate_pitch={}, source_usage=dict(usage))
    for n in sorted({r['distinct_pitches'] for r in examples}):
        mask = truth.sum(axis=1) == n
        summary['by_distinct_pitch_count'][str(n)] = dict(
            frozen=counts(activity[mask], truth[mask], cutoff),
            mixtures=example_summary([r for r in examples if r['distinct_pitches'] == n]),
            targets=target_summary([r for r in targets if r['distinct_pitches'] == n]))
    for gain in sorted({r['relative_scheduled_gain_db'] for r in targets}):
        selected = [r for r in targets if r['relative_scheduled_gain_db'] == gain]
        summary['by_relative_scheduled_gain_db'][str(gain)] = dict(
            all=target_summary(selected), single_component_pitch=target_summary(
                [r for r in selected if not r['duplicate_pitch']]))
    for duplicated in (False, True):
        summary['by_duplicate_pitch'][str(duplicated).lower()] = dict(
            mixtures=example_summary([r for r in examples if r['duplicate_pitch'] == duplicated]),
            targets=target_summary([r for r in targets if r['duplicate_pitch'] == duplicated]))
    return summary, dict(examples=examples, targets=targets)


def run(report_path, prediction_path, plan_path, sources_path, output):
    report = json.loads(report_path.read_text())
    for path in (prediction_path, plan_path):
        expected = report['evidence'][path.name]
        if path.stat().st_size != expected['bytes'] or digest(path) != expected['sha256']:
            raise ValueError('Saved member hash/size differs from report')
    with np.load(prediction_path, allow_pickle=False) as saved:
        if set(saved.files) != {'activity', 'targets', 'cutoff'}:
            raise ValueError('Unexpected saved arrays')
        activity, truth, cutoff = saved['activity'], saved['targets'], float(saved['cutoff'])
    if activity.shape != (4096, 53) or cutoff != report['cutoff_fit']['cutoff']:
        raise ValueError('Frozen training dimensions or cutoff differ')
    with gzip.open(plan_path, 'rt') as f:
        plan = json.load(f)
    summary, details = diagnose(activity, truth, plan, cutoff)
    train = report['mixtures']['train']
    frozen = train['summary']['overall']
    for field in ('examples', 'true_positive', 'false_positive', 'false_negative'):
        if summary['frozen'][field] != frozen[field]:
            raise ValueError('Frozen classification identity failed: '+field)
    if summary['frozen']['complete_sets'] != round(frozen['exact_set_percent']*len(truth)/100):
        raise ValueError('Frozen complete-set identity failed')
    for n, row in summary['by_distinct_pitch_count'].items():
        original = train['summary']['by_distinct_pitch_count'][n]
        for field in ('examples', 'true_positive', 'false_positive', 'false_negative'):
            if row['frozen'][field] != original[field]:
                raise ValueError('Frozen polyphony identity failed')
        if row['frozen']['complete_sets'] != round(original['exact_set_percent']*original['examples']/100):
            raise ValueError('Frozen polyphony complete-set identity failed')
    if summary['source_usage'] != train['source_take_uses']:
        raise ValueError('Saved source usage differs')
    pin = report['provenance']['specification']['references']['sources']
    if digest(sources_path) != pin['sha256']:
        raise ValueError('Source manifest pin mismatch')
    sources = json.loads(sources_path.read_text())
    # Validate directly from the frozen manifest without importing any audio code.
    train_keys = {file['stem']+':'+str(r['label_index']) for file in sources['files']
                  for r in file['takes'] if r['calibration_pass'] == 1}
    if set(summary['source_usage']) != train_keys or len(train_keys) != 200:
        raise ValueError('Training role isolation failed')
    output.mkdir(parents=True, exist_ok=False)
    with gzip.open(output/'details.json.gz', 'wt') as f:
        json.dump(details, f, allow_nan=False)
    result = dict(schema='m3_saved_ablation_ranking_v1', final=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        run_id=report['provenance']['run_id'], source_commit=report['provenance']['source_commit'],
        input_hashes={p.name: digest(p) for p in (report_path, prediction_path, plan_path, sources_path)},
        frozen_cutoff=cutoff, original_decision=report['decision'],
        identities_passed=True, analysis_script_sha256=digest(__file__),
        limits=['Training-only, no held-out or continuous score.',
                'Strict separation is an oracle per-mixture possibility, not an operational rule.',
                'Scheduled component gain is not measured mixture power; unisons may interfere.',
                'Original labels retained, including unresolved source-content uncertainty.'],
        summary=summary, details_sha256=digest(output/'details.json.gz'))
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output), frozen=summary['frozen'],
        nonsilent=summary['nonsilent'], missed=summary['frozen_missed_targets'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'predictions', 'plan', 'sources', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    run(args.report, args.predictions, args.plan, args.sources, args.output)
