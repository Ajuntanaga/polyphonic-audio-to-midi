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
from tools.harmonic_partial_variation import PARTIAL_VARIATION, partial_examples
from tools.harmonic_pitch_transposition import TRANSPOSITION, transposition_examples
from tools.harmonic_peak_contrast import CONTRAST, HarmonicContrastFeatures, contrast_summary
from tools.harmonic_phase_motion import (PHASE_MOTION, SINGLE_PITCH_BASELINE,
    HarmonicPhaseFeatures, single_pitch_preservation)
from tools.harmonic_pitch_scaled_windows import PITCH_SCALED_WINDOWS, HarmonicPitchScaledFeatures
from tools.harmonic_spectral_patches import (SPECTRAL_PATCHES, HarmonicPatchFeatures,
    fit_patch_normalization, make_patch_network)
from tools.harmonic_level_suppression import SUPPRESSION, HarmonicLevelBlindFeatures
from tools.harmonic_spectral_whitening import WHITENING, HarmonicWhitenedFeatures
from tools.harmonic_halo_context import (HALO_PARAMETERS, HALO_MODEL_PARAMS, INPUT_NOTE_COUNT,
    HarmonicHaloFeatures, central_features)
from tools.harmonic_grid_consistency import (GRID_CONSISTENCY, FULL_GRADIENT_CONSISTENCY,
    validate_consistency, shifted_grid, grid_consistency_loss)
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.harmonic_training_checkpoint import (training_identity, save_training_checkpoint,
    restore_training_checkpoint)


DEPENDENCIES = {'numpy': '1.26.4', 'scipy': '1.13.1', 'scikit-learn': '1.7.2',
                'joblib': '1.5.2', 'soundfile': '0.13.1', 'torch': '2.5.1+cpu'}


def dependency_versions():
    return {name: version(name) for name in DEPENDENCIES}


