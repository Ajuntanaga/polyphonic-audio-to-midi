"""Paired frozen training predictions; no fitting, audio, model or held-out data."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.harmonic_context_ranking import INTERVALS, RELATIONS, error_strata
from tools.spectral_ablation_ranking import counts, diagnose, digest


def require_pair(baseline_truth, current_truth, baseline_plan, current_plan):
    if not np.array_equal(baseline_truth, current_truth):
        raise ValueError('Paired targets differ')
    if baseline_plan != current_plan:
        raise ValueError('Paired mixture plans differ')


def paired_changes(baseline, current, truth, baseline_cutoff, current_cutoff,
                   plan, note_low=32):
    """Count paired classification changes with each arm's own frozen cutoff."""
    b, c = baseline >= baseline_cutoff, current >= current_cutoff
    polyphony = truth.sum(axis=1)
    be, ce = (b == truth).all(axis=1), (c == truth).all(axis=1)
    gained, lost = ~b & c, b & ~c
    # Silence has no weakest true pitch and is excluded from ordering statistics.
    bs = np.where(truth, baseline, np.inf).min(axis=1) > np.where(
        ~truth, baseline, -np.inf).max(axis=1)
    cs = np.where(truth, current, np.inf).min(axis=1) > np.where(
        ~truth, current, -np.inf).max(axis=1)

    def transitions(mask):
        return dict(examples=int(mask.sum()), baseline_exact=int(be[mask].sum()),
            current_exact=int(ce[mask].sum()),
            exact_gained=int((mask & ~be & ce).sum()),
            exact_lost=int((mask & be & ~ce).sum()),
            exact_both=int((mask & be & ce).sum()),
            exact_neither=int((mask & ~be & ~ce).sum()),
            genuine_gained=int((gained[mask] & truth[mask]).sum()),
            genuine_lost=int((lost[mask] & truth[mask]).sum()),
            false_new=int((gained[mask] & ~truth[mask]).sum()),
            false_removed=int((lost[mask] & ~truth[mask]).sum()),
            false_persistent=int((b[mask] & c[mask] & ~truth[mask]).sum()))

    result = dict(overall=transitions(np.ones(len(truth), bool)),
        by_distinct_pitch_count={str(n): transitions(polyphony == n)
                                for n in sorted(set(polyphony.tolist()))},
        ordering_by_distinct_pitch_count={}, target_gain_transitions={},
        false_harmonic_transitions={})
    for n in sorted(set(polyphony.tolist()) - {0}):
        mask = polyphony == n
        result['ordering_by_distinct_pitch_count'][str(n)] = dict(
            examples=int(mask.sum()), baseline_strict_separation=int(bs[mask].sum()),
            current_strict_separation=int(cs[mask].sum()),
            separation_gained=int((mask & ~bs & cs).sum()),
            separation_lost=int((mask & bs & ~cs).sum()),
            baseline_separated_but_incomplete=int((mask & bs & ~be).sum()),
            current_separated_but_incomplete=int((mask & cs & ~ce).sum()),
            baseline_ordering_failure=int((mask & ~bs).sum()),
            current_ordering_failure=int((mask & ~cs).sum()))

    relative_gain = np.full(truth.shape, np.nan)
    for i, row in enumerate(plan):
        components = row['components']
        if not components:
            continue
        loudest = max(x['gain_db'] for x in components)
        for note in {x['note'] for x in components}:
            relative_gain[i, note-note_low] = max(x['gain_db'] for x in components
                                                if x['note'] == note) - loudest
    above, below = np.zeros_like(truth), np.zeros_like(truth)
    for interval in INTERVALS:
        if interval < truth.shape[1]:
            above[:, interval:] |= truth[:, :-interval]
            below[:, :-interval] |= truth[:, interval:]
    relation = above.astype(np.uint8) + 2*below.astype(np.uint8)
    for group, mask in [('all', np.ones(len(truth), bool)),
                        ('five_pitch', polyphony == 5), ('single_pitch', polyphony == 1)]:
        gain_rows = result['target_gain_transitions'][group] = {}
        for gain in sorted(set(relative_gain[truth & mask[:, None]].tolist())):
            where = truth & mask[:, None] & (relative_gain == gain)
            gain_rows[str(gain)] = dict(expected=int(where.sum()),
                baseline_missing=int((where & ~b).sum()),
                current_missing=int((where & ~c).sum()),
                gained=int((where & gained).sum()), lost=int((where & lost).sum()))
        false_rows = result['false_harmonic_transitions'][group] = {}
        for code, name in enumerate(RELATIONS):
            where = ~truth & mask[:, None] & (relation == code)
            false_rows[name] = dict(opportunities=int(where.sum()),
                baseline=int((where & b).sum()), current=int((where & c).sum()),
                new=int((where & gained).sum()), removed=int((where & lost).sum()),
                persistent=int((where & b & c).sum()))

    def notes(mask):
        return (np.flatnonzero(mask)+note_low).tolist()

    def example_arm(scores, pred, y):
        return dict(predicted=notes(pred), missing=notes(y & ~pred), extra=notes(~y & pred),
            exact=bool(np.array_equal(pred, y)),
            weakest_true=float(scores[y].min()) if y.any() else None,
            strongest_false=float(scores[~y].max()),
            strict_separation=bool(scores[y].min() > scores[~y].max()) if y.any() else None)

    changed = []
    for i in np.flatnonzero((b != c).any(axis=1)):
        changed.append(dict(example=int(i), distinct_pitches=int(polyphony[i]),
            expected=notes(truth[i]), mixture_plan=plan[i],
            baseline=example_arm(baseline[i], b[i], truth[i]),
            current=example_arm(current[i], c[i], truth[i])))
    single_regressions = [row for row in changed if row['distinct_pitches'] == 1
                          and row['baseline']['exact'] and not row['current']['exact']]
    result['single_pitch_exact_losses'] = single_regressions
    result['changed_examples'] = len(changed)
    result['per_note'] = [dict(note=j+note_low, expected=int(truth[:, j].sum()),
        genuine_gained=int((gained[:, j] & truth[:, j]).sum()),
        genuine_lost=int((lost[:, j] & truth[:, j]).sum()),
        false_new=int((gained[:, j] & ~truth[:, j]).sum()),
        false_removed=int((lost[:, j] & ~truth[:, j]).sum())) for j in range(truth.shape[1])]
    return result, changed


