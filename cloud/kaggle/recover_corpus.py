"""Private Kaggle CPU bootstrap; builds and replays the uploaded source snapshot."""
import hashlib
from datetime import datetime, timezone
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


def prepare_source(root, inputs):
    manifests = list(inputs.rglob('recovery-inputs.json'))
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
    return source, corpus, manifest_path


def stage_commands(root, source, corpus, manifest_path):
    build = root / 'native-build'
    return [
        ['cmake', '-S', str(source / 'cloud/native'), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release'],
        ['cmake', '--build', str(build), '--parallel', '2'],
        ['ctest', '--test-dir', str(build), '--output-on-failure'],
        ['python3', '-B', '-m', 'tools.portable_corpus_replay',
         '--binary', str(build / 'm3_replay'), '--corpus', str(corpus),
         '--manifest', str(manifest_path), '--output', str(root / 'corpus-results')],
    ]


def run(root, inputs):
    report = dict(schema='m3_recovery_bootstrap_v1', state='running', final=False,
                  stage='verify source', completed_stages=[], promotion_accepted=False,
                  installed_output_changed=False)

    def save():
        report['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = root / 'bootstrap-report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(root / 'bootstrap-report.json')

    save()
    try:
        source, corpus, manifest = prepare_source(root, inputs)
        for index, command in enumerate(stage_commands(root, source, corpus, manifest)):
            report.update(stage=index, command=command, log=f'stage-{index}.log')
            save()
            print('Starting:', ' '.join(command), flush=True)
            with (root / report['log']).open('w') as log:
                subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=11400 if index == 3 else 900)
            report['completed_stages'].append(index)
            save()
        report.update(state='completed', final=True, stage='reference recovery finished')
    except Exception as error:
        report.update(state='failed', final=True, error=f'{type(error).__name__}: {error}',
                      returncode=getattr(error, 'returncode', None))
        raise
    finally:
        save()


def main():
    run(Path('/kaggle/working'), Path('/kaggle/input'))


if __name__ == '__main__':
    main()
