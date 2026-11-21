"""One frozen cross-fitted pitch-ablation screen; recorded execution is GitHub CPU only."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy

from tools.direct_spectrum_learning import SETTINGS, mixture_plan, render_mixture, validate_manifest
from tools.spectral_dictionary import IdentityTransform, build_templates, fit_training_cutoff, template_plan
from tools.spectral_ablation import PARAMETERS, AveragedPower, CrossfitAblation, complete_chord_gate, summarize
from tools.portable_direct_spectrum_learning import (continuous_dataset, fetch_release,
    save_gzip_json, source_waves)
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def role_examples(role, takes, waves, extractor, bulk):
    remote_only()
    plan = mixture_plan(takes, role=role, count=PARAMETERS['mixture_counts'][role],
                        seed=SETTINGS[role+'_seed'])
    save_gzip_json(bulk/(role+'-mixture-plan.json.gz'), plan)
    x = np.empty((len(plan), len(extractor.names)), dtype=np.float64)
    y = np.empty((len(plan), 53), dtype=bool)
    for i, row in enumerate(plan):
        audio, target = render_mixture(row, waves)
        x[i], y[i] = extractor(audio), target
    counts = Counter(c['source_key'] for row in plan for c in row['components'])
    if set(counts) != {take['key'] for take in takes if take['role'] == role}:
        raise ValueError('Source omitted or cross-role source used')
    return x, y, dict(counts)


def activities(model, features):
    return np.concatenate([model.activity(features[i:i+32]) for i in range(0, len(features), 32)])


def run(spec_path, output):
    remote_only()  # Before reading sources, writing output, downloads or fitting.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_spectral_ablation_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured')
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA') or scipy.__version__ != '1.13.1'
                or np.__version__ != '1.26.4'
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']):
            raise ValueError('Frozen execution provenance mismatch')
        require_identity(spec['mixture_and_clock_settings'], SETTINGS, 'unchanged context, clock and mixture rule')
        require_identity(spec['ablation_parameters'], PARAMETERS, 'fixed power, folds, support and example counts')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), scipy=scipy.__version__, numpy=np.__version__)
        references = {}
        for name, pin in spec['references'].items():
            path = root/pin['path']
            check_hash(path, pin['sha256'])
            references[name] = json.loads(path.read_text())
        takes, counts = validate_manifest(references['sources'])
        require_identity(counts, dict(train=200, calibration=200, test=155), 'all original source roles')
        plan = template_plan(takes)
        if len(plan) != 200:
            raise ValueError('Expected all 200 training note/string cells')
        report['source_roles'] = dict(counts=counts, cross_role_original_overlap=False,
            all_original_labels_retained=True, source_consistency_metadata_used_to_filter=False,
            held_out_unit='Recording pass/source excerpt, same instrument/session')
        report['stage'] = 'retrieve existing pinned releases; build pass-1 power templates'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(references['sources'], folders['inputs'])
        extractor = AveragedPower()
        templates = build_templates(plan, waves, extractor)
        model = CrossfitAblation(templates, [row['note'] for row in plan], extractor.folds)
        save_gzip_json(folders['bulk']/'template-plan.json.gz', plan)
        report['dictionary'] = dict(atoms=len(plan), feature_count=len(extractor.names),
            median_crops_per_template=PARAMETERS['template_windows'], template_source_pass=1,
            labels_used_in_prediction=False, spectral_fold_counts=np.bincount(extractor.folds).tolist(),
            distinct_from_prior='Power averaging and whole-pitch cross-fitted residual ablation replace relative coefficient activity.')
        report['stage'] = 'train-only global cutoff; complete-chord identifiability check'
        save_json(report_path, report)
        started = time.perf_counter()
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        activity = activities(model, x)
        report['cutoff_fit'] = fit_training_cutoff(activity, y)
        model.cutoff = report['cutoff_fit']['cutoff']
        report['train_fit_seconds'] = time.perf_counter()-started
        model_path = folders['bulk']/'frozen-ablation-model.npz'
        np.savez_compressed(model_path, templates=templates, weights=model.weights,
            design=model.design, notes=model.notes, folds=model.folds,
            cutoff=model.cutoff, feature_names=np.asarray(extractor.names))
        report['frozen_model'] = dict(sha256=digest(model_path),
            persisted_before_held_out_scoring=True, cutoff=model.cutoff, training_fits=1)
        measured = summarize(activity, y, model.cutoff)
        train_gate = complete_chord_gate(measured['summary']) and report['cutoff_fit']['feasible']
        report['mixtures'] = dict(train=dict(measured, source_take_uses=usage,
            representation_gate=train_gate, evaluation_seconds=report['train_fit_seconds']))
        np.savez_compressed(folders['bulk']/'train-predictions.npz', activity=activity, targets=y, cutoff=model.cutoff)
        gates = dict(train_complete_chord_identifiability=train_gate)
        report['held_out_scoring'] = dict(executed=False, reason='Training identifiability failed; held-out data not evaluated.')
        save_json(report_path, report)
        if train_gate:
            report['stage'] = 'frozen model; both source-disjoint held-out roles'
            for role in ('calibration', 'test'):
                started = time.perf_counter()
                del x
                x, y, usage = role_examples(role, takes, waves, extractor, folders['bulk'])
                activity = activities(model, x)
                measured = summarize(activity, y, model.cutoff)
                gate = complete_chord_gate(measured['summary'])
                report['mixtures'][role] = dict(measured, source_take_uses=usage,
                    representation_gate=gate, evaluation_seconds=time.perf_counter()-started)
                gates[role+'_complete_chords'] = gate
                np.savez_compressed(folders['bulk']/(role+'-predictions.npz'), activity=activity, targets=y, cutoff=model.cutoff)
                save_json(report_path, report)
            report['held_out_scoring'] = dict(executed=True, reason='Training identifiability passed; both roles evaluated unchanged.')
        del waves, x, y, activity
        represented = train_gate and all(gates.values())
        report['datasets'] = {}
        report['continuous_replay'] = dict(executed=False,
            reason='Training and both held-out complete-chord gates must pass first.')
        if represented:
            report['stage'] = 'one continuous replay per recording on measured FIFO clock'
            save_json(report_path, report)
            for name, config in spec['datasets'].items():
                result = continuous_dataset(name, config, references['baseline']['datasets'][name],
                    folders['inputs'], extractor, IdentityTransform(), model, folders['bulk'])
                result['timing']['scope'] = 'Measured Python serial FIFO only; no native allocation/deadline or live-host/device proof.'
                result['saved_probability_semantics'] = 'Binary occupancy from residual support; not probability.'
                report['datasets'][name] = result
                gates[name+'_no_pitch_safety_regression'] = result['arms']['primary_fifo']['comparison']['no_pitch_safety_regression']
                save_json(report_path, report)
            gates['ordinary_gain_at_least_5pp'] = report['datasets']['ordinary']['arms']['primary_fifo']['comparison']['pitch_coverage_gain_pp'] >= 5
            report['continuous_replay'] = dict(executed=True, reason='Training and both held-out complete-chord gates passed.')
        passed = represented and all(gates.values())
        report.update(state='completed', final=True, stage='frozen power-ablation screen complete', gates=gates,
            representation_feasibility_passed=represented, research_screen_passed=passed,
            nnls_calls=model.nnls_calls,
            decision=('exploratory pass; independent recordings and implementation gates remain' if passed
                      else 'rejected at training identifiability' if not train_gate
                      else 'rejected at source-disjoint held-out gates' if not represented
                      else 'rejected by continuous safety or benefit gates'),
            limits=['All original 555 intended-label excerpts retained, including unresolved source-content inconsistencies.',
                'Spectral-coordinate folds are correlated, not independent validation; pass split is same instrument/session.',
                'Averaged power is not exactly additive for coherent harmonic mixtures.',
                'One template per note/string; within-take and between-take spectral variation remain.',
                'All gates and one train-only cutoff fixed; no tuning or retry of a rejected configuration.',
                'RMS-normalized sustained mixtures do not prove attacks, decays or string assignment.',
                'Ordinary continuous recording reuses source takes and is descriptive only.',
                'No unison multiplicity, delivered MIDI lifecycle, native realtime or live-device proof.'])
        report['evidence'] = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                              for p in folders['bulk'].iterdir() if p.is_file()}
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], decision=result['decision'], gates=result['gates'])))
