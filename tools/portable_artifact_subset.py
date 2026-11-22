"""Collect named, pinned evidence files from an existing M3 artifact on GitHub.

No recording, model, inference, replay or scoring is performed. Large source
archives stay on the runner; only the selected files and a receipt are retained.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile


REPOSITORY = 'Ajuntanaga/m3-offload'
MAX_ARCHIVE = 2 * 1024**3
MAX_SELECTED = 10 * 1024**2


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            result.update(chunk)
    return result.hexdigest()


def validate_files(files):
    if not isinstance(files, dict) or not files or len(files) > 20:
        raise ValueError('Expected 1 to 20 explicitly named files')
    for name, pin in files.items():
        parts = PurePosixPath(name)
        if (parts.is_absolute() or '..' in parts.parts or '\\' in name
                or str(parts) != name or name.endswith('/')
                or not name.endswith('.json')):
            raise ValueError('Invalid selected evidence path')
        if (not isinstance(pin['bytes'], int) or not 0 < pin['bytes'] <= MAX_SELECTED
                or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])):
            raise ValueError('Invalid selected evidence pin')
    if sum(pin['bytes'] for pin in files.values()) > MAX_SELECTED:
        raise ValueError('Selected evidence exceeds compact collection budget')


def extract_selected(archive, expected_archive_sha256, files, destination):
    """Verify the full archive and exact members before writing selected files."""
    validate_files(files)
    if digest(archive) != expected_archive_sha256:
        raise ValueError('Archive SHA256 differs; do not retry automatically')
    selected = {}
    with zipfile.ZipFile(archive) as bundle:
        for name, pin in files.items():
            matches = [entry for entry in bundle.infolist() if entry.filename == name]
            if len(matches) != 1:
                raise ValueError('Selected archive entry missing or duplicated: '+name)
            entry = matches[0]
            if (entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16)
                    or entry.flag_bits & 1 or entry.file_size != pin['bytes']):
                raise ValueError('Selected archive entry type or size differs: '+name)
            data = bundle.read(entry)
            if hashlib.sha256(data).hexdigest() != pin['sha256']:
                raise ValueError('Selected file SHA256 differs: '+name)
            # Only JSON event evidence is allowed, without changing its bytes.
            json.loads(data)
            selected[name] = data
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in selected.items():
        path = destination/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            for name, data in selected.items()}


def captured_api(endpoint, path, timeout):
    # Capture the raw bytes before any parsing. gh owns authentication; tokens
    # are neither requested from gh nor copied into reports or command arguments.
    with path.open('wb') as output, path.with_suffix(path.suffix+'.stderr').open('wb') as errors:
        result = subprocess.run(['gh', 'api', endpoint], stdout=output,
                                stderr=errors, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError('GitHub collection failed; no automatic retry')


def run(spec_path, output):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Archive collection executes on GitHub Actions only')
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('Wrong worker repository')
    source = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                            text=True, check=True).stdout.strip()
    if source != os.environ.get('SOURCE_SHA'):
        raise ValueError('Collection source revision differs')
    spec = json.loads(spec_path.read_text())
    if spec['repository'] != REPOSITORY or not isinstance(spec['artifact_id'], int):
        raise ValueError('Invalid recorded artifact')
    validate_files(spec['files'])
    output.mkdir(parents=True, exist_ok=False)
    logs, cache = output/'logs', output/'cache'
    logs.mkdir(); cache.mkdir()
    meta = logs/'artifact-metadata.json'
    captured_api(f"repos/{REPOSITORY}/actions/artifacts/{spec['artifact_id']}", meta, 45)
    artifact = json.loads(meta.read_bytes())
    identity = (artifact['id'] == spec['artifact_id']
                and artifact['name'] == spec['artifact_name']
                and artifact['workflow_run']['id'] == spec['producer_run_id']
                and artifact['workflow_run']['head_sha'] == spec['producer_worker_commit']
                and artifact.get('digest') == 'sha256:'+spec['archive_sha256']
                and not artifact['expired'])
    if not identity or not 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE:
        raise ValueError('Artifact provenance or archive budget differs')
    archive = cache/'source.zip'
    captured_api(f"repos/{REPOSITORY}/actions/artifacts/{spec['artifact_id']}/zip", archive, 480)
    if archive.stat().st_size != artifact['size_in_bytes']:
        raise ValueError('Downloaded archive byte count differs')
    files = extract_selected(archive, spec['archive_sha256'], spec['files'], output/'selected')
    receipt = dict(schema='m3_artifact_subset_v1', state='complete', final=True,
        collected_at=datetime.now(timezone.utc).isoformat(), source_commit=source,
        worker_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
        producer_run_id=spec['producer_run_id'], producer_source_commit=spec['producer_source_commit'],
        producer_worker_commit=spec['producer_worker_commit'], artifact_id=artifact['id'],
        artifact_name=artifact['name'], archive_sha256=spec['archive_sha256'],
        archive_bytes=archive.stat().st_size, specification_sha256=digest(spec_path),
        files=files, total_selected_bytes=sum(row['bytes'] for row in files.values()),
        processing='Verified byte-for-byte collection only; no audio, model, replay or scoring')
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt = run(args.spec, args.output)
    print(json.dumps(dict(state=receipt['state'], selected_bytes=receipt['total_selected_bytes'])))
