"""Locate C++ allocations in one physical-long OFF replay on GitHub Actions.

Record caller addresses with fixed storage, then symbolize after processing.
Instrumented times never satisfy real-time acceptance. No installed output changes.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import time

from tools.frozen_cue_corpus_gate import read_replay
from tools.portable_assignment_trace import digest, verify_inputs
from tools.portable_corpus_replay import SETTINGS, command_for, timing_gates


def trace_checks(timing):
    trace = timing.get('allocation_trace')
    if timing.get('timing_diagnostic_only') is not True or not isinstance(trace, dict):
        raise ValueError('Missing diagnostic-only allocation trace')
    for key in ('events', 'dropped', 'capacity'):
        if type(trace.get(key)) is not int or trace[key] < 0:
            raise ValueError('Invalid allocation trace count: ' + key)
    sites = trace.get('callsites')
    if trace['capacity'] != 64 or not isinstance(sites, list) or len(sites) > trace['capacity']:
        raise ValueError('Invalid allocation trace capacity')
    addresses = set()
    for site in sites:
        address = site.get('return_address', '')
        if (not isinstance(address, str) or not re.fullmatch(r'0x[0-9a-f]+', address)
                or int(address, 16) == 0 or address in addresses
                or type(site.get('count')) is not int or site['count'] <= 0
                or type(site.get('bytes')) is not int or site['bytes'] < 0):
            raise ValueError('Invalid or duplicate allocation callsite')
        addresses.add(address)
    return dict(counter_accounting=(trace['events'] == timing.get('cpp_allocations')
                                    == sum(site['count'] for site in sites) + trace['dropped']),
                all_callsites_retained=trace['dropped'] == 0,
                allocation_reproduced=trace['events'] > 0)


def reference_identity(reference, parsed, tsv_hash):
    return (tsv_hash == reference['tsv_sha256'] and parsed['output'] == reference['output']
            and parsed['exact_matches_by_string_count'] == reference['exact_matches_by_string_count'])


def run(binary, corpus, manifest_path, reference_path, output, timeout):
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    report = dict(schema='m3_allocation_trace_v1', state='running', final=False,
                  stage='verify inputs', dataset='physical-long', mode='off', block_samples=32,
                  installed_output_changed=False, promotion_accepted=False,
                  timing_diagnostic_only=True, live_readiness='not measured', settings=SETTINGS,
                  interpretation='C++ new caller capture only. C/C++ hook counts can overlap; '
                                 'they are not added. Instrumented timings cannot pass acceptance.')

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    save()
    try:
        manifest = json.loads(manifest_path.read_text())
        verify_inputs(corpus, manifest, 'physical-long')
        reference_report = json.loads(reference_path.read_text())
        if reference_report['settings'] != SETTINGS:
            raise ValueError('Reference settings differ')
        reference = reference_report['datasets']['physical-long']['runs']['off-32']
        report.update(source=manifest.get('source', {}), verified_inputs=4,
                      input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
                      baseline_report_sha256=digest(reference_path), baseline=reference,
                      baseline_source=reference_report['source'], stage='traced OFF replay')
        tsv = output / 'physical-long-off-32.tsv'
        timing_path = output / 'timing.json'
        command = command_for(binary, corpus, 'physical-long', 'off', 32, timing_path.resolve())
        report['command'] = command
        save()
        started = time.monotonic()
        with tsv.open('x') as stdout, (output / 'replay.stderr').open('x') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, timeout=timeout, check=True)
        parsed = read_replay(tsv)
        timing = json.loads(timing_path.read_text())
        tsv_hash = digest(tsv)
        report.update(elapsed_seconds=time.monotonic() - started, output=parsed['output'],
                      exact_matches_by_string_count=parsed['exact_matches_by_string_count'],
                      tsv_sha256=tsv_hash, timing=timing,
                      recorded_reference_bit_identical=reference_identity(reference, parsed, tsv_hash),
                      gates=timing_gates(timing, parsed, 32))
        report['trace_checks'] = trace_checks(timing)
        save()
        if not report['recorded_reference_bit_identical']:
            raise ValueError('Traced replay differs from retained OFF reference')
        if not report['gates']['timed_scored_identity'] or timing.get('allocation_guard') is not True:
            raise ValueError('Timed replay identity or allocation guard failed')
        if not all(report['trace_checks'].values()):
            raise ValueError('Allocation trace incomplete or allocation not reproduced')
        report.update(stage='symbolize callers after replay', callsites=[])
        save()
        with (output / 'symbolization.log').open('x') as log:
            for site in timing['allocation_trace']['callsites']:
                # The saved address is just after the call instruction.
                address = hex(int(site['return_address'], 16) - 1)
                result = subprocess.run(['addr2line', '-C', '-f', '-i', '-e', str(binary), address],
                                        capture_output=True, text=True, check=True, timeout=20)
                log.write(site['return_address'] + '\n' + result.stdout + result.stderr)
                report['callsites'].append(dict(site, lookup_address=address,
                                                symbols=result.stdout.splitlines(),
                                                resolved=bool(result.stdout.strip())
                                                and '??' not in result.stdout))
        report['all_callsites_resolved'] = all(site['resolved'] for site in report['callsites'])
        if not report['all_callsites_resolved']:
            raise ValueError('At least one caller could not be resolved')
        report.update(state='completed', final=True, stage='allocation diagnosis collected')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}')
        raise
    finally:
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    if args.replay_timeout_seconds <= 0:
        parser.error('--replay-timeout-seconds must be positive')
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
