"""Synthetic release probe on the corrected original and adapted ONNX graphs; GitHub Actions CPU only.

Plan and predictions: docs/recovery/CLAUDE-M3-RELEASE-PROBE-PROPOSAL-20261122.md; exact treatments:
docs/recovery/CLAUDE-M3-RELEASE-PROBE-TREATMENTS-20261122.md.  One window per synthetic signal, no recordings, no streaming, no fit.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from tools import basic_pitch_release_probe as probe
from tools.basic_pitch_streaming import SETTINGS

INPUT = 'serving_default_input_2:0'
OUTPUTS = ('StatefulPartitionedCall:1', 'StatefulPartitionedCall:2')
MODELS = ('unmodified', 'adapted')


def remote_only():
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Model execution requires GitHub Actions')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def find_model(root, name):
    matches = sorted(Path(root).rglob(name + '.onnx'))
    if len(matches) != 1:
        raise ValueError('Expected exactly one %s.onnx under the evidence directory, found %d' % (name, len(matches)))
    return matches[0]


class Backend:
    def __init__(self, path):
        remote_only()
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = SETTINGS['intra_op_threads']
        options.inter_op_num_threads = SETTINGS['inter_op_threads']
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
        if self.session.get_providers() != ['CPUExecutionProvider']:
            raise ValueError('CPU-only session required')
        inputs = self.session.get_inputs()
        outputs = {r.name for r in self.session.get_outputs()}
        if len(inputs) != 1 or inputs[0].name != INPUT or not set(OUTPUTS) <= outputs:
            raise ValueError('Pinned ONNX interface mismatch')
        self.version = ort.__version__

    def predict(self, window):
        if window.shape != (SETTINGS['model_samples'],) or window.dtype != np.float32:
            raise ValueError('Window must be float32 of the model length')
        note, onset = self.session.run(list(OUTPUTS), {INPUT: window.reshape(1, -1, 1)})
        return note[0], onset[0]


def signals():
    """(key, midi or None, case key, signal) for every probe input, in a fixed order."""
    for midi in probe.PITCHES:
        for key, kind, tau in probe.all_cases():
            if kind != 'silence':
                yield ('%d_%s' % (midi, key), midi, key, tau, probe.render(midi, kind, tau))
    yield ('silence', None, 'silence', None, probe.render(0, 'silence'))


def run(spec_path, evidence, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    if spec['signal'] != probe_description():
        raise ValueError('Frozen probe description differs')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk_dir = output / 'report', output / 'bulk'
    report_dir.mkdir()
    bulk_dir.mkdir()
    report_path = report_dir / 'report.json'
    report = dict(schema='m3_basic_pitch_release_probe_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
        run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
        specification_sha256=digest(spec_path), installed_output_changed=False, promotion_accepted=False,
        live_readiness='not measured')
    save_json(report_path, report)
    start = time.perf_counter()
    try:
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__)
        backends, hashes = {}, {}
        for name in MODELS:
            path = find_model(evidence, name)
            hashes[name] = digest(path)
            if hashes[name] != spec['models'][name]['sha256']:
                raise ValueError('Model hash mismatch: ' + name)
            backends[name] = Backend(path)
        report['environment']['onnxruntime'] = backends[MODELS[0]].version
        report['model_hashes'] = hashes
        report['stage'] = 'inference'
        save_json(report_path, report)
        arrays = {name: {} for name in MODELS}
        results = {name: {} for name in MODELS}
        controls = {name: {} for name in MODELS}
        for label, midi, case, tau, signal in signals():
            for name in MODELS:
                note, onset = backends[name].predict(signal)
                if note.shape != (SETTINGS['model_frames'], SETTINGS['model_pitches']) or not np.all(np.isfinite(note)):
                    raise ValueError('Unexpected note output for %s %s' % (name, label))
                arrays[name][label + '_note'] = note.astype(np.float32)
                arrays[name][label + '_onset'] = onset.astype(np.float32)
                if midi is None:
                    controls[name]['silence_note_max'] = float(note.max())
                    controls[name]['silence_onset_max'] = float(onset.max())
                elif case == 'sustained':
                    controls[name].setdefault('sustained', {})[str(midi)] = dict(
                        active_at_end=bool(np.all(note[-4:, midi - SETTINGS['first_midi_note']] >= SETTINGS['frame_threshold'])),
                        note_at_end=float(note[-1, midi - SETTINGS['first_midi_note']]))
                else:
                    results[name].setdefault(case, {})[midi] = probe.measure(note, midi, tau)
        for name in MODELS:
            np.savez_compressed(bulk_dir / (name + '-outputs.npz'), **arrays[name])
        report['measurements'] = {name: {case: {str(m): row for m, row in rows.items()} for case, rows in results[name].items()}
                                  for name in MODELS}
        report['controls'] = controls
        report['verdicts'] = probe.verdicts(results)
        report['interpretation'] = ('Synthetic controlled contrast on the corrected original and epoch-2 graphs. Not guitar audio, not a gate, '
            'not a fit choice; a tail past a label end can be real ring-out. Predictions P0-P3 are judged exactly as registered.')
        report['state'] = 'complete'
        return report
    except Exception as error:
        report['state'] = 'failed'
        report['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        report['final'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['elapsed_seconds'] = time.perf_counter() - start
        report['peak_resident_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        save_json(report_path, report)


def probe_description():
    """The frozen signal parameters, compared with the spec so neither can drift alone."""
    return dict(onset=probe.ONSET, end=probe.END, taper=probe.TAPER, steady_rms=probe.STEADY_RMS, harmonics=probe.HARMONICS,
                pitches=list(probe.PITCHES), taus=list(probe.TAUS), active_frames=list(probe.ACTIVE_FRAMES),
                threshold=probe.THRESHOLD, frames=probe.FRAMES, samples=probe.SAMPLES, rate=probe.RATE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.spec, args.evidence, args.output)
    print(json.dumps(dict(state=result['state'], verdicts={k: v['verdict'] for k, v in result['verdicts'].items()})))
