"""Finite static binary inspection for a private, offline Kaggle CPU job.

Samples are read by file/binutils and never executed. This is a static triage
route, not an LLM server or a hardened malware-analysis environment.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def child_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024**2, 2 * 1024**2))


def command_result(command, log):
    row = {'command': command, 'log': log.name}
    with log.open('wb') as stream:
        try:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=45, preexec_fn=child_limits, check=False)
            row.update(returncode=result.returncode, passed=result.returncode == 0)
        except (OSError, subprocess.TimeoutExpired) as error:
            row.update(passed=False, error=type(error).__name__ + ': ' + str(error))
    row['log_bytes'] = log.stat().st_size
    row['output_limit_reached'] = row['log_bytes'] >= 2 * 1024**2
    if row['output_limit_reached']:
        row['passed'] = False
    return row


def run(config, inputs=Path('/kaggle/input'), output=Path('/kaggle/working/triage')):
    output.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'm3_private_static_triage_v1', 'state': 'running', 'final': False,
              'sample_execution': False, 'llm_inference': False, 'results': [],
              'synthetic_smoke': config['smoke']}

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        for tool in ('file', 'readelf', 'objdump', 'strings'):
            if not shutil.which(tool):
                raise RuntimeError('Required cloud tool is unavailable: ' + tool)
        samples = []
        if config['smoke']:
            source, binary = output / 'fixture.c', output / 'fixture'
            source.write_text('int square(int x) { return x*x; }\nint main(void) { return square(7); }\n')
            build = command_result(['cc', '-g', '-O0', str(source), '-o', str(binary)], output / 'build.log')
            report['fixture_build'] = build
            if not build['passed']:
                raise RuntimeError('Cloud fixture compilation failed')
            samples.append(binary)
        for item in config['files']:
            candidates = list(inputs.rglob(item['name']))
            if len(candidates) != 1:
                raise ValueError('Expected exactly one input: ' + item['name'])
            binary = candidates[0]
            if binary.is_symlink() or not binary.is_file() or binary.stat().st_size != item['bytes'] or digest(binary) != item['sha256']:
                raise ValueError('Input identity mismatch: ' + item['name'])
            samples.append(binary)
        if not samples:
            raise ValueError('No binaries selected')
        for index, binary in enumerate(samples):
            row = {'name': binary.name, 'bytes': binary.stat().st_size,
                   'sha256': digest(binary), 'tools': []}
            report['results'].append(row)
            with binary.open('rb') as stream:
                elf = stream.read(4) == b'\x7fELF'
            commands = [['file', '--', str(binary)], ['objdump', '-d', '--', str(binary)],
                        ['strings', '-a', '-n', '8', '--', str(binary)]]
            if elf:
                commands.append(['readelf', '-h', '-S', '-s', '--', str(binary)])
            for step, command in enumerate(commands):
                row['tools'].append(command_result(command, output / f'sample-{index}-{step}.log'))
                save()
        passed = all(item['passed'] for row in report['results'] for item in row['tools'])
        report.update(state='completed' if passed else 'failed', final=True)
        save()
        if not passed:
            raise RuntimeError('Static inspection failed or reached a time/output limit; see report')
    except Exception as error:
        report.update(state='failed', final=True, error=type(error).__name__ + ': ' + str(error))
        save()
        raise
