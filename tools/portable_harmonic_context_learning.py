"""One frozen harmonic context classifier screen, recorded execution on GitHub CPU."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, validate_manifest
from tools.harmonic_context_learning import (PARAMETERS, MODEL_PARAMS, COMPLETE_SET_PARAMS, SETWISE_PARAMS, FEATURE_COUNT,
    NOTE_COUNT, HarmonicFeatures, HarmonicContextModel, fit_normalization, normalized_context,
    make_network, complete_set_loss, setwise_loss, acceptance_gate, summarize)
from tools.spectral_dictionary import IdentityTransform, fit_training_cutoff
from tools.portable_direct_spectrum_learning import (continuous_dataset, fetch_release,
    role_examples, source_waves)
from tools.pitch_detector_comparison import digest
from tools.harmonic_source_variation import VARIATION, variation_examples
from tools.harmonic_pitch_transposition import TRANSPOSITION, transposition_examples
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


DEPENDENCIES = {'numpy': '1.26.4', 'scipy': '1.13.1', 'scikit-learn': '1.7.2',
                'joblib': '1.5.2', 'soundfile': '0.13.1', 'torch': '2.5.1+cpu'}


def dependency_versions():
    return {name: version(name) for name in DEPENDENCIES}


def fit_model(features, truth, model_params=None):
    remote_only()
    import torch
    params = MODEL_PARAMS if model_params is None else model_params
    torch.set_num_threads(params['torch_threads'])
    torch.use_deterministic_algorithms(params['deterministic'])
    torch.manual_seed(params['seed'])
    truth = np.asarray(truth, dtype=bool)
    if truth.shape != (len(features), NOTE_COUNT) or set(np.unique(truth)) != {False, True}:
        raise ValueError('Expected aligned training targets with both binary classes')
    mean, scale = fit_normalization(features)
    inputs = torch.from_numpy(normalized_context(features, mean, scale))
    targets = torch.from_numpy(truth.astype(np.float32))
    network = make_network().train()
    optimizer = torch.optim.Adam(network.parameters(), lr=params['learning_rate'],
                                 weight_decay=params['weight_decay'])
    if params['loss'] == MODEL_PARAMS['loss']:
        criterion = torch.nn.BCEWithLogitsLoss()
    elif params['loss'] == COMPLETE_SET_PARAMS['loss']:
        criterion = complete_set_loss
    elif params['loss'] == SETWISE_PARAMS['loss']:
        criterion = setwise_loss
    else:
        raise ValueError('Unknown frozen training objective')
    generator = torch.Generator().manual_seed(params['seed'])
    losses = []
    started = time.perf_counter()
    for epoch in range(params['epochs']):
        order = torch.randperm(len(inputs), generator=generator)
        total_loss = 0.0
        for indices in order.split(params['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(network(inputs[indices]), targets[indices])
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())*len(indices)
        losses.append(total_loss/len(inputs))
        print(f'epoch {epoch+1}/{params["epochs"]}: loss={losses[-1]:.9g}', flush=True)
    network.eval()
    return HarmonicContextModel(mean, scale, network), dict(seconds=time.perf_counter()-started,
        epochs=len(losses), mixtures=len(features), pooled_candidate_rows=len(features)*NOTE_COUNT,
        features_per_candidate=FEATURE_COUNT, shared_binary_outputs=1,
        parameter_count=sum(p.numel() for p in network.parameters()),
        final_loss=losses[-1], loss_curve=losses, held_out_used=False, fits=1,
        objective=params['loss'])


def save_model(path, model, extractor, model_params=None):
    remote_only()
    import torch
    torch.save(dict(state_dict=model.network.state_dict(), mean=torch.from_numpy(model.mean),
        scale=torch.from_numpy(model.scale), cutoff=model.cutoff,
        coordinate_names=extractor.coordinate_names, settings=SETTINGS,
        feature_parameters=PARAMETERS,
        model_parameters=MODEL_PARAMS if model_params is None else model_params), path)


def run(spec_path, output):
    remote_only()  # Before dependencies, file reads, recorded inputs, output or fitting.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_harmonic_context_learning_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured')
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Frozen execution provenance mismatch')
        versions = dependency_versions()
        require_identity(versions, DEPENDENCIES, 'pinned CPU dependencies')
        require_identity(spec['mixture_and_clock_settings'], SETTINGS, 'unchanged mixtures, context and clocks')
        require_identity(spec['harmonic_parameters'], PARAMETERS, 'fixed relative harmonic coordinates')
        params = spec['model_parameters']
        frozen_params = {p['loss']: p for p in (MODEL_PARAMS, COMPLETE_SET_PARAMS, SETWISE_PARAMS)}
        if params.get('loss') not in frozen_params:
            raise ValueError('Unknown frozen training objective')
        loss_only = params['loss'] != MODEL_PARAMS['loss']
        variation = spec.get('training_source_variation')
        transposition = spec.get('training_pitch_transposition')
        if variation is not None and transposition is not None:
            raise ValueError('Training augmentations cannot be combined in this screen')
        if variation is not None:
            require_identity(variation, VARIATION, 'fixed training-only source variation')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if transposition is not None:
            require_identity(transposition, TRANSPOSITION, 'fixed coherent training transposition')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        require_identity(params, frozen_params[params['loss']],
                         'one fixed shared context classifier and objective')
        report['training_objective'] = params['loss']
        if params['loss'] == COMPLETE_SET_PARAMS['loss']:
            report['schema'] = 'm3_harmonic_complete_set_learning_v1'
        elif params['loss'] == SETWISE_PARAMS['loss']:
            report['schema'] = 'm3_harmonic_setwise_learning_v1'
        if variation is not None:
            report['schema'] = 'm3_harmonic_source_variation_v1'
        if transposition is not None:
            report['schema'] = 'm3_harmonic_pitch_transposition_v1'
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), dependencies=versions)
        references = {}
        for name, pin in spec['references'].items():
            path = root/pin['path']
            check_hash(path, pin['sha256'])
            references[name] = json.loads(path.read_text())
        takes, counts = validate_manifest(references['sources'])
        require_identity(counts, dict(train=200, calibration=200, test=155), 'all original source roles')
        report['source_roles'] = dict(counts=counts, cross_role_original_overlap=False,
            all_original_labels_retained=True, source_consistency_metadata_used_to_filter=False,
            held_out_unit='Recording pass/source excerpt; protocol, instrument and session are not independent')
        report['stage'] = 'retrieve existing pinned releases'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(references['sources'], folders['inputs'])
        extractor = HarmonicFeatures()
        report['features'] = dict(coordinate_names=extractor.coordinate_names,
            per_candidate=FEATURE_COUNT, candidate_count=NOTE_COUNT,
            flatten_order='mixture, candidate MIDI32..84, shared coordinate',
            identity_features=False, exact_pitch_shift_equivariance=False,
            receptive_field_pitches=1+2*sum(MODEL_PARAMS['dilations']),
            boundary_context='Zero padding supplies incomplete context and can encode boundary position.',
            distinction=('Clean training plus transposed companions; same epochs, twice the optimizer steps.' if transposition is not None else
                'Only training component envelopes change versus the setwise model.' if variation is not None else
                'Only the training objective changes versus the frozen context baseline.' if loss_only else
                'Unchanged harmonic rows feed shared convolutions across pitches, then a shared binary readout; capacity also changes.'))
        report['stage'] = 'training mixtures; one shared fit and training-only cutoff'
        save_json(report_path, report)
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        if 'training_plan_identity' in spec:
            actual = hashlib.sha256(gzip.decompress((folders['bulk']/'train-mixture-plan.json.gz').read_bytes())).hexdigest()
            require_identity(actual, spec['training_plan_identity']['decoded_sha256'], 'unchanged training mixture plan')
            report['training_plan_identity'] = dict(spec['training_plan_identity'], verified=True)
        if variation is not None:
            fit_x, fit_y, report['training_source_variation'] = variation_examples(
                folders['bulk']/'train-mixture-plan.json.gz', waves, extractor, folders['bulk'])
            require_identity(report['training_source_variation']['decoded_sha256'],
                spec['varied_plan_identity']['decoded_sha256'], 'frozen varied training plan')
            if not np.array_equal(fit_y, y):
                raise ValueError('Source variation changed training targets')
            model, report['fit'] = fit_model(fit_x, fit_y, model_params=params)
            del fit_x, fit_y
        elif transposition is not None:
            augmented_x, augmented_y, report['training_pitch_transposition'] = transposition_examples(
                folders['bulk']/'train-mixture-plan.json.gz', takes, waves, extractor, folders['bulk'])
            require_identity(report['training_pitch_transposition']['decoded_sha256'],
                spec['transposed_plan_identity']['decoded_sha256'], 'frozen transposed training plan')
            if (augmented_x.shape != x.shape or augmented_y.shape != y.shape or
                    not np.array_equal(augmented_y.sum(axis=1), y.sum(axis=1))):
                raise ValueError('Transposition changed mixture count or chord completeness')
            fit_x, fit_y = np.concatenate((x, augmented_x)), np.concatenate((y, augmented_y))
            del augmented_x, augmented_y
            model, report['fit'] = fit_model(fit_x, fit_y, model_params=params)
            report['fit']['optimizer_steps'] = params['epochs']*((len(fit_x)+params['batch_size']-1)//params['batch_size'])
            report['fit']['clean_and_companion_mixtures'] = len(fit_x)
            del fit_x, fit_y
        else:
            model, report['fit'] = fit_model(x, y, model_params=params)
        probability = model.activity(x)
        report['cutoff_fit'] = fit_training_cutoff(probability, y)
        model.cutoff = report['cutoff_fit']['cutoff']
        model_path = folders['bulk']/'frozen-harmonic-context-model.pt'
        save_model(model_path, model, extractor, model_params=params)
        report['frozen_model'] = dict(sha256=digest(model_path), cutoff=model.cutoff,
            persisted_before_held_out_scoring=True, training_fits=1)
        measured = summarize(probability, y, model.cutoff)
        train_gate = acceptance_gate(measured['summary'], training=True) and report['cutoff_fit']['feasible']
        report['mixtures'] = dict(train=dict(measured, source_take_uses=usage, representation_gate=train_gate))
        np.savez_compressed(folders['bulk']/'train-predictions.npz', probability=probability, targets=y, cutoff=model.cutoff)
        gates = dict(train_complete_chords=train_gate)
        report['held_out_scoring'] = dict(executed=False, reason='Training complete-chord gate failed.')
        save_json(report_path, report)
        if train_gate:
            report['stage'] = 'frozen model; both untouched recording passes'
            for role in ('calibration', 'test'):
                del x
                x, y, usage = role_examples(role, takes, waves, extractor, folders['bulk'])
                probability = model.activity(x)
                measured = summarize(probability, y, model.cutoff)
                gate = acceptance_gate(measured['summary'])
                report['mixtures'][role] = dict(measured, source_take_uses=usage, representation_gate=gate)
                gates[role+'_complete_chords'] = gate
                np.savez_compressed(folders['bulk']/(role+'-predictions.npz'), probability=probability, targets=y, cutoff=model.cutoff)
                save_json(report_path, report)
            report['held_out_scoring'] = dict(executed=True, reason='Training passed; both roles scored without refitting.')
        del waves, x, y, probability
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
                result['saved_probability_semantics'] = 'Binary occupancy at frozen train-only cutoff; raw mixture probabilities saved separately.'
                result['timing']['scope'] = 'Measured Python serial FIFO only; no native allocation/deadline or live-host/device proof.'
                report['datasets'][name] = result
                gates[name+'_no_pitch_safety_regression'] = result['arms']['primary_fifo']['comparison']['no_pitch_safety_regression']
                save_json(report_path, report)
            gates['ordinary_gain_at_least_5pp'] = report['datasets']['ordinary']['arms']['primary_fifo']['comparison']['pitch_coverage_gain_pp'] >= 5
            report['continuous_replay'] = dict(executed=True, reason='All three complete-chord gates passed.')
        passed = represented and all(gates.values())
        report.update(state='completed', final=True, stage='frozen harmonic-context screen complete', gates=gates,
            representation_feasibility_passed=represented, research_screen_passed=passed,
            decision=('exploratory pass; independent recordings and implementation gates remain' if passed
                      else 'rejected at training complete-chord gate' if not train_gate
                      else 'rejected at source-disjoint held-out gates' if not represented
                      else 'rejected by continuous safety or benefit gates'),
            limits=['All 555 intended-label excerpts retained, including known unresolved source-content disagreements.',
                'Pass1 ascending, pass2 descending, pass3 checkpoint protocols differ; not a pure take-only generalization test.',
                'Harmonic-coordinate weight sharing is not exact shift equivariance at finite FFT resolution.',
                'RMS-normalized sustained mixtures do not prove attacks, decays, lanes or unison multiplicity.',
                'Joint-context binary outputs still do not enforce a valid complete chord or string assignment.',
                ('Training transposition shifts spectrum/formants and duration, using the same 200 sources; twice the optimizer steps confounds attribution. No independent recording content.' if transposition is not None else
                 'Training envelopes vary on the same 200 sources; this supplies no independent recording content.' if variation is not None else
                 'Only the training objective changes versus the frozen context baseline; one seed/configuration is not a general result.' if loss_only else
                 'Model capacity and optimizer also change; this is not an isolated context ablation.'),
                'Held-out roles are source-disjoint development checks already used in previous experiments, not a fresh final benchmark.',
                'Zero padding and finite FFT resolution break exact pitch-shift equivariance.',
                'The longer trailing context spans 170.67ms; measured callback cost is not pluck-to-MIDI latency.',
                'Ordinary reuses source takes and is descriptive; no delivered-MIDI, native realtime or live-device proof.',
                'One configuration and train-only cutoff; no held-out tuning, promotion or installed change.'])
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
