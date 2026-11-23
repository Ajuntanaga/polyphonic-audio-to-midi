"""Pinned, standalone Soundshed causal comparison. GitHub Actions CPU only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import urllib.request

from tools.pitch_detector_comparison import digest, read_labels
from tools.portable_basic_pitch_comparison import captured_text, check_hash, remote_only, save_json
from tools.soundshed_comparison import evaluate, read_events, research_screen


def download_pinned(asset, directory, repository, commit):
    remote_only()
    relative = Path(asset['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid asset path')
    target = directory / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Asset already exists; no download retry')
    url = f'https://raw.githubusercontent.com/{repository}/{commit}/{asset["path"]}'
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
        raise ValueError('Pinned asset differs: ' + asset['path'])
    return dict(bytes=len(payload), git_blob_sha1=actual, sha256=digest(target), url=url)


def command(args, log, *, timeout=600):
    remote_only()
    # Capture output before inspecting exit state; retained even on build failure.
    completed = subprocess.run([str(x) for x in args], capture_output=True, text=True,
                               timeout=timeout, check=False)
    log.write_text(completed.stdout + '\nSTDERR:\n' + completed.stderr)
    completed.check_returncode()
    return completed.stdout


def build_and_check(root, upstream, output, report_dir):
    remote_only()
    shared = ['g++', '-std=c++20', '-O3', '-msse3', '-Wall', '-Wextra',
              '-I', upstream / 'core/src']
    sources = [upstream / 'core/src/dsp' / (name + '.cpp')
               for name in ('PolyNoteDetector', 'PolyNoteModel', 'PolySpectrum')]
    reference = output / 'upstream-tests'
    command(shared + ['-I', upstream / 'core/tests/helpers',
        upstream / 'core/tests/PolyNoteDetectorTests.cpp', *sources, '-o', reference],
        report_dir / 'compile-reference.log')
    stdout = command([reference], report_dir / 'upstream-tests.log')
    match = re.search(r'\b(\d+)/(\d+) checks passed\s*$', stdout)
    if not match or int(match[1]) != int(match[2]) or int(match[2]) == 0:
        raise ValueError('Unchanged upstream reference tests did not all pass')
    executable = output / 'soundshed-replay'
    command(shared + [root / 'tools/soundshed_replay.cpp', *sources, '-o', executable],
        report_dir / 'compile-replay.log')
    return executable, dict(passed=True, checks=int(match[2]),
        upstream_tests_unmodified=True, compiler=captured_text(['g++', '--version']),
        flags=['-std=c++20', '-O3', '-msse3', '-Wall', '-Wextra'],
        reference_sha256=digest(reference), replay_sha256=digest(executable))


def measure(name, config, baseline, inputs, output, executable):
    remote_only()
    import numpy as np
    import soundfile as sf
    bulk, report_dir = output / 'bulk', output / 'report'
    clock = {k: config[k] for k in ('sample_count', 'sample_rate')}
    wav = inputs / 'corpus' / (name + '.wav')
    info = sf.info(str(wav))
    if (info.frames != clock['sample_count'] or info.samplerate != clock['sample_rate']
            or info.channels != 1 or info.samplerate != 96000):
        raise ValueError('Pinned mono recording clock differs: ' + name)
    audio, rate = sf.read(str(wav), dtype='float32', always_2d=False)
    if audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError('Invalid recording samples')
    audio = np.asarray(audio * np.float32(10 ** (-9 / 20)), dtype='<f4')
    raw = output / (name + '-input.f32')
    audio.tofile(raw)
    del audio
    event_path, timing_path = bulk / (name + '-events.tsv'), bulk / (name + '-timing.json')
    started = time.perf_counter()
    try:
        command([executable, raw, rate, clock['sample_count'], 512, event_path, timing_path],
                report_dir / (name + '-replay.log'), timeout=600)
    finally:
        raw.unlink()  # Our temporary conversion only; never archive or alter the recording.
    wall = time.perf_counter() - started
    timing = json.loads(timing_path.read_text())
    spans, audit = read_events(event_path, **clock)
    if (timing['samples'] != clock['sample_count'] or timing['sample_rate'] != rate
            or timing['events'] != audit['source_event_count'] or timing['block'] != 512
            or timing['hop_samples'] != 512 or timing['detector_frames'] != clock['sample_count'] // 512):
        raise ValueError('Replay clock/event accounting differs')
    span_path = bulk / (name + '-pitch-spans.json')
    save_json(span_path, dict(**clock, clock=audit['clock'], spans=spans,
        current_spans=baseline['pitch_spans'], audit=audit))
    # The detector has exited and its outputs are saved before reading annotations.
    labels = read_labels(inputs / 'corpus' / (name + '.tsv'))
    result = evaluate(spans, labels, baseline, **clock)
    result.update(event_audit=audit, timing=timing, replay_wall_seconds=wall,
        audio=dict(**clock, channels=info.channels, input_trim_db=-9),
        bulk={p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
              for p in (event_path, timing_path, span_path)})
    return result


def run(spec_path, inputs, output):
    remote_only()  # Before all filesystem access, native work and optional imports.
    output.mkdir(parents=True, exist_ok=False)
    report_dir, bulk = output / 'report', output / 'bulk'
    report_dir.mkdir()
    bulk.mkdir()
    upstream = bulk / 'upstream'
    upstream.mkdir()
    report_path = report_dir / 'report.json'
    report = dict(schema='m3_soundshed_comparison_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), datasets={},
        installed_output_changed=False, promotion_accepted=False, live_readiness='not measured')
    try:
        root = Path(__file__).resolve().parents[1]
        spec = json.loads(spec_path.read_text())
        source = captured_text(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        if (source != os.environ.get('SOURCE_SHA')
                or os.environ.get('GITHUB_REPOSITORY') != spec['worker_repository']
                or os.environ.get('INPUT_SHA256') != spec['input_bundle_sha256']):
            raise ValueError('Source/worker/input provenance differs from dispatch')
        check_hash(inputs / 'recovery-inputs.json', spec['input_manifest_sha256'])
        baseline_path = root / spec['baseline_file']
        check_hash(baseline_path, spec['baseline_sha256'])
        baseline = json.loads(baseline_path.read_text())
        if set(spec['datasets']) != {'ordinary', 'extended-middle'} or set(baseline['datasets']) != set(spec['datasets']):
            raise ValueError('Both frozen protected recordings are required')
        for name, config in spec['datasets'].items():
            for ext, key in (('wav', 'wav_sha256'), ('tsv', 'labels_sha256')):
                check_hash(inputs / 'corpus' / (name + '.' + ext), config[key])
            saved = baseline['datasets'][name]
            if (saved['labels_sha256'] != config['labels_sha256'] or any(
                    saved[k] != config['baseline'][k] for k in ('source_commit', 'raw_midi_sha256', 'run_id'))):
                raise ValueError('Saved CURRENT provenance differs: ' + name)
        report['provenance'] = dict(source_commit=source, worker_commit=os.environ['GITHUB_SHA'],
            worker_repository=os.environ['GITHUB_REPOSITORY'], run_id=os.environ['GITHUB_RUN_ID'],
            run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], specification_sha256=digest(spec_path),
            baseline_sha256=spec['baseline_sha256'], input_bundle_sha256=spec['input_bundle_sha256'],
            input_manifest_sha256=spec['input_manifest_sha256'], model=spec['model'],
            protocol=spec['protocol'], python=sys.version, platform=platform.platform())
        report['stage'] = 'pinned upstream source and weights'
        save_json(report_path, report)
        receipts = {}
        for asset in spec['assets']:
            receipts[asset['path']] = download_pinned(asset, upstream,
                spec['model']['repository'], spec['model']['commit'])
        report['asset_receipts'] = receipts
        save_json(bulk / 'asset-receipts.json', receipts)
        (report_dir / 'environment.txt').write_text(captured_text([sys.executable, '-m', 'pip', 'freeze', '--all']) + '\n')
        report['stage'] = 'unchanged upstream native tests before corpus'
        save_json(report_path, report)
        executable, report['reference_checks'] = build_and_check(root, upstream, output, report_dir)
        for name, config in spec['datasets'].items():
            report['stage'] = name
            save_json(report_path, report)
            report['datasets'][name] = measure(name, config, baseline['datasets'][name], inputs, output, executable)
            save_json(report_path, report)
        report['screen'] = research_screen(report['datasets'])
        report.update(state='completed', final=True, stage='both protected recordings scored',
            verdict=('PASSES_CAUSAL_PITCH_BUDGET_SCREEN'
                     if report['screen']['arms']['range_preserving']['budget_pass']
                     else 'REJECTED_CAUSAL_PITCH_SCREEN'))
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_or_updated_at'] = datetime.now(timezone.utc).isoformat()
        save_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.spec, args.inputs, args.output)


if __name__ == '__main__':
    main()
