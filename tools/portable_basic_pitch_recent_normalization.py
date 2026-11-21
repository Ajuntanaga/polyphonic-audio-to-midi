"""One controlled model-window normalization screen, GitHub CPU only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys

from tools.basic_pitch_recent_normalization import (MINIMUM, RANGE, NORMALIZATION,
    assess, rewrite_normalization, stream_pair)
from tools.basic_pitch_streaming import SETTINGS, NS, ceil_div, timing_summary
from tools.neural_crop_model import export
from tools.pitch_detector_comparison import compare, digest, read_labels
from tools.portable_basic_pitch_bass_view import (REFERENCE_CROP_SHA, FRAME_COLUMNS,
    TIMING_COLUMNS, activation_identity, chunks, score_events)
from tools.portable_basic_pitch_cached_diagnosis import cached_arrays, fetch_artifact
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.portable_basic_pitch_streaming import StreamingBackend


class NormalizationBackend(StreamingBackend):
    def __init__(self, path):
        self.statistics = []
        super().__init__(path)
        self.statistics.clear()  # Exclude the inherited zero-window warmup.

    def predict(self, window):
        note, onset, minimum, width = self.session.run(
            ['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2', MINIMUM, RANGE],
            {'serving_default_input_2:0': window.reshape(1, 43844, 1).astype(self.np.float32, copy=False)})
        if minimum.shape != (1,) or width.shape != (1,):
            raise ValueError('Unexpected normalization statistics shape')
        values = float(minimum[0]), float(width[0])
        if not all(self.np.isfinite(v) for v in values) or values[1] < 0:
            raise ValueError('Invalid normalization statistics')
        self.statistics.append(values)
        return note[0], onset[0]


def normalization_summary(reference, candidate):
    import numpy as np
    a, b = np.asarray(reference), np.asarray(candidate)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 2 or not len(a):
        raise ValueError('Incomplete paired normalization statistics')
    def quantiles(values):
        return {key: float(value) for key, value in zip(('min', 'p50', 'p90', 'max'),
                np.quantile(values, [0, .5, .9, 1]))}
    nonzero = a[:, 1] > 0
    return dict(windows=len(a), minimum_changed_windows=int(np.count_nonzero(a[:, 0] != b[:, 0])),
        range_changed_windows=int(np.count_nonzero(a[:, 1] != b[:, 1])),
        reference_zero_range_windows=int(np.count_nonzero(~nonzero)),
        candidate_zero_range_windows=int(np.count_nonzero(b[:, 1] == 0)),
        candidate_minus_reference_minimum=quantiles(b[:, 0] - a[:, 0]),
        candidate_over_reference_range=quantiles(b[nonzero, 1] / a[nonzero, 1]) if nonzero.any() else None)


def measure(name, config, current, offline, inputs, bulk, cache, reference, candidate):
    remote_only()
    reference.statistics.clear(); candidate.statistics.clear()
    wav = inputs / 'corpus' / (name + '.wav')
    info = reference.sf.info(str(wav))
    if info.samplerate != 96000 or info.frames != config['sample_count']:
        raise ValueError('Recording clock mismatch')
    print(name + ': fixed normalization pair starting', flush=True)
    with reference.sf.SoundFile(str(wav)) as audio:
        result = stream_pair(chunks(audio), info.frames, reference, candidate,
            progress=lambda calls, count: print(f'{name}: windows={calls}, source={count}/{info.frames}', flush=True))
    cleanup = max(ceil_div(info.frames * NS, 96000), result['worker_finish_ns'])
    files = []
    for arm, backend in (('reference', reference), ('candidate', candidate)):
        row = result[arm]
        if not row['model_calls'] or len(backend.statistics) != row['model_calls']:
            raise ValueError('Missing model windows/statistics')
        path = bulk / (name + '-' + arm + '.npz')
        backend.np.savez_compressed(path, note=row['notes'], onset=row['onsets'],
            frames=backend.np.asarray(row['frames'], dtype='int64'),
            timing=backend.np.asarray(result['timing'], dtype='int64'),
            normalization=backend.np.asarray(backend.statistics, dtype='float64'))
        files.append(path)
        path = bulk / (name + '-' + arm + '-events.json')
        save_json(path, dict(events=row['events'], cleanup=dict(emitted_ns=cleanup, notes=row['open_decoder_pitches']),
            frame_columns=FRAME_COLUMNS, timing_columns=TIMING_COLUMNS,
            normalization_columns=['minimum_log_power', 'maximum_offset_log_power']))
        files.append(path)
    # Reference identity is a fail-closed prerequisite to any quality comparison.
    saved = cached_arrays(cache / (name + '-stream.npz'), stream=True)
    events = json.loads((cache / (name + '-events.json')).read_text())
    identity = activation_identity(result['reference'], dict(notes=saved['note'], onsets=saved['onset'],
        frames=saved['frames'], events=events['events'], open_decoder_pitches=events['cleanup']['notes']))
    # No annotations are exposed to either model/decoder; first value read is here.
    labels = read_labels(inputs / 'corpus' / (name + '.tsv'))
    clock = dict(sample_count=info.frames, sample_rate=96000)
    arms = {arm: score_events(result[arm]['events'], labels, clock) for arm in ('reference', 'candidate')}
    for row in arms.values():
        for clock_name, values in row.items():
            values['comparison_to_reference'] = compare(arms['reference'][clock_name]['measurement'], values['measurement'])
            values['comparison_to_current'] = compare(current['measurement'], values['measurement'])
            values['comparison_to_offline'] = compare(offline, values['measurement'])
    return dict(audio=dict(**clock, channels=info.channels), arms=arms, reference_identity=identity,
        normalization=normalization_summary(reference.statistics, candidate.statistics),
        timing=timing_summary(result['timing']), model_calls=result['reference']['model_calls'],
        source_samples_consumed=result['source_samples'], worker_finish_ns=result['worker_finish_ns'],
        cleanup_emitted_ns=cleanup,
        bulk={p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in files})


def run(spec_path, inputs, model_checkout, output):
    remote_only()  # Before recordings, model access or any output directory.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk, logs = (output / name for name in ('report', 'bulk', 'logs'))
    for path in (report_dir, bulk, logs): path.mkdir()
    report_path = report_dir / 'report.json'
    report = dict(schema='m3_basic_pitch_recent_normalization_v1', state='running', final=False,
        datasets={}, started_at=datetime.now(timezone.utc).isoformat(),
        promotion_accepted=False, installed_output_changed=False)
    try:
        spec = json.loads(spec_path.read_text())
        if spec['streaming'] != SETTINGS or spec['normalization'] != NORMALIZATION:
            raise ValueError('Implementation differs from frozen settings')
        root = Path(__file__).resolve().parents[1]
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Dispatch pin mismatch')
        if captured_text(['git', '-C', str(model_checkout), 'rev-parse', 'HEAD']) != spec['model']['commit']:
            raise ValueError('Model checkout pin mismatch')
        model = model_checkout / spec['model']['path']
        check_hash(model, spec['model']['sha256'])
        if os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']:
            raise ValueError('Input release pin mismatch')
        check_hash(inputs / 'recovery-inputs.json', spec['input_manifest_sha256'])
        baseline_path, offline_path = root / spec['baseline_file'], root / spec['offline_reference_file']
        check_hash(baseline_path, spec['baseline_sha256'])
        check_hash(offline_path, spec['offline_reference_sha256'])
        baseline, offline = json.loads(baseline_path.read_text()), json.loads(offline_path.read_text())
        if set(spec['datasets']) != {'ordinary', 'extended-middle'}:
            raise ValueError('Both fixed recordings required')
        for name, config in spec['datasets'].items():
            if config['sample_rate'] != 96000: raise ValueError('Only original96k clock is allowed')
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(inputs / 'corpus' / (name + '.' + ext), config[key])
            saved = baseline['datasets'][name]
            if (any(saved[k] != config['baseline'][k] for k in ('raw_midi_sha256', 'source_commit', 'run_id'))
                    or saved['labels_sha256'] != config['labels_sha256']):
                raise ValueError('CURRENT baseline provenance mismatch')
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
            specification_sha256=digest(spec_path), python=sys.version, platform=platform.platform())
        report['scope'] = dict(primary='One measured serial FIFO for both arms; includes both model calls',
            diagnostic='Same event sequence at source availability; not delivered MIDI',
            changed='Only time support of log-CQT minimum and maximum-offset reductions:172 to28 frames',
            timing_limit='Paired CPU service is not single-arm deployment timing',
            no_claims=['live latency', 'native allocation/deadline safety', 'host/device delivery',
                       'string/unison assignment', 'installed improvement'])
        (report_dir / 'environment.txt').write_text(captured_text([sys.executable, '-m', 'pip', 'freeze', '--all']) + '\n')
        cache = output / 'reference-cache'
        report['reference_artifact'] = fetch_artifact(spec['worker_repository'], spec['stream_reference_artifact'], cache, logs)
        models = output / 'models'; models.mkdir()
        cropped = models / 'readout164.onnx'
        report['reference_crop'] = export(model, cropped, report_dir / 'reference-crop.json')
        check_hash(cropped, REFERENCE_CROP_SHA)
        import onnx
        original = onnx.load(cropped)
        backends = {}
        for arm, recent in (('reference', False), ('candidate', True)):
            path = models / (arm + '.onnx')
            onnx.save_model(rewrite_normalization(original, recent), path)
            backends[arm] = NormalizationBackend(path)
            report[arm + '_model'] = dict(sha256=digest(path), bytes=path.stat().st_size,
                original_initializers_unchanged=True, unrelated_nodes_unchanged=True,
                normalization_support=NORMALIZATION[arm + '_time_range'],
                backend=backends[arm].metadata)
        for name, config in spec['datasets'].items():
            report['stage'] = name + ' paired pass'; save_json(report_path, report)
            report['datasets'][name] = measure(name, config, baseline['datasets'][name], offline['datasets'][name],
                inputs, bulk, cache, backends['reference'], backends['candidate'])
            save_json(report_path, report)
        report.update(state='completed', final=True, stage='Both reference identities passed; fixed screen scored',
                      screen=assess(report['datasets']))
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'inputs', 'model-checkout', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.inputs, args.model_checkout, args.output)
    print(json.dumps(dict(state=result['state'], screen=result['screen'])))


if __name__ == '__main__': main()
