#!/usr/bin/env python3
"""Build and measure bounded partial-motion diagnostics on Modal.

Uploads source only. Reuses the existing protected audio volume; it does not
change the installed plugin or infer a string count from mixture motion.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone

import modal

ROOT = Path(__file__).resolve().parents[1]
MOUNT = Path('/mnt/m3')
app = modal.App('m3-partial-motion-capture')
volume = modal.Volume.from_name('m3-protected-replay-data')
image = (modal.Image.from_registry('ubuntu:24.04', add_python='3.12')
         .apt_install('g++', 'cmake')
         .pip_install('numpy<3')
         .env({'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'})
         .add_local_dir(ROOT / 'native', '/opt/m3/native', copy=True)
         .add_local_file(ROOT / 'CMakeLists.txt', '/opt/m3/project.cmake', copy=True)
         .add_local_file(ROOT / 'tools/partial_motion_evidence.py',
                         '/opt/m3/partial_motion_evidence.py', copy=True))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def wave_duration(path):
    """Read only the RIFF header; PCM and float/extensible have the same clock."""
    rate = align = size = None
    with Path(path).open('rb') as stream:
        header = stream.read(12)
        if header[:4] != b'RIFF' or header[8:] != b'WAVE':
            raise ValueError('expected RIFF WAVE')
        while chunk := stream.read(8):
            kind, length = struct.unpack('<4sI', chunk)
            if kind == b'fmt ':
                fmt = stream.read(length)
                _, _, rate, _, align, _ = struct.unpack('<HHIIHH', fmt[:16])
            elif kind == b'data':
                size = length
                stream.seek(length, 1)
            else:
                stream.seek(length, 1)
            stream.seek(length & 1, 1)
    if not rate or not align or size is None:
        raise ValueError('missing wave clock')
    return rate, size / align / rate


def build(out):
    source = Path('/opt/m3')
    text = (source / 'project.cmake').read_text()
    core = re.search(r'set\(M3_NATIVE_CORE_SOURCES\s+(.*?)\)', text, re.S)
    if not core:
        raise ValueError('native core source list missing')
    sources = core.group(1).split() + [
        'native/offline/frequency_refinement_shadow.cpp',
        'native/offline/joint_pitch_residual.cpp', 'native/offline/replay.cpp',
        'native/offline/unison_spectral_shadow.cpp']
    (source / 'motion_test_main.cpp').write_text(
        '#include "test_support.hpp"\nint main(){return m3::test::run_all_tests();}\n')
    (source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.20)
project(m3_motion LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
add_compile_definitions(M3_OFFLINE_REPLAY_DIAGNOSTICS=1 M3_SPECTRAL_TIER_DIAGNOSTICS=1
 M3_UNISON_SPECTRAL_SHADOW=1 M3_JOINT_RESIDUAL_SHADOW=1)
add_compile_options(-O2 -DNDEBUG -Wall -Wextra -Wpedantic -Wconversion -Wshadow
 -Werror -fno-exceptions -fno-rtti -fstack-protector-strong -fvisibility=hidden)
include_directories(native/include native/offline native/tests)
add_library(core STATIC ''' + ' '.join(sources) + ''')
add_executable(m3_replay native/offline/replay_main.cpp)
target_link_libraries(m3_replay PRIVATE core pthread m)
add_executable(m3_motion_tests native/tests/test_offline_replay.cpp
 native/tests/test_support.cpp motion_test_main.cpp)
target_link_libraries(m3_motion_tests PRIVATE core pthread m)
''')
    directory = Path('/tmp/m3-motion-build')
    with (out / 'build.log').open('w') as log:
        subprocess.run(['cmake', '-S', str(source), '-B', str(directory)],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        subprocess.run(['cmake', '--build', str(directory), '-j2'],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    return directory


def aggregate(path):
    csv.field_size_limit(8 * 1024 * 1024)
    with path.open() as stream:
        row = next(csv.DictReader(stream, delimiter='\t'))
    keys = ('fingerprint', 'labeled', 'matched', 'false_gap_voices',
            'false_wrong_note_voices', 'false_wrong_string_voices',
            'false_positive_voices')
    return {key: row[key] for key in keys}


def measure(trace, label_file, note):
    import sys
    sys.path.insert(0, '/opt/m3')
    import numpy as np
    from partial_motion_evidence import summarize_motion
    with trace.open() as stream:
        header = json.loads(next(stream))
        rows = [json.loads(line) for line in stream]
    samples = np.array([row['sample'] for row in rows])
    times = samples / header['sample_rate']
    signal = np.array([np.array(row['real']) + 1j * np.array(row['imaginary'])
                       for row in rows]).T
    posterior = np.array([row['posterior'] for row in rows])
    with label_file.open() as stream:
        labels = list(csv.DictReader(stream, delimiter='\t'))
    spans = []
    for index, label in enumerate(labels):
        if int(label['midi_note']) != note:
            continue
        start, end = int(label['start_sample']), int(label['end_sample'])
        # Complete causal three-second windows within each annotated pluck.
        width = int(3 * header['sample_rate'])
        for stop in range(start + width, end + 1, width):
            chosen = (samples >= stop - width) & (samples < stop)
            if chosen.sum() < 3:
                continue
            features = summarize_motion(times[chosen], signal[:, chosen],
                                        rows[0]['frequency_hz'][0])
            features.update({'annotation_index': index,
                             'start_sample': stop - width, 'end_sample': stop,
                             'expected_mask': int(label['string_mask']),
                             'cached_posterior_mean': posterior[chosen].mean(axis=0).tolist(),
                             'active_frames': sum(row['active'] for row, keep in zip(rows, chosen) if keep)})
            spans.append(features)
    return {'header': header, 'frames': len(rows),
            'first_sample': int(samples[0]), 'last_sample': int(samples[-1]),
            'windows': spans, 'classifier_gain': 'not measured',
            'independent_held_out_take': False}


def synthetic(out):
    import numpy as np
    import wave
    rate, duration, note = 48000, 8.0, 40
    t = np.arange(int(rate * duration)) / rate
    f0 = 440 * 2 ** ((note - 69) / 12)
    definitions = {
        'single-am': ([0.0], [0.5], 'am', 1),
        'single-two-decays': ([0.0], [0.5], 'two-decays', 1),
        'pair-simultaneous': ([-4.0, 3.0], [0.5, 0.5], 'decay', 3),
        'triple-staggered': ([-4.0, 0.0, 3.0], [0.5, 1.0, 1.5], 'decay', 7),
    }
    cases = []
    for name, (cents, onsets, envelope, mask) in definitions.items():
        audio = np.zeros_like(t)
        for voice, (detune, onset) in enumerate(zip(cents, onsets)):
            age = np.maximum(0, t - onset)
            gain = np.exp(-0.35 * age)
            if envelope == 'am':
                gain *= 1 + 0.35 * np.sin(2 * np.pi * 3.2 * age)
            if envelope == 'two-decays':
                gain = 0.6 * np.exp(-2.5 * age) + 0.4 * np.exp(-0.3 * age)
            for h in range(1, 7):
                audio += (0.12 / len(cents) / h * gain * (t >= onset) *
                          np.sin(2 * np.pi * f0 * 2 ** (detune / 1200) * h * age
                                 + 0.37 * voice * h))
        wav, labels = out / f'{name}.wav', out / f'{name}.tsv'
        with wave.open(str(wav), 'wb') as stream:
            stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes(np.round(audio * 32767).astype('<i2').tobytes())
        labels.write_text('start_sample\tend_sample\tmidi_note\tstring_mask\n'
                          f'{int(max(onsets) * rate)}\t{len(t)}\t{note}\t{mask}\n')
        cases.append((name, wav, labels, note, False))
    return cases


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2.0,
              memory=4096, timeout=3600, max_containers=1)
def capture(run_id: str):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id):
        raise ValueError('invalid run identifier')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = {'run_id': run_id, 'state': 'running', 'final': False,
              'installed_changed': False, 'datasets': {}, 'stage': 'build',
              'started_at': datetime.now(timezone.utc).isoformat()}

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    try:
        files = sorted(Path('/opt/m3/native').rglob('*'))
        report['source_files_sha256'] = {str(p.relative_to('/opt/m3')): sha256(p)
                                         for p in files if p.is_file()}
        report['measurement_module_sha256'] = sha256('/opt/m3/partial_motion_evidence.py')
        save()
        directory = build(out)
        report['binary_sha256'] = sha256(directory / 'm3_replay')
        report['stage'] = 'causal native tests'
        save()
        for name, test_filter in (('motion', 'offline_partial_motion'), ('offline', 'offline_')):
            with (out / f'{name}-tests.log').open('w') as log:
                subprocess.run([str(directory / 'm3_motion_tests')], check=True,
                               env={**os.environ, 'M3_TEST_FILTER': test_filter},
                               stdout=log, stderr=subprocess.STDOUT, timeout=600)
            report[f'{name}_tests'] = (out / f'{name}-tests.log').read_text().splitlines()[-1]
        save()
        cases = [('physical-long', MOUNT / 'corpus/physical-long.wav',
                  MOUNT / 'corpus/physical-long.tsv', 40, True),
                 ('isolated-08', MOUNT / 'corpus/isolated-08.wav',
                  MOUNT / 'corpus/isolated-08.tsv', 40, True)] + synthetic(out)
        calibration = MOUNT / 'corpus/calibration.m3cb'
        settings = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
                    'max-polyphony': 5, 'max-fret': 24}
        settings_hash = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        for name, wav, labels, note, real_audio in cases:
            report['stage'] = f'capture {name}'
            save()
            rate, duration = wave_duration(wav)
            # Full recording capture, or fail explicitly rather than silently clip.
            if duration * rate / 64 > 90000:
                raise ValueError(f'{name}: recording exceeds bounded capture')
            base = [str(directory / 'm3_replay'), '--wav', str(wav),
                    '--labels', str(labels), '--calibration', str(calibration)]
            for key, value in settings.items():
                base += ['--' + key, str(value)]
            baseline_path = out / f'{name}-baseline.tsv'
            with baseline_path.open('w') as stdout, (out / f'{name}-replay.log').open('w') as log:
                subprocess.run(base + ['--block', '512'], stdout=stdout, stderr=log,
                               check=True, timeout=360)
            baseline = aggregate(baseline_path)
            result = {'baseline': baseline, 'replays': {}, 'all_outputs_identical': True,
                      'all_traces_identical': True, 'audio_duration_seconds': duration,
                      'source_identity': name, 'take_identity': name + ':original-recording'
                          if real_audio else name + ':controlled-generator'}
            reference_hash = None
            for block in ((32, 512, 1024) if real_audio else (512,)):
                trace = out / f'{name}-{block}.jsonl'
                replay = out / f'{name}-{block}.tsv'
                command = base + ['--block', str(block), '--partial-motion-trace', str(trace),
                                  '--partial-motion-note', str(note),
                                  '--partial-motion-start', '0',
                                  '--partial-motion-end', str(duration)]
                with replay.open('w') as stdout, (out / f'{name}-replay.log').open('a') as log:
                    subprocess.run(command, stdout=stdout, stderr=log, check=True, timeout=360)
                current, trace_hash = aggregate(replay), sha256(trace)
                result['replays'][str(block)] = current
                result['all_outputs_identical'] &= current == baseline
                result['all_traces_identical'] &= reference_hash in (None, trace_hash)
                if reference_hash is None:
                    reference_hash = trace_hash
                    result['measurement'] = measure(trace, labels, note)
                    result['provenance'] = {
                        'audio_sha256': sha256(wav), 'labels_sha256': sha256(labels),
                        'calibration_sha256': sha256(calibration),
                        'settings': settings, 'settings_sha256': settings_hash,
                        'sample_rate': rate, 'sample_origin': 0, 'note': note,
                        'trace_sha256': trace_hash,
                        'posterior_join': 'same observation row, no cross-file interpolation'}
                    with trace.open('rb') as src, gzip.open(out / f'{name}.jsonl.gz', 'wb',
                                                           compresslevel=1) as dest:
                        shutil.copyfileobj(src, dest)
                trace.unlink()
            report['datasets'][name] = result
            save()
            if not result['all_outputs_identical'] or not result['all_traces_identical']:
                raise ValueError(f'{name}: diagnostic parity failed')
        report.update(state='completed', stage='measured capture complete', final=True,
                      conclusion='Capture only; conditional classifier gain is not measured.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        for log in ('build.log', 'motion-tests.log', 'offline-tests.log'):
            path = out / log
            if path.exists():
                report[log + '_tail'] = path.read_text()[-12000:]
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=1.0,
              memory=2048, timeout=1200, max_containers=1)
def analyze_saved_capture(run_id: str, source_run: str):
    """Condition existing observations only: no build, audio replay or sweep."""
    import sys
    import numpy as np
    sys.path.insert(0, '/opt/m3')
    from partial_motion_evidence import (
        condition_mixture_tracks, summarize_motion, trajectories,
    )
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value)
           for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    prior = json.loads((source / 'report.json').read_text())
    if prior['state'] != 'completed' or not prior['final']:
        raise ValueError('source capture is not complete')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = {
        'run_id': run_id, 'source_run': source_run, 'state': 'running',
        'final': False, 'installed_changed': False, 'datasets': {},
        'source_report_sha256': sha256(source / 'report.json'),
        'measurement_module_sha256': sha256('/opt/m3/partial_motion_evidence.py'),
        'conditioning': {'stages': 2, 'time_constant_seconds': 0.015,
                         'selection': 'fixed production phasor reference; not tuned',
                         'warmup': 'full captured prefix; never reset at annotation'},
        'started_at': datetime.now(timezone.utc).isoformat(),
    }

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    try:
        for name, previous in prior['datasets'].items():
            report['stage'] = f'condition saved {name}'
            save()
            if not previous['all_outputs_identical'] or not previous['all_traces_identical']:
                raise ValueError(f'{name}: source diagnostic parity failed')
            digest = hashlib.sha256()
            rows = []
            with gzip.open(source / f'{name}.jsonl.gz', 'rb') as stream:
                header_line = next(stream)
                digest.update(header_line)
                header = json.loads(header_line)
                for line in stream:
                    digest.update(line)
                    rows.append(json.loads(line))
            if digest.hexdigest() != previous['provenance']['trace_sha256']:
                raise ValueError(f'{name}: saved trace hash mismatch')
            samples = np.array([row['sample'] for row in rows])
            times = samples / header['sample_rate']
            signal = np.array([np.array(row['real']) + 1j * np.array(row['imaginary'])
                               for row in rows]).T
            center = rows[0]['frequency_hz'][0]
            centers = rows[0]['frequency_hz']
            del rows
            conditioned = condition_mixture_tracks(
                times, signal, observation_period=64 / header['sample_rate'])
            windows = []
            for earlier in previous['measurement']['windows']:
                chosen = ((samples >= earlier['start_sample'])
                          & (samples < earlier['end_sample']))
                features = summarize_motion(times[chosen], conditioned[:, chosen], center)
                windows.append({
                    'start_sample': earlier['start_sample'],
                    'end_sample': earlier['end_sample'],
                    'expected_mask': earlier['expected_mask'],
                    'raw': {'pairs': earlier['pairs'],
                            'valid_increment_counts': earlier['valid_increment_counts']},
                    'conditioned': features,
                })
            result = {'frames': len(samples), 'sample_rate': header['sample_rate'],
                      'demodulation_centers_hz': centers, 'windows': windows,
                      'classifier_gain': 'not measured'}
            if name in ('single-am', 'single-two-decays'):
                controls = {}
                for mode, values in (('raw', signal), ('conditioned', conditioned)):
                    track = trajectories(times, values, center)
                    # One second after the known synthetic attack, not a
                    # label-derived input to the feature or conditioner.
                    steady = track['increment_times'] >= 1.5
                    measured = track['cents'][:, steady]
                    rms, dominant = [], []
                    for band in measured:
                        valid = np.isfinite(band)
                        rms.append(float(np.sqrt(np.mean(band[valid] ** 2)))
                                   if valid.any() else None)
                        if valid.all() and len(band) > 2:
                            power = np.abs(np.fft.rfft(band - np.mean(band))) ** 2
                            frequencies = np.fft.rfftfreq(len(band), 64 / header['sample_rate'])
                            dominant.append(float(frequencies[1 + np.argmax(power[1:])]))
                        else:
                            dominant.append(None)
                    controls[mode] = {
                        'expected_frequency_cents': 0.0,
                        'rms_frequency_error_cents_by_harmonic': rms,
                        'dominant_frequency_error_modulation_hz': dominant,
                    }
                result['known_single_source_control'] = controls
            report['datasets'][name] = result
            save()
        report.update(state='completed', final=True, stage='saved capture analysis complete',
                      conclusion='Measurement conditioning only; source count and classifier gain remain unmeasured.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
    save()
    return report


@app.local_entrypoint()
def main(run_id: str, source_run: str = ''):
    result = (analyze_saved_capture.remote(run_id, source_run)
              if source_run else capture.remote(run_id))
    target = ROOT / 'build/modal' / f'{run_id}.json'
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'state': result['state'], 'report': str(target),
                      'stage': result['stage'], 'final': result['final']}))
    if result['state'] != 'completed':
        raise SystemExit(1)
