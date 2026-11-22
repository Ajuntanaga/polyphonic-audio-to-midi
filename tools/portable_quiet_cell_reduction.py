"""Reduce an already completed raw-cell artifact once on GitHub CPU only."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import time
import zipfile

from tools.portable_artifact_subset import captured_api, digest
from tools.quiet_cell_reduction import reduce_stream


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


class HashedLines:
    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
        self.size = 0

    def __iter__(self):
        return self

    def __next__(self):
        line = self.stream.readline()
        if not line:
            raise StopIteration
        self.hash.update(line)
        self.size += len(line)
        return line.decode('utf-8')


def checked_member(bundle, pin):
    name = pin['path']
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not name.endswith('.tsv.gz'):
        raise ValueError('Invalid pinned cell member name')
    matches = [entry for entry in bundle.infolist() if entry.filename == name]
    if (len(matches) != 1 or matches[0].is_dir()
            or stat.S_ISLNK(matches[0].external_attr >> 16)
            or matches[0].flag_bits & 1 or matches[0].file_size != pin['bytes']):
        raise ValueError('Missing, duplicated or wrong-size cell member')
    return matches[0]


def run(spec_path, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'Ajuntanaga/m3-offload':
        raise RuntimeError('Saved-cell reduction is GitHub worker only')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA'):
        raise ValueError('Dispatch source differs')
    spec = json.loads(spec_path.read_text())
    if (spec['schema'] != 'm3_quiet_cell_reduction_spec_v1'
            or spec['policy_change'] or spec['automatic_retry']
            or spec['interval_samples'] != 1920
            or spec['before_samples'] != 1920 or spec['after_samples'] != 9600
            or set(spec['datasets']) != {'ordinary', 'extended-middle'}):
        raise ValueError('Frozen reduction specification differs')
    mask_path = Path(spec['mask']['path'])
    if digest(mask_path) != spec['mask']['sha256']:
        raise ValueError('Frozen rapid-mute interval report differs')
    mask = json.loads(mask_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    folders = {name: output/name for name in ('report', 'logs', 'cache', 'tables')}
    for path in folders.values():
        path.mkdir()
    report_path = folders['report']/'report.json'
    report = dict(schema='m3_quiet_cell_reduction_v1', state='running', final=False,
        started_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        specification_sha256=digest(spec_path), specification=spec, datasets={},
        policy_change=False, installed_output_changed=False, promotion_accepted=False,
        processing='Saved complex-state arithmetic only; no audio, model, replay, policy or scoring')
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
            raise ValueError('Raw-cell artifact provenance differs')
        archive = folders['cache']/'raw-cells.zip'
        captured_api(f"repos/Ajuntanaga/m3-offload/actions/artifacts/{pin['id']}/zip", archive, 480)
        if archive.stat().st_size != pin['bytes'] or digest(archive) != pin['sha256']:
            raise ValueError('Raw-cell artifact bytes or digest differ')
        report['archive_verified'] = True
        save(report_path, report)
        with zipfile.ZipFile(archive) as bundle:
            for name, config in spec['datasets'].items():
                report['stage'] = name
                save(report_path, report)
                member = config['member']
                entry = checked_member(bundle, member)
                compressed = folders['cache']/(name+'.tsv.gz')
                with bundle.open(entry) as incoming, compressed.open('xb') as outgoing:
                    for chunk in iter(lambda: incoming.read(1024**2), b''):
                        outgoing.write(chunk)
                if digest(compressed) != member['sha256']:
                    raise ValueError('Compressed member digest differs')
                marked = mask['datasets'][name]
                if marked['rate'] != 96000 or marked['horizon'] != config['horizon']:
                    raise ValueError('Dataset rate or horizon differs')
                destination = folders['tables']/(name+'-quiet-cell-intervals.tsv.gz')
                with gzip.open(compressed, 'rb') as raw, destination.open('xb') as zipped:
                    lines = HashedLines(raw)
                    with gzip.GzipFile(filename='', mode='wb', fileobj=zipped, mtime=0, compresslevel=3) as gz:
                        with io.TextIOWrapper(gz, encoding='utf-8', newline='\n') as text:
                            row = reduce_stream(lines, text, marked=marked['marked_intervals'],
                                horizon=config['horizon'], lag_samples=spec['interval_samples'],
                                before_samples=spec['before_samples'], after_samples=spec['after_samples'])
                if (lines.size != member['raw_bytes'] or lines.hash.hexdigest() != member['raw_sha256']
                        or row['input_rows'] != config['rows']):
                    raise ValueError('Uncompressed member identity or row count differs')
                row['input_verified'] = True
                row['table'] = dict(path=destination.name, bytes=destination.stat().st_size,
                                    sha256=digest(destination))
                report['datasets'][name] = row
                save(report_path, report)
        report['state'] = 'complete'
        report['stage'] = 'fixed interval export complete; scientific separation unmeasured'
        report['table_bytes'] = sum(row['table']['bytes'] for row in report['datasets'].values())
        report['local_collection_within_32MiB'] = report['table_bytes'] <= 32*1024**2
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
    print(json.dumps(dict(state=result['state'], table_bytes=result['table_bytes'])))
