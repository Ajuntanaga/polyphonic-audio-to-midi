"""One frozen, remote-only saved-cell restart analysis; no replay or model."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import subprocess
import time
import zipfile

from tools.portable_artifact_subset import captured_api, digest
from tools.portable_quiet_cell_reduction import checked_member, save
from tools.quiet_cell_restart_analysis import analyze


def predictions(result):
    row = result['datasets']['ordinary']
    stats = row['summaries']['by_25ms']
    p, q = stats['interval_fundamental_share'], stats['recent_to_raw_harmonics']
    facts = [not p['design_bar'],
             q['auc'] > p['auc'] if None not in (q['auc'], p['auc']) else None,
             p['coverage']['positive'] >= .90 if p['coverage']['positive'] is not None else None]
    return [dict(prediction=name, probability=probability, observed=fact,
                 brier=(probability-int(fact))**2 if fact is not None else None)
            for name, probability, fact in zip(
                ('primary_fails_design_bar', 'recent_over_raw_outranks_interval_fundamental',
                 'positive_interval_coverage_at_least_90_percent'), (.65, .60, .85), facts)]


def run(spec_path, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise RuntimeError('Saved-cell analysis is GitHub worker only')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA'):
        raise ValueError('Dispatch source differs')
    spec = json.loads(spec_path.read_text())
    if (spec['schema'] != 'm3_quiet_cell_restart_spec_v1' or spec['policy_change']
            or spec['automatic_retry'] or spec['bootstraps'] != 2000
            or spec['seed'] != 20261122
            or set(spec['datasets']) != {'ordinary', 'extended-middle'}):
        raise ValueError('Frozen analysis specification differs')
    inputs = {}
    for name in ('mask', 'census'):
        pin = spec[name]
        path = Path(pin['path'])
        if digest(path) != pin['sha256']:
            raise ValueError(f'Committed {name} identity differs')
        inputs[name] = json.loads(path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_quiet_cell_restart_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        specification_sha256=digest(spec_path), specification=spec, datasets={},
        policy_change=False, installed_output_changed=False, promotion_accepted=False,
        processing='Saved complex interval rows only; no audio, native replay, model or policy')
    save(report_path, report)
    start = time.perf_counter()
    try:
        pin = spec['artifact']
        metadata = folders['logs']/'artifact-metadata.json'
        captured_api(f"repos/Ajuntanaga/m3-offload/actions/artifacts/{pin['id']}", metadata, 45)
        artifact = json.loads(metadata.read_bytes())
        if (artifact['id'] != pin['id'] or artifact['name'] != pin['name']
                or artifact['workflow_run']['id'] != pin['run_id']
                or artifact['workflow_run']['head_sha'] != pin['worker_commit']
                or artifact.get('digest') != 'sha256:'+pin['sha256']
                or artifact['size_in_bytes'] != pin['bytes'] or artifact['expired']):
            raise ValueError('Reduced-table artifact provenance differs')
        archive = folders['cache']/'reduced-cells.zip'
        captured_api(f"repos/Ajuntanaga/m3-offload/actions/artifacts/{pin['id']}/zip", archive, 300)
        if archive.stat().st_size != pin['bytes'] or digest(archive) != pin['sha256']:
            raise ValueError('Reduced-table artifact bytes or digest differ')
        report['archive_verified'] = True
        save(report_path, report)
        with zipfile.ZipFile(archive) as bundle:
            for name, config in spec['datasets'].items():
                report['stage'] = name
                save(report_path, report)
                pin = config['member']
                entry = checked_member(bundle, pin)
                compressed = folders['cache']/(name+'.tsv.gz')
                with bundle.open(entry) as incoming, compressed.open('xb') as outgoing:
                    for chunk in iter(lambda: incoming.read(1024**2), b''):
                        outgoing.write(chunk)
                if digest(compressed) != pin['sha256']:
                    raise ValueError('Compressed member digest differs')
                census, mask = (inputs[k]['datasets'][name] for k in ('census', 'mask'))
                if (mask['horizon'] != config['horizon']
                        or len(census['truncated_spans']) != config['original_spans']):
                    raise ValueError('Pinned population differs')
                with gzip.open(compressed, 'rt', encoding='utf-8', newline='') as lines:
                    row = analyze(iter(lines), census=census, mask=mask,
                                  expected_rows=config['rows'], bootstraps=spec['bootstraps'])
                if row['interval_status_counts'] != config['status_counts']:
                    raise ValueError('Reduced status totals differ')
                row['input_verified'] = True
                report['datasets'][name] = row
                save(report_path, report)
        report['predictions'] = predictions(report)
        ordinary = report['datasets']['ordinary']
        report['reading'] = ('primary design lead; prospective causal replay still required'
            if ordinary['primary_supported'] else 'secondary descriptive lead only'
            if ordinary['any_interval_design_bar'] else 'no scalar route meets the frozen design bar')
        report['state'] = 'complete'
        report['stage'] = 'fixed saved-cell evidence analysis final'
    except Exception as error:
        report['state'] = 'failed'
        report['error'] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        report['final'] = True
        report['elapsed_seconds'] = time.perf_counter()-start
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.spec, args.output)
    print(json.dumps(dict(state=result['state'], reading=result['reading'])))
