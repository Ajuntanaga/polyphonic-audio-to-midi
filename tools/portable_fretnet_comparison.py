"""One fixed, reference-checked FretNet comparison. GitHub Actions CPU only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import urllib.request

from tools.fretnet_comparison import (decode_tablature, evaluate, frame_windows,
                                     research_screen, tablature_spans)
from tools.pitch_detector_comparison import digest, read_labels
from tools.portable_basic_pitch_comparison import (captured_text, check_hash,
                                                  remote_only, save_json)


def download_pinned(asset, directory, repository, commit):
    remote_only()
    target = directory / asset['name']
    url = f'https://raw.githubusercontent.com/{repository}/{commit}/{asset["path"]}'
    if target.exists():
        raise ValueError('Asset already exists; this runner does not retry downloads')
    with urllib.request.urlopen(url, timeout=120) as response, target.open('xb') as stream:
        remaining = asset['bytes'] + 1
        while remaining:
            block = response.read(min(1024 * 1024, remaining))
            if not block:
                break
            stream.write(block)
            remaining -= len(block)
    payload = target.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
    if len(payload) != asset['bytes'] or actual != asset['git_blob_sha1']:
        raise ValueError('Pinned remote asset differs: ' + asset['name'])
    return target, dict(bytes=len(payload), git_blob_sha1=actual, sha256=digest(target), url=url)


class Backend:
    def __init__(self, model_path):
        remote_only()
        import numpy as np
        import librosa
        import onnxruntime as ort
        import soundfile as sf
        import torch
        self.np, self.librosa, self.sf, self.torch = np, librosa, sf, torch
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                            providers=['CPUExecutionProvider'])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        self.metadata = dict(numpy=np.__version__, librosa=librosa.__version__,
            onnxruntime=ort.__version__, torch=torch.__version__, soundfile=sf.__version__,
            providers=self.session.get_providers(),
            inputs=[dict(name=x.name, shape=x.shape, type=x.type) for x in inputs],
            outputs=[dict(name=x.name, shape=x.shape, type=x.type) for x in outputs])
        if (len(inputs) != 1 or inputs[0].name != 'feats'
                or inputs[0].type != 'tensor(float)' or len(inputs[0].shape) != 5
                or inputs[0].shape[2:] != [6, 144, 9]
                or {o.name for o in outputs} != {'tablature', 'tablature_rel', 'onsets'}
                or self.session.get_providers() != ['CPUExecutionProvider']):
            raise ValueError('Pinned ONNX interface differs: ' + json.dumps(self.metadata))

    def sigmoid(self, values):
        return self.torch.sigmoid(self.torch.from_numpy(self.np.ascontiguousarray(values))).numpy()

    def infer(self, features, chunk=128):
        np = self.np
        if (features.dtype != np.float32 or features.ndim != 5
                or features.shape[0] != 1 or features.shape[2:] != (6, 144, 9)
                or not np.isfinite(features).all() or features.shape[1] < 1):
            raise ValueError('Invalid ONNX input tensor')
        names = ['tablature', 'tablature_rel', 'onsets']
        parts = {name: [] for name in names}
        for start in range(0, features.shape[1], chunk):
            batch = np.ascontiguousarray(features[:, start:start + chunk])
            raw = self.session.run(names, {'feats': batch})
            for name, value, width in zip(names, raw, (126, 120, 120)):
                if (value.shape != (1, batch.shape[1], width) or value.dtype != np.float32
                        or not np.isfinite(value).all()):
                    raise ValueError('Invalid raw head: ' + name)
                parts[name].append(value)
        return {name: np.concatenate(values, axis=1) for name, values in parts.items()}

    def hcqt(self, audio):
        """amt-tools 7822dc2 HCQT/HVQT/VQT, gamma=0; each harmonic dB-normalized."""
        np, librosa = self.np, self.librosa
        if audio.ndim != 1 or audio.dtype != np.float32 or not np.isfinite(audio).all():
            raise ValueError('Expected normalized finite mono float32 audio')
        channels, counts = [], []
        for harmonic in (.5, 1, 2, 3, 4, 5):
            fmin = librosa.note_to_hz('E2') * harmonic
            fmax = max(librosa.cqt_frequencies(n_bins=144, fmin=fmin, bins_per_octave=36))
            constant_q = 1 / (2 ** (1 / 36) - 1)
            cutoff = fmax * (1 + .5 * librosa.filters.window_bandwidth('hann') / constant_q)
            early = getattr(librosa.core.constantq, '__early_downsample_count')(
                nyquist=22050 / 2, filter_cutoff=cutoff, hop_length=512, n_octaves=4)
            factors = 2 ** np.arange(early, early + 4)
            count = int(np.min(np.ceil(len(audio) / factors) // (512 // factors) + 1))
            counts.append(count)
            amplitude = np.abs(librosa.vqt(audio, sr=22050, hop_length=512,
                fmin=fmin, n_bins=144, bins_per_octave=36, gamma=0))
            channels.append(librosa.amplitude_to_db(amplitude, ref=np.max, top_db=80) / 80 + 1)
        count = min(counts)
        if any(c.shape[1] < count for c in channels):
            raise ValueError('VQT shorter than author expected-frame calculation')
        return np.stack([c[:, :count] for c in channels]).astype(np.float32), np.arange(count) * 512 / 22050

    def load_audio(self, path):
        audio, rate = self.librosa.load(str(path), sr=22050, mono=True,
                                        dtype=self.np.float32, res_type='kaiser_best')
        if rate != 22050 or not audio.size or not self.np.isfinite(audio).all():
            raise ValueError('Invalid resampled recording')
        rms = self.np.sqrt(self.np.mean(audio ** 2))
        if rms > 0:
            audio = audio / rms
        return audio


def numerical_check(actual, expected, *, atol=1e-4, rtol=1e-4):
    import numpy as np
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        return dict(passed=False, actual_shape=list(actual.shape), reference_shape=list(expected.shape))
    difference = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
    return dict(passed=bool(np.allclose(actual, expected, atol=atol, rtol=rtol)),
                max_abs=float(difference.max()), mean_abs=float(difference.mean()), atol=atol, rtol=rtol)


def reference_checks(backend, paths, pairs):
    remote_only()
    np, results = backend.np, {}
    for pair in pairs:
        with np.load(paths[pair['forward']], allow_pickle=False) as fixture, \
                np.load(paths[pair['frontend']], allow_pickle=False) as frontend:
            features = fixture['features']
            raw = backend.infer(features)
            gates = {name: numerical_check(raw[name], fixture[name]) for name in raw}
            expected_frets = decode_tablature(fixture['tablature'], backend.sigmoid)
            actual_frets = decode_tablature(raw['tablature'], backend.sigmoid)
            gates['decoded_positions'] = dict(passed=bool(np.array_equal(actual_frets, expected_frets)),
                mismatches=int(np.count_nonzero(actual_frets != expected_frets)))
            gates['window_preparation'] = numerical_check(frame_windows(frontend['hcqt']), features,
                                                         atol=0, rtol=0)
            calculated, times = backend.hcqt(frontend['audio'])
            count = frontend['hcqt'].shape[2]
            gates['frontend'] = numerical_check(calculated[:, :, :count], frontend['hcqt'])
            gates['nominal_times'] = numerical_check(times[:count], fixture['times'], atol=1e-6, rtol=0)
            # Check execution chunking against a single call before corpus use.
            whole = backend.infer(features, chunk=features.shape[1])
            gates['chunked_positions'] = dict(passed=bool(np.array_equal(
                actual_frets, decode_tablature(whole['tablature'], backend.sigmoid))))
            gates['chunked_logits'] = numerical_check(raw['tablature'], whole['tablature'])
            results[pair['name']] = dict(gates=gates, passed=all(g['passed'] for g in gates.values()),
                                         frames=int(features.shape[1]))
    return results


def measure(name, config, baseline, inputs, bulk, backend):
    remote_only()
    wav = inputs / 'corpus' / (name + '.wav')
    info = backend.sf.info(str(wav))
    clock = {key: config[key] for key in ('sample_count', 'sample_rate')}
    if info.frames != clock['sample_count'] or info.samplerate != clock['sample_rate']:
        raise ValueError('Recording clock mismatch: ' + name)
    start = time.perf_counter()
    audio = backend.load_audio(wav)
    hcqt, times = backend.hcqt(audio)
    frontend_seconds = time.perf_counter() - start
    start = time.perf_counter()
    arrays = backend.infer(frame_windows(hcqt))
    frets = decode_tablature(arrays['tablature'], backend.sigmoid)
    inference_seconds = time.perf_counter() - start
    spans = tablature_spans(frets, **clock)
    array_path = bulk / (name + '-outputs.npz')
    backend.np.savez_compressed(array_path, times=times, frets=frets, **arrays)
    span_path = bulk / (name + '-pitch-spans.json')
    save_json(span_path, dict(clock='offline nominal frame i*512/22050, no fitted offset',
        **clock, spans=spans, current_spans=baseline['pitch_spans']))
    # No annotation contents are read until all outputs for this recording exist.
    labels = read_labels(inputs / 'corpus' / (name + '.tsv'))
    result = evaluate(spans, labels, baseline, **clock)
    result.update(frames=int(frets.shape[1]), span_count=len(spans),
        frontend_wall_seconds=frontend_seconds, inference_decode_wall_seconds=inference_seconds,
        timing_scope='Offline whole-file frontend and nominal frame output; not causal delivery.',
        audio=dict(**clock, channels=info.channels),
        bulk={p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in (array_path, span_path)})
    return result


def run(spec_path, inputs, output):
    remote_only()  # Must precede all input/output access and optional imports.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk, assets = output / 'report', output / 'bulk', output / 'assets'
    for path in (report_dir, bulk, assets):
        path.mkdir()
    report_path = report_dir / 'report.json'
    report = dict(schema='m3_fretnet_comparison_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), datasets={},
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured')
    try:
        root = Path(__file__).resolve().parents[1]
        spec = json.loads(spec_path.read_text())
        source_sha = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if source_sha != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
            raise ValueError('Source/worker provenance differs from dispatch')
        if os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']:
            raise ValueError('Workflow input bundle pin differs')
        check_hash(inputs / 'recovery-inputs.json', spec['input_manifest_sha256'])
        baseline_path = root / spec['baseline_file']
        check_hash(baseline_path, spec['baseline_sha256'])
        baseline = json.loads(baseline_path.read_text())
        if set(spec['datasets']) != {'ordinary', 'extended-middle'} or set(baseline['datasets']) != set(spec['datasets']):
            raise ValueError('Unexpected protected recordings')
        for name, config in spec['datasets'].items():
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(inputs / 'corpus' / (name + '.' + ext), config[key])
            saved = baseline['datasets'][name]
            if (saved['labels_sha256'] != config['labels_sha256'] or any(
                    saved[k] != config['baseline'][k] for k in ('source_commit', 'raw_midi_sha256', 'run_id'))):
                raise ValueError('Saved baseline provenance differs: ' + name)
        report['provenance'] = dict(source_commit=source_sha, worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification_sha256=digest(spec_path),
            baseline_sha256=spec['baseline_sha256'], input_bundle_sha256=spec['input_bundle_sha256'],
            input_manifest_sha256=spec['input_manifest_sha256'], model=spec['model'],
            protocol=spec['protocol'], python=sys.version, platform=platform.platform())
        report['stage'] = 'pinned model and reference fixtures'
        save_json(report_path, report)
        paths, receipts = {}, {}
        for asset in spec['assets']:
            paths[asset['name']], receipts[asset['name']] = download_pinned(
                asset, assets, spec['model']['repository'], spec['model']['commit'])
        report['asset_receipts'] = receipts
        backend = Backend(paths['model.onnx'])
        report['backend'] = backend.metadata
        (report_dir / 'environment.txt').write_text(captured_text([sys.executable, '-m', 'pip', 'freeze', '--all']) + '\n')
        report['stage'] = 'reference identity before corpus'
        save_json(report_path, report)
        report['reference_checks'] = reference_checks(backend, paths, spec['reference_pairs'])
        save_json(report_path, report)
        if not all(row['passed'] for row in report['reference_checks'].values()):
            raise ValueError('Reference gate failed; no corpus inference is permitted')
        for name, config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path, report)
            report['datasets'][name] = measure(name, config, baseline['datasets'][name], inputs, bulk, backend)
            save_json(report_path, report)
        report['screen'] = research_screen(report['datasets'])
        report.update(state='completed', final=True, stage='both protected recordings scored',
            verdict=('PASSES_OFFLINE_PITCH_BUDGET_SCREEN' if report['screen']['arms']['fretnet']['budget_pass']
                     else 'REJECTED_OFFLINE_PITCH_SCREEN'))
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
    parser.add_argument('--output', type=Path, required=True)
    result = run(**vars(parser.parse_args()))
    print(json.dumps(dict(state=result['state'], screen=result['screen']), allow_nan=False))
