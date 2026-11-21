"""Summarize one GitHub-only synthetic ORT thread/profile comparison."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess


def distribution(values):
    values = sorted(values)
    if not values:
        raise ValueError('Empty timing series')
    return dict(count=len(values), minimum=values[0],
                median=values[(len(values)-1)//2],
                p99=values[math.ceil(len(values)*0.99)-1], maximum=values[-1],
                mean=sum(values)/len(values))


def cpu_metadata():
    selected = {'processor', 'model name', 'cpu MHz', 'cache size', 'flags',
                'physical id', 'core id', 'cpu cores', 'siblings'}
    processors = []
    for block in Path('/proc/cpuinfo').read_text().split('\n\n'):
        row = dict(line.split(':', 1) for line in block.splitlines() if ':' in line)
        row = {k.strip(): v.strip() for k, v in row.items() if k.strip() in selected}
        if row:
            processors.append(row)
    cgroup = {}
    for name in ('cpu.max', 'cpu.stat', 'cpuset.cpus.effective'):
        path = Path('/sys/fs/cgroup')/name
        if path.is_file():
            cgroup[name] = path.read_text().strip()
    return dict(platform=platform.platform(), machine=platform.machine(),
                logical_cpus=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)),
                processors=processors, cgroup=cgroup)


def summarize(data, profile):
    names = ['reference_2_main', 'single_1_main', 'parallel_4_main', 'reference_2_worker']
    if (data['schema'] != 'm3_ort_synthetic_diagnosis_v1' or data['signals'] != 32
            or data['calls_per_case'] != 128 or [r['name'] for r in data['cases']] != names):
        raise ValueError('Unexpected synthetic comparison scope')
    cases = []
    for row in data['cases']:
        calls = row['call_ns']
        if len(calls) != 128 or any(not isinstance(v, int) or v <= 0 for v in calls):
            raise ValueError('Incomplete or invalid timing series')
        cases.append({**{k:v for k,v in row.items() if k != 'call_ns'},
                      'model_call_ns': distribution(calls),
                      'numerical_pass': row['all_finite'] and row['maximum_activation_error'] <= 1e-5})
    operators, nodes = defaultdict(list), defaultdict(list)
    session_runs = []
    for event in profile:
        if event.get('cat') == 'Node' and event.get('name', '').endswith('_kernel_time'):
            duration = event.get('dur')
            if duration is None or not math.isfinite(duration) or duration < 0:
                raise ValueError('Invalid profile duration')
            operators[event.get('args', {}).get('op_name', 'unknown')].append(duration)
            nodes[event['name']].append(duration)
        if event.get('name') == 'model_run' and 'dur' in event:
            session_runs.append(event['dur'])
    def ranked(groups):
        return sorted((dict(name=name, calls=len(times), total_us=sum(times),
                            mean_us=sum(times)/len(times)) for name,times in groups.items()),
                      key=lambda row: row['total_us'], reverse=True)
    if not operators or len(session_runs) != 9:
        raise ValueError('Missing operator profile or warmup-plus-eight run count')
    return dict(cases=cases, numerical_identity_pass=all(r['numerical_pass'] for r in cases),
                profiled_model_run_us=distribution(session_runs), operators=ranked(operators),
                top_nodes=ranked(nodes)[:30],
                profile_note='Separate two-thread session: one warmup plus eight synthetic windows. '
                             'Node durations include profiling overhead; not the timing comparison.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Model/native execution is GitHub-only')
    spec = json.loads(Path('docs/recovery/neural-lab-20261121.json').read_text())
    model_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if model_hash != spec['model']['sha256']:
        raise ValueError('Model hash mismatch')
    report_dir, bulk = args.output/'report', args.output/'bulk'
    report_dir.mkdir(parents=True, exist_ok=False)
    bulk.mkdir()
    report = dict(schema='m3_neural_ort_diagnosis_report_v1',
                  started_at=datetime.now(timezone.utc).isoformat(),
                  source_sha=os.environ.get('SOURCE_SHA'), worker_sha=os.environ.get('GITHUB_SHA'),
                  run_id=os.environ.get('GITHUB_RUN_ID'), model_sha256=model_hash,
                  sdk_sha256=os.environ.get('ORT_SDK_SHA256'), cpu_before=cpu_metadata(),
                  scope='Four fixed synthetic CPU configurations, no recorded audio, labels, '
                        'detector-policy change, plugin installation or readiness claim.')
    with (report_dir/'native.stdout').open('wb') as stdout, (report_dir/'native.stderr').open('wb') as stderr:
        run = subprocess.run([str(args.harness.resolve()), str(args.model.resolve()), str(bulk.resolve())],
                             stdout=stdout, stderr=stderr, check=False, timeout=180)
    report.update(native_exit=run.returncode, cpu_after=cpu_metadata(),
                  completed_at=datetime.now(timezone.utc).isoformat())
    try:
        data = json.loads((bulk/'measurements.json').read_text())
        profile_path = Path(data['profile_path']).resolve()
        if profile_path.parent != bulk.resolve():
            raise ValueError('Unexpected profile location')
        report.update(summarize(data, json.loads(profile_path.read_text())))
    except Exception as exc:
        report.update(numerical_identity_pass=False, error=str(exc))
    (report_dir/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(native_exit=run.returncode,
                          numerical_identity_pass=report['numerical_identity_pass'],
                          cases=report.get('cases', [])), indent=2))
    return 0 if run.returncode == 0 and report['numerical_identity_pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
