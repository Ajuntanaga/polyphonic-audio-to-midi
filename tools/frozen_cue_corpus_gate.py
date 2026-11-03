"""Compare whole-corpus replay output without hiding losses in individual labels."""
from __future__ import annotations

import csv
from pathlib import Path
import re
import wave


ERRORS = ('false_wrong_note_voices', 'false_wrong_string_voices',
          'false_gap_voices', 'false_positive_voices')
COUNTS = ('labeled', 'matched', *ERRORS)
LABEL_FIELDS = ('label_index', 'start_sample', 'end_sample', 'midi_note',
                'string_mask', 'calibration_pass', 'labeled', 'matched')


def read_corpus_wave(path):
    """Decode mono PCM16 exactly like native replay, or retain float32 samples."""
    import numpy as np
    from tools.controlled_descriptor_overlap import read_float_wave

    try:
        stream = wave.open(str(path), 'rb')
    except wave.Error:
        return read_float_wave(path)
    with stream:
        rate, count = stream.getframerate(), stream.getnframes()
        if (stream.getnchannels() != 1 or stream.getsampwidth() != 2
                or stream.getcomptype() != 'NONE' or rate <= 0):
            raise ValueError('expected mono PCM16 or float32 WAVE')
        payload = stream.readframes(count)
        if len(payload) != count * 2:
            raise ValueError('incomplete PCM16 waveform')
    values = np.frombuffer(payload, dtype='<i2').astype(np.float32)
    values *= np.float32(1.0 / 32768.0)
    return rate, values


def _count(value):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError('expected a nonnegative integer count')
    return int(value)


def read_replay(path):
    """Retain output identity and every label's identity and exact-mask matches."""
    csv.field_size_limit(8 * 1024 * 1024)
    with Path(path).open(newline='') as stream:
        rows = csv.reader(stream, delimiter='\t')
        header, values = next(rows), next(rows)
        if len(set(header)) != len(header) or len(values) != len(header):
            raise ValueError('malformed replay aggregate')
        aggregate = dict(zip(header, values))
        output = {key: _count(aggregate[key]) for key in COUNTS}
        output['fingerprint'] = aggregate['fingerprint']
        if not re.fullmatch(r'[0-9a-f]{16}', output['fingerprint']):
            raise ValueError('invalid replay fingerprint')
        header = next((row for row in rows if row and row[0] == 'label_index'), None)
        if (header is None or len(set(header)) != len(header)
                or not set(LABEL_FIELDS).issubset(header)):
            raise ValueError('missing or malformed label-details header')
        labels = []
        for values in rows:
            if not values:
                continue
            if len(values) != len(header):
                raise ValueError('malformed label-details row')
            row = dict(zip(header, values))
            label = {key: _count(row[key]) for key in LABEL_FIELDS}
            if (label['label_index'] != len(labels)
                    or label['end_sample'] <= label['start_sample']
                    or label['midi_note'] > 127 or label['string_mask'] > 255
                    or label['matched'] > label['labeled']):
                raise ValueError('invalid label identity or counts')
            labels.append(label)
    if any(sum(row[key] for row in labels) != output[key] for key in ('labeled', 'matched')):
        raise ValueError('label and aggregate accounting disagree')
    groups = {}
    for row in labels:
        group = groups.setdefault(str(row['string_mask'].bit_count()), dict(labeled=0, matched=0))
        for key in ('labeled', 'matched'):
            group[key] += row[key]
    return dict(output=output, labels=labels, exact_matches_by_string_count=groups)


def compare_replays(before, after):
    """A gain elsewhere cannot compensate for any lost label or safety count."""
    a, b = before['labels'], after['labels']
    if (len(a) != len(b) or before['output']['labeled'] != after['output']['labeled']
            or any(left[key] != right[key] for left, right in zip(a, b)
                   for key in LABEL_FIELDS if key != 'matched')):
        raise ValueError('label identity or accounting changed')
    delta = {key: after['output'][key] - before['output'][key]
             for key in ('matched', *ERRORS)}
    changed = [dict(label_index=left['label_index'], midi_note=left['midi_note'],
                    string_mask=left['string_mask'], labeled=left['labeled'],
                    baseline_matched=left['matched'], current_matched=right['matched'],
                    matched_delta=right['matched'] - left['matched'])
               for left, right in zip(a, b) if left['matched'] != right['matched']]
    losses = [row['label_index'] for row in changed if row['matched_delta'] < 0]
    regressions = [key for key in ERRORS if delta[key] > 0]
    return dict(delta=delta, changed_labels=changed, lost_labels=losses,
                increased_error_counts=regressions,
                gate_pass=delta['matched'] >= 0 and not losses and not regressions,
                output_bit_identical=before['output'] == after['output'])