def load_frozen(report_path, evidence_dir):
    report = json.loads(report_path.read_text())
    paths = [evidence_dir/name for name in ('train-predictions.npz', 'train-mixture-plan.json.gz')]
    for path in paths:
        pin = report['evidence'][path.name]
        if path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
            raise ValueError('Saved member hash/size mismatch')
    with np.load(paths[0], allow_pickle=False) as saved:
        if set(saved.files) != {'probability', 'targets', 'cutoff'}:
            raise ValueError('Unexpected saved arrays')
        probability, truth, cutoff = saved['probability'], saved['targets'], float(saved['cutoff'])
    if (probability.shape != (16384, 53) or truth.shape != probability.shape or
            truth.dtype != np.dtype(bool) or not np.isfinite(probability).all() or
            (probability < 0).any() or (probability > 1).any() or
            not 0 < cutoff <= 1 or cutoff != report['cutoff_fit']['cutoff']):
        raise ValueError('Invalid training arrays or frozen cutoff')
    raw_plan = gzip.decompress(paths[1].read_bytes())
    plan = json.loads(raw_plan)
    summary = report['mixtures']['train']['summary']
    groups = [('overall', np.ones(len(truth), bool), summary['overall'])]
    groups += [(n, truth.sum(axis=1) == int(n), row)
               for n, row in summary['by_distinct_pitch_count'].items()]
    for name, mask, original in groups:
        actual = counts(probability[mask], truth[mask], cutoff)
        for field in ('examples', 'true_positive', 'false_positive', 'false_negative'):
            if actual[field] != original[field]:
                raise ValueError('Frozen count mismatch: '+name+'/'+field)
        if actual['complete_sets'] != round(original['examples']*original['exact_set_percent']/100):
            raise ValueError('Frozen exact-set mismatch: '+name)
    pred = probability >= cutoff
    for row in summary['per_note']:
        j = row['note']-32
        actual = dict(support=int(truth[:, j].sum()),
            true_positive=int((pred[:, j] & truth[:, j]).sum()),
            false_positive=int((pred[:, j] & ~truth[:, j]).sum()),
            false_negative=int((~pred[:, j] & truth[:, j]).sum()))
        if any(row[k] != v for k, v in actual.items()):
            raise ValueError('Frozen per-note mismatch')
    return report, probability, truth, cutoff, plan, raw_plan, paths


