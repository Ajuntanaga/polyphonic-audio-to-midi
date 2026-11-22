"""One fixed source-disjoint spectrum-learning experiment; GitHub CPU only."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import time

import numpy as np

from tools.direct_spectrum_learning import (MODEL_PARAMS, SETTINGS, SpectrumFeatures,
    classification_summary, fifo_clock, mixture_plan, prediction_spans,
    render_mixture, representation_gate, trailing_context, validate_manifest)
from tools.pitch_detector_comparison import compare, digest, read_labels, score
from tools.portable_basic_pitch_cached_diagnosis import require_identity
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json


def fetch_release(repository, pin, cache, destination, logs):
    remote_only()
    download = cache/pin['release']
    download.mkdir()
    command = ['gh', 'release', 'download', pin['release'], '--repo', repository,
               '--pattern', pin['asset'], '--dir', str(download)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    (logs/(pin['release']+'.stdout')).write_text(result.stdout)
    (logs/(pin['release']+'.stderr')).write_text(result.stderr)
    result.check_returncode()
    path = download/pin['asset']
    check_hash(path, pin['sha256'])
    destination.mkdir(exist_ok=True)
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe input archive member')
        archive.extractall(destination, members=members, filter='data')
    return dict(pin, verified=True, bytes=path.stat().st_size, members=len(members))


def load_wave(path, sample_count, sample_rate):
    remote_only()
    import soundfile as sf
    wave, rate = sf.read(path, dtype='float64', always_2d=False)
    if rate != sample_rate or wave.shape != (sample_count,) or not np.isfinite(wave).all():
        raise ValueError('Waveform shape, rate or values differ: '+path.name)
    return wave


def source_waves(manifest, inputs):
    remote_only()
    waves = {}
    for source in manifest['files']:
        wav, labels = inputs/source['raw_path'], inputs/source['labels_path']
        check_hash(wav, source['raw_sha256'])
        check_hash(labels, source['labels_sha256'])
        with labels.open(newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        if len(rows) != len(source['takes']):
            raise ValueError('Source label count differs')
        for i, (row, take) in enumerate(zip(rows, source['takes'])):
            if take['label_index'] != i or any(int(row[key]) != take[key] for key in
                    ('start_sample', 'end_sample', 'midi_note', 'string_mask', 'calibration_pass')):
                raise ValueError('Source label metadata differs')
        waves[source['stem']] = load_wave(wav, source['sample_count'], source['sample_rate'])
    return waves


def save_gzip_json(path, value):
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        json.dump(value, stream, separators=(',', ':'), allow_nan=False)


def role_examples(role, takes, waves, extractor, bulk):
    remote_only()
    plan = mixture_plan(takes, role=role, count=SETTINGS[role+'_examples'],
                        seed=SETTINGS[role+'_seed'])
    save_gzip_json(bulk/(role+'-mixture-plan.json.gz'), plan)
    x = np.empty((len(plan), len(extractor.names)), dtype=getattr(extractor, 'storage_dtype', np.float64))
    y = np.empty((len(plan), SETTINGS['note_high']-SETTINGS['note_low']+1), dtype=bool)
    for i, row in enumerate(plan):
        audio, target = render_mixture(row, waves)
        x[i], y[i] = extractor(audio), target
    counts = Counter(c['source_key'] for row in plan for c in row['components'])
    expected = {take['key'] for take in takes if take['role'] == role}
    if set(counts) != expected:
        raise ValueError('A retained source was omitted or another role entered the mixtures')
    return x, y, dict(counts)


def continuous_dataset(name, config, baseline, inputs, extractor, scaler, model, bulk):
    remote_only()
    clock = {key: config[key] for key in ('sample_count', 'sample_rate')}
    wav, label_path = inputs/'corpus'/(name+'.wav'), inputs/'corpus'/(name+'.tsv')
    check_hash(wav, config['wav_sha256'])
    check_hash(label_path, config['labels_sha256'])
    wave = load_wave(wav, **clock)
    wave *= 10**(SETTINGS['input_trim_db']/20)
    source_ends = np.arange(SETTINGS['block'], len(wave), SETTINGS['block'], dtype=np.int64)
    source_ends = np.r_[source_ends, len(wave)]
    probability = np.empty((len(source_ends), 53), dtype=np.float64)
    service_ns = np.empty(len(source_ends), dtype=np.int64)
    for i, end in enumerate(source_ends):
        started = time.perf_counter_ns()
        features = extractor(trailing_context(wave, int(end)))
        probability[i] = model.predict_proba(scaler.transform(features.reshape(1, -1)))[0]
        service_ns[i] = time.perf_counter_ns()-started
    timing = fifo_clock(source_ends, service_ns)
    # Integer ceil: never claim a sample before the measured result is available.
    emitted = (timing[:, 3]*clock['sample_rate']+999_999_999)//1_000_000_000
    primary = prediction_spans(probability, emitted, clock['sample_count'])
    diagnostic = prediction_spans(probability, source_ends, clock['sample_count'])
    np.savez_compressed(bulk/(name+'-predictions.npz'), probability=probability,
                        timing=timing, source_ends=source_ends, emitted_samples=emitted)
    save_gzip_json(bulk/(name+'-spans.json.gz'), dict(primary_fifo=primary,
                                                   source_availability=diagnostic))
    # Continuous labels are used only for scoring after the frozen prediction tape.
    labels = read_labels(label_path)
    reference = score(baseline['pitch_spans'], labels, **clock)
    require_identity(reference, baseline['measurement'], name+' complete CURRENT score')
    arms = {}
    for arm, spans in [('primary_fifo', primary), ('source_availability_diagnostic', diagnostic)]:
        measured = score(spans, labels, **clock)
        comparison = compare(reference, measured)
        arms[arm] = dict(measurement=measured, comparison=comparison,
            occupancy_segments=len(spans),
            labels_gaining=sum(r['present_samples_delta'] > 0 for r in comparison['label_deltas']),
            labels_losing=sum(r['present_samples_delta'] < 0 for r in comparison['label_deltas']),
            labels_becoming_missing=sum(r['current_present_samples'] > 0 and r['model_present_samples'] == 0
                                       for r in comparison['label_deltas']))
    return dict(current_complete_score_identity=True, current_measurement=reference, arms=arms,
        source_relationship=('Reuses training-source takes: descriptive stress score, not independent validation.'
                             if name == 'ordinary' else 'Separately recorded physical middle-range check.'),
        timing_columns=['source_end', 'arrival_ns', 'service_ns', 'finish_ns', 'queued_ns'],
        timing=dict(callbacks=len(timing), service_ns_p50=float(np.percentile(service_ns, 50)),
            service_ns_p99=float(np.percentile(service_ns, 99)), service_ns_max=int(service_ns.max()),
            service_seconds_total=float(service_ns.sum()/1e9),
            queued_callbacks=int((timing[:, 4] > 0).sum()), max_queue_ns=int(timing[:, 4].max()),
            results_after_recording_end=int((emitted >= len(wave)).sum()),
            scope='Measured Python feature/scaler/MLP cost in a serial FIFO; no native allocations, '
                  'audio driver, actual host scheduling or device delivery measurement.'),
        eof=dict(last_prediction_active_notes=(np.flatnonzero(probability[-1] >= SETTINGS['cutoff'])+32).tolist(),
                 closure='Scoring boundary only, not evidence of a delivered NoteOff or stuck MIDI.'))


def run(spec_path, output):
    remote_only()  # Before recorded input, model fitting, dependencies or downloads.
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    import sklearn
    import joblib
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'inputs', 'bulk')}
    for folder in folders.values():
        folder.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_direct_spectrum_learning_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), installed_output_changed=False,
        promotion_accepted=False, live_readiness='not measured')
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA') or sklearn.__version__ != '1.7.2'
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']):
            raise ValueError('Frozen execution provenance mismatch')
        require_identity(spec['settings'], SETTINGS, 'spectrum settings')
        require_identity(spec['model_parameters'], json.loads(json.dumps(MODEL_PARAMS)), 'model parameters')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification=spec, specification_sha256=digest(spec_path), python=sys.version,
            platform=platform.platform(), sklearn=sklearn.__version__, numpy=np.__version__)
        references = {}
        for name, pin in spec['references'].items():
            path = root/pin['path']
            check_hash(path, pin['sha256'])
            references[name] = json.loads(path.read_text())
        takes, counts = validate_manifest(references['sources'])
        require_identity(counts, dict(train=200, calibration=200, test=155), 'all source roles')
        report['source_roles'] = dict(counts=counts, cross_role_original_overlap=False,
            all_takes_retained=True, held_out_unit='Recording pass/source excerpt, same instrument/session')
        report['stage'] = 'retrieve existing pinned input releases'
        save_json(report_path, report)
        report['inputs'] = [fetch_release(spec['worker_repository'], pin, folders['cache'],
                            folders['inputs'], folders['logs']) for pin in spec['input_releases']]
        waves = source_waves(references['sources'], folders['inputs'])
        extractor = SpectrumFeatures()
        report['feature_names'] = extractor.names
        report['stage'] = 'generate training mixtures and fit one frozen model'
        save_json(report_path, report)
        x, y, usage = role_examples('train', takes, waves, extractor, folders['bulk'])
        scaler = StandardScaler()
        normalized = scaler.fit_transform(x)
        model = MLPClassifier(**MODEL_PARAMS)
        started = time.perf_counter()
        model.fit(normalized, y)
        report['fit'] = dict(seconds=time.perf_counter()-started, epochs=model.n_iter_,
            examples=len(x), feature_count=x.shape[1], output_count=y.shape[1],
            final_loss=float(model.loss_), loss_curve=[float(v) for v in model.loss_curve_],
            held_out_used=False, fits=1)
        model_path = folders['bulk']/'frozen-spectrum-model.joblib'
        joblib.dump(dict(model=model, scaler=scaler, feature_names=extractor.names,
                         settings=SETTINGS, model_parameters=MODEL_PARAMS), model_path, compress=3)
        report['frozen_model'] = dict(sha256=digest(model_path), persisted_before_held_out_scoring=True,
                                    cutoff=SETTINGS['cutoff'])
        report['stage'] = 'frozen model; evaluate all source-disjoint mixtures'
        save_json(report_path, report)
        report['mixtures'] = {}
        for role in ('train', 'calibration', 'test'):
            if role != 'train':
                x, y, usage = role_examples(role, takes, waves, extractor, folders['bulk'])
                normalized = scaler.transform(x)
            probability = model.predict_proba(normalized)
            summary = classification_summary(probability, y)
            report['mixtures'][role] = dict(summary=summary, source_take_uses=usage,
                                            representation_gate=representation_gate(summary))
            np.savez_compressed(folders['bulk']/(role+'-predictions.npz'), probability=probability, targets=y)
            save_json(report_path, report)
        del waves, normalized, x, y
        report['stage'] = 'one continuous replay per recording with measured FIFO cost'
        save_json(report_path, report)
        report['datasets'] = {}
        for name, config in spec['datasets'].items():
            report['datasets'][name] = continuous_dataset(name, config,
                references['baseline']['datasets'][name], folders['inputs'], extractor, scaler, model, folders['bulk'])
            save_json(report_path, report)
        gates = {role+'_representation': report['mixtures'][role]['representation_gate']
                 for role in ('calibration', 'test')}
        gates['ordinary_gain_at_least_5pp'] = (report['datasets']['ordinary']['arms']['primary_fifo']
                                             ['comparison']['pitch_coverage_gain_pp'] >= 5)
        for name in report['datasets']:
            gates[name+'_no_pitch_safety_regression'] = report['datasets'][name]['arms']['primary_fifo']['comparison']['no_pitch_safety_regression']
        represented = gates['calibration_representation'] and gates['test_representation']
        report.update(state='completed', final=True, stage='one frozen fit and screen complete', gates=gates,
            representation_feasibility_passed=represented, research_screen_passed=all(gates.values()),
            decision=('exploratory pass; new-recording and implementation checks remain' if all(gates.values())
                else 'rejected as replacement; representation result reported separately'),
            limits=['Different takes of one instrument/session, not independent player/session data.',
                'Pass-3 target-pitch uncertainties retained; no relabeling or exclusion.',
                'RMS-normalized isolated sustain mixtures do not establish real chord attack/decay performance.',
                'Ordinary reuses training takes; only descriptive continuous stress evidence.',
                'No lane assignment, unison multiplicity, delivered MIDI, native allocation/deadline or device test.',
                'No tuning, rerun, installed change or promotion is authorized by a favorable research score.'])
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
