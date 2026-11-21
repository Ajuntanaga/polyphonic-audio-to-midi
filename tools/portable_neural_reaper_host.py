"""One isolated real-time REAPER host observation, GitHub CPU execution only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time
import zipfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def verify(path, expected):
    if digest(path) != expected:
        raise ValueError(f'Hash differs: {Path(path).name}')


def run_capture(command, output, *, env=None, timeout=180):
    """Retain command output before interpreting status or content."""
    with Path(output).open('wb') as stdout, Path(str(output)+'.stderr').open('wb') as stderr:
        result = subprocess.run(command, stdout=stdout, stderr=stderr, env=env,
                                timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f'{command[0]} exit {result.returncode}; see {Path(output).name}')


def read_metrics(path):
    result = {}
    with path.open() as f:
        for row in csv.DictReader(f, delimiter='\t'):
            try:
                result[row['metric']] = float(row['value'])
            except ValueError:
                result[row['metric']] = row['value']
    return result


def evaluate(metrics, events, sample_count):
    active = set()
    duplicate_ons = unmatched_offs = note_ons = ordinary_ons = panic_ons = 0
    invalid_events = 0
    for row in events:
        kind, channel = row['status'] & 0xf0, row['status'] & 15
        key = channel, row['note']
        if not (0 <= row['note'] <= 127 and 0 <= row['velocity'] <= 127
                and 0 <= row['offset'] < 1024):
            invalid_events += 1
        if kind == 0x90 and row['velocity'] > 0:
            note_ons += 1
            ordinary_ons += row['phase'] == 1
            panic_ons += row['phase'] == 3
            duplicate_ons += key in active
            active.add(key)
        elif kind == 0x80 or (kind == 0x90 and row['velocity'] == 0):
            unmatched_offs += key not in active
            active.discard(key)
    duration = sample_count / 96000
    gates = {
        'script_completed': metrics.get('failure_count') == 0,
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
        'host_midi_received': ordinary_ons > 0,
        'default_gate_off': metrics.get('default_gate') == 0
                            and abs(metrics.get('default_threshold', -1) - .5) < 1e-5,
        'state_restored': metrics.get('restored_gate') == 1
                          and abs(metrics.get('restored_threshold', -1) - .6) < 1e-5,
        'panic_exercised_and_released': metrics.get('panic_before_active', 0) > 0
                                       and metrics.get('panic_after_active') == 0
                                       and not active and panic_ons == 0,
        'raw_midi_pairing': duplicate_ons == 0 and unmatched_offs == 0,
    }
    return dict(gates=gates, passed=all(gates.values()),
                midi=dict(note_ons=note_ons, ordinary_note_ons=ordinary_ons,
                          panic_note_ons=panic_ons, duplicate_ons=duplicate_ons,
                          unmatched_offs=unmatched_offs, final_open=len(active)))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args(argv)
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise RuntimeError('Native/audio execution is restricted to the authorized GitHub worker')
    root = Path(__file__).resolve().parents[1]
    spec = json.loads(args.spec.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    logs, bulk, report_dir = (output / n for n in ('logs', 'bulk', 'report'))
    for directory in (logs, bulk, report_dir):
        directory.mkdir()
    scratch = Path(os.environ['RUNNER_TEMP']) / 'm3-reaper-host'
    scratch.mkdir(exist_ok=False)
    report = dict(schema='m3_reaper_host_v1', final=False, stage='acquisition',
                  specification=spec, specification_sha256=digest(args.spec),
                  source_commit=os.environ['SOURCE_SHA'], worker_commit=os.environ['GITHUB_SHA'],
                  run_id=os.environ['GITHUB_RUN_ID'], platform=platform.platform(),
                  interpretation='Real REAPER host, dummy audio on GitHub CPU; no device, live guitar, latency, musical-quality, or installed acceptance claim.')
    def save():
        (report_dir/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    try:
        save()
        archive = scratch/'package.zip'
        run_capture(['gh','api',f"repos/Ajuntanaga/m3-offload/actions/artifacts/{spec['package']['artifact_id']}/zip"],archive)
        verify(archive,spec['package']['sha256'])
        with zipfile.ZipFile(archive) as z:
            matches=[n for n in z.namelist() if n.endswith('/M3_Neural_Lab.vst3.tar.gz') or n=='M3_Neural_Lab.vst3.tar.gz']
            if len(matches)!=1: raise ValueError('Package archive member ambiguous')
            bundle_tar=scratch/'bundle.tar.gz';bundle_tar.write_bytes(z.read(matches[0]))
        vst=scratch/'vst';vst.mkdir()
        with tarfile.open(bundle_tar) as t: t.extractall(vst,filter='data')
        bundle=vst/'M3_Neural_Lab.vst3'
        verify(bundle/'Contents/Resources/nmp.onnx',spec['package']['model_sha256'])
        inputs=scratch/'inputs';inputs.mkdir()
        run_capture(['gh','release','download',spec['inputs']['tag'],'--repo','Ajuntanaga/m3-offload',
                     '--pattern','recovery-inputs.tar.gz','--dir',str(inputs)],logs/'inputs-download.log')
        verify(inputs/'recovery-inputs.tar.gz',spec['inputs']['sha256'])
        with tarfile.open(inputs/'recovery-inputs.tar.gz') as t: t.extractall(inputs,filter='data')
        verify(inputs/'recovery-inputs.json',spec['inputs']['manifest_sha256'])
        wav=inputs/'corpus/ordinary.wav';verify(wav,spec['recording']['sha256'])
        reaper_tar=scratch/'reaper.tar.xz'
        run_capture(['curl','--fail','--location','--max-time','120',spec['reaper']['url'],'--output',str(reaper_tar)],logs/'reaper-download.log')
        verify(reaper_tar,spec['reaper']['sha256'])
        with tarfile.open(reaper_tar) as t: t.extractall(scratch,filter='data')
        executable=scratch/'reaper_linux_x86_64/REAPER/reaper'
        if not executable.is_file(): raise ValueError('Official REAPER layout differs')
        profile=scratch/'profile';(profile/'Effects').mkdir(parents=True)
        (profile/'Scripts').mkdir()
        for name in ('input','capture'):
            shutil.copy2(root/f'Effects/tests/m3_neural_host_{name}.jsfx',profile/'Effects')
        script=profile/'Scripts/m3_neural_host.lua'
        shutil.copy2(root/'Scripts/tests/m3_neural_host.lua',script)
        # Use an explicit, paced JACK dummy server instead of relying on the
        # undocumented defaults of REAPER's internal dummy device. This profile
        # belongs only to this runner; no user device or profile is accessed.
        (profile/'reaper.ini').write_text('[reaper]\nlinux_audio_bsize=512\nlinux_audio_bufs=2\nlinux_audio_mode=0\nlinux_audio_nch_in=0\nlinux_audio_nch_out=2\nlinux_audio_srate=96000\naudiocloseinactive=0\naudioclosestop=0\nnewprojdo=0\nsaveFlags=0\nwarnmaxram64=0\nvstpath='+str(vst)+'\n')
        shutil.copy2(profile/'reaper.ini',logs/'reaper-before.ini')
        (profile/'host_config.lua').write_text('return {wav='+json.dumps(str(wav))+',output='+json.dumps(str(bulk))+',samples='+str(spec['recording']['samples'])+'}\n')
        run_capture(['luac','-p',str(script)],logs/'lua-syntax.log')
        report.update(stage='real REAPER playback',bundle_sha256=digest(bundle/'Contents/x86_64-linux/M3_Neural_Lab.so'))
        save()
        env=os.environ.copy();env['DISPLAY']=':99';env['XDG_CONFIG_HOME']=str(scratch/'xdg')
        env['JACK_DEFAULT_SERVER']='m3-neural-host';env['JACK_NO_START_SERVER']='1'
        with (logs/'xvfb.log').open('wb') as xf, (logs/'jack.log').open('wb') as jf:
            xvfb=subprocess.Popen(['Xvfb',':99','-screen','0','1280x800x24','-nolisten','tcp'],stdout=xf,stderr=subprocess.STDOUT,env=env)
            jack=None
            try:
                jack_command=['jackd','--no-realtime','--name','m3-neural-host',
                              '-d','dummy','--rate','96000','--period','512','--wait','5333',
                              '--capture','0','--playback','2']
                report['audio_server_command']=jack_command;save()
                jack=subprocess.Popen(jack_command,stdout=jf,stderr=subprocess.STDOUT,env=env)
                time.sleep(2)
                if jack.poll() is not None: raise RuntimeError('JACK dummy server exited; see jack.log')
                run_capture(['jack_lsp'],logs/'jack-ports-before.txt',env=env,timeout=10)
                command=[str(executable),'-newinst','-noactivate','-cfgfile',str(profile/'reaper.ini'),'-nosplash',str(script)]
                report['host_command']=command;save()
                with (logs/'reaper.log').open('wb') as lf:
                    proc=subprocess.Popen(command,stdout=lf,stderr=subprocess.STDOUT,env=env)
                    try:
                        proc.wait(timeout=210)
                    except subprocess.TimeoutExpired:
                        run_capture(['xwininfo','-root','-tree'],logs/'windows-at-timeout.txt',env=env,timeout=10)
                        proc.terminate()
                        try: proc.wait(timeout=10)
                        except subprocess.TimeoutExpired: proc.kill();proc.wait()
                        raise RuntimeError('REAPER observation timed out; window inventory retained')
                    report['host_exit']=proc.returncode
            finally:
                if (profile/'reaper.ini').is_file():
                    shutil.copy2(profile/'reaper.ini',logs/'reaper-after.ini')
                if jack is not None and jack.poll() is None:
                    jack.terminate();jack.wait(timeout=10)
                xvfb.terminate();xvfb.wait(timeout=10)
        metrics=read_metrics(bulk/'metrics.tsv')
        with (bulk/'events.tsv').open() as f:
            events=[{k:int(v) for k,v in row.items()} for row in csv.DictReader(f,delimiter='\t')]
        report.update(metrics=metrics,result=evaluate(metrics,events,spec['recording']['samples']),
                      state='completed',final=True,stage='host observation complete')
        for name in ('phase.log','failures.txt','metrics.tsv'):
            shutil.copy2(bulk/name,logs/name)
        report['event_evidence']={'sha256':digest(bulk/'events.tsv'),'bytes':(bulk/'events.tsv').stat().st_size}
        save()
        print(json.dumps(report['result'],sort_keys=True),flush=True)
        return 0 if report['result']['passed'] else 2
    except Exception as error:
        report.update(state='failed',final=True,error=f'{type(error).__name__}: {error}')
        save()
        raise
    finally:
        for name in ('phase.log','failures.txt','metrics.tsv'):
            if (bulk/name).is_file():
                shutil.copy2(bulk/name,logs/name)


if __name__=='__main__':
    raise SystemExit(main())
