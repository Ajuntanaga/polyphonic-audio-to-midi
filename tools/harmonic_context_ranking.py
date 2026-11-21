"""Diagnose frozen harmonic-context training arrays; no model/audio/fit."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np

from tools.spectral_ablation_ranking import counts, diagnose, digest


INTERVALS = (12, 19, 24, 28, 31, 36)
RELATIONS = ('unrelated', 'above_only', 'below_only', 'both')


def error_strata(activity, truth, cutoff, details):
    """Exclusive error classes and harmonic-association denominators."""
    pred = activity >= cutoff
    missing, extra = truth & ~pred, ~truth & pred
    has_missing, has_extra = missing.any(axis=1), extra.any(axis=1)
    polyphony = truth.sum(axis=1)
    above, below = np.zeros_like(truth), np.zeros_like(truth)
    for interval in INTERVALS:
        if interval < truth.shape[1]:
            above[:, interval:] |= truth[:, :-interval]
            below[:, :-interval] |= truth[:, interval:]
    relation = above.astype(np.uint8) + 2 * below.astype(np.uint8)

    def rate(numerator, denominator):
        return 100 * numerator / denominator if denominator else None

    result = dict(intervals_semitones=list(INTERVALS), by_distinct_pitch_count={},
                  target_gain_strata={}, harmonic_relation_strata={})
    for n in sorted(set(polyphony.tolist())):
        mask = polyphony == n
        result['by_distinct_pitch_count'][str(n)] = dict(
            examples=int(mask.sum()),
            exact=int((mask & ~has_missing & ~has_extra).sum()),
            missing_only=int((mask & has_missing & ~has_extra).sum()),
            extra_only=int((mask & ~has_missing & has_extra).sum()),
            both=int((mask & has_missing & has_extra).sum()),
            missing_pitches=int(missing[mask].sum()),
            extra_pitches=int(extra[mask].sum()))
    for group, mask in [('all', np.ones(len(truth), bool)), ('five_pitch', polyphony == 5)]:
        rows = [r for r in details['targets'] if mask[r['example']]]
        result['target_gain_strata'][group] = {}
        for gain in sorted({r['relative_scheduled_gain_db'] for r in rows}):
            selected = [r for r in rows if r['relative_scheduled_gain_db'] == gain]
            missed = [r for r in selected if not r['frozen_detected']]
            result['target_gain_strata'][group][str(gain)] = dict(
                expected=len(selected), missed=len(missed),
                miss_percent=rate(len(missed), len(selected)),
                missed_above_all_false=sum(r['above_all_false'] for r in missed),
                missed_tied_with_false=sum(r['tied_with_strongest_false'] for r in missed),
                missed_below_false=sum(r['below_strongest_false'] for r in missed))
        relations = result['harmonic_relation_strata'][group] = {}
        for code, name in enumerate(RELATIONS):
            where = mask[:, None] & (relation == code)
            expected = int((where & truth).sum())
            missed = int((where & missing).sum())
            opportunities = int((where & ~truth).sum())
            false = int((where & extra).sum())
            relations[name] = dict(expected=expected, missed=missed,
                miss_percent=rate(missed, expected), false_opportunities=opportunities,
                false_outputs=false, false_percent=rate(false, opportunities))
    result['per_note'] = [dict(note=j+32, expected=int(truth[:, j].sum()),
        missing=int(missing[:, j].sum()), extra=int(extra[:, j].sum()),
        five_expected=int(truth[polyphony == 5, j].sum()),
        five_missing=int(missing[polyphony == 5, j].sum()),
        five_extra=int(extra[polyphony == 5, j].sum())) for j in range(truth.shape[1])]
    return result


def run(report_path, prediction_path, plan_path, sources_path, output):
    report = json.loads(report_path.read_text())
    for path in (prediction_path, plan_path):
        pin = report['evidence'][path.name]
        if path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
            raise ValueError('Saved member hash/size differs from report')
    with np.load(prediction_path, allow_pickle=False) as saved:
        if set(saved.files) != {'probability', 'targets', 'cutoff'}:
            raise ValueError('Unexpected saved arrays')
        probability, truth, cutoff = saved['probability'], saved['targets'], float(saved['cutoff'])
    if probability.shape != (16384, 53) or cutoff != report['cutoff_fit']['cutoff']:
        raise ValueError('Frozen training dimensions or cutoff differ')
    with gzip.open(plan_path, 'rt') as f:
        plan = json.load(f)
    summary, details = diagnose(probability, truth, plan, cutoff)
    train = report['mixtures']['train']
    by_pitch_count = train['summary']['by_distinct_pitch_count']
    groups = [('overall', np.ones(len(truth), bool), train['summary']['overall'])]
    groups += [(n, truth.sum(axis=1) == int(n), row) for n, row in by_pitch_count.items()]
    for name, mask, original in groups:
        actual = counts(probability[mask], truth[mask], cutoff)
        for field in ('examples', 'true_positive', 'false_positive', 'false_negative'):
            if actual[field] != original[field]:
                raise ValueError('Frozen classification identity failed: '+name+'/'+field)
        if actual['complete_sets'] != round(original['exact_set_percent']*original['examples']/100):
            raise ValueError('Frozen complete-set identity failed: '+name)
    pred = probability >= cutoff
    for row in train['summary']['per_note']:
        j = row['note']-32
        measured = dict(support=int(truth[:, j].sum()),
            true_positive=int((pred[:, j] & truth[:, j]).sum()),
            false_positive=int((pred[:, j] & ~truth[:, j]).sum()),
            false_negative=int((~pred[:, j] & truth[:, j]).sum()))
        if any(row[k] != v for k, v in measured.items()):
            raise ValueError('Frozen per-pitch identity failed')
    if summary['source_usage'] != train['source_take_uses']:
        raise ValueError('Saved source usage differs')
    pin = report['provenance']['specification']['references']['sources']
    if digest(sources_path) != pin['sha256']:
        raise ValueError('Source manifest pin mismatch')
    sources = json.loads(sources_path.read_text())
    train_keys = {file['stem']+':'+str(r['label_index']) for file in sources['files']
                  for r in file['takes'] if r['calibration_pass'] == 1}
    if set(summary['source_usage']) != train_keys or len(train_keys) != 200:
        raise ValueError('Training role isolation failed')
    strata = error_strata(probability, truth, cutoff, details)
    output.mkdir(parents=True, exist_ok=False)
    with gzip.open(output/'details.json.gz', 'wt') as f:
        json.dump(details, f, allow_nan=False)
    result = dict(schema='m3_saved_harmonic_context_ranking_v1', final=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        run_id=report['provenance']['run_id'], source_commit=report['provenance']['source_commit'],
        input_hashes={p.name: digest(p) for p in (report_path, prediction_path, plan_path, sources_path)},
        frozen_cutoff=cutoff, original_decision=report['decision'],
        identities_passed=True, training_source_count=len(train_keys),
        analysis_script_sha256=digest(__file__),
        ranking_script_sha256=digest(Path(__file__).with_name('spectral_ablation_ranking.py')),
        limits=['Training-only, no held-out or continuous score.',
                'Strict separation is an oracle per-mixture possibility, not an operational rule.',
                'Scheduled component gain is not measured mixture power; unisons may interfere.',
                'Harmonic associations are descriptive, not causal mechanisms.',
                'Original labels retained, including unresolved source-content uncertainty.'],
        summary=summary, error_strata=strata, details_sha256=digest(output/'details.json.gz'))
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output), frozen=summary['frozen'],
        five_pitch=strata['by_distinct_pitch_count']['5'],
        five_rankings=summary['by_distinct_pitch_count']['5']['mixtures'],
        missed=summary['frozen_missed_targets']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'predictions', 'plan', 'sources', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    run(args.report, args.predictions, args.plan, args.sources, args.output)
