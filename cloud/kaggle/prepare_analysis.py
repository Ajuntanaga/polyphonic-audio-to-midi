"""Prepare a private static-analysis batch locally; never uploads or reads keys."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from cloud.kaggle.binary_triage import digest


def prepare(username, slug, output, binaries=(), smoke=False):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', username) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', slug):
        raise ValueError('Invalid Kaggle username or slug')
    if bool(binaries) == smoke:
        raise ValueError('Select either explicit binaries or a generated smoke fixture')
    if len(binaries) > 4 or any(p.is_symlink() or not p.is_file() for p in binaries):
        raise ValueError('Select at most four regular files, without symlinks')
    if sum(p.stat().st_size for p in binaries) > 128 * 1024**2:
        raise ValueError('This bounded batch accepts at most 128 MiB of input')
    output.mkdir(parents=True, exist_ok=False)
    kernel = output / 'kernel'
    kernel.mkdir()
    config = {'smoke': smoke, 'files': []}
    dataset_id = username + '/' + slug + '-inputs'
    if binaries:
        dataset = output / 'dataset'
        dataset.mkdir()
        for index, binary in enumerate(binaries):
            # Neutral names avoid uploading private workstation paths.
            name = f'sample-{index}.bin'
            target = dataset / name
            shutil.copyfile(binary, target)
            config['files'].append({'name': name, 'bytes': target.stat().st_size, 'sha256': digest(target)})
        (dataset / 'dataset-metadata.json').write_text(json.dumps({
            'id': dataset_id, 'title': slug + ' inputs', 'licenses': [{'name': 'other'}],
            'description': 'Private analysis inputs; no public redistribution license granted.'}, indent=2) + '\n')
    source = Path(__file__).with_name('binary_triage.py').read_text()
    source += '\nrun(' + repr(config) + ')\n'
    (kernel / 'analysis.py').write_text(source)
    (kernel / 'kernel-metadata.json').write_text(json.dumps(dict(
        id=username + '/' + slug, title=slug.replace('-', ' '), code_file='analysis.py',
        language='python', kernel_type='script', is_private=True, enable_gpu=False,
        enable_internet=False, dataset_sources=[dataset_id] if binaries else [],
        competition_sources=[], kernel_sources=[], model_sources=[]), indent=2) + '\n')
    receipt = dict(kernel=str(kernel), uploaded=False, input_count=len(binaries),
                   smoke=smoke, source_sha256=hashlib.sha256(source.encode()).hexdigest())
    (output / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--output', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--binary', type=Path, action='append')
    group.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(args.username, args.slug, args.output, args.binary or (), args.smoke), indent=2))


if __name__ == '__main__':
    main()
