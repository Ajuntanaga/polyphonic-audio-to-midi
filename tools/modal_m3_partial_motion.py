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
                   'controlled_admission_gate', 'independent_partial_evidence',
                   'frozen_cue_diagnosis', 'frozen_cue_corpus_gate', 'frozen_cue_native_gate')
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


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=1800, max_containers=1)
def capture_frozen_partial_cues(run_id: str, source_run: str, cue_free_lane: bool = False):
    """Replay frozen, past-only cues on the unchanged held-out waveforms."""
    import sys
    sys.path.insert(0, '/opt/m3')
    import numpy as np
    from tools.controlled_admission_gate import CASES, FIELDS, evaluate_admission, read_target_detail
    from tools.controlled_descriptor_overlap import read_float_wave, write_float_wave, controlled_mixtures
    from tools.independent_partial_evidence import CONFIG, FROZEN_SCREEN, frozen_cue_intervals
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final') or
            not previous.get('screen_passed') or previous['config'] != CONFIG or
            previous['frozen_screen'] != FROZEN_SCREEN):
        raise ValueError('source is not a completed frozen held-out screen')
    corpus_id = previous['corpus_id']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', corpus_id):
        raise ValueError('invalid corpus identifier')
    corpus = MOUNT / 'corpus' / corpus_id
    manifest = json.loads((corpus / 'manifest.json').read_text())
    if (sha256(corpus / 'manifest.json') != previous['manifest_sha256'] or
            manifest != previous['manifest'] or manifest['calibration_pass'] != 2):
        raise ValueError('held-out manifest changed')
    baseline = MOUNT / 'results/controlled-admission-20261103T1457Z/m3_replay'
    calibration = MOUNT / 'corpus/calibration.m3cb'
    baseline_hash = 'b7c698019bcb5a669fae523c6b1d0b3eac3acf21cc120725b20bb2e55f025646'
    calibration_hash = 'b7025b4fd3ea55901ea9f189966b4f62b6fe905ad16b9f8d0df88a0a1a76e997'
    if sha256(baseline) != baseline_hash or sha256(calibration) != calibration_hash:
        raise ValueError('baseline binary or calibration changed')
    settings = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
                'max-polyphony': 5, 'max-fret': 24}
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, corpus_id=corpus_id,
        state='running', final=False, stage='prepare frozen-cue replay', installed_changed=False,
        started_at=datetime.now(timezone.utc).isoformat(), config=CONFIG, frozen_screen=FROZEN_SCREEN,
        source_report_sha256=sha256(source / 'report.json'), manifest_sha256=previous['manifest_sha256'],
        baseline_binary_sha256=baseline_hash, calibration_sha256=calibration_hash, settings=settings,
        source_files_sha256={str(p.relative_to('/opt/m3')): sha256(p)
                            for p in sorted(Path('/opt/m3/native').rglob('*')) if p.is_file()},
        analysis_source_sha256={name: sha256('/opt/m3/tools/' + name + '.py') for name in OVERLAP_MODULES},
        cue_free_lane_reassignment=cue_free_lane,
        cue_pitch_admission=not cue_free_lane,
        cue_free_lane_tuning_guard=(dict(mode='contradiction_veto', valid_phase_required=False,
            tuning_availability='settled_output_projection', maximum_absolute_cents=60.0,
            valid_phase_required_after_evidence_seconds=0.160,
            missing_mature_tuning='reject_reassignment',
            maximum_assignment_age_seconds_exclusive=0.160,
            established_assignment='preserve_existing_lane',
            minimum_incumbent_advantage_cents=0.75) if cue_free_lane else None),
        datasets={}, tests={}, limits=[
            'Separate plucks from the same session; mixtures and frames are correlated.',
            'Frozen feature sidecars are offline; their spectral computation is not in the audio callback.',
            'The causal window is 170.7 ms; cue release waits for its end. Live latency is not measured.',
            'No broad corpus, room-noise, lifecycle or installed-plugin acceptance follows from this screen.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        components = {}
        for name in ('target', 'octave', 'nearby'):
            identity, path = manifest['components'][name], corpus / (name + '.wav')
            if sha256(path) != identity['wave_sha256']:
                raise ValueError('held-out crop changed')
            rate, values = read_float_wave(path)
            if (rate != 96000 or len(values) != 220800 or
                    hashlib.sha256(values.tobytes()).hexdigest() != identity['samples_sha256']):
                raise ValueError('held-out clock or samples changed')
            components[name] = values.astype(np.float64)
        mixtures = controlled_mixtures(components['target'],
            {key: components[key] for key in ('octave', 'nearby')}, prefix=24000, suffix=96000)
        cases = {}
        for name, item in mixtures.items():
            metadata = item['metadata']
            cases[name] = (item['audio'], True, metadata['interferer'])
            if metadata['interferer'] is not None:
                added = components[metadata['interferer']] * metadata['interferer_scale'] * metadata['common_gain']
                cases[name + '_source_only'] = (np.pad(np.asarray(added, dtype='<f4'),
                                                      (24000, 96000)), False, metadata['interferer'])
        cases['silence'] = (np.zeros(340800, dtype='<f4'), False, None)
        if set(cases) != set(previous['cases']):
            raise ValueError('held-out case coverage changed')
        for name, (values, has_target, added) in cases.items():
            saved = previous['cases'][name]
            if (saved['sample_rate'] != 96000 or len(values) != saved['sample_count'] or
                    hashlib.sha256(values.tobytes()).hexdigest() != saved['audio_sha256']):
                raise ValueError(f'{name}: reconstructed audio differs from frozen features')
            trace = source / (name + '-partials.jsonl.gz')
            if sha256(trace) != saved['trace_sha256']:
                raise ValueError(f'{name}: frozen feature trace changed')
            # Only mixture features enter this exporter. Labels score the replay below.
            with gzip.open(trace, 'rt') as stream:
                intervals = frozen_cue_intervals((json.loads(line) for line in stream),
                                                  sample_count=len(values))
            cues = out / (name + '-cues.tsv')
            cues.write_text('m3_frozen_note_cues_v1\t96000\t1024\n' + ''.join(
                f"{row['begin_sample']}\t{row['end_sample']}\t{row['midi_note']}\n" for row in intervals))
            wav, labels = out / (name + '.wav'), out / (name + '.tsv')
            write_float_wave(wav, 96000, values)
            text = 'start_sample\tend_sample\tmidi_note\tstring_mask\tcalibration_pass\n'
            if has_target:
                text += '24000\t244800\t36\t1\t2\n'
            if added is not None:
                text += f"24000\t244800\t{manifest['components'][added]['midi_note']}\t8\t2\n"
            labels.write_text(text)
            report['datasets'][name] = dict(sample_rate=96000, sample_count=len(values),
                audio_sha256=sha256(wav), samples_sha256=saved['audio_sha256'], labels_sha256=sha256(labels),
                cue_sha256=sha256(cues), cue_intervals=len(intervals), feature_trace_sha256=saved['trace_sha256'],
                has_target=has_target, replays={})
        report['stage'] = 'build diagnostic replay and focused tests'
        save()
        directory = build(out, detector_tests=True)
        binary = directory / 'm3_replay'
        report['binary_sha256'] = sha256(binary)
        shutil.copy2(binary, out / 'm3_replay')
        for name, executable, test_filter in (
                ('cue-free-lane', 'm3_detector_tests', 'native_detector_cue_free_lane'),
                ('fundamental-admission', 'm3_detector_tests', 'native_detector_fundamental_admission'),
                ('harmonic-admission', 'm3_detector_tests', 'native_detector_calibrated_harmonic_admission'),
                ('offline-replay', 'm3_motion_tests', '')):
            report['stage'] = name + ' tests'
            save()
            log_path = out / (name + '-tests.log')
            with log_path.open('w') as log:
                subprocess.run([str(directory / executable)], stdout=log, stderr=subprocess.STDOUT,
                    env=dict(os.environ, M3_TEST_FILTER=test_filter), check=True, timeout=240)
            summary = re.findall(r'Ran (\d+) tests: (\d+) failure\(s\)', log_path.read_text())
            if len(summary) != 1 or int(summary[0][0]) == 0 or int(summary[0][1]) != 0:
                raise ValueError('missing successful test accounting')
            report['tests'][name] = dict(count=int(summary[0][0]), failures=0, log_sha256=sha256(log_path))
        missing_cue = subprocess.run([str(binary), '--wav', str(out / 'solo.wav'),
                '--diagnostic-cue-free-lane-reassignment'], capture_output=True, text=True, timeout=30)
        if (missing_cue.returncode != 1 or
                'free-lane reassignment requires frozen odd-partial cues' not in missing_cue.stderr):
            raise ValueError('missing-cue configuration was not rejected')
        report['missing_cue_rejected'] = True
        for name, item in report['datasets'].items():
            wav, labels, cues = (out / (name + suffix) for suffix in ('.wav', '.tsv', '-cues.tsv'))
            for mode, executable, block in (('baseline', baseline, 512), ('off', binary, 512),
                    ('on', binary, 512), ('on32', binary, 32), ('on1024', binary, 1024)):
                report['stage'] = f'{name}: {mode}, block {block}'
                save()
                args = [str(executable), '--wav', str(wav), '--labels', str(labels),
                        '--calibration', str(calibration), '--block', str(block), '--label-details']
                for key, value in settings.items():
                    args += ['--' + key, str(value)]
                if mode.startswith('on'):
                    args += ['--diagnostic-odd-partial-cues', str(cues)]
                    if cue_free_lane:
                        args += ['--diagnostic-cue-free-lane-reassignment']
                output = out / f'{name}-{mode}.tsv'
                with output.open('w') as stdout, (out / f'{name}-{mode}.log').open('w') as log:
                    subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
                replay = dict(output=aggregate(output))
                if item['has_target']:
                    replay['target'] = read_target_detail(output)
                item['replays'][mode] = replay
            replays = item['replays']
            item['control_identical'] = replays['off'] == replays['baseline']
            item['buffer_outputs_identical'] = replays['on32'] == replays['on'] == replays['on1024']
            if not item['control_identical'] or not item['buffer_outputs_identical']:
                raise ValueError(f'{name}: baseline OFF or buffer parity failed')
            if not item['has_target']:
                off, on = (replays[key]['output'] for key in ('off', 'on'))
                if off['labeled'] != on['labeled']:
                    raise ValueError(f'{name}: label accounting changed')
                item['delta'] = {key: int(on[key]) - int(off[key]) for key in FIELDS}
                item['gate_pass'] = item['delta']['matched'] >= 0 and all(
                    item['delta'][key] <= 0 for key in FIELDS[1:])
            save()
        gate = evaluate_admission({name: report['datasets'][name] for name in CASES})
        for name, result in gate.pop('cases').items():
            report['datasets'][name].update(result)
        negative_regressions = [name for name, item in report['datasets'].items()
                                if not item['has_target'] and not item['gate_pass']]
        gate['negative_regressions'] = negative_regressions
        gate['accepted_for_corpus_screen'] &= not negative_regressions
        gate['verdict'] = 'advance to corpus screen' if gate['accepted_for_corpus_screen'] else 'rejected'
        report.update(state='completed', final=True, stage='frozen cue replay complete',
                      completed_at=datetime.now(timezone.utc).isoformat(), **gate)
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        logs = sorted(out.glob('*.log'), key=lambda path: path.stat().st_mtime)[-3:]
        report['log_tails'] = {path.name: path.read_text()[-4000:] for path in logs}
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=900, max_containers=1)
def capture_frozen_cue_selection(run_id: str, source_run: str):
    """Trace one frozen-cue replay with its saved binary; no build or sweep."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.controlled_admission_gate import read_target_detail
    from tools.frozen_cue_diagnosis import summarize_cues
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if previous.get('state') != 'completed' or not previous.get('final'):
        raise ValueError('source capture is not final')
    saved = previous['datasets']['nearby_0dB']
    binary, wav, labels, cues = (source / name for name in
        ('m3_replay', 'nearby_0dB.wav', 'nearby_0dB.tsv', 'nearby_0dB-cues.tsv'))
    calibration = MOUNT / 'corpus/calibration.m3cb'
    identities = ((binary, previous['binary_sha256']), (wav, saved['audio_sha256']),
                  (labels, saved['labels_sha256']), (cues, saved['cue_sha256']),
                  (calibration, previous['calibration_sha256']))
    if any(sha256(path) != expected for path, expected in identities):
        raise ValueError('saved binary, audio, labels, cues or calibration changed')
    target = saved['replays']['on']['target']
    start, end = target['start_sample'], target['end_sample']
    rate = saved['sample_rate']
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
        stage='trace saved frozen-cue replay', installed_changed=False,
        started_at=datetime.now(timezone.utc).isoformat(),
        source_report_sha256=sha256(source / 'report.json'),
        binary_sha256=previous['binary_sha256'], calibration_sha256=previous['calibration_sha256'],
        analysis_sha256=sha256('/opt/m3/tools/frozen_cue_diagnosis.py'),
        saved_input_hashes={path.name: digest for path, digest in identities},
        settings=previous['settings'], control=saved['replays']['on'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        candidate, outcome = out / 'candidate.tsv', out / 'outcome.tsv'
        args = [str(binary), '--wav', str(wav), '--labels', str(labels),
                '--calibration', str(calibration), '--block', '512', '--label-details',
                '--diagnostic-odd-partial-cues', str(cues),
                '--candidate-trace', str(candidate), '--candidate-trace-note', str(target['midi_note']),
                '--candidate-trace-start', str(start / rate),
                '--candidate-trace-end', str(end / rate), '--outcome-trace', str(outcome)]
        for key, value in previous['settings'].items():
            args += ['--' + key, str(value)]
        report['command'] = args
        save()
        replay, log_path = out / 'replay.tsv', out / 'replay.log'
        with replay.open('w') as stdout, log_path.open('w') as log:
            subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
        report['replay'] = dict(output=aggregate(replay), target=read_target_detail(replay))
        report['output_identical'] = report['replay'] == report['control']
        if not report['output_identical']:
            raise ValueError('diagnostics changed saved output or target matches')
        report['trace_counts'] = {}
        for name in ('candidate', 'outcome'):
            counts = re.findall(rf'{name}_trace frames=(\d+) cap=(\d+) truncated=(\d+)',
                                log_path.read_text())
            if len(counts) != 1 or int(counts[0][2]) or int(counts[0][0]) > int(counts[0][1]):
                raise ValueError('incomplete trace accounting')
            report['trace_counts'][name] = dict(zip(('frames', 'cap', 'truncated'), map(int, counts[0])))
        with cues.open() as stream:
            if next(stream).strip() != 'm3_frozen_note_cues_v1\t96000\t1024':
                raise ValueError('unknown frozen cue format')
            intervals = [tuple(map(int, line.split('\t'))) for line in stream if line.strip()]
        if len(intervals) != saved['cue_intervals']:
            raise ValueError('saved cue count changed')
        with candidate.open() as c, outcome.open() as o:
            if next(o).strip() != '# m3_candidate_outcome_v2':
                raise ValueError('unknown outcome format')
            report['diagnosis'] = summarize_cues(
                csv.DictReader(c, delimiter='\t'), csv.DictReader(o, delimiter='\t'), intervals,
                note=target['midi_note'], start=start, end=end, sample_count=saved['sample_count'],
                label_index=target['label_index'], string_mask=target['string_mask'])
        joined = report['diagnosis']['all_labeled']
        if joined['frames'] != target['labeled'] or joined['target_matched'] != target['matched']:
            raise ValueError('joined trace disagrees with native target scoring')
        for trace in (candidate, outcome):
            report[trace.stem + '_trace_sha256'] = sha256(trace)
            with trace.open('rb') as src, gzip.open(str(trace) + '.gz', 'wb', compresslevel=1) as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            trace.unlink()
        report.update(state='completed', final=True, stage='frozen-cue selection diagnosed',
                      completed_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=7200, max_containers=1)
def capture_frozen_cue_corpus(run_id: str, source_run: str, dataset: str,
                             cue_checkpoint_run: str = '', reuse_cue_features: bool = False):
    """Screen one untouched corpus with saved binaries and label-blind cues."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.frozen_cue_corpus_gate import (read_corpus_wave, read_replay, compare_replays,
                                            reuse_frozen_cue_checkpoint)
    from tools.independent_partial_evidence import CONFIG, FROZEN_SCREEN, measure, frozen_cue_intervals
    datasets = ('ordinary', 'constructed', 'isolated-08', 'isolated-05', 'isolated-02',
                'physical-long', 'physical-middle', 'physical-highmid', 'physical-high',
                'extended-middle', 'extended-highmid', 'extended-high',
                'physical-four', 'synthetic-four')
    if (any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run))
            or dataset not in datasets
            or (reuse_cue_features and not cue_checkpoint_run)
            or (cue_checkpoint_run and not re.fullmatch(r'[a-zA-Z0-9_-]+', cue_checkpoint_run))):
        raise ValueError('invalid corpus or run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final')
            or not previous.get('accepted_for_corpus_screen')
            or previous.get('cue_free_lane_reassignment') is not True
            or previous['config'] != CONFIG or previous['frozen_screen'] != FROZEN_SCREEN):
        raise ValueError('source did not pass the controlled cue/free-lane screen')
    corpus = MOUNT / 'corpus'
    manifest = json.loads((corpus / 'manifest.json').read_text())
    wav, labels, calibration = corpus / (dataset + '.wav'), corpus / (dataset + '.tsv'), corpus / 'calibration.m3cb'
    baseline = MOUNT / 'results/controlled-admission-20261103T1457Z/m3_replay'
    binary = source / 'm3_replay'
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    settings = {'a4': 440, 'input-trim': -9, 'sensitivity': 60, 'response': 75,
                'max-polyphony': 5, 'max-fret': 24}
    report = dict(run_id=run_id, source_run=source_run, dataset=dataset,
        state='running', final=False, stage='verify saved binaries and corpus', installed_changed=False,
        started_at=datetime.now(timezone.utc).isoformat(), settings=settings,
        cue_free_lane_reassignment=previous['cue_free_lane_reassignment'],
        cue_pitch_admission=previous.get('cue_pitch_admission', True),
        config=CONFIG, frozen_screen=FROZEN_SCREEN, cue_notes=list(range(32, 85)),
        source_report_sha256=sha256(source / 'report.json'),
        corpus_manifest_sha256=sha256(corpus / 'manifest.json'),
        analysis_source_sha256={name: sha256('/opt/m3/tools/' + name + '.py') for name in OVERLAP_MODULES},
        replays={}, limits=[
            'This run screens one corpus; other recordings remain unchecked by this run.',
            'Cues scan MIDI 32 through 84, fixed from tuning plus 24 frets; annotations never select cues.',
            'Same saved native binary as the controlled screen; no native build or install.',
            'Spectral cues remain offline, with a 170.7 ms causal window; live latency is unmeasured.',
            'A safety regression stops before additional buffer checks or other corpora.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        if previous['settings'] != settings:
            raise ValueError('replay settings changed')
        if (report['analysis_source_sha256']['independent_partial_evidence'] !=
                previous['analysis_source_sha256']['independent_partial_evidence']):
            raise ValueError('frozen cue calculation changed')
        for name, path in (('baseline_binary', baseline), ('binary', binary), ('calibration', calibration)):
            report[name + '_sha256'] = sha256(path)
            if report[name + '_sha256'] != previous[name + '_sha256']:
                raise ValueError(name + ' differs from accepted source')
        for path in (wav, labels, calibration):
            identity = manifest[path.name]
            if path.stat().st_size != identity['bytes'] or sha256(path) != identity['sha256']:
                raise ValueError(path.name + ' differs from protected manifest')
            report[path.suffix.lstrip('.') + '_sha256'] = identity['sha256']
        if wav.stat().st_size > 512 * 1024 * 1024:
            raise ValueError('waveform exceeds this bounded screen memory budget')
        rate, values = read_corpus_wave(wav)
        if rate != 96000:
            raise ValueError('frozen native cue clock requires 96 kHz')
        report.update(sample_rate=rate, sample_count=len(values),
                      stage='measure frozen cues across the playable pitch range')
        save()
        cue_path = out / (dataset + '-cues.tsv')
        if cue_checkpoint_run:
            report['stage'] = 'verify saved cue checkpoint'
            save()
            checkpoint = MOUNT / 'results' / cue_checkpoint_run
            checkpoint_report = checkpoint / 'report.json'
            saved = json.loads(checkpoint_report.read_text())
            saved_cues = checkpoint / (dataset + '-cues.tsv')
            cue_fields = reuse_frozen_cue_checkpoint(saved, report, cue_sha256=sha256(saved_cues),
                                                     allow_native_change=reuse_cue_features)
            shutil.copyfile(saved_cues, cue_path)
            report.update(cue_fields, cue_checkpoint_run=cue_checkpoint_run,
                          cue_features_reused_across_native_versions=reuse_cue_features,
                          cue_checkpoint_report_sha256=sha256(checkpoint_report))
        else:
            cue_counts = {str(note): 0 for note in report['cue_notes']}
            cue_total = 0

            def observations():
                for index, row in enumerate(measure(values, rate, notes=tuple(report['cue_notes']))):
                    if index % 1000 == 0:
                        report['feature_samples_processed'] = row['sample'] + 1
                        save()
                    yield row

            intervals = frozen_cue_intervals(observations(), sample_count=len(values))
            if len(intervals) > 100000:
                raise ValueError('cue count exceeds saved binary sidecar capacity; no cues were dropped')
            with cue_path.open('w') as stream:
                stream.write('m3_frozen_note_cues_v1\t96000\t1024\n')
                for row in intervals:
                    stream.write(f"{row['begin_sample']}\t{row['end_sample']}\t{row['midi_note']}\n")
                    cue_counts[str(row['midi_note'])] += 1
                    cue_total += 1
            report.update(cue_intervals=cue_total, cue_intervals_by_note=cue_counts,
                          cue_sha256=sha256(cue_path), feature_samples_processed=len(values))
            del intervals
        del values
        for mode, executable, block in (('baseline', baseline, 512), ('off', binary, 512),
                ('on', binary, 512), ('on32', binary, 32), ('on1024', binary, 1024)):
            report['stage'] = f'{dataset}: {mode}, block {block}'
            save()
            args = [str(executable), '--wav', str(wav), '--labels', str(labels),
                    '--calibration', str(calibration), '--block', str(block), '--label-details']
            for key, value in settings.items():
                args += ['--' + key, str(value)]
            if mode.startswith('on'):
                args += ['--diagnostic-odd-partial-cues', str(cue_path),
                         '--diagnostic-cue-free-lane-reassignment']
            output = out / (mode + '.tsv')
            with output.open('w') as stdout, (out / (mode + '.log')).open('w') as log:
                subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=1500)
            report['replays'][mode] = read_replay(output)
            if mode == 'off':
                report['control_identical'] = report['replays']['baseline'] == report['replays']['off']
                if not report['control_identical']:
                    raise ValueError('old baseline and new OFF outputs differ')
            if mode == 'on':
                report['comparison'] = compare_replays(report['replays']['off'], report['replays']['on'])
                if not report['comparison']['gate_pass']:
                    report['buffer_outputs_identical'] = None
                    break
            if mode == 'on1024':
                report['buffer_outputs_identical'] = (
                    report['replays']['on'] == report['replays']['on32'] == report['replays']['on1024'])
                if not report['buffer_outputs_identical']:
                    raise ValueError('ON outputs depend on buffer size')
            save()
        accepted = report['comparison']['gate_pass'] and report.get('buffer_outputs_identical') is True
        report.update(state='completed', final=True, stage=dataset + ' corpus screen complete',
            completed_at=datetime.now(timezone.utc).isoformat(), protected_corpus_pass=accepted,
            strict_match_improvement=report['comparison']['delta']['matched'] > 0,
            verdict=('passed corpus screen' if accepted else 'rejected'))
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        report['log_tails'] = {path.name: path.read_text()[-3000:] for path in out.glob('*.log')}
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=1800, max_containers=1)
def capture_corpus_cue_failure(run_id: str, source_run: str, label_index: int,
                               trace_checkpoint_run: str = ''):
    """Trace one failed passage with the saved binary and full recording history."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.frozen_cue_corpus_gate import read_replay
    from tools.frozen_cue_diagnosis import summarize_cues
    if (any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in
            (run_id, source_run, *([trace_checkpoint_run] if trace_checkpoint_run else [])))
            or label_index < 0):
        raise ValueError('invalid trace source or label')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final')
            or previous.get('verdict') != 'rejected'):
        raise ValueError('source must be a completed rejected corpus screen')
    dataset = previous['dataset']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', dataset):
        raise ValueError('invalid saved corpus name')
    binary_source = previous['source_run']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', binary_source):
        raise ValueError('invalid saved binary source')
    binary = MOUNT / 'results' / binary_source / 'm3_replay'
    corpus = MOUNT / 'corpus'
    wav, labels, calibration = (corpus / name for name in
                               (dataset + '.wav', dataset + '.tsv', 'calibration.m3cb'))
    cues = source / (dataset + '-cues.tsv')
    identities = ((binary, previous['binary_sha256']), (wav, previous['wav_sha256']),
                  (labels, previous['tsv_sha256']), (calibration, previous['calibration_sha256']),
                  (cues, previous['cue_sha256']))
    if any(sha256(path) != expected for path, expected in identities):
        raise ValueError('saved binary, corpus or cues changed')
    targets = {mode: next(row for row in previous['replays'][mode]['labels']
                         if row['label_index'] == label_index) for mode in ('off', 'on')}
    if targets['on']['matched'] >= targets['off']['matched']:
        raise ValueError('selected passage did not lose matches')
    target = targets['off']
    start, end, rate = target['start_sample'], target['end_sample'], previous['sample_rate']
    window_start, window_end = max(0, start - 32768), min(previous['sample_count'], end + 16384)
    with cues.open() as stream:
        if next(stream).strip() != 'm3_frozen_note_cues_v1\t96000\t1024':
            raise ValueError('unknown frozen cue format')
        intervals = [tuple(map(int, line.split('\t'))) for line in stream if line.strip()]
    if len(intervals) != previous['cue_intervals']:
        raise ValueError('cue interval count changed')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, dataset=dataset,
        state='running', final=False, stage='trace paired corpus failure', installed_changed=False,
        started_at=datetime.now(timezone.utc).isoformat(), settings=previous['settings'],
        source_report_sha256=sha256(source / 'report.json'),
        binary_sha256=previous['binary_sha256'],
        saved_input_hashes={path.name: digest for path, digest in identities},
        target=target, window_start=window_start, window_end=window_end,
        sample_count=previous['sample_count'], sample_rate=rate, replays={},
        limits=['Same saved binary, complete audio history and frozen cues; no build or policy change.',
                'Assignment rows are sampled every 16 detector ticks; outcome rows cover every tick.',
                'Annotations select the reported passage only, never detector evidence.'])
    checkpoint = None
    if trace_checkpoint_run:
        checkpoint = MOUNT / 'results' / trace_checkpoint_run
        saved = json.loads((checkpoint / 'report.json').read_text())
        if (saved.get('state') != 'failed' or not saved.get('final')
                or set(saved.get('replays', {})) != {'off'}
                or saved['replays']['off'].get('output_identical') is not True
                or saved['replays']['off'].get('traces')):
            raise ValueError('trace checkpoint must contain only a completed raw OFF replay')
        for key in ('source_run', 'dataset', 'settings', 'source_report_sha256',
                    'binary_sha256', 'saved_input_hashes', 'target', 'window_start',
                    'window_end', 'sample_count', 'sample_rate'):
            if saved.get(key) != report[key]:
                raise ValueError('trace checkpoint differs: ' + key)
        for name in ('off.tsv', 'off.log', 'off-candidate.tsv',
                     'off-outcome.tsv', 'off-assignment.tsv'):
            if not (checkpoint / name).is_file() or not (checkpoint / name).stat().st_size:
                raise ValueError('trace checkpoint missing: ' + name)
        if read_replay(checkpoint / 'off.tsv') != previous['replays']['off']:
            raise ValueError('trace checkpoint OFF output differs from source')
        report['trace_checkpoint'] = dict(run_id=trace_checkpoint_run, reused_mode='off',
            report_sha256=sha256(checkpoint / 'report.json'))

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        for mode in ('off', 'on'):
            report['stage'] = mode + ': trace full recording, summarize failed passage'
            save()
            paths = {kind: out / f'{mode}-{kind}.tsv' for kind in ('candidate', 'outcome', 'assignment')}
            args = [str(binary), '--wav', str(wav), '--labels', str(labels),
                    '--calibration', str(calibration), '--block', '512', '--label-details',
                    '--candidate-trace', str(paths['candidate']),
                    '--candidate-trace-note', str(target['midi_note']),
                    '--candidate-trace-start', str(window_start / rate),
                    '--candidate-trace-end', str(window_end / rate),
                    '--outcome-trace', str(paths['outcome']),
                    '--assignment-trace', str(paths['assignment'])]
            for key, value in previous['settings'].items():
                args += ['--' + key, str(value)]
            if mode == 'on':
                args += ['--diagnostic-odd-partial-cues', str(cues),
                         '--diagnostic-cue-free-lane-reassignment']
            replay, log_path = out / (mode + '.tsv'), out / (mode + '.log')
            reused = mode == 'off' and checkpoint is not None
            if reused:
                paths = {kind: checkpoint / path.name for kind, path in paths.items()}
                for name in (replay.name, log_path.name):
                    shutil.copyfile(checkpoint / name, out / name)
                args = saved['replays']['off']['command']
            else:
                with replay.open('w') as stdout, log_path.open('w') as log:
                    subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=600)
            measured = read_replay(replay)
            if measured != previous['replays'][mode]:
                raise ValueError(mode + ' diagnostics changed the saved corpus output')
            details = dict(output=measured['output'], target=targets[mode], output_identical=True,
                           command=args, reused_trace=reused, trace_counts={}, traces={})
            report['replays'][mode] = details
            for kind in paths:
                pattern = (r'assignment_trace rows=(\d+) cap=(\d+) truncated=(\d+) sampled_frames=(\d+) decimation=(\d+)'
                           if kind == 'assignment' else rf'{kind}_trace frames=(\d+) cap=(\d+) truncated=(\d+)')
                counts = re.findall(pattern, log_path.read_text())
                if len(counts) != 1 or int(counts[0][2]) or int(counts[0][0]) > int(counts[0][1]):
                    raise ValueError('incomplete ' + kind + ' trace accounting')
                details['trace_counts'][kind] = list(map(int, counts[0]))
            with paths['candidate'].open() as c, paths['outcome'].open() as o:
                if next(o).strip() != '# m3_candidate_outcome_v2':
                    raise ValueError('unknown outcome format')
                details['diagnosis'] = summarize_cues(
                    (row for row in csv.DictReader(c, delimiter='\t') if start <= int(row['sample']) < end),
                    csv.DictReader(o, delimiter='\t'), intervals,
                    note=target['midi_note'], start=start, end=end, sample_count=previous['sample_count'],
                    label_index=label_index, string_mask=target['string_mask'])
            joined = details['diagnosis']['all_labeled']
            if joined['frames'] != target['labeled'] or joined['target_matched'] != targets[mode]['matched']:
                raise ValueError('joined trace disagrees with native target scoring')
            for kind, path in paths.items():
                window = out / f'{mode}-{kind}-window.tsv.gz'
                with path.open() as src, gzip.open(window, 'wt', compresslevel=1) as dst:
                    line = next(src)
                    if line.startswith('#'):
                        dst.write(line)
                        line = next(src)
                    dst.write(line)
                    sample_column = line.rstrip('\n').split('\t').index('sample')
                    kept = total_rows = 0
                    for line in src:
                        total_rows += 1
                        sample = int(line.split('\t')[sample_column])
                        if window_start <= sample < window_end:
                            dst.write(line)
                            kept += 1
                if total_rows != details['trace_counts'][kind][0]:
                    raise ValueError('trace file row count differs: ' + kind)
                full = out / (path.name + '.gz')
                details['traces'][kind] = dict(raw_sha256=sha256(path), raw_bytes=path.stat().st_size,
                    window_file=window.name, window_rows=kept, window_sha256=sha256(window))
                with path.open('rb') as src, gzip.open(full, 'wb', compresslevel=1) as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                if not reused:
                    path.unlink()
            save()
        report.update(state='completed', final=True, stage='paired corpus failure traced',
                      completed_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=1800, max_containers=1)
def capture_cue_decisions(run_id: str, source_run: str):
    """Record exact reassignment inputs without changing the saved ON output."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.frozen_cue_corpus_gate import read_replay
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid decision trace source')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final')
            or previous.get('dataset') != 'constructed' or previous.get('verdict') != 'rejected'):
        raise ValueError('expected a completed rejected constructed screen')
    small_run = previous['source_run']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', small_run):
        raise ValueError('invalid saved small-screen source')
    small = MOUNT / 'results' / small_run
    small_report = json.loads((small / 'report.json').read_text())
    if small_report.get('state') != 'completed' or not small_report.get('final'):
        raise ValueError('small screen is incomplete')
    nearby = small_report['datasets']['nearby_0dB']
    corpus = MOUNT / 'corpus'
    calibration = corpus / 'calibration.m3cb'
    cases = {
        'nearby_0dB': dict(wav=small / 'nearby_0dB.wav', labels=small / 'nearby_0dB.tsv',
            cues=small / 'nearby_0dB-cues.tsv', expected=read_replay(small / 'nearby_0dB-on.tsv'),
            hashes=(nearby['audio_sha256'], nearby['labels_sha256'], nearby['cue_sha256']),
            target_sample=44799, target_note=36),
        'constructed': dict(wav=corpus / 'constructed.wav', labels=corpus / 'constructed.tsv',
            cues=source / 'constructed-cues.tsv', expected=previous['replays']['on'],
            hashes=(previous['wav_sha256'], previous['tsv_sha256'], previous['cue_sha256']),
            target_sample=4751551, target_note=49)}
    if sha256(calibration) != previous['calibration_sha256']:
        raise ValueError('saved calibration changed')
    for case in cases.values():
        if any(sha256(case[key]) != digest for key, digest in
               zip(('wav', 'labels', 'cues'), case['hashes'])):
            raise ValueError('saved audio, labels or cues changed')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, small_source_run=small_run,
        state='running', final=False, stage='build exact decision instrumentation',
        installed_changed=False, started_at=datetime.now(timezone.utc).isoformat(),
        settings=previous['settings'], source_report_sha256=sha256(source / 'report.json'),
        small_report_sha256=sha256(small / 'report.json'),
        calibration_sha256=previous['calibration_sha256'], tests={}, datasets={},
        limits=['Offline instrumentation only; the reassignment rule is unchanged.',
                'Every nonzero cue proposal is recorded, plus regular sampled context.',
                'Known good and harmful sample positions select report rows, not detector inputs.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        directory = build(out, detector_tests=True)
        binary = out / 'm3_replay'
        shutil.copy2(directory / 'm3_replay', binary)
        report['binary_sha256'] = sha256(binary)
        report['stage'] = 'native cue and offline trace tests'
        save()
        for name, executable, test_filter in (
                ('cue-free-lane', 'm3_detector_tests', 'native_detector_cue_free_lane'),
                ('offline', 'm3_motion_tests', 'offline_')):
            log_path = out / (name + '-tests.log')
            with log_path.open('w') as log:
                subprocess.run([str(directory / executable)], stdout=log, stderr=subprocess.STDOUT,
                    env=dict(os.environ, M3_TEST_FILTER=test_filter), check=True, timeout=240)
            counts = re.findall(r'Ran (\d+) tests: (\d+) failure\(s\)', log_path.read_text())
            if len(counts) != 1 or int(counts[0][0]) == 0 or int(counts[0][1]):
                raise ValueError('missing or failed native test accounting: ' + name)
            report['tests'][name] = dict(tests=int(counts[0][0]), failures=int(counts[0][1]))
        for name, case in cases.items():
            report['stage'] = name + ': replay unchanged ON policy with decision inputs'
            save()
            trace, replay, log_path = (out / (name + suffix) for suffix in
                                       ('-assignment.tsv', '-on.tsv', '-on.log'))
            args = [str(binary), '--wav', str(case['wav']), '--labels', str(case['labels']),
                    '--calibration', str(calibration), '--block', '512', '--label-details',
                    '--assignment-trace', str(trace), '--diagnostic-odd-partial-cues', str(case['cues']),
                    '--diagnostic-cue-free-lane-reassignment']
            for key, value in previous['settings'].items():
                args += ['--' + key, str(value)]
            with replay.open('w') as stdout, log_path.open('w') as log:
                subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=600)
            measured = read_replay(replay)
            if measured != case['expected']:
                raise ValueError(name + ': instrumentation changed output or per-label counts')
            counts = re.findall(r'assignment_trace rows=(\d+) cap=(\d+) truncated=(\d+) sampled_frames=(\d+) decimation=(\d+)',
                                log_path.read_text())
            if len(counts) != 1 or int(counts[0][2]) or int(counts[0][0]) > int(counts[0][1]):
                raise ValueError(name + ': incomplete assignment trace')
            proposals, target, rows = [], None, 0
            with trace.open() as stream:
                for row in csv.DictReader(stream, delimiter='\t'):
                    rows += 1
                    if int(row['cue_proposal_mask']):
                        proposals.append(row)
                    if int(row['sample']) == case['target_sample'] and int(row['note']) == case['target_note']:
                        target = row
            if rows != int(counts[0][0]) or target is None or not proposals:
                raise ValueError(name + ': missing decision or inconsistent trace row count')
            proposal_path = out / (name + '-proposals.json')
            proposal_path.write_text(json.dumps(proposals, indent=2, allow_nan=False) + '\n')
            compressed = out / (trace.name + '.gz')
            raw_hash, raw_bytes = sha256(trace), trace.stat().st_size
            with trace.open('rb') as src, gzip.open(compressed, 'wb', compresslevel=1) as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            trace.unlink()
            report['datasets'][name] = dict(output=measured['output'], output_identical=True,
                all_labels_identical=True, trace_counts=list(map(int, counts[0])),
                proposal_count=len(proposals), applied_count=sum(int(row['cue_applied']) for row in proposals),
                first_proposal=proposals[0], target_decision=target,
                proposal_file=proposal_path.name, proposal_sha256=sha256(proposal_path),
                trace_file=compressed.name, trace_sha256=sha256(compressed),
                raw_trace_sha256=raw_hash, raw_trace_bytes=raw_bytes, command=args)
            save()
        report.update(state='completed', final=True, stage='exact cue decisions captured; output unchanged',
                      completed_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        report['log_tails'] = {path.name: path.read_text()[-3000:] for path in out.glob('*.log')}
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=1800, max_containers=1)
def capture_native_frozen_cue(run_id: str, source_run: str, pffft: bool = False):
    """Build a standalone native measurement; never run or replace the plugin."""
    import sys
    sys.path.insert(0, '/opt/m3')
    import numpy as np
    from tools.frozen_cue_corpus_gate import read_corpus_wave
    from tools.frozen_cue_native_gate import compare_native_observations, TOLERANCES
    from tools.independent_partial_evidence import CONFIG, FROZEN_SCREEN
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final') or
            not previous.get('accepted_for_corpus_screen') or
            previous.get('config') != CONFIG or previous.get('frozen_screen') != FROZEN_SCREEN):
        raise ValueError('source is not a completed frozen cue replay screen')
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
        experiment='native_frozen_cue', replay_binary_sha256=previous['binary_sha256'],
        fft_backend='pffft-double-avx' if pffft else 'reference-radix2',
        stage='build standalone native measurement', installed_changed=False,
        started_at=datetime.now(timezone.utc).isoformat(), config=CONFIG, frozen_screen=FROZEN_SCREEN,
        source_report_sha256=sha256(source / 'report.json'), numeric_tolerances=TOLERANCES,
        cue_notes=list(range(32, 85)), datasets={}, tests={},
        source_files_sha256={str(path.relative_to('/opt/m3')): sha256(path) for path in [
            *Path('/opt/m3/native/offline').glob('frozen_partial_cue*'),
            Path('/opt/m3/native/tests/test_frozen_partial_cue.cpp'),
            Path('/opt/m3/native/tests/test_support.cpp'),
            Path('/opt/m3/native/tests/offline_test_main.cpp'),
            Path('/opt/m3/tools/frozen_cue_native_gate.py'),
            Path('/opt/m3/tools/independent_partial_evidence.py')]},
        limits=['Standalone cue timing excludes detector and plugin work.',
                'Modal CPU timing is not a live-host deadline guarantee.',
                'The causal measurement window remains 170.7 ms at 96 kHz.',
                'This probe is not linked into either installed plugin.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    save()
    try:
        vendor = Path('/opt/m3/native/offline/vendor/pffft')
        if pffft:
            cpu = Path('/proc/cpuinfo').read_text()
            features = re.search(r'^flags\s*:\s*(.*)$', cpu, re.M)
            if not features or 'avx' not in features[1].split():
                raise ValueError('AVX is required for this standalone FFT experiment')
            model = re.search(r'^model name\s*:\s*(.*)$', cpu, re.M)
            report['cpu_model'] = model[1] if model else 'not reported'
            upstream = json.loads((vendor / 'UPSTREAM.json').read_text())
            if upstream['commit'] != '7ae36e8c1d352cba66231de953cfa35f235b9e7a':
                raise ValueError('unexpected PFFFT revision')
            for relative, digest in upstream['files_sha256'].items():
                path = vendor / relative
                if not path.resolve().is_relative_to(vendor) or sha256(path) != digest:
                    raise ValueError('vendored PFFFT source changed: ' + relative)
            report['fft_upstream'] = upstream
            for path in [vendor / 'UPSTREAM.json',
                         Path('/opt/m3/native/tests/offline_c_allocation_guard.cpp'),
                         Path('/opt/m3/native/tests/offline_c_allocation_guard.hpp')]:
                report['source_files_sha256'][str(path.relative_to('/opt/m3'))] = sha256(path)
            report['limits'].append('Fixed workspace size excludes the opaque FFT setup; setup OOM handling is unverified.')
        flags = ['g++', '-std=c++17', '-O2', '-DNDEBUG', '-Wall', '-Wextra', '-Wpedantic',
                 '-Wconversion', '-Wshadow', '-Werror', '-fno-exceptions', '-fno-rtti',
                 '-fstack-protector-strong', '-fvisibility=hidden',
                 '-I/opt/m3/native/offline', '-I/opt/m3/native/tests']
        if pffft:
            flags += ['-mavx', '-ffp-contract=off', '-DM3_FROZEN_CUE_PFFFT=1',
                      '-DPFFFT_STATIC_DEFINE', '-I' + str(vendor / 'include/pffft')]
        report['compiler_flags'] = flags
        obj = out / 'frozen_partial_cue.o'
        probe, tests = out / 'm3_frozen_cue_probe', out / 'm3_frozen_cue_tests'
        library_objects = []
        with (out / 'build.log').open('w') as log:
            if pffft:
                cflags = ['gcc', '-std=gnu99', '-O2', '-DNDEBUG', '-mavx', '-ffp-contract=off',
                          '-DPFFFT_STATIC_DEFINE', '-I' + str(vendor / 'include/pffft')]
                report['fft_compiler_flags'] = cflags
                for stem in ('pffft_double', 'pffft_common'):
                    target = out / (stem + '.o')
                    subprocess.run(cflags + ['-c', str(vendor / 'src' / (stem + '.c')),
                                   '-o', str(target)], stdout=log, stderr=subprocess.STDOUT,
                                   check=True, timeout=120)
                    library_objects.append(str(target))
            subprocess.run(flags + ['-c', '/opt/m3/native/offline/frozen_partial_cue.cpp',
                           '-o', str(obj)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            for executable, sources in (
                    (probe, ['native/offline/frozen_partial_cue_main.cpp']),
                    (tests, ['native/tests/test_frozen_partial_cue.cpp',
                             'native/tests/test_support.cpp', 'native/tests/offline_test_main.cpp'])):
                extra = []
                if pffft and executable == tests:
                    sources += ['native/tests/offline_c_allocation_guard.cpp']
                    extra = ['-DM3_OFFLINE_C_ALLOCATION_GUARD=1'] + [
                        '-Wl,--wrap=' + name for name in
                        ('malloc', 'calloc', 'realloc', 'aligned_alloc', 'posix_memalign', 'free')]
                subprocess.run(flags + extra + [str(obj)] + library_objects
                               + ['/opt/m3/' + name for name in sources]
                               + ['-pthread', '-lm', '-o', str(executable)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        report['binary_sha256'] = sha256(probe)
        report['stage'] = 'native boundary, clock and allocation tests'
        save()
        with (out / 'tests.log').open('w') as log:
            subprocess.run([str(tests)], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        summaries = re.findall(r'Ran (\d+) tests: (\d+) failure\(s\)', (out / 'tests.log').read_text())
        if len(summaries) != 1 or int(summaries[0][0]) != (5 if pffft else 4) or int(summaries[0][1]) != 0:
            raise ValueError('missing successful native test accounting')
        report['tests'] = dict(count=int(summaries[0][0]), failures=0,
                               allocation_coverage='C++ operators and linked C functions' if pffft else 'C++ operators',
                               log_sha256=sha256(out / 'tests.log'))
        for name, saved in previous['datasets'].items():
            if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
                raise ValueError('invalid case name')
            wav = source / (name + '.wav')
            if sha256(wav) != saved['audio_sha256']:
                raise ValueError('saved audio changed: ' + name)
            rate, values = read_corpus_wave(wav)
            if rate != 96000 or len(values) != saved['sample_count']:
                raise ValueError('saved audio clock changed: ' + name)
            samples = np.asarray(values, dtype='<f4')
            if hashlib.sha256(samples.tobytes()).hexdigest() != saved['samples_sha256']:
                raise ValueError('saved samples changed: ' + name)
            raw, observations, cues, timing = (out / (name + suffix) for suffix in
                ('.f32', '-native.tsv', '-native-cues.tsv', '-timing.json'))
            samples.tofile(raw)
            report['stage'] = name + ': native measurement and frozen-reference comparison'
            save()
            with (out / (name + '.log')).open('w') as log:
                subprocess.run([str(probe), str(raw), str(observations), str(cues), str(timing)],
                    stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            comparison = compare_native_observations(samples, observations, cues)
            measured = json.loads(timing.read_text())
            if (measured['sample_count'] != len(samples) or measured['sample_rate'] != rate
                    or measured['block_size'] != 32):
                raise ValueError('native timing clock mismatch')
            measured['standalone_budget_pass'] = (measured['block_p99_ns'] <= measured['p99_budget_ns']
                and measured['block_max_ns'] <= measured['block_deadline_ns'])
            report['datasets'][name] = dict(sample_count=len(samples), sample_rate=rate,
                samples_sha256=saved['samples_sha256'], observations_sha256=sha256(observations),
                cues_sha256=sha256(cues), comparison=comparison, timing=measured)
            save()
        report['parity_pass'] = all(item['comparison']['parity_pass'] for item in report['datasets'].values())
        report['standalone_timing_pass'] = all(item['timing']['standalone_budget_pass'] for item in report['datasets'].values())
        report.update(state='completed', final=True, stage='native cue parity and timing complete',
            completed_at=datetime.now(timezone.utc).isoformat(),
            verdict=('native parity and standalone timing passed; host integration unverified'
                     if report['parity_pass'] and report['standalone_timing_pass'] else
                     'rejected for audio callback: native parity or timing gate failed'))
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        logs = sorted(out.glob('*.log'), key=lambda path: path.stat().st_mtime)[-3:]
        report['log_tails'] = {path.name: path.read_text()[-4000:] for path in logs}
    save()
    return report


@app.function(image=image, volumes={str(MOUNT): volume}, cpu=2, memory=4096,
              timeout=1800, max_containers=1)
def capture_delayed_frozen_cues(run_id: str, source_run: str):
    """Test one fixed scheduling delay with the saved binary; no build or sweep."""
    import sys
    sys.path.insert(0, '/opt/m3')
    from tools.controlled_admission_gate import CASES, FIELDS, evaluate_admission, read_target_detail
    from tools.independent_partial_evidence import CONFIG, FROZEN_SCREEN
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value) for value in (run_id, source_run)):
        raise ValueError('invalid run identifier')
    source = MOUNT / 'results' / source_run
    previous = json.loads((source / 'report.json').read_text())
    if (previous.get('state') != 'completed' or not previous.get('final') or
            not previous.get('accepted_for_corpus_screen') or
            not previous.get('cue_free_lane_reassignment') or
            previous.get('config') != CONFIG or previous.get('frozen_screen') != FROZEN_SCREEN):
        raise ValueError('source is not an accepted frozen string-correction screen')
    binary, calibration = source / 'm3_replay', MOUNT / 'corpus/calibration.m3cb'
    if sha256(binary) != previous['binary_sha256'] or sha256(calibration) != previous['calibration_sha256']:
        raise ValueError('saved binary or calibration changed')
    expected_cases = set(CASES) | {name + '_source_only' for name in CASES if name != 'solo'} | {'silence'}
    if set(previous['datasets']) != expected_cases:
        raise ValueError('controlled case coverage changed')
    delay = 1024
    out = MOUNT / 'results' / run_id
    out.mkdir(exist_ok=False, parents=True)
    report = dict(run_id=run_id, source_run=source_run, state='running', final=False,
        experiment='delayed_frozen_cue', stage='prepare fixed one-hop cue delay',
        started_at=datetime.now(timezone.utc).isoformat(), installed_changed=False,
        source_report_sha256=sha256(source / 'report.json'),
        binary_sha256=previous['binary_sha256'], calibration_sha256=previous['calibration_sha256'],
        config=CONFIG, frozen_screen=FROZEN_SCREEN, settings=previous['settings'],
        availability_delay_samples=delay, availability_delay_ms=1000.0 * delay / 96000,
        cue_duration_samples=1024, controls_reused=True, datasets={},
        limits=['Saved cue intervals are shifted by one hop, including their expiry.',
                'The measurement window is unchanged; cue evidence is one hop older.',
                'OFF and unit-test evidence are reused from the identical saved binary.',
                'This delay screen neither implements nor times an incremental FFT.',
                'No installed or live-host behavior changes.'])

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        volume.commit()

    def replay(name, block, mode):
        args = [str(binary), '--wav', str(source / (name + '.wav')),
                '--labels', str(source / (name + '.tsv')), '--calibration', str(calibration),
                '--block', str(block), '--label-details', '--diagnostic-odd-partial-cues',
                str(out / (name + '-cues.tsv')), '--diagnostic-cue-free-lane-reassignment']
        for key, value in previous['settings'].items():
            args += ['--' + key, str(value)]
        output = out / f'{name}-{mode}.tsv'
        with output.open('w') as stdout, (out / f'{name}-{mode}.log').open('w') as log:
            subprocess.run(args, stdout=stdout, stderr=log, check=True, timeout=180)
        result = dict(output=aggregate(output))
        if previous['datasets'][name]['has_target']:
            result['target'] = read_target_detail(output)
        return result

    save()
    try:
        for name, saved in previous['datasets'].items():
            for suffix, key in (('.wav', 'audio_sha256'), ('.tsv', 'labels_sha256'),
                                ('-cues.tsv', 'cue_sha256')):
                if sha256(source / (name + suffix)) != saved[key]:
                    raise ValueError(name + ': saved input changed')
            if not saved['control_identical'] or not saved['buffer_outputs_identical']:
                raise ValueError(name + ': original control or buffer checks failed')
            old_off = dict(output=aggregate(source / (name + '-off.tsv')))
            if saved['has_target']:
                old_off['target'] = read_target_detail(source / (name + '-off.tsv'))
            if old_off != saved['replays']['off']:
                raise ValueError(name + ': saved OFF evidence changed')
            intervals, original_count, last = [], 0, (-1, -1)
            with (source / (name + '-cues.tsv')).open() as stream:
                if next(stream).rstrip('\n') != 'm3_frozen_note_cues_v1\t96000\t1024':
                    raise ValueError('unexpected cue clock')
                for line in stream:
                    begin, end, note = map(int, line.split())
                    if (not 0 <= begin < end <= saved['sample_count'] or
                            begin % 1024 or end != min(begin + 1024, saved['sample_count']) or
                            not 32 <= note <= 84 or (begin, note) <= last):
                        raise ValueError(name + ': malformed original cue')
                    last = (begin, note)
                    original_count += 1
                    shifted = begin + delay
                    if shifted < saved['sample_count']:
                        intervals.append((shifted, min(end + delay, saved['sample_count']), note))
            if original_count != saved['cue_intervals']:
                raise ValueError(name + ': original cue accounting changed')
            cues = out / (name + '-cues.tsv')
            cues.write_text('m3_frozen_note_cues_v1\t96000\t1024\n' + ''.join(
                f'{begin}\t{end}\t{note}\n' for begin, end, note in intervals))
            item = dict(sample_rate=96000, sample_count=saved['sample_count'],
                has_target=saved['has_target'], cue_intervals=len(intervals), cue_sha256=sha256(cues),
                original_cue_sha256=saved['cue_sha256'], control_identical=True,
                buffer_outputs_identical=False,
                replays={key: saved['replays'][key] for key in ('baseline', 'off')})
            report['datasets'][name] = item
            report['stage'] = name + ': delayed cue replay, block 512'
            save()
            item['replays']['on'] = replay(name, 512, 'on')
            old, new = saved['replays']['on'], item['replays']['on']
            if old['output']['labeled'] != new['output']['labeled']:
                raise ValueError(name + ': label accounting changed')
            delta = {key: int(new['output'][key]) - int(old['output'][key]) for key in FIELDS}
            target_delta = new['target']['matched'] - old['target']['matched'] if saved['has_target'] else 0
            item.update(delta_against_undelayed=delta, target_delta_against_undelayed=target_delta,
                undelayed_gain_preserved=target_delta >= 0 and delta['matched'] >= 0
                    and all(delta[key] <= 0 for key in FIELDS[1:]))
            if not saved['has_target']:
                off, on = (item['replays'][mode]['output'] for mode in ('off', 'on'))
                item['delta'] = {key: int(on[key]) - int(off[key]) for key in FIELDS}
                item['gate_pass'] = item['delta']['matched'] >= 0 and all(
                    item['delta'][key] <= 0 for key in FIELDS[1:])
            save()
        gate = evaluate_admission({name: report['datasets'][name] for name in CASES})
        for name, result in gate.pop('cases').items():
            report['datasets'][name].update(result)
        negative_regressions = [name for name, item in report['datasets'].items()
                                if not item['has_target'] and not item['gate_pass']]
        lost_gains = [name for name, item in report['datasets'].items() if not item['undelayed_gain_preserved']]
        gate['negative_regressions'], gate['lost_undelayed_gains'] = negative_regressions, lost_gains
        gate['accepted_for_corpus_screen'] &= not negative_regressions and not lost_gains
        if gate['accepted_for_corpus_screen']:
            for name, item in report['datasets'].items():
                for block in (32, 1024):
                    report['stage'] = f'{name}: delayed cue buffer check, block {block}'
                    save()
                    item['replays']['on' + str(block)] = replay(name, block, 'on' + str(block))
                item['buffer_outputs_identical'] = item['replays']['on32'] == item['replays']['on'] == item['replays']['on1024']
                if not item['buffer_outputs_identical']:
                    raise ValueError(name + ': delayed cue buffer invariance failed')
                save()
        gate['verdict'] = ('fixed one-hop delay preserves all demonstrated gains; native scheduling remains unverified'
                           if gate['accepted_for_corpus_screen'] else 'rejected: fixed delay loses matches or exceeds error limits')
        report.update(state='completed', final=True, stage='fixed cue delay screen complete',
                      completed_at=datetime.now(timezone.utc).isoformat(), **gate)
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        report['log_tails'] = {path.name: path.read_text()[-3000:]
                              for path in sorted(out.glob('*.log'))[-3:]}
    save()
    return report


@app.local_entrypoint()
def main(run_id: str, source_run: str = '', string_evidence: bool = False,
         controlled_overlap: bool = False, selection_source: str = '',
         admission_source: str = '', cue_source: str = '', cue_selection_source: str = '',
         cue_free_lane: bool = False, cue_corpus_source: str = '',
         cue_corpus_dataset: str = 'ordinary', cue_corpus_trace_source: str = '',
         cue_corpus_trace_label: int = -1, cue_checkpoint_run: str = '',
         cue_trace_checkpoint_run: str = '', cue_decision_source: str = '',
         reuse_cue_features: bool = False, native_cue_source: str = '', delayed_cue_source: str = '',
         native_cue_pffft: bool = False):
    if native_cue_pffft and not native_cue_source:
        raise ValueError('PFFFT requires a standalone native cue source')
    if cue_free_lane and not cue_source:
        raise ValueError('free-lane reassignment requires a frozen cue source')
    if cue_checkpoint_run and not cue_corpus_source:
        raise ValueError('cue checkpoint requires a corpus screen')
    if reuse_cue_features and not (cue_checkpoint_run and cue_corpus_source):
        raise ValueError('feature reuse requires a corpus screen and saved cue checkpoint')
    if cue_trace_checkpoint_run and not cue_corpus_trace_source:
        raise ValueError('trace checkpoint requires a corpus failure diagnosis')
    if (bool(source_run) + string_evidence + controlled_overlap + bool(selection_source)
            + bool(admission_source) + bool(cue_source) + bool(cue_selection_source)
            + bool(cue_corpus_source) + bool(cue_corpus_trace_source) + bool(cue_decision_source)
            + bool(native_cue_source) + bool(delayed_cue_source)) > 1:
        raise ValueError('select one analysis or capture job')
    result = (capture_delayed_frozen_cues.remote(run_id, delayed_cue_source) if delayed_cue_source else
              capture_native_frozen_cue.remote(run_id, native_cue_source, native_cue_pffft) if native_cue_source else
              capture_cue_decisions.remote(run_id, cue_decision_source) if cue_decision_source else
              capture_corpus_cue_failure.remote(run_id, cue_corpus_trace_source,
              cue_corpus_trace_label, cue_trace_checkpoint_run) if cue_corpus_trace_source else
              capture_frozen_cue_corpus.remote(run_id, cue_corpus_source, cue_corpus_dataset,
              cue_checkpoint_run, reuse_cue_features) if cue_corpus_source else
              capture_frozen_cue_selection.remote(run_id, cue_selection_source) if cue_selection_source else
              capture_frozen_partial_cues.remote(run_id, cue_source, cue_free_lane) if cue_source else
              capture_controlled_admission.remote(run_id, admission_source) if admission_source else
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
