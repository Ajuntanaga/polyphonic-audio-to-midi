"""Paired production-shaped VST3 observation in REAPER, GitHub CPU only."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tarfile
import time

from tools.portable_neural_reaper_host import digest, read_metrics, run_capture, verify


def check_compile_modes(entries):
    """A same-binary comparison or an offline-policy build must fail closed."""
    modes = {}
    for target, batch in (
        ('m3_vst3_production', False), ('m3_vst3_batch_cell_lab', True),
        ('m3_vst3_realtime_tests', False), ('m3_batch_cell_realtime_tests', True),
    ):
        found = []
        for entry in entries:
            args = entry.get('arguments') or shlex.split(entry['command'])
            if (entry['file'].endswith('/polyphonic_pitch_detector.cpp')
                    and any(f'CMakeFiles/{target}.dir/' in arg for arg in args)):
                found.append(args)
        if len(found) != 1:
            raise ValueError(f'Expected one detector compile command for {target}')
        definitions = sorted(arg[2:] for arg in found[0] if arg.startswith('-D'))
        keys = {item.split('=')[0] for item in definitions}
        forbidden = {key for key in keys if key.startswith('M3_OFFLINE_')
                     or key in {'M3_SPECTRAL_TIER_DIAGNOSTICS',
                                'M3_UNISON_SPECTRAL_SHADOW', 'M3_JOINT_RESIDUAL_SHADOW'}}
        if forbidden or ('M3_BATCH_CELL_LAB' in keys) != batch:
            raise ValueError(f'Unexpected detector compile mode for {target}: {definitions}')
        modes[target] = definitions
    return modes


def ordinary_rows(events, sample_count):
    return [row for row in events
            if row['phase'] == 1 and 0 <= row['sample'] < sample_count]


def evaluate_arm(metrics, events, sample_count):
    active = set()
    duplicate_ons = unmatched_offs = panic_ons = invalid_events = 0
    for row in events:
        kind, channel = row['status'] & 0xf0, row['status'] & 15
        key = channel, row['note']
        if not (0 <= row['status'] <= 255 and 0 <= row['note'] <= 127
                and 0 <= row['velocity'] <= 127 and 0 <= row['offset'] < 512
                and row['phase'] in (1, 2, 3)):
            invalid_events += 1
        if kind == 0x90 and row['velocity'] > 0:
            duplicate_ons += key in active
            active.add(key)
            panic_ons += row['phase'] == 3
        elif kind == 0x80 or (kind == 0x90 and row['velocity'] == 0):
            unmatched_offs += key not in active
            active.discard(key)
    ordinary = ordinary_rows(events, sample_count)
    note_ons = sum((row['status'] & 0xf0) == 0x90 and row['velocity'] > 0
                   for row in ordinary)
    duration = sample_count / 96000
    gates = {
        'host_and_script_completed': metrics.get('host_exit') == 0
                                    and metrics.get('failure_count') == 0,
        'audio_engine_started': metrics.get('audio_running_at_play', 0) != 0
                                and 'JACK' in str(metrics.get('audio_mode', '')).upper(),
        'rate_and_block': metrics.get('sample_rate') == 96000
                          and metrics.get('block_size') == 512
                          and metrics.get('max_block') == 512,
        'full_recording': metrics.get('recorded_samples') == sample_count
                          and metrics.get('last_recorded_sample') == sample_count
                          and metrics.get('recording_discontinuities') == 0,
        'real_time_pacing': duration <= metrics.get('ordinary_wall_seconds', -1) <= duration + 6,
        'dry_identity': metrics.get('dry_max_error') == 0
                        and metrics.get('dry_changed_samples') == 0
                        and metrics.get('dry_samples', 0) >= sample_count
                        and metrics.get('input_peak', 0) > 0
                        and metrics.get('nonfinite') == 0,
        'capture_complete': metrics.get('overflow') == 0
                            and metrics.get('event_count') == len(events)
                            and invalid_events == 0,
        'ordinary_host_midi_received': note_ons > 0,
        'production_defaults': metrics.get('parameter_image_matches') == 1,
        'state_restored': abs(metrics.get('restored_trim', -1) - .625) < 1e-5,
        'panic_exercised_and_released': metrics.get('panic_before_active', 0) > 0
                                       and metrics.get('panic_after_active') == 0
                                       and metrics.get('panic_ready') == 0
                                       and metrics.get('final_active') == 0
                                       and not active and panic_ons == 0,
    }
    return dict(gates=gates, passed=all(gates.values()),
                ordinary_events=len(ordinary), ordinary_note_ons=note_ons,
                raw_pairing=dict(duplicate_ons=duplicate_ons, unmatched_offs=unmatched_offs,
                                 final_open=len(active), panic_note_ons=panic_ons,
                                 interpretation='Descriptive; scalar pairing defects are not repaired by batching.'))


def compare_arms(scalar, batch, sample_count):
    left, right = (ordinary_rows(rows, sample_count) for rows in (scalar, batch))
    mismatch = next((i for i in range(min(len(left), len(right)))
                     if left[i] != right[i]), None)
    if mismatch is None and len(left) != len(right):
        mismatch = min(len(left), len(right))
    return dict(passed=bool(left) and mismatch is None,
                scalar_events=len(left), batch_events=len(right),
                first_mismatch=None if mismatch is None else dict(
                    index=mismatch,
                    scalar=left[mismatch] if mismatch < len(left) else None,
                    batch=right[mismatch] if mismatch < len(right) else None),
                compared_fields=['phase', 'sample', 'offset', 'status', 'note', 'velocity'],
                time_shift_samples=0, tolerance_samples=0)


def host_config(spec, arm, wav, output):
    parameters = ','.join('{' + json.dumps(name) + ',' + repr(value) + '}'
                          for name, value in spec['parameters_normalized'].items())
    return ('return {wav=' + json.dumps(str(wav)) + ',output=' + json.dumps(str(output))
            + ',samples=' + str(spec['recording']['samples'])
            + ',plugin=' + json.dumps(arm['plugin']) + ',parameters={' + parameters + '}}\n')


def stop_process(proc):
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def observe_arm(root, spec, arm, executable, wav, build, scratch, logs, bulk, env):
    name = arm['name']
    logs, bulk, scratch = logs/name, bulk/name, scratch/name
    for folder in (logs, bulk, scratch):
        folder.mkdir()
    vst = scratch/'vst'
    vst.mkdir()
    package = arm['package']
    bundle = build/'VST3'/f'{package}.vst3'
    binary = bundle/'Contents/x86_64-linux'/f'{package}.so'
    if not binary.is_file():
        raise FileNotFoundError(f'Built bundle missing: {binary}')
    shutil.copytree(bundle, vst/bundle.name)
    archive = bulk/f'{package}.vst3.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(bundle, arcname=bundle.name)
    profile = scratch/'profile'
    (profile/'Effects').mkdir(parents=True)
    (profile/'Scripts').mkdir()
    for part in ('input', 'capture'):
        shutil.copy2(root/f'Effects/tests/m3_neural_host_{part}.jsfx', profile/'Effects')
    script = profile/'Scripts/m3_batch_cell_host.lua'
    shutil.copy2(root/'Scripts/tests/m3_batch_cell_host.lua', script)
    (profile/'reaper.ini').write_text(
        '[reaper]\nlinux_audio_bsize=512\nlinux_audio_bufs=2\nlinux_audio_mode=0\n'
        'linux_audio_nch_in=0\nlinux_audio_nch_out=2\nlinux_audio_srate=96000\n'
        'audiocloseinactive=0\naudioclosestop=0\nnewprojdo=0\nsaveFlags=0\n'
        'warnmaxram64=0\nvstpath=' + str(vst) + '\n')
    shutil.copy2(profile/'reaper.ini', logs/'reaper-before.ini')
    (profile/'host_config.lua').write_text(host_config(spec, arm, wav, bulk))
    run_capture(['luac', '-p', str(script)], logs/'lua-syntax.log')
    run_capture(['luac', '-p', str(profile/'host_config.lua')], logs/'config-syntax.log')
    env = dict(env, XDG_CONFIG_HOME=str(scratch/'xdg'))
    command = [str(executable), '-newinst', '-noactivate', '-cfgfile',
               str(profile/'reaper.ini'), '-nosplash', str(script)]
    proc = None
    try:
        with (logs/'reaper.log').open('wb') as logfile:
            proc = subprocess.Popen(command, stdout=logfile, stderr=subprocess.STDOUT, env=env)
            try:
                proc.wait(timeout=210)
            except subprocess.TimeoutExpired:
                run_capture(['xwininfo', '-root', '-tree'], logs/'windows-at-timeout.txt',
                            env=env, timeout=10)
                raise RuntimeError(f'{name} REAPER observation timed out')
    finally:
        stop_process(proc)
        if (profile/'reaper.ini').is_file():
            shutil.copy2(profile/'reaper.ini', logs/'reaper-after.ini')
        for filename in ('phase.log', 'failures.txt', 'metrics.tsv'):
            if (bulk/filename).is_file():
                shutil.copy2(bulk/filename, logs/filename)
    metrics = read_metrics(bulk/'metrics.tsv')
    metrics['host_exit'] = proc.returncode
    with (bulk/'events.tsv').open() as stream:
        events = [{key: int(value) for key, value in row.items()}
                  for row in csv.DictReader(stream, delimiter='\t')]
    return dict(command=command, metrics=metrics,
                result=evaluate_arm(metrics, events, spec['recording']['samples']),
                binary_sha256=digest(binary), bundle_archive_sha256=digest(archive),
                event_evidence=dict(path=f'{name}/events.tsv', sha256=digest(bulk/'events.tsv'),
                                    bytes=(bulk/'events.tsv').stat().st_size)), events


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--build', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload'):
        raise RuntimeError('Native/audio execution requires the authorized GitHub worker')
    root = Path(__file__).resolve().parents[1]
    spec = json.loads(args.spec.read_text())
    if [arm['name'] for arm in spec['arms']] != ['scalar', 'batch']:
        raise ValueError('Frozen paired arm order differs')
    build, output = args.build.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs, bulk, report_dir = (output/name for name in ('logs', 'bulk', 'report'))
    for directory in (logs, bulk, report_dir):
        directory.mkdir()
    scratch = Path(os.environ['RUNNER_TEMP'])/'m3-batch-cell-host'
    scratch.mkdir(exist_ok=False)
    report = dict(schema='m3_batch_cell_host_v1', final=False, stage='compile-mode check',
                  specification=spec, specification_sha256=digest(args.spec), arms={},
                  source_commit=os.environ['SOURCE_SHA'], worker_commit=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], platform=platform.platform(),
                  interpretation='Real REAPER on dummy audio; production-shaped scalar/batch comparison. No installed, device, live-guitar, acoustic re-pluck or note-quality acceptance.')

    def save():
        (report_dir/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')

    try:
        save()
        report['compile_modes'] = check_compile_modes(json.loads((build/'compile_commands.json').read_text()))
        report['stage'] = 'pinned acquisition'
        save()
        inputs = scratch/'inputs'
        inputs.mkdir()
        run_capture(['gh', 'release', 'download', spec['inputs']['tag'], '--repo',
                     'Ajuntanaga/m3-offload', '--pattern', 'recovery-inputs.tar.gz',
                     '--dir', str(inputs)], logs/'inputs-download.log')
        verify(inputs/'recovery-inputs.tar.gz', spec['inputs']['sha256'])
        with tarfile.open(inputs/'recovery-inputs.tar.gz') as tar:
            tar.extractall(inputs, filter='data')
        verify(inputs/'recovery-inputs.json', spec['inputs']['manifest_sha256'])
        wav = inputs/'corpus/ordinary.wav'
        verify(wav, spec['recording']['sha256'])
        reaper_tar = scratch/'reaper.tar.xz'
        run_capture(['curl', '--fail', '--location', '--max-time', '120', spec['reaper']['url'],
                     '--output', str(reaper_tar)], logs/'reaper-download.log')
        verify(reaper_tar, spec['reaper']['sha256'])
        with tarfile.open(reaper_tar) as tar:
            tar.extractall(scratch, filter='data')
        executable = scratch/'reaper_linux_x86_64/REAPER/reaper'
        if not executable.is_file():
            raise ValueError('Official REAPER layout differs')
        env = dict(os.environ, DISPLAY=':99', JACK_DEFAULT_SERVER='m3-batch-host',
                   JACK_NO_START_SERVER='1')
        xvfb = jack = None
        with (logs/'xvfb.log').open('wb') as xf, (logs/'jack.log').open('wb') as jf:
            try:
                xvfb = subprocess.Popen(['Xvfb', ':99', '-screen', '0', '1280x800x24',
                                         '-nolisten', 'tcp'], stdout=xf, stderr=subprocess.STDOUT, env=env)
                command = ['jackd', '--no-realtime', '--name', 'm3-batch-host', '-d', 'dummy',
                           '--rate', '96000', '--period', '512', '--wait', '5333',
                           '--capture', '0', '--playback', '2']
                report['audio_server_command'] = command
                save()
                jack = subprocess.Popen(command, stdout=jf, stderr=subprocess.STDOUT, env=env)
                time.sleep(2)
                if jack.poll() is not None or xvfb.poll() is not None:
                    raise RuntimeError('Isolated host services exited; see logs')
                run_capture(['jack_lsp'], logs/'jack-ports-before.txt', env=env, timeout=10)
                captured = {}
                for arm in spec['arms']:
                    report['stage'] = 'real REAPER playback: ' + arm['name']
                    save()
                    result, events = observe_arm(root, spec, arm, executable, wav, build,
                                                 scratch, logs, bulk, env)
                    report['arms'][arm['name']] = result
                    captured[arm['name']] = events
                    save()
                report['identity'] = compare_arms(captured['scalar'], captured['batch'],
                                                   spec['recording']['samples'])
            finally:
                stop_process(jack)
                stop_process(xvfb)
        passed = report['identity']['passed'] and all(
            arm['result']['passed'] for arm in report['arms'].values())
        report.update(state='completed', final=True, stage='paired host observation complete', passed=passed)
        save()
        print(json.dumps(dict(passed=passed, identity=report['identity']), sort_keys=True), flush=True)
        return 0 if passed else 2
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
