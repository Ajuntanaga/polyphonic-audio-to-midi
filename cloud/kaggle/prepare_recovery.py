"""Prepare private Kaggle recovery files locally; never uploads or reads credentials."""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from tools.portable_recovery import digest, inventory
from tools.replay_corpus import CORPUS_FILES, REPO_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.username):
        parser.error('Invalid username')
    args.output.mkdir(parents=True, exist_ok=False)
    dataset, kernel = args.output / 'dataset', args.output / 'kernel'
    dataset.mkdir()
    kernel.mkdir()
    # Copies freeze the inputs independently of later local edits.
    for name, path in sorted(CORPUS_FILES.items()):
        shutil.copyfile(path, dataset / name)
    report = inventory({name: dataset / name for name in CORPUS_FILES}, hash_files=True)
    tracked = subprocess.check_output(
        ['git', 'ls-files', '-z', 'CMakeLists.txt', 'native', 'tools', 'cloud/native'],
        cwd=REPO_ROOT).decode().split('\0')
    names = sorted(set(filter(None, tracked)) | {'tools/portable_corpus_replay.py'})
    snapshot = {'created_at': datetime.now(timezone.utc).isoformat(),
                'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                                       cwd=REPO_ROOT, text=True).strip(),
                'files': {name: digest(REPO_ROOT / name) for name in names}}
    manifest_bytes = (json.dumps(snapshot, indent=2) + '\n').encode()
    archive_path = dataset / 'm3-source.tar'
    with tarfile.open(archive_path, 'x') as archive:
        for name in names:
            archive.add(REPO_ROOT / name, arcname='source/' + name, recursive=False)
        info = tarfile.TarInfo('source/source-manifest.json')
        info.size = len(manifest_bytes)
        archive.addfile(info, io.BytesIO(manifest_bytes))
    import hashlib
    report['source'] = dict(base_commit=snapshot['base_commit'],
                            archive_sha256=digest(archive_path),
                            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
    # No local usernames or source paths are needed in the uploaded manifest.
    for name, row in report['files'].items():
        row['source'] = name
    (dataset / 'recovery-inputs.json').write_text(json.dumps(report, indent=2) + '\n')
    dataset_id = args.username + '/m3-recovered-corpus-20261108'
    (dataset / 'dataset-metadata.json').write_text(json.dumps({
        'title': 'M3 recovered corpus 20261108', 'id': dataset_id,
        'description': 'Private recovery inputs. Original authors retain all rights. '
                       'No public redistribution license is granted.',
        'licenses': [{'name': 'other'}]}, indent=2) + '\n')
    shutil.copyfile(Path(__file__).with_name('recover_corpus.py'), kernel / 'recover_corpus.py')
    (kernel / 'kernel-metadata.json').write_text(json.dumps(dict(
        id=args.username + '/m3-recovered-corpus', title='M3 recovered corpus',
        code_file='recover_corpus.py', language='python', kernel_type='script',
        is_private=True, enable_gpu=False, enable_internet=False,
        dataset_sources=[dataset_id], competition_sources=[], kernel_sources=[],
        model_sources=[]), indent=2) + '\n')
    print(json.dumps(dict(dataset=str(dataset), kernel=str(kernel), private=True,
                          input_count=len(CORPUS_FILES), input_bytes=report['total_present_bytes'],
                          archive_bytes=archive_path.stat().st_size,
                          source=report['source'], uploaded=False), indent=2))


if __name__ == '__main__':
    main()
