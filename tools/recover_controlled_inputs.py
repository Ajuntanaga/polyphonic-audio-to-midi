"""Recover exact held-out crops with bounded reads; no audio processing or upload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile

from tools.portable_recovery import digest


def float_crop(path, begin, end, rate):
    if not 0 <= begin < end or end - begin > rate * 10:
        raise ValueError('Invalid or oversized crop')
    with path.open('rb') as stream:
        size = path.stat().st_size
        header = stream.read(12)
        if (len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE'
                or struct.unpack_from('<I', header, 4)[0] + 8 != size):
            raise ValueError('Invalid RIFF WAVE')
        fmt = data = None
        while stream.tell() + 8 <= size:
            kind, length = struct.unpack('<4sI', stream.read(8))
            offset = stream.tell()
            if offset + length + (length & 1) > size:
                raise ValueError('Incomplete WAVE chunk')
            if kind == b'fmt ':
                if fmt is not None or length < 16:
                    raise ValueError('Invalid WAVE format chunk')
                fmt = struct.unpack('<HHIIHH', stream.read(16))
            elif kind == b'data':
                if data is not None:
                    raise ValueError('Multiple WAVE data chunks')
                data = offset, length
            stream.seek(offset + length + (length & 1))
        if (fmt != (3, 1, rate, rate * 4, 4, 32) or data is None
                or data[1] % 4 or end * 4 > data[1]):
            raise ValueError('Expected mono float32 WAVE and an in-range crop')
        stream.seek(data[0] + begin * 4)
        samples = stream.read((end - begin) * 4)
        if len(samples) != (end - begin) * 4:
            raise ValueError('Incomplete crop')
    fmt_bytes = struct.pack('<HHIIHH', *fmt)
    body = b'WAVEfmt ' + struct.pack('<I', 16) + fmt_bytes
    body += b'data' + struct.pack('<I', len(samples)) + samples
    wave = b'RIFF' + struct.pack('<I', len(body)) + body
    return samples, wave


def recover(reference_path, recordings, repository, calibration, output, bundle):
    reference = json.loads(reference_path.read_text())
    if set(reference['components']) != {'target', 'octave', 'nearby'}:
        raise ValueError('Expected the three held-out components')
    if digest(calibration) != reference['calibration_sha256']:
        raise ValueError('Historical calibration differs')
    output.mkdir(parents=True, exist_ok=False)
    corpus = output / 'corpus'
    corpus.mkdir()
    files = {}
    for name, item in reference['components'].items():
        if digest(repository / item['source_labels']) != item['source_labels_sha256']:
            raise ValueError('Historical labels differ: ' + name)
        samples, wave = float_crop(recordings / item['source_wave'],
            item['source_start_sample'], item['source_end_sample'], item['sample_rate'])
        if (len(samples) != item['sample_count'] * 4
                or hashlib.sha256(samples).hexdigest() != item['samples_sha256']
                or hashlib.sha256(wave).hexdigest() != item['wave_sha256']):
            raise ValueError('Historical crop differs: ' + name)
        path = corpus / (name + '.wav')
        with path.open('xb') as stream:
            stream.write(wave)
        files[path.name] = dict(sha256=item['wave_sha256'], bytes=len(wave),
                               state='historical-hash-match')
    shutil.copyfile(calibration, corpus / 'calibration.m3cb')
    if digest(corpus / 'calibration.m3cb') != reference['calibration_sha256']:
        raise ValueError('Calibration changed during recovery')
    files['calibration.m3cb'] = dict(sha256=reference['calibration_sha256'],
        bytes=calibration.stat().st_size, state='historical-hash-match')
    manifest = dict(schema='m3_controlled_inputs_v1', corpus_id=reference['corpus_id'],
        reference_sha256=digest(reference_path), files=files,
        note='Exact held-out input recovery only; no detector acceptance or new-session coverage.')
    manifest_path = output / 'recovery-inputs.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    with bundle.open('xb') as destination:
        with tarfile.open(fileobj=destination, mode='w:gz', compresslevel=1) as archive:
            archive.add(manifest_path, arcname=manifest_path.name, recursive=False)
            for name in sorted(files):
                archive.add(corpus / name, arcname='corpus/' + name, recursive=False)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'recordings', 'repository', 'calibration', 'output', 'bundle'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    manifest = recover(args.reference, args.recordings, args.repository,
                       args.calibration, args.output, args.bundle)
    print(json.dumps(dict(inputs=len(manifest['files']), bundle_bytes=args.bundle.stat().st_size,
                          bundle_sha256=digest(args.bundle))))


if __name__ == '__main__':
    main()
