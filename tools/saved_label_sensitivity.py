"""Hypothetical target sensitivity on saved predictions; no audio/model access."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path

import numpy as np

from tools.saved_source_transfer import source_index
from tools.spectral_ablation_ranking import counts, digest


NON_OCTAVE = 'sustained_non_octave_disagreement_unresolved'
OCTAVE = 'octave_related_disagreement_ambiguous'


def analyze(probability, truth, plan, cutoff, replacements, broader, note_low=32):
    probability, truth = np.asarray(probability), np.asarray(truth)
    if (probability.ndim != 2 or truth.dtype != np.dtype(bool) or
            probability.shape != truth.shape or len(plan) != len(truth) or
            not np.isfinite(probability).all() or (probability < 0).any() or
            (probability > 1).any() or not 0 < cutoff <= 1 or
            not set(replacements) <= set(broader)):
        raise ValueError('Invalid predictions, cutoff, or source sets')
    hypothetical = np.zeros_like(truth)
    affected = np.zeros(len(plan), bool)
    broad_affected = affected.copy()
    for i, row in enumerate(plan):
        if row['example'] != i:
            raise ValueError('Plan order differs')
        original = set()
        for component in row['components']:
            key, note = component['source_key'], component['note']
            original.add(note)
            substitute = replacements.get(key, note)
            if not note_low <= substitute < note_low + truth.shape[1]:
                raise ValueError('Hypothetical note out of range')
            hypothetical[i, substitute-note_low] = True
            affected[i] |= key in replacements
            broad_affected[i] |= key in broader
        if original != set((np.flatnonzero(truth[i])+note_low).tolist()):
            raise ValueError('Original targets differ from plan')
    pred = probability >= cutoff
    exact = (truth == pred).all(axis=1)
    new_exact = (hypothetical == pred).all(axis=1)
    original_cardinality, new_cardinality = truth.sum(axis=1), hypothetical.sum(axis=1)

    def group(mask):
        size = int(mask.sum())
        original = counts(probability[mask], truth[mask], cutoff)
        alt = counts(probability[mask], hypothetical[mask], cutoff)
        bounds = {}
        for name, exposed in [('eight_non_octave', affected), ('all_fifteen', broad_affected)]:
            upper = int(((exact | exposed) & mask).sum())
            bounds[name] = dict(affected_examples=int((exposed & mask).sum()),
                affected_original_failures=int((exposed & ~exact & mask).sum()),
                complete_set_upper_bound=upper,
                percent=100*upper/size if size else None,
                target_70_percent_count=(7*size+9)//10,
                gap_to_target=max(0, (7*size+9)//10-upper))
        return dict(original=original, hypothetical=alt, optimistic_bounds=bounds,
            examples_with_changed_targets=int(((truth != hypothetical).any(axis=1) & mask).sum()),
            cardinality_changed=int(((original_cardinality != new_cardinality) & mask).sum()),
            newly_exact=int((~exact & new_exact & mask).sum()),
            lost_exact=int((exact & ~new_exact & mask).sum()))

    if not np.array_equal(truth[~affected], hypothetical[~affected]):
        raise ValueError('Unaffected targets changed')
    all_mask = np.ones(len(plan), bool)
    summary = dict(overall=group(all_mask),
        by_original_distinct_pitch_count={str(n): group(original_cardinality == n)
            for n in sorted(set(original_cardinality.tolist()))},
        by_component_count={str(n): group(np.array([len(r['components']) == n for r in plan]))
            for n in sorted({len(r['components']) for r in plan})})
    rows = [dict(example=i, original_notes=(np.flatnonzero(truth[i])+note_low).tolist(),
        hypothetical_notes=(np.flatnonzero(hypothetical[i])+note_low).tolist(),
        predicted_notes=(np.flatnonzero(pred[i])+note_low).tolist(),
        source_keys=[c['source_key'] for c in plan[i]['components']],
        original_exact=bool(exact[i]), hypothetical_exact=bool(new_exact[i]))
        for i in np.flatnonzero(affected).tolist()]
    return summary, rows


def run(report_path, evidence, sources_path, consistency_path, output):
    report = json.loads(report_path.read_text())
    refs = report['provenance']['specification']['references']
    for path, key in [(sources_path, 'sources'), (consistency_path, 'source_consistency')]:
        if digest(path) != refs[key]['sha256']:
            raise ValueError('Reference pin differs: '+key)
    metadata = json.loads(consistency_path.read_text())
    sources = source_index(json.loads(sources_path.read_text()), metadata)
    selected = [r for r in metadata['sources'] if r['status'] == NON_OCTAVE]
    replacements = {r['source_key']: r['periodic_pitch_estimate'] for r in selected}
    broader = {r['source_key'] for r in metadata['sources'] if r['status'] in (NON_OCTAVE, OCTAVE)}
    if (len(replacements) != 8 or len(broader) != 15 or
            any(sources[k]['role'] != 'test' for k in broader)):
        raise ValueError('Frozen source selection differs')
    cutoff = report['cutoff_fit']['cutoff']
    hashes = {str(p): digest(p) for p in (report_path, sources_path, consistency_path)}
    roles, example_rows = {}, {}
    for role, size in [('train', 16384), ('calibration', 4096), ('test', 4096)]:
        prediction = evidence/(role+'-predictions.npz')
        plan_path = evidence/(role+'-mixture-plan.json.gz')
        for path in (prediction, plan_path):
            pin = report['evidence'][path.name]
            hashes[str(path)] = digest(path)
            if path.stat().st_size != pin['bytes'] or hashes[str(path)] != pin['sha256']:
                raise ValueError('Evidence pin differs: '+path.name)
        with np.load(prediction, allow_pickle=False) as saved:
            probability, truth = saved['probability'], saved['targets']
            if probability.shape != (size, 53) or float(saved['cutoff']) != cutoff:
                raise ValueError('Shape/cutoff differs')
        with gzip.open(plan_path, 'rt') as handle:
            plan = json.load(handle)
        used = set()
        for row in plan:
            if row['role'] != role:
                raise ValueError('Plan role differs')
            for c in row['components']:
                s = sources[c['source_key']]
                if s['role'] != role or s['midi_note'] != c['note']:
                    raise ValueError('Source role/note differs')
                used.add(c['source_key'])
        if used != {k for k, s in sources.items() if s['role'] == role}:
            raise ValueError('Original source coverage differs')
        summary, rows = analyze(probability, truth, plan, cutoff, replacements, broader)
        original_groups = report['mixtures'][role]['summary']
        for group, prior in [(summary['overall'], original_groups['overall'])] + [
                (summary['by_original_distinct_pitch_count'][n], p)
                for n, p in original_groups['by_distinct_pitch_count'].items()]:
            measured = group['original']
            for key in ('examples', 'true_positive', 'false_positive', 'false_negative'):
                if measured[key] != prior[key]:
                    raise ValueError('Original count differs: '+key)
            if measured['complete_sets'] != round(prior['exact_set_percent']*prior['examples']/100):
                raise ValueError('Original exact sets differ')
        if role != 'test' and summary['overall']['original'] != summary['overall']['hypothetical']:
            raise ValueError('Non-test score changed')
        roles[role], example_rows[role] = summary, rows
    result = dict(schema='m3_saved_label_sensitivity_v1', final=True,
        created_at=datetime.now(timezone.utc).isoformat(),
        run_id=report['provenance']['run_id'], source_commit=report['provenance']['source_commit'],
        frozen_cutoff=cutoff, original_decision=report['decision'],
        official_scores_unchanged=True, identities_passed=True,
        input_hashes=hashes, analysis_script_sha256=digest(__file__),
        hypothetical_replacements=replacements, broader_source_keys=sorted(broader),
        roles=roles,
        limitations=['Hypothetical targets are not verified replacement labels or acceptance scores.',
            'The optimistic bound grants every affected row a perfect result, not a realizable policy.',
            'Original pitch-cardinality groups stay fixed even if a hypothetical unison changes size.',
            'Other source labels may be uncertain; the named sets are not exhaustive.',
            'Saved source-variation model only; no new inference, audio, training, or installed gain.'])
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (output/'affected-examples.json').write_text(json.dumps(example_rows, indent=2, allow_nan=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('report', 'evidence', 'sources', 'consistency', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.report, args.evidence, args.sources, args.consistency, args.output)
    print(json.dumps(result['roles']['test'], indent=2))