def run(baseline_report, baseline_evidence, baseline_ranking, current_report,
        current_evidence, sources, output):
    br, b, by, bc, bp, braw, bpaths = load_frozen(baseline_report, baseline_evidence)
    cr, c, cy, cc, cp, craw, cpaths = load_frozen(current_report, current_evidence)
    require_pair(by, cy, bp, cp)
    if braw != craw:
        raise ValueError('Decompressed plan bytes differ')
    previous = json.loads(baseline_ranking.read_text())
    if (not previous['identities_passed'] or previous['run_id'] != br['provenance']['run_id'] or
            previous['frozen_cutoff'] != bc):
        raise ValueError('Baseline diagnosis identity differs')
    for path in (baseline_report, *bpaths, sources):
        if previous['input_hashes'][path.name] != digest(path):
            raise ValueError('Baseline diagnosis input hash mismatch')
    for report in (br, cr):
        if report['provenance']['specification']['references']['sources']['sha256'] != digest(sources):
            raise ValueError('Source manifest pin mismatch')
    manifest = json.loads(sources.read_text())
    keys = {file['stem']+':'+str(r['label_index']) for file in manifest['files']
            for r in file['takes'] if r['calibration_pass'] == 1}
    usage = dict(Counter(x['source_key'] for row in cp for x in row['components']))
    if len(keys) != 200 or set(usage) != keys or any(
            usage != r['mixtures']['train']['source_take_uses'] for r in (br, cr)):
        raise ValueError('Source role/usage mismatch')
    summary, details = diagnose(c, cy, cp, cc)
    strata = error_strata(c, cy, cc, details)
    comparison, changed = paired_changes(b, c, cy, bc, cc, cp)
    output.mkdir(parents=True, exist_ok=False)
    with gzip.open(output/'changed-examples.json.gz', 'wt') as f:
        json.dump(changed, f, allow_nan=False)
    with gzip.open(output/'current-ranking-details.json.gz', 'wt') as f:
        json.dump(details, f, allow_nan=False)
    result = dict(schema='m3_complete_set_paired_training_v1', final=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        baseline_run=br['provenance']['run_id'], current_run=cr['provenance']['run_id'],
        baseline_source=br['provenance']['source_commit'], current_source=cr['provenance']['source_commit'],
        baseline_cutoff=bc, current_cutoff=cc,
        input_hashes={str(p): digest(p) for p in (baseline_report, *bpaths, baseline_ranking,
                                                current_report, *cpaths, sources)},
        analysis_hashes={str(p): digest(p) for p in (Path(__file__),
            Path(__file__).with_name('harmonic_context_ranking.py'),
            Path(__file__).with_name('spectral_ablation_ranking.py'))},
        identities_passed=True, training_sources=len(keys),
        training_plan_sha256=hashlib.sha256(craw).hexdigest(),
        baseline_ranking=previous['summary'], current_ranking=summary,
        baseline_errors=previous['error_strata'], current_errors=strata,
        comparison=comparison,
        original_decisions=dict(baseline=br['decision'], current=cr['decision']),
        installed_output_changed=False, labels_changed=False,
        limits=['Training only; neither held-out nor continuous scoring executed.',
                'No fitting, cutoff selection, audio/model load or new remote processing.',
                'Strict separation is an oracle bound, not a deployable threshold or gain.',
                'Scores of different objectives are not calibrated to each other.',
                'Scheduled relative gain and harmonic associations are descriptive.',
                'Changed examples means changed pitch decisions at the original cutoffs.',
                'All source labels retained, including recorded content uncertainties.'],
        outputs={p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                 for p in output.iterdir()})
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(output=str(output), overall=comparison['overall'],
        by_polyphony=comparison['by_distinct_pitch_count'],
        five_ordering=comparison['ordering_by_distinct_pitch_count']['5'],
        current_five=strata['by_distinct_pitch_count']['5'],
        single_exact_losses=len(comparison['single_pitch_exact_losses'])), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-report', 'baseline-evidence', 'baseline-ranking',
                 'current-report', 'current-evidence', 'sources', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    run(**vars(parser.parse_args()))
