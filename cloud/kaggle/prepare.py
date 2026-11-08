"""Prepare a private, offline Kaggle notebook without credentials or recordings."""
import argparse
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.username):
        parser.error('Invalid Kaggle username')
    source = Path(__file__).with_name('gpu_spectra.py')
    notebook = json.loads(source.with_name('m3-gpu-probe.ipynb').read_text())
    notebook['cells'][1]['source'] = source.read_text().splitlines(keepends=True)
    notebook['cells'][1]['outputs'] = []
    notebook['cells'][1]['execution_count'] = None
    metadata = dict(id=args.username + '/m3-portable-gpu-spectra',
                    title='M3 portable GPU spectra', code_file='m3-gpu-probe.ipynb',
                    language='python', kernel_type='notebook', is_private=True,
                    enable_gpu=True, enable_internet=False, dataset_sources=[],
                    competition_sources=[], kernel_sources=[], model_sources=[])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'm3-gpu-probe.ipynb').write_text(json.dumps(notebook, indent=2) + '\n')
    (args.output / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Prepared private generated-audio notebook; nothing uploaded.')


if __name__ == '__main__':
    main()
