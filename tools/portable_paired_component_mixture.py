"""One frozen-model paired crop/level observation on GitHub CPU; never fit."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import time

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, mixture_plan, render_mixture, validate_manifest
from tools.harmonic_context_learning import (HarmonicContextModel, PARAMETERS,
    SETWISE_PARAMS, make_network)
from tools.paired_component_mixture import (PairedCensus, PROBABILITY_ATOL,
    RECOMPOSITION_ATOL, paired_audio, probabilities, require_reproduction)
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_cached_diagnosis import fetch_artifact
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_direct_spectrum_learning import fetch_release, source_waves
from tools.portable_harmonic_context_learning import DEPENDENCIES, dependency_versions
from tools.shared_harmonic_learning import HarmonicFeatures


ROLES = ('train', 'calibration', 'test')
BATCH = 128


def validate_model_metadata(saved, cutoff, extractor):
    expected = dict(settings=SETTINGS, feature_parameters=PARAMETERS,
        coordinate_names=extractor.coordinate_names, model_parameters=SETWISE_PARAMS,
        cutoff=cutoff)
    for key, value in expected.items():
        if saved.get(key) != value:
            raise ValueError('Frozen model metadata differs: ' + key)
    # Source 7481905 saved this fixed 62-coordinate/53-pitch architecture
    # before these redundant fields were added. Accept that exact legacy
    # schema; normalization and strict state_dict loading still check tensors.
    dimensions = dict(feature_count=62, input_note_count=53, output_note_count=53)
    present = dimensions.keys() & saved.keys()
    if present and present != dimensions.keys():
        raise ValueError('Incomplete frozen model dimension metadata')
    for key in present:
        if saved[key] != dimensions[key]:
            raise ValueError('Frozen model metadata differs: ' + key)
    if any(saved.get(key) is not None for key in (
            'contrast_parameters', 'suppression_parameters', 'whitening_parameters',
            'halo_parameters', 'training_grid_consistency')):
        raise ValueError('Unexpected model variant')


def load_model(path, cutoff, extractor):
    remote_only()
    import torch
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    saved = torch.load(path, map_location='cpu', weights_only=True)
    validate_model_metadata(saved, cutoff, extractor)
    mean, scale = saved['mean'].numpy(), saved['scale'].numpy()
    if (mean.shape != (62,) or scale.shape != (62,) or not np.isfinite(mean).all()
            or not np.isfinite(scale).all() or (scale <= 0).any()):
        raise ValueError('Invalid frozen normalization')
    network = make_network()
    network.load_state_dict(saved['state_dict'], strict=True)
    network.eval()
    return HarmonicContextModel(mean, scale, network, cutoff=cutoff)


def load_reference(role, saved, takes, cutoff):
    plan = json.loads(gzip.decompress((saved / (role + '-mixture-plan.json.gz')).read_bytes()))
    generated = mixture_plan(takes, role=role, count=SETTINGS[role + '_examples'],
                             seed=SETTINGS[role + '_seed'])
    if plan != generated:
        raise ValueError('Original plan/source identity differs: ' + role)
    with np.load(saved / (role + '-predictions.npz'), allow_pickle=False) as archive:
        if set(archive.files) != {'probability', 'targets', 'cutoff'} or float(archive['cutoff']) != cutoff:
            raise ValueError('Original prediction format/cutoff differs')
        probability = probabilities(archive['probability'], len(plan)).copy()
        targets = archive['targets'].copy()
    if targets.dtype != np.bool_ or targets.shape != probability.shape:
        raise ValueError('Original target shape/type differs')
    return dict(plan=plan, probability=probability, targets=targets)


def reproduce(reference, waves, extractor, model):
    remote_only()
    plan = reference['plan']
    actual = np.empty_like(reference['probability'])
    for start in range(0, len(plan), BATCH):
        rows = plan[start:start+BATCH]
        features = np.empty((len(rows), len(extractor.names)), dtype=np.float64)
        for local, row in enumerate(rows):
            mixed, targets = render_mixture(row, waves)
            if not np.array_equal(targets, reference['targets'][start+local]):
                raise ValueError('Original intended target identity differs')
            features[local] = extractor(mixed)
        actual[start:start+len(rows)] = model.activity(features)
    identity = require_reproduction(actual, reference['probability'], model.cutoff)
    identity.update(examples=len(plan), targets_identical=True, regenerated_plan_identical=True)
    return actual, identity


def measure_components(role, reference, waves, extractor, model, bulk):
    remote_only()
    plan = reference['plan']
    offsets = np.cumsum([0] + [len(row['components']) for row in plan], dtype=np.int64)
    probability = np.empty((int(offsets[-1]), 53), dtype=np.float64)
    rms = np.empty(len(probability), dtype=np.float64)
    features = []
    feature_start = 0
    max_recomposition_error = 0.0
    for row_index, row in enumerate(plan):
        _, _, solos, error = paired_audio(row, waves)
        max_recomposition_error = max(max_recomposition_error, error)
        for component_index, audio in enumerate(solos):
            index = int(offsets[row_index]) + component_index
            rms[index] = float(np.sqrt(np.mean(audio * audio)))
            features.append(extractor(audio))
            if len(features) == BATCH:
                probability[feature_start:feature_start+BATCH] = model.activity(np.asarray(features, dtype=np.float64))
                feature_start += BATCH
                features.clear()
    if features:
        probability[feature_start:] = model.activity(np.asarray(features, dtype=np.float64))
    census = PairedCensus(model.cutoff)
    singleton_max_error, singleton_count = 0.0, 0
    for index, row in enumerate(plan):
        begin, end = offsets[index:index+2]
        solo = probability[begin:end]
        if len(solo) == 1:
            identity = require_reproduction(solo, reference['actual'][index:index+1], model.cutoff)
            singleton_max_error = max(singleton_max_error, identity['max_absolute_probability_error'])
            singleton_count += 1
        census.add(row, reference['actual'][index], solo, rms[begin:end])
    np.savez_compressed(bulk / (role + '-paired-predictions.npz'),
        mixture_probability=reference['actual'], targets=reference['targets'],
        component_probability=probability, component_offsets=offsets,
        component_rms=rms, cutoff=model.cutoff)
    result = census.finish()
    result['integrity'] = dict(component_recomposition_max_absolute_error=max_recomposition_error,
        singleton_examples=singleton_count, singleton_probability_max_absolute_error=singleton_max_error,
        singleton_changed_decisions=0, components=len(probability))
    return result


def run(spec_path, output):
    remote_only()  # Before any recorded input, model, output creation or dependency probe.
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output / name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report'] / 'report.json'
    report = dict(schema='m3_paired_component_mixture_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        fits=0, cutoff_retuned=False, labels_changed=False, roles={})
    started = time.perf_counter()
    try:
        spec = json.loads(spec_path.read_text())
        report['spec_sha256'] = digest(spec_path)
        report['frozen_reference'] = spec['frozen_reference']
        report['cutoff'] = spec['cutoff']
        report['source_sha'] = captured_text(['git', 'rev-parse', 'HEAD'])
        report['worker_sha'] = os.environ.get('GITHUB_SHA')
        report['run_id'] = os.environ.get('GITHUB_RUN_ID')
        if report['source_sha'] != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Source/worker identity mismatch')
        if spec['probability_absolute_tolerance'] != PROBABILITY_ATOL or spec['recomposition_absolute_tolerance'] != RECOMPOSITION_ATOL:
            raise ValueError('Frozen integrity tolerance differs')
        report['dependencies'] = dependency_versions()
        if report['dependencies'] != DEPENDENCIES:
            raise ValueError('Pinned dependency mismatch')
        pin = spec['sources']
        source_path = Path(pin['path'])
        check_hash(source_path, pin['sha256'])
        manifest = json.loads(source_path.read_text())
        takes, report['source_roles'] = validate_manifest(manifest)
        saved = folders['cache'] / 'saved-reference'
        report['artifact_identity'] = fetch_artifact(spec['worker_repository'], spec['artifact'], saved, folders['logs'])
        references = {role: load_reference(role, saved, takes, spec['cutoff']) for role in ROLES}
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(manifest, folders['inputs'])
        extractor = HarmonicFeatures()
        model = load_model(saved / 'frozen-harmonic-context-model.pt', spec['cutoff'], extractor)
        report['stage'] = 'reproduce every original mixture before component inference'
        report['mixture_identity'] = {}
        save_json(report_path, report)
        for role in ROLES:
            print('Reproducing original ' + role, flush=True)
            references[role]['actual'], report['mixture_identity'][role] = reproduce(references[role], waves, extractor, model)
            save_json(report_path, report)
        report['all_original_mixtures_reproduced'] = True
        report['stage'] = 'one exact-crop/effective-level solo observation per component'
        save_json(report_path, report)
        for role in ROLES:
            print('Measuring paired components ' + role, flush=True)
            report['roles'][role] = measure_components(role, references[role], waves, extractor, model, folders['bulk'])
            save_json(report_path, report)
        report.update(state='completed', final=True, stage='paired observation final',
            decision='diagnostic complete; original model rejection and installed scores unchanged',
            limits=spec['limits'])
        report['evidence'] = {p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
            for p in folders['bulk'].iterdir() if p.is_file()}
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['seconds'] = time.perf_counter() - started
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.spec, arguments.output)
