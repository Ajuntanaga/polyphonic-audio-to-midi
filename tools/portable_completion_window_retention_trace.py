"""Localize snapshot-only changes in the rejected completion-window trial.

The GitHub worker captures two unchanged policies. Complete snapshot outcomes
are compared over the whole recording; assignment traces cover the known raw
hold differences. No detector policy or acceptance threshold changes here.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import shutil

from tools.candidate_outcome_analysis import _candidates, compare_streams
from tools.portable_assignment_trace import digest
from tools.portable_corpus_replay import SETTINGS
from tools.portable_pending_string_trace import run as capture


DATASET = 'physical-long'
CASE = dict(label_index=3, midi_note=40, string_mask=7,
            start_sample=2932608, end_sample=5452800)
WINDOW = (3580736, 3598656)
CONDITIONS = (
    ('current-on', ('--diagnostic-spectral-lane-collision',)),
    ('completion-window-retention-on', ('--diagnostic-spectral-lane-collision',
                                        '--diagnostic-completion-window-retention')))
REFERENCE_SCHEMA = 'm3_completion_window_retention_trace_references_v1'
INTERPRETATION = (
    'Both complete scored TSV and raw MIDI streams must reproduce saved references; '
    'current-ON must also reproduce its saved full outcome. The rejected trial had '
    'no prior full outcome digest. Exact wrong-note additions/removals are snapshot '
    'voice frames, not MIDI events. Complete outcomes cover the recording; bounded '
    'assignment evidence covers only the stated window. No policy, installed output, '
    'timing, allocation or external host acceptance is changed or established.')


def validate_reference(reference, manifest):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != DATASET
            or reference['settings'] != SETTINGS or reference['case'] != CASE
            or reference['window'] != list(WINDOW) or reference['block_samples'] != 512
            or reference['conditions'] != {name: list(flags) for name, flags in CONDITIONS}
            or set(reference['replay_references']) != {name for name, _ in CONDITIONS}):
        raise ValueError('Wrong fixed completion-window trace selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if reference['source'][key] != manifest['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in (DATASET+'.wav', DATASET+'.tsv', 'calibration.m3cb', 'templates.tsv'):
        if reference['inputs'][name] != manifest['files'][name]:
            raise ValueError('Saved input identity differs: ' + name)
    for policy, _ in CONDITIONS:
        row = reference['replay_references'][policy]
        for key in ('tsv_sha256', 'midi_sha256', *(['outcome_sha256'] if policy == 'current-on' else [])):
            if not re.fullmatch('[0-9a-f]{64}', row.get(key, '')):
                raise ValueError('A saved complete digest is required: ' + key)
        held = row['held_labels'][str(CASE['label_index'])]
        if (row['sample_count'] != 5646848 or row['sample_rate'] != 96000
                or any(held[key] != value for key, value in CASE.items())
                or held['first_exact_hold_delay_samples'] != 520639):
            raise ValueError('Saved annotation, sample clock or first exact hold changed')


def context(frame):
    if frame is None:
        return None
    return dict(sample=frame['sample'], tick=frame['tick'], quiet=frame['quiet'],
        signal_samples=frame['signal_samples'], labels=frame['labels'],
        matched_labels=sorted(frame['matched']), voices=frame['voices'],
        candidates=_candidates(frame))


class WrongNoteChanges:
    """Keep every wrong-note multiplicity change and the preceding paired tick."""
    def __init__(self):
        self.previous = (None, None)
        self.frames = []
        self.counts = Counter()

    def __call__(self, control, trial):
        counts = [Counter(v[:3] for v in f['voices'] if v[3] == 1)
                  for f in (control, trial)]
        removed, added = counts[0]-counts[1], counts[1]-counts[0]
        if removed or added:
            self.counts['removed'] += sum(removed.values())
            self.counts['added'] += sum(added.values())
            self.frames.append(dict(sample=control['sample'], tick=control['tick'],
                removed=[dict(identity=key, count=n) for key, n in sorted(removed.items())],
                added=[dict(identity=key, count=n) for key, n in sorted(added.items())],
                control=context(control), trial=context(trial),
                preceding_control=context(self.previous[0]),
                preceding_trial=context(self.previous[1])))
        self.previous = (control, trial)


class CompleteOutcomes:
    def __init__(self, output, references):
        self.output, self.references = output, references
        self.control = None
        self.captured = set()

    def __call__(self, policy, path):
        if policy not in self.references or policy in self.captured:
            raise ValueError('Unexpected or repeated policy capture')
        result = dict(captured_raw_sha256=digest(path))
        if policy == CONDITIONS[1][0]:
            if self.control is None:
                raise ValueError('Current outcome must be captured before trial')
            observer = WrongNoteChanges()
            with gzip.open(self.control, 'rt', encoding='utf-8') as a, path.open() as b:
                comparison = compare_streams(a, b, self.references['current-on']['output'],
                    self.references[policy]['output'], observe_frame=observer)
            if (observer.counts['added']-observer.counts['removed'] !=
                    comparison['trial'].get('wrong_note', 0)-comparison['control'].get('wrong_note', 0)):
                raise ValueError('Wrong-note localization does not reconcile to full totals')
            result.update(comparison=comparison, wrong_note_changes={
                key: observer.counts[key] for key in ('added', 'removed')},
                changed_wrong_note_frames=observer.frames, truncated=False,
                voice_identity_fields=['detected_note', 'emitted_note', 'string'],
                voice_fields=['detected_note', 'emitted_note', 'string', 'outcome',
                              'age_ticks', 'cents_valid', 'cents_q8', 'evidence_mask'])
        elif policy != 'current-on' or self.control is not None:
            raise ValueError('Unexpected or repeated policy capture')
        destination = self.output / (policy+'-complete-outcome.tsv.gz')
        with path.open('rb') as source, gzip.open(destination, 'wb', compresslevel=1) as target:
            shutil.copyfileobj(source, target)
        result['complete_outcome'] = dict(file=destination.name, sha256=digest(destination),
                                          bytes=destination.stat().st_size)
        if policy == 'current-on':
            self.control = destination
        self.captured.add(policy)
        return result


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    reference = json.loads(reference_path.read_text())
    validate_reference(reference, json.loads(manifest_path.read_text()))
    return capture(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, dataset=DATASET, cases=(CASE,), conditions=CONDITIONS,
        window=lambda label: WINDOW,
        observe_outcome=CompleteOutcomes(output, reference['replay_references']),
        schema='m3_completion_window_retention_trace_v1', interpretation=INTERPRETATION)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'corpus', 'manifest', 'reference-report', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--replay-timeout-seconds', type=int, default=900)
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.reference_report, args.output,
        timeout=args.replay_timeout_seconds)


if __name__ == '__main__':
    main()
