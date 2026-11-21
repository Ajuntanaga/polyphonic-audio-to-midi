"""One frozen measured-spectrum dictionary screen; GitHub Actions CPU only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy

from tools.direct_spectrum_learning import SETTINGS, representation_gate, validate_manifest
from tools.spectral_dictionary import (PARAMETERS, DenseMagnitude, DictionaryModel,
    IdentityTransform, build_templates, fit_training_cutoff, stratified_summary, template_plan)
from tools.portable_direct_spectrum_learning import (continuous_dataset, fetch_release,
    role_examples, save_gzip_json, source_waves)
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def activities(model, features):
    # Keep the matrix projection bounded, without changing per-example NNLS.
    return np.concatenate([model.activity(features[i:i+128]) for i in range(0, len(features), 128)])


def run(spec_path, output):
    remote_only()  # Before source reads, waveform access, fitting or downloads.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_spectral_dictionary_v1', state='running', final=False,
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
        require_identity(spec['mixture_and_clock_settings'], SETTINGS, 'reused mixture and clock settings')
        require_identity(spec['dictionary_parameters'], PARAMETERS, 'dictionary parameters')
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
        require_identity(counts, dict(train=200, calibration=200, test=155), 'all source roles')
        plan = template_plan(takes)
        if len(plan) != 200:
            raise ValueError('Expected all 200 train note/string templates')
        report['source_roles'] = dict(counts=counts, cross_role_original_overlap=False,
            all_takes_retained=True, held_out_unit='Recording pass/source excerpt, same instrument/session')
        report['stage'] = 'retrieve existing pinned releases; build pass-1 templates'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(references['sources'], folders['inputs'])
        extractor = DenseMagnitude()
        templates = build_templates(plan, waves, extractor)
        model = DictionaryModel(templates, [row['note'] for row in plan])
        save_gzip_json(folders['bulk']/'template-plan.json.gz', plan)
        report['dictionary'] = dict(atoms=len(plan), feature_count=len(extractor.names),
            templates_per_note_string=1, median_crops_per_template=PARAMETERS['template_windows'],
            template_source_pass=1, labels_used_in_prediction=False,
            role='Full measured spectrum, fixed weights and ridge; NNLS coefficients vary per frame.')
        report['stage'] = 'fit one global presence cutoff using train mixtures only'
        save_json(report_path, report)
        started = time.perf_counter()
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        activity = activities(model, x)
        report['cutoff_fit'] = fit_training_cutoff(activity, y)
        model.cutoff = report['cutoff_fit']['cutoff']
        report['train_fit_seconds'] = time.perf_counter()-started
        model_path = folders['bulk']/'frozen-dictionary.npz'
        np.savez_compressed(model_path, templates=templates, weights=model.weights,
            design=model.design, qr_r=model.r, projector=model.projector, notes=model.notes,
            cutoff=model.cutoff, feature_names=np.asarray(extractor.names))
        report['frozen_model'] = dict(sha256=digest(model_path),
            persisted_before_held_out_scoring=True, cutoff=model.cutoff, training_fits=1)
        report['stage'] = 'frozen dictionary; score both source-disjoint held-out roles'
        report['mixtures'] = {}
        for role in ('train', 'calibration', 'test'):
            started = time.perf_counter()
            if role != 'train':
                del x
                x, y, usage = role_examples(role, takes, waves, extractor, folders['bulk'])
                activity = activities(model, x)
            measured = stratified_summary(activity, y, model.cutoff)
            report['mixtures'][role] = dict(measured, source_take_uses=usage,
                representation_gate=representation_gate(measured['summary']),
                evaluation_seconds=time.perf_counter()-started)
            np.savez_compressed(folders['bulk']/(role+'-predictions.npz'), activity=activity,
                                targets=y, cutoff=model.cutoff)
            save_json(report_path, report)
        del waves, x, y, activity
        gates = {role+'_representation': report['mixtures'][role]['representation_gate']
                 for role in ('calibration', 'test')}
        represented = report['cutoff_fit']['feasible'] and all(gates.values())
        report['datasets'] = {}
        report['continuous_replay'] = dict(executed=False,
            reason='Both held-out representation gates must pass before any continuous replay.')
        if represented:
            report['stage'] = 'one continuous replay per recording with measured FIFO cost'
            save_json(report_path, report)
            for name, config in spec['datasets'].items():
                result = continuous_dataset(name, config, references['baseline']['datasets'][name],
                    folders['inputs'], extractor, IdentityTransform(), model, folders['bulk'])
                result['timing']['scope'] = ('Measured Python dense FFT/NNLS/cutoff cost in a serial FIFO; '
                    'no native allocations, audio driver, actual host scheduling or device test.')
                result['saved_probability_semantics'] = 'Binary occupancy; not calibrated probability.'
                report['datasets'][name] = result
                gates[name+'_no_pitch_safety_regression'] = result['arms']['primary_fifo']['comparison']['no_pitch_safety_regression']
                save_json(report_path, report)
            gates['ordinary_gain_at_least_5pp'] = (report['datasets']['ordinary']['arms']['primary_fifo']
                ['comparison']['pitch_coverage_gain_pp'] >= 5)
            report['continuous_replay'] = dict(executed=True, reason='Both held-out gates passed.')
        passed = represented and all(gates.values())
        report.update(state='completed', final=True, stage='frozen dictionary screen complete', gates=gates,
            representation_feasibility_passed=represented, research_screen_passed=passed,
            decision=('exploratory pass; independent recordings and implementation gates remain' if passed
                      else 'rejected; no continuous replay' if not represented
                      else 'rejected by continuous safety or benefit gates'),
            limits=['Same instrument/session; no different-player/session generalization.',
                'All 555 intended-label excerpts retained, including known pass-3 target uncertainties.',
                'Magnitude spectra are only approximately additive for coherent mixtures; harmonic-related strata reported.',
                'RMS-normalized sustain mixtures do not establish chord attack/decay performance.',
                'Ordinary reuses training takes and would be descriptive only.',
                'Relative coefficient cutoff is trained once; no probability or audibility interpretation.',
                'No string assignment, unison multiplicity, host MIDI, native deadlines or live-device proof.',
                'No tuning, unchanged retry, installation or promotion.'])
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
