"""Synthetic mixed-level probe of the two pinned Basic Pitch graphs; GitHub Actions CPU only.

No recording, no corpus, no decoder, no policy and no fitting.  Each synthetic window (tools/mixed_level_probe.py) goes through the unmodified
pinned graph and through the same graph with the two normalization scalars added as outputs (Codex's rewrite_normalization with recent=False, which
changes no node, weight or initialiser); note/onset must agree between them or the decision verdicts are withheld.  Plan and registered
verdicts: docs/recovery/CLAUDE-M3-MIXED-LEVEL-PROPOSAL-20261122.md.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

import numpy as np

from tools.basic_pitch_recent_normalization import MINIMUM, RANGE, rewrite_normalization
from tools.mixed_level_probe import build_windows, identity, run_windows, windows_digest
from tools.pitch_detector_comparison import digest
from tools.portable_basic_pitch_comparison import remote_only, save_json
from tools.portable_basic_pitch_onnx_export import collect_reference
from tools.portable_basic_pitch_operator_profile import session

INPUT = 'serving_default_input_2:0'
NOTE = 'StatefulPartitionedCall:1'
ONSET = 'StatefulPartitionedCall:2'
FROZEN_PROBE = dict(
    floors=['zero', 'dither'], forms=['sustained', 'cut'], pitches=[52, 64, 76], levels=[-80, -70, -60, -50, -40, -30],
    deltas=[10, 20, 35], timings=['through', 'ended'], companion_cap=-10, companion_midi=43,
    reference_companion_levels=[-60, -40, -20, -10], dither_db=-96.0, noise_seed=20261122, readout_frames=[164, 165],
    cut_sample=41984, ended_sample=22050, window_samples=43844, sample_rate=22050, expected_windows=474)


def validate_spec(spec):
    if (spec['schema'] != 'm3_mixed_level_probe_spec_v1' or spec['probe'] != FROZEN_PROBE
            or spec['models'] != ['unmodified', 'adapted'] or spec['identity_tolerance'] != 1e-6
            or spec['onnxruntime_version'] != '1.20.1'
            or set(spec['reference_members']) != {'unmodified.onnx', 'adapted.onnx'}):
        raise ValueError('Frozen mixed-level probe specification differs')


def stats_runner(exposed):
    def run(samples):
        note, onset, minimum, range_ = exposed.run([NOTE, ONSET, MINIMUM, RANGE],
                                                   {INPUT: samples.reshape(1, 43844, 1).astype(np.float32, copy=False)})
        return note[0], onset[0], float(np.asarray(minimum).reshape(-1)[0]), float(np.asarray(range_).reshape(-1)[0])
    return run


def plain_runner(plain):
    def run(samples):
        note, onset = plain.run([NOTE, ONSET], {INPUT: samples.reshape(1, 43844, 1).astype(np.float32, copy=False)})
        return note[0], onset[0]
    return run


def check_interface(opened, outputs):
    inputs = opened.get_inputs()
    names = {o.name for o in opened.get_outputs()}
    if len(inputs) != 1 or inputs[0].name != INPUT or inputs[0].shape != [1, 43844, 1] or not set(outputs) <= names:
        raise ValueError('Pinned ONNX interface mismatch')


def run(spec_path, output):
    remote_only()
    spec = json.loads(spec_path.read_text())
    validate_spec(spec)
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA') or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']:
        raise ValueError('Dispatch/source mismatch')
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output / name for name in ('report', 'logs', 'cache', 'reference', 'bulk')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report'] / 'report.json'
    report = dict(schema='m3_mixed_level_probe_v1', state='running', final=False,
                  started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
                  worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                  run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification=spec,
                  specification_sha256=digest(spec_path), installed_output_changed=False, promotion_accepted=False,
                  models={})
    save_json(report_path, report)
    start = time.perf_counter()
    try:
        import onnx
        import onnxruntime as ort
        if ort.__version__ != spec['onnxruntime_version']:
            raise ValueError('ORT version differs')
        report['environment'] = dict(python=sys.version, platform=platform.platform(), numpy=np.__version__,
                                     onnx=onnx.__version__, onnxruntime=ort.__version__, intra_threads=2,
                                     inter_threads=1, graph_optimizations='disabled')
        references = collect_reference(spec, folders)
        report['reference_collection'] = dict(artifact=spec['artifact'], members=spec['reference_members'], verified=True)
        windows = build_windows(spec)
        if len(windows) != spec['probe']['expected_windows']:
            raise ValueError('Unexpected window count')
        report['window_count'] = len(windows)
        report['windows_digest'] = windows_digest(windows)
        save_json(report_path, report)
        for arm in spec['models']:
            report['stage'] = arm
            source_path = references[arm + '.onnx']
            exposed_path = folders['bulk'] / (arm + '-normalization-exposed.onnx')
            onnx.save_model(rewrite_normalization(onnx.load(str(source_path)), False), str(exposed_path))
            plain, exposed = session(source_path), session(exposed_path)
            check_interface(plain, [NOTE, ONSET])
            check_interface(exposed, [NOTE, ONSET, MINIMUM, RANGE])
            started = time.perf_counter()
            records = run_windows(windows, stats_runner(exposed), plain_runner(plain))
            report['models'][arm] = dict(
                model_sha256=digest(source_path), exposed_model_sha256=digest(exposed_path),
                identity=identity(records, spec['identity_tolerance']), windows=records,
                elapsed_seconds=time.perf_counter() - started)
            del plain, exposed
            save_json(report_path, report)
        report['state'] = 'complete'
        report['installed_output_changed'] = False
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], windows=result['window_count'],
                          identity={a: m['identity'] for a, m in result['models'].items()})))
