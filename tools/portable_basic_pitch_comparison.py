"""One pinned, default-setting Basic Pitch comparison; GitHub Actions only.

This is an offline detector comparison, not a production policy or latency test.
The baseline comes from saved MIDI; this runner never rebuilds or replays M3.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from tools.pitch_detector_comparison import compare, digest, model_spans, read_labels, score


def remote_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recorded-audio/model execution requires GitHub Actions')


def captured_text(command):
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    result.check_returncode()
    return result.stdout.strip()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def check_hash(path, expected):
    actual = digest(path)
    if actual != expected:
        raise ValueError(f'Input hash mismatch: {path.name}')
    return actual


class OnnxBackend:
    def __init__(self, model_path):
        remote_only()
        # These dependencies and all model/audio I/O stay behind the remote gate.
        import numpy as np
        import soundfile as sf
        import onnxruntime as ort
        from basic_pitch.inference import Model, predict

        self.np, self.sf, self.predict_function = np, sf, predict
        self.model = Model(model_path)
        if self.model.model_type != Model.MODEL_TYPES.ONNX:
            raise ValueError('Expected the pinned ONNX model backend')
        providers = self.model.model.get_providers()
        if providers != ['CPUExecutionProvider']:
            raise ValueError('Expected CPU-only inference')
        self.metadata = dict(onnxruntime_version=ort.__version__, providers=providers,
                             numpy_version=np.__version__, soundfile_version=sf.__version__)

    def audio_info(self, path):
        info = self.sf.info(str(path))
        return dict(sample_rate=info.samplerate, sample_count=info.frames,
                    channels=info.channels, subtype=info.subtype)

    def predict(self, path, settings):
        arrays, unused_midi, notes = self.predict_function(path, self.model, **settings)
        if set(arrays) != {'note', 'onset', 'contour'} or any(
                a.ndim != 2 or not a.size or not self.np.isfinite(a).all()
                for a in arrays.values()):
            raise ValueError('Incomplete or nonfinite model activations')
        return arrays, notes

    def save_arrays(self, path, arrays):
        self.np.savez_compressed(path, **arrays)
        return {key: dict(shape=list(value.shape), dtype=str(value.dtype))
                for key, value in arrays.items()}


def measure_dataset(name, config, baseline, inputs, bulk, prediction, backend):
    """Predict once, then load annotations and score; no quality-based retries."""
    remote_only()
    wav = inputs / 'corpus' / (name + '.wav')
    info = backend.audio_info(wav)
    clock = {key: config[key] for key in ('sample_count', 'sample_rate')}
    if any(info[key] != value for key, value in clock.items()):
        raise ValueError('Audio sample clock mismatch: ' + name)
    started = time.perf_counter()
    arrays, notes = backend.predict(wav, prediction)
    inference_seconds = time.perf_counter() - started
    spans, audit = model_spans(notes, **clock)
    # Validate before converting numpy scalars to JSON primitives. Keep all notes.
    raw_notes = [[float(s), float(e), int(p), float(a),
                  None if bends is None else [int(b) for b in bends]]
                 for s, e, p, a, bends in notes]
    note_path = bulk / (name + '-notes.json')
    save_json(note_path, dict(columns=['start_seconds', 'end_seconds', 'midi_note',
                                      'amplitude', 'pitch_bends'], events=raw_notes))
    array_path = bulk / (name + '-activations.npz')
    shapes = backend.save_arrays(array_path, arrays)
    # No label contents are used before this point.
    labels = read_labels(inputs / 'corpus' / (name + '.tsv'))
    measured = score(spans, labels, **clock)
    combined = score(baseline['pitch_spans'] + spans, labels, **clock)
    union_comparison = compare(baseline['measurement'], combined)
    union_diagnostic = dict(report_only=True, affects_research_screen=False,
        interpretation='Literal pitch-occupancy union of saved CURRENT and Basic Pitch; '
            'no annotation-based selection, timing adjustment or false-note removal. '
            'Diagnostic of complementarity only, not a deployable fusion policy. '
            'In comparison_to_saved_current, model means this union.',
        measurement=combined, comparison_to_saved_current=union_comparison,
        added_present_pitch_samples_over_saved_current=union_comparison['sample_deltas']['present_pitch_samples'],
        added_present_pitch_samples_over_basic_pitch=(combined['pitch_sets']['totals']['present_pitch_samples']
            - measured['pitch_sets']['totals']['present_pitch_samples']),
        promotion_accepted=False)
    return dict(audio=info, note_event_audit=audit, model=measured,
        baseline_run_id=baseline['run_id'], comparison=compare(baseline['measurement'], measured),
        report_only_union=union_diagnostic,
        inference_wall_seconds=inference_seconds,
        timing_scope='Whole-file offline inference/postprocessing; not real-time or end-to-end latency.',
        bulk={note_path.name: dict(sha256=digest(note_path), bytes=note_path.stat().st_size),
              array_path.name: dict(sha256=digest(array_path), bytes=array_path.stat().st_size,
                                   arrays=shapes)})


def research_screen(datasets):
    if set(datasets) != {'ordinary', 'extended-middle'}:
        raise ValueError('The fixed comparison requires both datasets')
    gain = datasets['ordinary']['comparison']['pitch_coverage_gain_pp']
    useful = gain is not None and gain >= 5.0
    safe = all(row['comparison']['no_pitch_safety_regression'] for row in datasets.values())
    return dict(useful_pitch_gain=useful, no_pitch_safety_regression=safe,
                research_screen_pass=useful and safe, promotion_accepted=False,
                interpretation='Offline research result only; string assignment, unisons, '
                    'raw retriggers, native deadlines, host delivery and live readiness unmeasured.')


def run(spec_path, inputs, model_checkout, output):
    remote_only()  # Before spec/input reads, output creation or dependency imports.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk = output / 'report', output / 'bulk'
    report_dir.mkdir()
    bulk.mkdir()
    report = dict(schema='m3_basic_pitch_comparison_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), datasets={},
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured')
    report_path = report_dir / 'report.json'
    try:
        spec = json.loads(spec_path.read_text())
        root = Path(__file__).resolve().parents[1]
        source_sha = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if source_sha != os.environ.get('SOURCE_SHA'):
            raise ValueError('Source checkout differs from pinned dispatch input')
        if os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Unexpected worker repository')
        model_sha = captured_text(['git', '-C', str(model_checkout), 'rev-parse', 'HEAD'])
        if model_sha != spec['model']['commit']:
            raise ValueError('Basic Pitch source revision mismatch')
        model_path = model_checkout / spec['model']['path']
        check_hash(model_path, spec['model']['sha256'])
        baseline_path = root / spec['baseline_file']
        check_hash(baseline_path, spec['baseline_sha256'])
        baseline = json.loads(baseline_path.read_text())
        check_hash(inputs / 'recovery-inputs.json', spec['input_manifest_sha256'])
        if os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']:
            raise ValueError('Workflow bundle pin differs from frozen protocol')
        if set(spec['datasets']) != {'ordinary', 'extended-middle'} or set(
                baseline['datasets']) != set(spec['datasets']):
            raise ValueError('Unexpected dataset selection')
        for name, config in spec['datasets'].items():
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(inputs / 'corpus' / (name + '.' + ext), config[key])
            reference = baseline['datasets'][name]
            if (reference['labels_sha256'] != config['labels_sha256']
                    or reference['raw_midi_sha256'] != config['baseline']['raw_midi_sha256']
                    or reference['source_commit'] != config['baseline']['source_commit']
                    or reference['run_id'] != config['baseline']['run_id']):
                raise ValueError('Baseline provenance mismatch: ' + name)
        report['provenance'] = dict(source_commit=source_sha,
            worker_commit=os.environ['GITHUB_SHA'], worker_repository=os.environ['GITHUB_REPOSITORY'],
            run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
            specification_sha256=digest(spec_path), baseline_sha256=spec['baseline_sha256'],
            input_release=spec['input_release'], input_bundle_sha256=spec['input_bundle_sha256'],
            bundle_verification='Workflow sha256sum before extraction',
            input_manifest_sha256=spec['input_manifest_sha256'], model=spec['model'],
            prediction=spec['prediction'], protocol=spec['protocol'], python=sys.version,
            platform=platform.platform())
        (report_dir / 'environment.txt').write_text(
            captured_text([sys.executable, '-m', 'pip', 'freeze', '--all']) + '\n')
        backend = OnnxBackend(model_path)
        report['backend'] = backend.metadata
        for name, config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path, report)
            report['datasets'][name] = measure_dataset(name, config, baseline['datasets'][name],
                inputs, bulk, spec['prediction'], backend)
            save_json(report_path, report)
        # A quality failure does not skip the negative-control dataset.
        report['screen'] = research_screen(report['datasets'])
        report.update(state='completed', stage='both datasets scored', final=True)
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
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--model-checkout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], screen=result['screen']), allow_nan=False))
