"""One frozen harmonic context classifier screen, recorded execution on GitHub CPU."""
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, validate_manifest
from tools.harmonic_context_learning import (PARAMETERS, MODEL_PARAMS, FEATURE_COUNT,
    NOTE_COUNT, HarmonicFeatures, HarmonicContextModel, fit_normalization, normalized_context,
    make_network, acceptance_gate, summarize)
from tools.spectral_dictionary import IdentityTransform, fit_training_cutoff
from tools.portable_direct_spectrum_learning import (continuous_dataset, fetch_release,
    role_examples, source_waves)
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


DEPENDENCIES = {'numpy': '1.26.4', 'scipy': '1.13.1', 'scikit-learn': '1.7.2',
                'joblib': '1.5.2', 'soundfile': '0.13.1', 'torch': '2.5.1+cpu'}


def dependency_versions():
    return {name: version(name) for name in DEPENDENCIES}


def fit_model(features, truth):
    remote_only()
    import torch
    torch.set_num_threads(MODEL_PARAMS['torch_threads'])
    torch.use_deterministic_algorithms(MODEL_PARAMS['deterministic'])
    torch.manual_seed(MODEL_PARAMS['seed'])
    truth = np.asarray(truth, dtype=bool)
    if truth.shape != (len(features), NOTE_COUNT) or set(np.unique(truth)) != {False, True}:
        raise ValueError('Expected aligned training targets with both binary classes')
    mean, scale = fit_normalization(features)
    inputs = torch.from_numpy(normalized_context(features, mean, scale))
    targets = torch.from_numpy(truth.astype(np.float32))
    network = make_network().train()
    optimizer = torch.optim.Adam(network.parameters(), lr=MODEL_PARAMS['learning_rate'],
                                 weight_decay=MODEL_PARAMS['weight_decay'])
    criterion = torch.nn.BCEWithLogitsLoss()
    generator = torch.Generator().manual_seed(MODEL_PARAMS['seed'])
    losses = []
    started = time.perf_counter()
    for epoch in range(MODEL_PARAMS['epochs']):
        order = torch.randperm(len(inputs), generator=generator)
        total_loss = 0.0
        for indices in order.split(MODEL_PARAMS['batch_size']):
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(network(inputs[indices]), targets[indices])
            if not torch.isfinite(loss):
                raise ValueError('Nonfinite training loss')
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())*len(indices)
        losses.append(total_loss/len(inputs))
        print(f'epoch {epoch+1}/{MODEL_PARAMS["epochs"]}: loss={losses[-1]:.9g}', flush=True)
    network.eval()
    return HarmonicContextModel(mean, scale, network), dict(seconds=time.perf_counter()-started,
        epochs=len(losses), mixtures=len(features), pooled_candidate_rows=len(features)*NOTE_COUNT,
        features_per_candidate=FEATURE_COUNT, shared_binary_outputs=1,
        parameter_count=sum(p.numel() for p in network.parameters()),
        final_loss=losses[-1], loss_curve=losses, held_out_used=False, fits=1)


def save_model(path, model, extractor):
    remote_only()
    import torch
    torch.save(dict(state_dict=model.network.state_dict(), mean=torch.from_numpy(model.mean),
        scale=torch.from_numpy(model.scale), cutoff=model.cutoff,
        coordinate_names=extractor.coordinate_names, settings=SETTINGS,
        feature_parameters=PARAMETERS, model_parameters=MODEL_PARAMS), path)


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
        require_identity(spec['model_parameters'], MODEL_PARAMS, 'one fixed shared context classifier')
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
            distinction='Unchanged harmonic rows feed shared convolutions across pitches, then a shared binary readout; capacity also changes.')
        report['stage'] = 'training mixtures; one shared fit and training-only cutoff'
        save_json(report_path, report)
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        model, report['fit'] = fit_model(x, y)
        probability = model.activity(x)
        report['cutoff_fit'] = fit_training_cutoff(probability, y)
        model.cutoff = report['cutoff_fit']['cutoff']
        model_path = folders['bulk']/'frozen-harmonic-context-model.pt'
        save_model(model_path, model, extractor)
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
                'Model capacity and optimizer also change; this is not an isolated context ablation.',
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