def fit_model(features, truth, model_params=None, grid_consistency=None, spectral_patches=None,
              *, checkpoint_path=None, resume_checkpoint=None, checkpoint_context=None):
    remote_only()
    import torch
    params = MODEL_PARAMS if model_params is None else model_params
    if (checkpoint_path is not None or resume_checkpoint is not None) and (
            spectral_patches is None or checkpoint_path is None):
        raise ValueError('Epoch recovery requires the patch experiment and an output checkpoint')
    if spectral_patches is not None:
        require_identity(spectral_patches, SPECTRAL_PATCHES, 'fixed spectral patch encoder')
        require_identity(params, SETWISE_PARAMS, 'fixed patch optimizer and pitch context')
        if grid_consistency is not None:
            raise ValueError('Patch encoder cannot be combined with grid consistency')
    if grid_consistency is not None:
        validate_consistency(grid_consistency)
        if params['padding'] != 'zero' or params['loss'] != SETWISE_PARAMS['loss']:
            raise ValueError('Grid consistency requires the original zero-padded setwise network')
    torch.set_num_threads(params['torch_threads'])
    torch.use_deterministic_algorithms(params['deterministic'])
    torch.manual_seed(params['seed'])
    truth = np.asarray(truth, dtype=bool)
    features = np.asarray(features)
    if params['padding'] not in ('zero', 'valid'):
        raise ValueError('Unknown context padding')
    halo = params['padding'] == 'valid'
    input_note_count = INPUT_NOTE_COUNT if halo else NOTE_COUNT
    if features.ndim != 2 or features.shape[1] % input_note_count:
        raise ValueError('Expected complete candidate feature rows')
    feature_count = features.shape[1]//input_note_count
    if truth.shape != (len(features), NOTE_COUNT) or set(np.unique(truth)) != {False, True}:
        raise ValueError('Expected aligned training targets with both binary classes')
    if spectral_patches is not None:
        if feature_count != SPECTRAL_PATCHES['feature_count'] or features.dtype != np.float32:
            raise ValueError('Expected float32 dense spectral patch features')
        mean, scale = fit_patch_normalization(features)
        inputs = None  # Normalize one shuffled batch at a time, without a second full feature matrix.
        network = make_patch_network().train()
    else:
        mean, scale = fit_normalization(central_features(features) if halo else features, feature_count)
        inputs = torch.from_numpy(normalized_context(features, mean, scale, feature_count,
                                                    note_count=input_note_count))
        network = make_network(feature_count, valid_context=halo).train()
    targets = torch.from_numpy(truth.astype(np.float32))
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
    supervised_losses, consistency_losses = [], []
    first_epoch, previous_seconds = 0, 0.0
    identity = None
    if checkpoint_path is not None:
        if not isinstance(checkpoint_context, dict) or not checkpoint_context:
            raise ValueError('Checkpoint execution identity is required')
        identity = training_identity(features, truth, mean, scale, params, spectral_patches,
            dict(execution=checkpoint_context, torch=str(torch.__version__), numpy=np.__version__))
        if resume_checkpoint is not None:
            first_epoch, losses, previous_seconds = restore_training_checkpoint(
                resume_checkpoint, network, optimizer, generator, mean, scale, identity)
            print(f'resumed completed epoch {first_epoch}/{params["epochs"]}', flush=True)
    started = time.perf_counter()
    def persist_progress():
        save_training_checkpoint(checkpoint_path, network, optimizer, generator, mean, scale,
            identity, losses, previous_seconds+time.perf_counter()-started)
        save_json(Path(checkpoint_path).with_suffix('.json'), dict(
            completed_epochs=len(losses), planned_epochs=params['epochs'],
            last_training_loss=losses[-1], training_loss_is_tracking_score=False,
            checkpoint_sha256=digest(checkpoint_path), checkpoint_bytes=Path(checkpoint_path).stat().st_size,
            resumed_from_epoch=first_epoch, updated_at=datetime.now(timezone.utc).isoformat()))
    for epoch in range(first_epoch, params['epochs']):
        order = torch.randperm(len(features), generator=generator)
        total_loss = 0.0
        supervised_total = consistency_total = 0.0
        for indices in order.split(params['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            batch = (torch.from_numpy(normalized_context(features[indices.numpy()], mean, scale,
                       feature_count)) if spectral_patches is not None else inputs[indices])
            logits = network(batch)
            loss = criterion(logits, targets[indices])
            if grid_consistency is not None:
                consistency = grid_consistency_loss(logits, network(shifted_grid(inputs[indices])),
                    full_gradient=grid_consistency == FULL_GRADIENT_CONSISTENCY)
                supervised_total += float(loss.detach())*len(indices)
                consistency_total += float(consistency.detach())*len(indices)
                loss = loss + grid_consistency['weight']*consistency
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())*len(indices)
        losses.append(total_loss/len(features))
        if grid_consistency is not None:
            supervised_losses.append(supervised_total/len(inputs))
            consistency_losses.append(consistency_total/len(inputs))
        if checkpoint_path is not None:
            persist_progress()
        print(f'epoch {epoch+1}/{params["epochs"]}: loss={losses[-1]:.9g}', flush=True)
    if checkpoint_path is not None and first_epoch == params['epochs']:
        persist_progress()
    network.eval()
    fit = dict(seconds=previous_seconds+time.perf_counter()-started,
        epochs=len(losses), mixtures=len(features), pooled_candidate_rows=len(features)*NOTE_COUNT,
        input_note_count=input_note_count, output_note_count=NOTE_COUNT,
        normalization_rows=len(features)*NOTE_COUNT,
        features_per_candidate=feature_count, shared_binary_outputs=1,
        parameter_count=sum(p.numel() for p in network.parameters()),
        final_loss=losses[-1], loss_curve=losses, held_out_used=False, fits=1,
        objective=params['loss'])
    if checkpoint_path is not None:
        fit['recovery'] = dict(resumed_from_epoch=first_epoch,
            epochs_executed_this_invocation=params['epochs']-first_epoch,
            checkpoint_sha256=digest(checkpoint_path), identity=identity,
            checkpoint_interval='each completed epoch', mid_epoch_work_repeated_after_interruption=True)
    if spectral_patches is not None:
        fit.update(spectral_patch_parameters=SPECTRAL_PATCHES,
            feature_storage_dtype=str(features.dtype), normalized_batch_storage=True,
            optimizer_steps=params['epochs']*((len(features)+params['batch_size']-1)//params['batch_size']),
            training_forwards_per_step=1, inference_forwards_per_batch=1)
        require_identity(fit['parameter_count'], SPECTRAL_PATCHES['parameter_count'],
                         'frozen patch encoder parameter count')
    if grid_consistency is not None:
        fit.update(training_grid_consistency=dict(grid_consistency),
            supervised_loss_curve=supervised_losses, consistency_loss_curve=consistency_losses,
            optimizer_steps=params['epochs']*((len(inputs)+params['batch_size']-1)//params['batch_size']),
            training_forwards_per_step=2, inference_forwards_per_batch=1)
    return HarmonicContextModel(mean, scale, network, input_note_count=input_note_count), fit


def save_model(path, model, extractor, model_params=None, grid_consistency=None):
    remote_only()
    import torch
    saved = dict(state_dict=model.network.state_dict(), mean=torch.from_numpy(model.mean),
        scale=torch.from_numpy(model.scale), cutoff=model.cutoff,
        coordinate_names=extractor.coordinate_names, settings=SETTINGS,
        feature_parameters=PARAMETERS, feature_count=len(extractor.coordinate_names),
        contrast_parameters=getattr(extractor, 'contrast_parameters', None),
        suppression_parameters=getattr(extractor, 'suppression_parameters', None),
        whitening_parameters=getattr(extractor, 'whitening_parameters', None),
        halo_parameters=getattr(extractor, 'halo_parameters', None),
        input_note_count=model.input_note_count, output_note_count=NOTE_COUNT,
        model_parameters=MODEL_PARAMS if model_params is None else model_params)
    if isinstance(extractor, HarmonicPhaseFeatures):
        saved['phase_parameters'] = PHASE_MOTION
    if isinstance(extractor, HarmonicPitchScaledFeatures):
        saved['pitch_scaled_window_parameters'] = PITCH_SCALED_WINDOWS
        saved['window_lengths_by_candidate'] = extractor.window_lengths.tolist()
    if isinstance(extractor, HarmonicPatchFeatures):
        saved['spectral_patch_parameters'] = SPECTRAL_PATCHES
    if grid_consistency is not None:
        validate_consistency(grid_consistency)
        saved['training_grid_consistency'] = dict(grid_consistency)
    torch.save(saved, path)


def run(spec_path, output, *, training_recovery=None, resume_checkpoint=None):
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
        partial = spec.get('training_partial_variation')
        transposition = spec.get('training_pitch_transposition')
        contrast = spec.get('harmonic_peak_contrast')
        phase = spec.get('harmonic_phase_motion')
        pitch_scaled = spec.get('harmonic_pitch_scaled_windows')
        spectral_patches = spec.get('harmonic_spectral_patches')
        if training_recovery is not None and spectral_patches is None:
            raise ValueError('Training recovery is scoped to the frozen patch experiment')
        if resume_checkpoint is not None and training_recovery is None:
            raise ValueError('Resume requires the pinned training recovery envelope')
        suppression = spec.get('harmonic_level_suppression')
        whitening = spec.get('harmonic_spectral_whitening')
        halo = spec.get('harmonic_halo_context')
        grid_consistency = spec.get('training_grid_consistency')
        if sum(value is not None for value in (variation, partial, transposition, contrast, phase, pitch_scaled, spectral_patches, suppression, whitening, halo, grid_consistency)) > 1:
            raise ValueError('Representation and augmentation changes cannot be combined in this screen')
        if spectral_patches is not None:
            require_identity(spectral_patches, SPECTRAL_PATCHES, 'fixed dense spectral patch encoder')
            require_identity(spec['single_pitch_baseline'], SINGLE_PITCH_BASELINE, 'frozen single-pitch preservation')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise objective and optimizer')
        if pitch_scaled is not None:
            require_identity(pitch_scaled, PITCH_SCALED_WINDOWS, 'fixed past-only pitch-scaled windows')
            require_identity(spec['single_pitch_baseline'], SINGLE_PITCH_BASELINE, 'frozen single-pitch preservation')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if phase is not None:
            require_identity(phase, PHASE_MOTION, 'fixed trailing harmonic phase motion')
            require_identity(spec['single_pitch_baseline'], SINGLE_PITCH_BASELINE, 'frozen single-pitch preservation')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if grid_consistency is not None:
            validate_consistency(grid_consistency)
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise architecture and supervised objective')
        if halo is not None:
            require_identity(halo, HALO_PARAMETERS, 'fixed measured halo and central output range')
            require_identity(params, HALO_MODEL_PARAMS, 'fixed valid-context setwise model')
        if whitening is not None:
            require_identity(whitening, WHITENING, 'fixed frame-local spectral whitening')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if partial is not None:
            require_identity(partial, PARTIAL_VARIATION, 'fixed independent partial envelopes')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if suppression is not None:
            require_identity(suppression, SUPPRESSION, 'fixed absolute-level suppression')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if contrast is not None:
            require_identity(contrast, CONTRAST, 'fixed trailing harmonic peak contrast')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if variation is not None:
            require_identity(variation, VARIATION, 'fixed training-only source variation')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        if transposition is not None:
            require_identity(transposition, TRANSPOSITION, 'fixed coherent training transposition')
            require_identity(params, SETWISE_PARAMS, 'unchanged setwise model and objective')
        require_identity(params, HALO_MODEL_PARAMS if halo is not None else frozen_params[params['loss']],
                         'one fixed shared context classifier and objective')
        report['training_objective'] = params['loss']
        if params['loss'] == COMPLETE_SET_PARAMS['loss']:
            report['schema'] = 'm3_harmonic_complete_set_learning_v1'
        elif params['loss'] == SETWISE_PARAMS['loss']:
            report['schema'] = 'm3_harmonic_setwise_learning_v1'
        if variation is not None:
            report['schema'] = 'm3_harmonic_source_variation_v1'
        if partial is not None:
            report['schema'] = 'm3_harmonic_partial_variation_v1'
        if transposition is not None:
            report['schema'] = 'm3_harmonic_pitch_transposition_v1'
        if contrast is not None:
            report['schema'] = 'm3_harmonic_peak_contrast_v1'
        if phase is not None:
            report['schema'] = 'm3_harmonic_phase_motion_v1'
        if pitch_scaled is not None:
            report['schema'] = 'm3_harmonic_pitch_scaled_windows_v1'
        if spectral_patches is not None:
            report['schema'] = 'm3_harmonic_spectral_patches_v1'
        if suppression is not None:
            report['schema'] = 'm3_harmonic_level_suppression_v1'
        if whitening is not None:
            report['schema'] = 'm3_harmonic_spectral_whitening_v1'
        if halo is not None:
            report['schema'] = 'm3_harmonic_halo_context_v1'
        if grid_consistency is not None:
            report['schema'] = ('m3_harmonic_full_gradient_consistency_v1'
                if grid_consistency == FULL_GRADIENT_CONSISTENCY else 'm3_harmonic_grid_consistency_v1')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), dependencies=versions)
        if training_recovery is not None:
            folders['checkpoint'] = output/'checkpoint'
            folders['checkpoint'].mkdir()
            report['execution_recovery'] = dict(envelope=training_recovery,
                resume_checkpoint_sha256=None if resume_checkpoint is None else digest(resume_checkpoint),
                scientific_specification_unchanged=True, original_timeout_run_weights_available=False)
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
        extractor = (HarmonicPatchFeatures() if spectral_patches is not None else
                     HarmonicPitchScaledFeatures() if pitch_scaled is not None else
                     HarmonicPhaseFeatures() if phase is not None else
                     HarmonicHaloFeatures() if halo is not None else
                     HarmonicWhitenedFeatures() if whitening is not None else
                     HarmonicLevelBlindFeatures() if suppression is not None else
                     HarmonicContrastFeatures() if contrast is not None else HarmonicFeatures())
        report['features'] = dict(coordinate_names=extractor.coordinate_names,
            per_candidate=len(extractor.coordinate_names), candidate_count=NOTE_COUNT,
            input_candidate_count=len(extractor.names)//len(extractor.coordinate_names),
            flatten_order=('mixture, measured context MIDI-4..120, shared coordinate; outputs MIDI32..84' if halo is not None
                           else 'mixture, candidate MIDI32..84, shared coordinate'),
            identity_features=False, exact_pitch_shift_equivariance=False,
            receptive_field_pitches=1+2*sum(MODEL_PARAMS['dilations']),
            boundary_context=('Measured 36-pitch halo each side; valid convolutions, no padded boundary in any output receptive field.' if halo is not None
                              else 'Zero padding supplies incomplete context and can encode boundary position.'),
            distinction=('Training-only one-row feature-grid consistency; same features, network, scaler, plans, optimizer steps and inference as setwise baseline.' if grid_consistency is not None else
                '25 offsets per partial replace five; a shared two-layer local shape encoder feeds the original pitch-context layers. Original fixed windows and RMS; denser evidence and capacity change together.' if spectral_patches is not None else
                'Only the harmonic/RMS window lengths scale inversely with candidate pitch. Same 62 coordinates, 14465 parameters, initialization, plans and training; no future context.' if pitch_scaled is not None else
                'Original 62 coordinates plus 12 past-only phase-motion values; input layer gains 384 parameters, no augmentation.' if phase is not None else
                'Measured context replaces all padding; same central features, scaler rows, 14465 parameters and initialization. Added context and boundary removal change together.' if halo is not None else
                'Only the current-frame spectral envelope is partially whitened; original RMS, 62 slots, network, plans and initialization are unchanged versus setwise baseline.' if whitening is not None else
                'Only RMS coordinates 30 and 61 are zeroed; all 62 slots, other 60 values, model shape and initialization are unchanged versus setwise baseline.' if suppression is not None else
                'Original 62 coordinates plus 44 peak-contrast coordinates; input layer gains 1408 parameters, no augmentation.' if contrast is not None else
                'Clean training plus transposed companions; same epochs, twice the optimizer steps.' if transposition is not None else
                'Only training component partial envelopes change; same 62 features, model, examples and optimizer steps.' if partial is not None else
                'Only training component envelopes change versus the setwise model.' if variation is not None else
                'Only the training objective changes versus the frozen context baseline.' if loss_only else
                'Unchanged harmonic rows feed shared convolutions across pitches, then a shared binary readout; capacity also changes.'))
        if pitch_scaled is not None:
            report['features']['pitch_scaled_window_parameters'] = PITCH_SCALED_WINDOWS
            report['features']['window_lengths_by_candidate'] = extractor.window_lengths.tolist()
        if spectral_patches is not None:
            report['features']['spectral_patch_parameters'] = SPECTRAL_PATCHES
        report['stage'] = 'training mixtures; one shared fit and training-only cutoff'
        save_json(report_path, report)
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        if 'training_plan_identity' in spec:
            actual = hashlib.sha256(gzip.decompress((folders['bulk']/'train-mixture-plan.json.gz').read_bytes())).hexdigest()
            require_identity(actual, spec['training_plan_identity']['decoded_sha256'], 'unchanged training mixture plan')
            report['training_plan_identity'] = dict(spec['training_plan_identity'], verified=True)
        if partial is not None:
            fit_x, fit_y, report['training_partial_variation'] = partial_examples(
                folders['bulk']/'train-mixture-plan.json.gz', waves, extractor, folders['bulk'])
            require_identity(report['training_partial_variation']['decoded_sha256'],
                spec['partial_plan_identity']['decoded_sha256'], 'frozen partial-varied training plan')
            if fit_x.shape != x.shape or not np.array_equal(fit_y, y):
                raise ValueError('Partial variation changed training shape or targets')
            model, report['fit'] = fit_model(fit_x, fit_y, model_params=params)
            del fit_x, fit_y
        elif variation is not None:
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
        elif grid_consistency is not None:
            model, report['fit'] = fit_model(x, y, model_params=params, grid_consistency=grid_consistency)
        elif spectral_patches is not None:
            recovery = {} if training_recovery is None else dict(
                checkpoint_path=folders['checkpoint']/'training-state.pt',
                resume_checkpoint=resume_checkpoint,
                checkpoint_context=dict(source_commit=source,
                    specification_sha256=digest(spec_path), dependencies=versions,
                    recovery_envelope=training_recovery))
            model, report['fit'] = fit_model(x, y, model_params=params,
                spectral_patches=spectral_patches, **recovery)
        else:
            model, report['fit'] = fit_model(x, y, model_params=params)
        probability = model.activity(x)
        report['cutoff_fit'] = fit_training_cutoff(probability, y)
        model.cutoff = report['cutoff_fit']['cutoff']
        model_path = folders['bulk']/'frozen-harmonic-context-model.pt'
        save_model(model_path, model, extractor, model_params=params,
                   **({'grid_consistency': grid_consistency} if grid_consistency is not None else {}))
        report['frozen_model'] = dict(sha256=digest(model_path), cutoff=model.cutoff,
            persisted_before_held_out_scoring=True, training_fits=1)
        measured = summarize(probability, y, model.cutoff)
        train_gate = acceptance_gate(measured['summary'], training=True) and report['cutoff_fit']['feasible']
        report['mixtures'] = dict(train=dict(measured, source_take_uses=usage, representation_gate=train_gate))
        if contrast is not None:
            report['contrast_diagnostics'] = dict(train=contrast_summary(x, y, probability, model.cutoff))
        np.savez_compressed(folders['bulk']/'train-predictions.npz', probability=probability, targets=y, cutoff=model.cutoff)
        gates = dict(train_complete_chords=train_gate)
        if phase is not None or pitch_scaled is not None or spectral_patches is not None:
            report['single_pitch_preservation'] = single_pitch_preservation(probability, y, model.cutoff)
            gates['train_single_pitch_noninferiority'] = report['single_pitch_preservation']['passed']
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
                if contrast is not None:
                    report['contrast_diagnostics'][role] = contrast_summary(x, y, probability, model.cutoff)
                gates[role+'_complete_chords'] = gate
                np.savez_compressed(folders['bulk']/(role+'-predictions.npz'), probability=probability, targets=y, cutoff=model.cutoff)
                save_json(report_path, report)
            report['held_out_scoring'] = dict(executed=True, reason='Training passed; both roles scored without refitting.')
        del waves, x, y, probability
        represented = train_gate and all(gates.values())
        report['datasets'] = {}
        report['continuous_replay'] = dict(executed=False,
            reason='Training, both held-out complete-chord gates and any recorded preservation gate must pass first.')
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
                      else 'rejected by single-pitch preservation' if not gates.get('train_single_pitch_noninferiority', True)
                      else 'rejected at source-disjoint held-out gates' if not represented
                      else 'rejected by continuous safety or benefit gates'),
            limits=['All 555 intended-label excerpts retained, including known unresolved source-content disagreements.',
                'Pass1 ascending, pass2 descending, pass3 checkpoint protocols differ; not a pure take-only generalization test.',
                'Harmonic-coordinate weight sharing is not exact shift equivariance at finite FFT resolution.',
                'RMS-normalized sustained mixtures do not prove attacks, decays, lanes or unison multiplicity.',
                'Joint-context binary outputs still do not enforce a valid complete chord or string assignment.',
                ('Feature rows move together, retaining FFT and source signatures. This is not physical transposition or proof of source invariance. Consistency may propagate errors or remove useful position evidence; one seed and weight only.' if grid_consistency is not None else
                 'Dense patches and encoder capacity change together, with float32 stored features and bounded normalization. They may overfit source timbre or leakage; no source separation, exact equivariance or unique causal attribution.' if spectral_patches is not None else
                 'Pitch-scaled windows shorten high-pitch averaging and reduce high-pitch frequency resolution. RMS context changes with them; nearby notes, noise and attack variation can regress. This is not a full constant-Q transform or exact pitch equivariance.' if pitch_scaled is not None else
                 'Phase increments overlap and are not independent. Shared harmonics, leakage, noise and bends can confound them; no source ownership or hard phase gate. Added capacity and changed initialization also affect the comparison.' if phase is not None else
                 'Measured halo adds spectral context and removes boundary cues together; no unique attribution to either. Very low halo pitches are FFT-unresolved; high probes may be weak.' if halo is not None else
                 'Whitening can amplify leakage/noise and alter relative note strengths or remove useful timbre evidence. It uses only the present trailing frame, with no new silence or pitch gate.' if whitening is not None else
                 'Absolute RMS inputs are suppressed, but existing relative-power floors remain level-dependent at very low levels. Losing level evidence may increase quiet/noise false outputs; no added silence gate.' if suppression is not None else
                 'Peak contrast is learned evidence, with no hard harmonicity rejection; vibrato, inharmonicity and overlapping peaks can weaken it. Input capacity also increases.' if contrast is not None else
                 'Training transposition shifts spectrum/formants and duration, using the same 200 sources; twice the optimizer steps confounds attribution. No independent recording content.' if transposition is not None else
                 'Independent partial envelopes use the intended training note, not verified pitch; crop-periodic spectral shaping is training-only and supplies no independent recording content. It can alter transients or suppress an already weak partial.' if partial is not None else
                 'Training envelopes vary on the same 200 sources; this supplies no independent recording content.' if variation is not None else
                 'Only the training objective changes versus the frozen context baseline; one seed/configuration is not a general result.' if loss_only else
                 'Model capacity and optimizer also change; this is not an isolated context ablation.'),
                'Held-out roles are source-disjoint development checks already used in previous experiments, not a fresh final benchmark.',
                ('Valid context removes padding cues; finite FFT resolution and fixed floors still break exact audio pitch-shift equivariance.' if halo is not None else
                 'Zero padding and finite FFT resolution break exact pitch-shift equivariance.'),
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
