"""Private Kaggle CPU bootstrap; builds and replays the uploaded source snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    root = Path('/kaggle/working')
    manifests = list(Path('/kaggle/input').rglob('recovery-inputs.json'))
    if len(manifests) != 1:
        raise ValueError('Expected exactly one recovery dataset')
    manifest_path = manifests[0]
    corpus = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    archives = list(corpus.rglob('m3-source.tar'))
    if archives:
        if len(archives) != 1 or sha256(archives[0]) != manifest['source']['archive_sha256']:
            raise ValueError('Source archive identity failed')
        with tarfile.open(archives[0]) as archive:
            for member in archive.getmembers():
                path = Path(member.name)
                if not member.isfile() or path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unexpected source archive member')
            archive.extractall(root)
        source = root / 'source'
    else:
        # Kaggle may unpack tar inputs before mounting them.
        sources = list(corpus.rglob('source-manifest.json'))
        if len(sources) != 1:
            raise ValueError('Source snapshot missing or ambiguous')
        source = sources[0].parent
    source_manifest = source / 'source-manifest.json'
    if sha256(source_manifest) != manifest['source']['manifest_sha256']:
        raise ValueError('Source manifest identity failed')
    for name, expected in json.loads(source_manifest.read_text())['files'].items():
        if sha256(source / name) != expected:
            raise ValueError('Source file identity failed: ' + name)
    build = root / 'native-build'
    commands = [
        ['cmake', '-S', str(source / 'cloud/native'), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release'],
        ['cmake', '--build', str(build), '--parallel', '2'],
        ['ctest', '--test-dir', str(build), '--output-on-failure'],
        ['python3', '-B', '-m', 'tools.portable_corpus_replay',
         '--binary', str(build / 'm3_replay'), '--corpus', str(corpus),
         '--manifest', str(manifest_path), '--output', str(root / 'corpus-results')],
    ]
    for index, command in enumerate(commands):
        print('Starting:', ' '.join(command), flush=True)
        with (root / f'stage-{index}.log').open('w') as log:
            subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=11400 if index == 3 else 900)
        print('Completed:', index, flush=True)


if __name__ == '__main__':
    main()
