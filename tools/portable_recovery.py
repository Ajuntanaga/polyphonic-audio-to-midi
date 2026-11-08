"""Inventory surviving replay inputs without importing or contacting Modal.

Hashing is opt-in. Presence alone never establishes identity with the old volume.
Bundles are local only; this tool does not upload anything.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

from tools.replay_corpus import CORPUS_FILES, DATASETS, REPO_ROOT


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def inventory(files, *, hash_files=False, expected=None):
    rows = {}
    for name, path in sorted(files.items()):
        path = Path(path)
        try:
            source = str(path.relative_to(REPO_ROOT))
        except ValueError:
            source = str(path)
        row = dict(source=source, state='missing-locally', bytes=None, sha256=None)
        if path.is_file():
            before = path.stat()
            row.update(state='present-unverified', bytes=before.st_size)
            if hash_files:
                row['sha256'] = digest(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Input changed while hashing: ' + name)
                prior = (expected or {}).get(name, {}).get('sha256')
                if prior:
                    row['state'] = 'historical-hash-match' if prior == row['sha256'] else 'historical-hash-mismatch'
                else:
                    row['state'] = 'present-new-hash-no-historical-reference'
        rows[name] = row
    return dict(schema=1, created_at=datetime.now(timezone.utc).isoformat(), files=rows,
                missing=[name for name, row in rows.items() if row['state'] == 'missing-locally'],
                total_present_bytes=sum(row['bytes'] or 0 for row in rows.values()),
                note='Local inventory. Missing locally does not mean deleted remotely; new hashes do not recover historical identity.')


def bundle(files, report, output):
    # Exclusive creation prevents accidental destruction of a prior recovery bundle.
    if any(row['sha256'] is None or row['state'] == 'historical-hash-mismatch'
           for row in report['files'].values()):
        raise ValueError('Bundle requires all selected inputs present, hashed, and no historical mismatch')
    import io
    with Path(output).open('xb') as destination:
        with tarfile.open(fileobj=destination, mode='w') as archive:
            for name, path in sorted(files.items()):
                archive.add(path, arcname='corpus/' + name, recursive=False)
            payload = json.dumps(report, indent=2).encode()
            info = tarfile.TarInfo('recovery-manifest.json')
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hash', action='store_true', dest='hash_files')
    parser.add_argument('--expected', type=Path, help='Earlier inventory JSON with files/name/sha256')
    parser.add_argument('--dataset', action='append', choices=sorted(DATASETS))
    parser.add_argument('--bundle', type=Path, help='Create an uncompressed local tar; implies hashing')
    args = parser.parse_args()
    files = CORPUS_FILES
    if args.dataset:
        names = {'calibration.m3cb', 'templates.tsv'} | {
            name + suffix for name in args.dataset for suffix in ('.wav', '.tsv')}
        files = {name: path for name, path in files.items() if name in names}
    expected = json.loads(args.expected.read_text())['files'] if args.expected else None
    report = inventory(files, hash_files=args.hash_files or bool(args.bundle), expected=expected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'files'}))
    if args.bundle:
        bundle(files, report, args.bundle)


if __name__ == '__main__':
    main()
