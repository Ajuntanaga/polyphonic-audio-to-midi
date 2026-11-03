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
                         '/opt/m3/partial_motion_evidence.py', copy=True)
         .add_local_file(ROOT / 'tools/string_evidence_audit.py',
                         '/opt/m3/string_evidence_audit.py', copy=True))
OVERLAP_MODULES = ('controlled_descriptor_overlap', 'string_likelihood_decomposition',
                   'string_observation_shadow', 'string_evidence_audit',
                   'controlled_admission_gate')
for module in OVERLAP_MODULES:
    image = image.add_local_file(ROOT / 'tools' / (module + '.py'),
                                 '/opt/m3/tools/' + module + '.py', copy=True)
image = image.add_local_file(ROOT / 'tools/selection_trace_diagnosis.py',
                             '/opt/m3/tools/selection_trace_diagnosis.py', copy=True)


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


def build(out, detector_tests=False):
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
''' + ('''
add_compile_definitions(M3_TESTING=1)
add_executable(m3_detector_tests native/tests/test_polyphonic_pitch_detector.cpp
 native/tests/test_support.cpp motion_test_main.cpp)
target_link_libraries(m3_detector_tests PRIVATE core pthread m)
''' if detector_tests else ''))
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
        condition_mixture_tracks, phase_window_trajectories, summarize_motion,
        summarize_phase_windows, summarize_reference_quality, trajectories,
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
        'phase_window': {'seconds': 0.160, 'emission_period_seconds': 0.160,
                         'selection': 'fixed phase-evidence timescale; not tuned',
                         'causality': 'complete past window; no annotation resets',
                         'minimum_motion_observations': 12},
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
            if any(row['frequency_hz'] != centers for row in rows):
                raise ValueError(f'{name}: harmonic configuration changed during capture')
            enabled_bands = np.asarray(centers) > 0
            detector_active = np.asarray([row['active'] for row in rows], dtype=bool)
            detector_phase_valid = np.asarray([row['phase_valid'] for row in rows], dtype=bool)
            del rows
            conditioned = condition_mixture_tracks(
                times, signal, observation_period=64 / header['sample_rate'])
            phase_track = phase_window_trajectories(times, conditioned, center)
            raw_increments = trajectories(times, signal, center)
            conditioned_increments = trajectories(times, conditioned, center)
            raw_windows = phase_window_trajectories(times, signal, center)
            labels_path = ((MOUNT / 'corpus' / f'{name}.tsv')
                           if name in ('physical-long', 'isolated-08')
                           else source / f'{name}.tsv')
            if sha256(labels_path) != previous['provenance']['labels_sha256']:
                raise ValueError(f'{name}: source annotation hash mismatch')
            short_spans = []
            quality_spans = []
            with labels_path.open() as stream:
                for index, label in enumerate(csv.DictReader(stream, delimiter='\t')):
                    if int(label['midi_note']) != previous['provenance']['note']:
                        continue
                    start, end = int(label['start_sample']), int(label['end_sample'])
                    span = (times >= start / header['sample_rate']) & (times < end / header['sample_rate'])
                    quality_spans.append({
                        'annotation_index': index, 'start_sample': start, 'end_sample': end,
                        'expected_mask': int(label['string_mask']),
                        'duration_seconds': (end - start) / header['sample_rate'],
                        'observations': int(span.sum()),
                        'detector_active_observations': int(detector_active[span].sum()),
                        'detector_phase_valid_observations': int(detector_phase_valid[span].sum()),
                        'raw': summarize_reference_quality(
                            raw_increments, raw_windows, enabled_bands,
                            start / header['sample_rate'], end / header['sample_rate']),
                        'conditioned': summarize_reference_quality(
                            conditioned_increments, phase_track, enabled_bands,
                            start / header['sample_rate'], end / header['sample_rate']),
                    })
                    if not 0 < end - start < 3 * header['sample_rate']:
                        continue
                    # Diagnostic control only. A short annotated hold cannot
                    # satisfy the unchanged three-second unison admission rule.
                    short_spans.append({
                        'annotation_index': index, 'start_sample': start,
                        'end_sample': end, 'expected_mask': int(label['string_mask']),
                        'duration_seconds': (end - start) / header['sample_rate'],
                        'eligible_unison_admission_window': False,
                        'phase_window': summarize_phase_windows(
                            phase_track, start / header['sample_rate'],
                            end / header['sample_rate']),
                    })
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
                    'phase_window': summarize_phase_windows(
                        phase_track, earlier['start_sample'] / header['sample_rate'],
                        earlier['end_sample'] / header['sample_rate']),
                })
            result = {'frames': len(samples), 'sample_rate': header['sample_rate'],
                      'demodulation_centers_hz': centers, 'windows': windows,
                      'short_annotation_diagnostics': short_spans,
                      'reference_quality_by_annotation': quality_spans,
                      'labels_sha256': previous['provenance']['labels_sha256'],
                      'classifier_gain': 'not measured'}
            if name in ('single-am', 'single-two-decays'):
                controls = {}
                for mode, track in (
                        ('raw', raw_increments),
                        ('conditioned', conditioned_increments),
                        ('phase_window', phase_track)):
                    # One second after the known synthetic attack, not a
                    # label-derived input to the feature or conditioner.
                    steady = track['increment_times'] >= 1.5
                    measured = track['cents'][:, steady]
                    rms, dominant = [], []
                    for band in measured:
                        valid = np.isfinite(band)
                        rms.append(float(np.sqrt(np.mean(band[valid] ** 2)))
                                   if valid.any() else None)
                        if mode != 'phase_window' and valid.all() and len(band) > 2:
                            power = np.abs(np.fft.rfft(band - np.mean(band))) ** 2
                            frequencies = np.fft.rfftfreq(len(band), 64 / header['sample_rate'])
                            dominant.append(float(frequencies[1 + np.argmax(power[1:])]))
                        else:
                            dominant.append(None)
                    controls[mode] = {
                        'expected_frequency_cents': 0.0,
                        'rms_frequency_error_cents_by_harmonic': rms,
                        'dominant_frequency_error_modulation_hz': dominant,
                        'valid_frequency_observations_by_harmonic':
                            np.isfinite(measured).sum(axis=1).tolist(),
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


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2.0,
              memory=4096, timeout=7200, max_containers=1)
def capture_string_evidence(run_id: str):
    """Capture current likelihood, history and assignment; no policy experiment."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from string_evidence_audit import summarize_files
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
        report['source_files_sha256'] = {
            str(path.relative_to('/opt/m3')): sha256(path)
            for path in sorted(Path('/opt/m3/native').rglob('*')) if path.is_file()}
        report['analysis_module_sha256'] = sha256('/opt/m3/string_evidence_audit.py')
        save()
        directory = build(out)
        binary = directory / 'm3_replay'
        report['binary_sha256'] = sha256(binary)
        report['stage'] = 'native offline tests'
        save()
        with (out / 'offline-tests.log').open('w') as log:
            subprocess.run([str(directory / 'm3_motion_tests')], check=True,
                           env={**os.environ, 'M3_TEST_FILTER': 'offline_'},
                           stdout=log, stderr=subprocess.STDOUT, timeout=600)
        report['offline_tests'] = (out / 'offline-tests.log').read_text().splitlines()[-1]
        settings = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
                    'max-polyphony': 5, 'max-fret': 24}
        calibration = MOUNT / 'corpus/calibration.m3cb'
        for name in ('ordinary', 'isolated-08'):
            wav, labels = (MOUNT / 'corpus' / (name + suffix) for suffix in ('.wav', '.tsv'))
            rate, duration = wave_duration(wav)
            sample_count = round(rate * duration)
            base = [str(binary), '--wav', str(wav), '--labels', str(labels),
                    '--calibration', str(calibration)]
            for key, value in settings.items():
                base += ['--' + key, str(value)]
            report['stage'] = f'{name} untraced control'
            save()
            control_path = out / f'{name}-control.tsv'
            with control_path.open('w') as stdout, (out / f'{name}-control.log').open('w') as log:
                subprocess.run(base + ['--block', '512'], stdout=stdout, stderr=log,
                               check=True, timeout=900)
            result = {'control': aggregate(control_path), 'replays': {},
                      'all_outputs_identical': True, 'all_traces_identical': True,
                      'provenance': {'audio_sha256': sha256(wav), 'labels_sha256': sha256(labels),
                                     'calibration_sha256': sha256(calibration), 'settings': settings,
                                     'sample_rate': rate, 'sample_count': sample_count,
                                     'take_identity': name + ':original-recording'}}
            report['datasets'][name] = result
            reference = None
            for block in (32, 512, 1024):
                report['stage'] = f'{name} assignment trace block {block}'
                save()
                trace = out / f'{name}-{block}-assignment.tsv'
                replay = out / f'{name}-{block}.tsv'
                log_path = out / f'{name}-{block}.log'
                with replay.open('w') as stdout, log_path.open('w') as log:
                    subprocess.run(base + ['--block', str(block), '--assignment-trace', str(trace)],
                                   stdout=stdout, stderr=log, check=True, timeout=900)
                metadata = re.findall(
                    r'assignment_trace rows=(\d+) cap=(\d+) truncated=(\d+) sampled_frames=(\d+) decimation=(\d+)',
                    log_path.read_text())
                if len(metadata) != 1:
                    raise ValueError(f'{name}: missing or duplicate trace accounting')
                rows, cap, truncated, sampled_frames, decimation = map(int, metadata[0])
                if truncated or rows > cap or decimation != 16:
                    raise ValueError(f'{name}: incomplete or incompatible trace')
                current, trace_hash = aggregate(replay), sha256(trace)
                result['replays'][str(block)] = current
                result['all_outputs_identical'] &= current == result['control']
                result['all_traces_identical'] &= reference in (None, trace_hash)
                if not result['all_outputs_identical'] or not result['all_traces_identical']:
                    raise ValueError(f'{name}: diagnostic parity failed at block {block}')
                if reference is None:
                    reference = trace_hash
                    result['provenance']['trace_sha256'] = trace_hash
                    result['analysis'] = summarize_files(
                        trace, labels, sample_rate=rate, sample_count=sample_count,
                        sampled_frames=sampled_frames, source_identity=name,
                        decimation=decimation)
                    if result['analysis']['trace_rows'] != rows:
                        raise ValueError(f'{name}: parsed trace row count mismatch')
                    with trace.open('rb') as src, gzip.open(out / f'{name}-assignment.tsv.gz', 'wb',
                                                           compresslevel=1) as dest:
                        shutil.copyfileobj(src, dest, length=1024 * 1024)
                trace.unlink()
                save()
        report.update(state='completed', final=True, stage='onset/settled evidence audit complete',
                      conclusion='Aligned disagreement measurements only; classifier gain and live improvement unmeasured.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        for name in ('build.log', 'offline-tests.log'):
            path = out / name
            if path.exists():
                report[name + '_tail'] = path.read_text()[-12000:]
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2.0,
              memory=4096, timeout=1800, max_containers=1)
def capture_controlled_overlap(run_id: str):
    """Five same-target mixtures: one solo and two added notes at two levels."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.controlled_descriptor_overlap import (
        read_float_wave, write_float_wave, controlled_mixtures, observations, compare_to_solo)
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id):
        raise ValueError('invalid run identifier')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, state='running', final=False, stage='prepare controlled mixtures',
                  installed_changed=False, datasets={}, started_at=datetime.now(timezone.utc).isoformat(),
                  limits=['One cropped target take, one competing string; no independent-take generalization.',
                          'Added-note spectra, detuning and envelopes differ; this does not isolate collision alone.',
                          'Paired descriptor observations are conditional on both lanes being available and unreserved.',
                          'Annotations score evidence only; no labels enter a MIDI policy.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        # Fixed before the run. No note/time/phase shifts or per-mixture gain fitting.
        definitions = [('target', 'isolated-08', 1003200, 1224000, 36, 1),
                       ('octave', 'isolated-05', 1003200, 1224000, 48, 8),
                       ('nearby', 'isolated-05', 1248000, 1468800, 49, 8)]
        arrays, components, rate = {}, {}, None
        for name, corpus, start, end, note, mask in definitions:
            wav, labels = (MOUNT / 'corpus' / (corpus + suffix) for suffix in ('.wav', '.tsv'))
            current_rate, audio = read_float_wave(wav)
            if rate not in (None, current_rate) or current_rate != 96000 or end > len(audio):
                raise ValueError('corpus clock or crop differs from the planned experiment')
            rate = current_rate
            with labels.open() as stream:
                matching = [row for row in csv.DictReader(stream, delimiter='\t')
                            if (int(row['start_sample']), int(row['end_sample']),
                                int(row['midi_note']), int(row['string_mask'])) == (start, end, note, mask)]
            if len(matching) != 1:
                raise ValueError('planned source annotation is missing or duplicated')
            arrays[name] = audio[start:end]
            components[name] = dict(corpus=corpus, audio_sha256=sha256(wav),
                                    labels_sha256=sha256(labels), start_sample=start, end_sample=end,
                                    midi_note=note, string_mask=mask,
                                    component_sha256=hashlib.sha256(arrays[name].tobytes()).hexdigest(),
                                    source_annotation=matching[0])
        prefix, suffix = rate // 4, rate
        cases = controlled_mixtures(arrays['target'], {key: arrays[key] for key in ('octave', 'nearby')},
                                     prefix=prefix, suffix=suffix)
        report['components'] = components
        report['analysis_source_sha256'] = {
            module: sha256('/opt/m3/tools/' + module + '.py') for module in OVERLAP_MODULES}
        report['source_files_sha256'] = {
            str(path.relative_to('/opt/m3')): sha256(path)
            for path in sorted(Path('/opt/m3/native').rglob('*')) if path.is_file()}
        report['stage'] = 'build diagnostic replay'
        save()
        binary = build(out) / 'm3_replay'
        report['binary_sha256'] = sha256(binary)
        calibration = MOUNT / 'corpus/calibration.m3cb'
        settings = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
                    'max-polyphony': 5, 'max-fret': 24}
        report['calibration_sha256'] = sha256(calibration)
        report['settings'] = settings
        solo = None
        for name, case in cases.items():
            wav, labels = out / (name + '.wav'), out / (name + '.tsv')
            write_float_wave(wav, rate, case['audio'])
            end = prefix + len(arrays['target'])
            label_text = f'start_sample\tend_sample\tmidi_note\tstring_mask\n{prefix}\t{end}\t36\t1\n'
            added = case['metadata']['interferer']
            if added is not None:
                label_text += f"{prefix}\t{end}\t{components[added]['midi_note']}\t8\n"
            labels.write_text(label_text)
            base = [str(binary), '--wav', str(wav), '--labels', str(labels), '--calibration', str(calibration)]
            for key, value in settings.items():
                base += ['--' + key, str(value)]
            result = dict(mixture=case['metadata'], audio_sha256=sha256(wav), labels_sha256=sha256(labels),
                          sample_rate=rate, sample_count=len(case['audio']), replays={},
                          all_outputs_identical=True, all_traces_identical=True)
            report['datasets'][name] = result
            reference = None
            # An untraced control proves diagnostics do not alter output; three blocks test clock invariance.
            for block, traced in ((512, False), (32, True), (512, True), (1024, True)):
                tag = str(block) if traced else 'control'
                report['stage'] = f'{name} replay {tag}'
                save()
                replay, trace = out / f'{name}-{tag}.tsv', out / f'{name}-{tag}-assignment.tsv'
                log_path = out / f'{name}-{tag}.log'
                args = base + ['--block', str(block)]
                if traced:
                    args += ['--assignment-trace', str(trace)]
                with replay.open('w') as stdout, log_path.open('w') as log:
                    subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
                current = aggregate(replay)
                if not traced:
                    result['control'] = current
                    continue
                result['replays'][tag] = current
                metadata = re.findall(
                    r'assignment_trace rows=(\d+) cap=(\d+) truncated=(\d+) sampled_frames=(\d+) decimation=(\d+)',
                    log_path.read_text())
                if len(metadata) != 1:
                    raise ValueError('missing or duplicate trace accounting')
                rows, cap, truncated, sampled_frames, decimation = map(int, metadata[0])
                stride = decimation * 64
                if truncated or rows > cap or decimation != 16 or sampled_frames != len(case['audio']) // stride:
                    raise ValueError('incomplete or incompatible assignment trace')
                trace_hash = sha256(trace)
                result['all_outputs_identical'] &= current == result['control']
                result['all_traces_identical'] &= reference in (None, trace_hash)
                if not result['all_outputs_identical'] or not result['all_traces_identical']:
                    raise ValueError(f'{name}: diagnostic parity failed at block {block}')
                if reference is None:
                    reference = trace_hash
                    result['trace_sha256'] = trace_hash
                    with trace.open() as stream:
                        measured = observations(csv.DictReader(stream, delimiter='\t'), note=36, lane=0,
                                                competitor=1, start=prefix, end=end, sample_rate=rate,
                                                sample_count=len(case['audio']), stride=stride)
                    if measured['trace_rows'] != rows:
                        raise ValueError('parsed trace accounting mismatch')
                    result['coverage'] = measured['coverage']
                    pair_path = out / f'{name}-pair.json'
                    pair_path.write_text(json.dumps(measured, indent=2, allow_nan=False) + '\n')
                    result['pair_observation_sha256'] = sha256(pair_path)
                    if name == 'solo':
                        solo = measured
                    else:
                        result['paired_comparison'] = compare_to_solo(solo, measured)
                    with trace.open('rb') as src, gzip.open(out / f'{name}-assignment.tsv.gz', 'wb',
                                                           compresslevel=1) as dest:
                        shutil.copyfileobj(src, dest, length=1024 * 1024)
                trace.unlink()
                save()
        report.update(state='completed', final=True, stage='controlled overlap comparison complete',
                      conclusion='Measured paired effect of added recordings; no production candidate or live-use claim.')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        path = out / 'build.log'
        if path.exists():
            report['build_log_tail'] = path.read_text()[-6000:]
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=900, max_containers=1)
def capture_controlled_selection(run_id: str, source_run: str):
    """One saved nearby_0dB replay; expose where its target leaves selection."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.selection_trace_diagnosis import summarize_selection
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if previous.get('state') != 'completed' or not previous.get('final'):
        raise ValueError('source capture is not final')
    saved = previous['datasets']['nearby_0dB']
    wav, labels = source / 'nearby_0dB.wav', source / 'nearby_0dB.tsv'
    calibration = MOUNT / 'corpus/calibration.m3cb'
    for path, expected in ((wav, saved['audio_sha256']), (labels, saved['labels_sha256']),
                           (calibration, previous['calibration_sha256'])):
        if sha256(path) != expected:
            raise ValueError('saved audio, labels or calibration changed')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
                  stage='build identical diagnostic replay', installed_changed=False,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  source_report_sha256=sha256(source / 'report.json'),
                  analysis_sha256=sha256('/opt/m3/tools/selection_trace_diagnosis.py'))

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        binary = build(out) / 'm3_replay'
        report['binary_sha256'] = sha256(binary)
        if report['binary_sha256'] != previous['binary_sha256']:
            raise ValueError('rebuilt binary differs from the saved control')
        report['calibration_sha256'] = sha256(calibration)
        with labels.open() as stream:
            target = [row for row in csv.DictReader(stream, delimiter='\t')
                      if int(row['midi_note']) == 36 and int(row['string_mask']) == 1]
        if len(target) != 1:
            raise ValueError('expected one target span')
        start, end = int(target[0]['start_sample']), int(target[0]['end_sample'])
        rate = saved['sample_rate']
        candidate, outcome = out / 'candidate.tsv', out / 'outcome.tsv'
        args = [str(binary), '--wav', str(wav), '--labels', str(labels),
                '--calibration', str(calibration), '--block', '512',
                '--candidate-trace', str(candidate), '--candidate-trace-note', '36',
                '--candidate-trace-start', str(start / rate),
                '--candidate-trace-end', str(end / rate), '--outcome-trace', str(outcome)]
        for key, value in previous['settings'].items():
            args += ['--' + key, str(value)]
        report.update(stage='one saved-mixture replay', command=args, settings=previous['settings'])
        save()
        replay, log_path = out / 'replay.tsv', out / 'replay.log'
        with replay.open('w') as stdout, log_path.open('w') as log:
            subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
        report['output'] = aggregate(replay)
        report['control'] = saved['control']
        report['output_identical'] = report['output'] == report['control']
        if not report['output_identical']:
            raise ValueError('diagnostics changed output')
        for name in ('candidate', 'outcome'):
            counts = re.findall(rf'{name}_trace frames=(\d+) cap=(\d+) truncated=(\d+)',
                                log_path.read_text())
            if len(counts) != 1 or int(counts[0][2]) or int(counts[0][0]) > int(counts[0][1]):
                raise ValueError('incomplete trace accounting')
        assignment = out / 'source-assignment.tsv'
        with gzip.open(source / 'nearby_0dB-assignment.tsv.gz', 'rb') as src, assignment.open('wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        if sha256(assignment) != saved['trace_sha256']:
            raise ValueError('saved assignment trace changed')
        with candidate.open() as c, outcome.open() as o, assignment.open() as a:
            if next(o).strip() != '# m3_candidate_outcome_v2':
                raise ValueError('unknown outcome format')
            report['diagnosis'] = summarize_selection(
                csv.DictReader(c, delimiter='\t'), csv.DictReader(o, delimiter='\t'),
                csv.DictReader(a, delimiter='\t'), note=36, start=start, end=end,
                sample_count=saved['sample_count'])
        for trace in (candidate, outcome):
            report[trace.stem + '_trace_sha256'] = sha256(trace)
            with trace.open('rb') as src, gzip.open(str(trace) + '.gz', 'wb', compresslevel=1) as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            trace.unlink()
        assignment.unlink()
        report.update(state='completed', final=True, stage='selection loss diagnosed')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=900, max_containers=1)
def capture_controlled_admission(run_id: str, source_run: str):
    """Paired admission OFF/ON using the five cached, unchanged waveforms."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.controlled_admission_gate import CASES, evaluate_admission, read_target_detail
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    cases = CASES
    if previous.get('state') != 'completed' or not previous.get('final'):
        raise ValueError('source capture is not final')
    if set(previous['datasets']) != set(cases):
        raise ValueError('expected the five controlled mixtures')
    calibration = MOUNT / 'corpus/calibration.m3cb'
    if sha256(calibration) != previous['calibration_sha256']:
        raise ValueError('calibration changed')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
                  stage='build offline admission trial', installed_changed=False,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  source_report_sha256=sha256(source / 'report.json'),
                  baseline_binary_sha256=previous['binary_sha256'],
                  calibration_sha256=sha256(calibration), settings=previous['settings'],
                  gate_source_sha256=sha256('/opt/m3/tools/controlled_admission_gate.py'),
                  detector_test_access_enabled=True,
                  source_files_sha256={str(p.relative_to('/opt/m3')): sha256(p)
                                       for p in sorted(Path('/opt/m3/native').rglob('*'))
                                       if p.is_file()}, datasets={}, tests={})

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        directory = build(out, detector_tests=True)
        binary = directory / 'm3_replay'
        report['binary_sha256'] = sha256(binary)
        report['binary_path'] = str(out / 'm3_replay')
        shutil.copy2(binary, report['binary_path'])
        report['stage'] = 'causal unit tests and replay tests'
        save()
        for name, executable, test_filter in (
                ('fundamental-admission', 'm3_detector_tests', 'native_detector_fundamental_admission'),
                ('harmonic-admission', 'm3_detector_tests', 'native_detector_calibrated_harmonic_admission'),
                ('offline-replay', 'm3_motion_tests', '')):
            log_path = out / (name + '-tests.log')
            env = dict(os.environ, M3_TEST_FILTER=test_filter)
            with log_path.open('w') as log:
                subprocess.run([str(directory / executable)], stdout=log,
                               stderr=subprocess.STDOUT, env=env, check=True, timeout=240)
            summary = re.findall(r'Ran (\d+) tests: (\d+) failure\(s\)', log_path.read_text())
            if len(summary) != 1 or int(summary[0][0]) == 0 or int(summary[0][1]) != 0:
                raise ValueError('missing successful test accounting')
            report['tests'][name] = dict(count=int(summary[0][0]), failures=0,
                                         log_sha256=sha256(log_path))
        for case in cases:
            saved = previous['datasets'][case]
            wav, labels = source / (case + '.wav'), source / (case + '.tsv')
            for path, key in ((wav, 'audio_sha256'), (labels, 'labels_sha256')):
                if sha256(path) != saved[key]:
                    raise ValueError(f'{case}: cached {key} changed')
            item = {key: saved[key] for key in ('audio_sha256', 'labels_sha256',
                                               'sample_rate', 'sample_count')}
            item['replays'] = {}
            report['datasets'][case] = item
            for enabled in (False, True):
                mode = 'on' if enabled else 'off'
                report['stage'] = f'{case}: admission {mode}, block 512'
                save()
                args = [str(binary), '--wav', str(wav), '--labels', str(labels),
                        '--calibration', str(calibration), '--block', '512', '--label-details']
                for key, value in previous['settings'].items():
                    args += ['--' + key, str(value)]
                if enabled:
                    args += ['--diagnostic-fundamental-admission']
                output = out / f'{case}-{mode}.tsv'
                with output.open('w') as stdout, (out / f'{case}-{mode}.log').open('w') as log:
                    subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
                item['replays'][mode] = dict(command=args, output=aggregate(output),
                                              target=read_target_detail(output))
            off, on = (item['replays'][mode]['output'] for mode in ('off', 'on'))
            item['control_identical'] = off == saved['control']
            if not item['control_identical'] or on['labeled'] != off['labeled']:
                raise ValueError(f'{case}: control or label accounting changed')
            save()
        gate = evaluate_admission(report['datasets'])
        for case, result in gate.pop('cases').items():
            report['datasets'][case].update(result)
        report.update(state='completed', final=True, stage='controlled admission screen complete',
                      **gate)
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        report['log_tails'] = {path.name: path.read_text()[-4000:]
                              for path in out.glob('*.log')}
    save()
    return report


@app.local_entrypoint()
def main(run_id: str, source_run: str = '', string_evidence: bool = False,
         controlled_overlap: bool = False, selection_source: str = '',
         admission_source: str = ''):
    if (bool(source_run) + string_evidence + controlled_overlap + bool(selection_source)
            + bool(admission_source)) > 1:
        raise ValueError('select one analysis or capture job')
    result = (capture_controlled_admission.remote(run_id, admission_source) if admission_source else
              capture_controlled_selection.remote(run_id, selection_source) if selection_source else
              capture_controlled_overlap.remote(run_id) if controlled_overlap else
              capture_string_evidence.remote(run_id) if string_evidence else
              analyze_saved_capture.remote(run_id, source_run) if source_run else capture.remote(run_id))
    target = ROOT / 'build/modal' / f'{run_id}.json'
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'state': result['state'], 'report': str(target),
                      'stage': result['stage'], 'final': result['final']}))
    if result['state'] != 'completed':
        raise SystemExit(1)
