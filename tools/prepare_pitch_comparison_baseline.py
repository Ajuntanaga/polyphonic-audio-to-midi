"""Export pitch-only reference statistics from already collected MIDI and labels.

No audio is read, inferred or replayed. Raw recordings, calibration and MIDI are
not copied into the source tree; the output contains derived scoring statistics
and merged pitch-occupancy spans for the report-only combined-detector diagnostic.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

from tools.midi_lifecycle_analysis import read_events
from tools.pitch_detector_comparison import digest, native_spans, read_labels, score, union_spans


def prepare(spec_path, output):
    spec = json.loads(spec_path.read_text())
    result = dict(schema=2, method='Saved CURRENT MIDI; pitch union only', datasets={})
    for name, config in spec['datasets'].items():
        source = config['baseline']
        labels_path = Path(source['local_labels'])
        if digest(labels_path) != config['labels_sha256']:
            raise ValueError('Reference label hash mismatch: ' + name)
        with gzip.open(source['local_midi_gzip'], 'rb') as stream:
            raw = stream.read()
        if hashlib.sha256(raw).hexdigest() != source['raw_midi_sha256']:
            raise ValueError('Reference MIDI hash mismatch: ' + name)
        with tempfile.TemporaryDirectory(prefix='m3-saved-midi-') as directory:
            path = Path(directory) / 'saved.tsv'
            path.write_bytes(raw)
            events = read_events(path, sample_count=config['sample_count'],
                                 transition_count=source['transitions'])
        clock = {k: config[k] for k in ('sample_count', 'sample_rate')}
        spans, audit = native_spans(events, **clock)
        result['datasets'][name] = dict(raw_midi_sha256=source['raw_midi_sha256'],
            labels_sha256=config['labels_sha256'], run_id=source['run_id'],
            source_commit=source['source_commit'], audit=audit,
            pitch_spans=union_spans(spans, sample_count=config['sample_count']),
            measurement=score(spans, read_labels(labels_path), **clock))
    # Exclusive creation avoids replacing a reference after seeing model output.
    with output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', dest='spec_path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    prepare(**vars(parser.parse_args()))
