"""Bounded observation-only recording diagnostic; execute on GitHub Actions."""
import argparse
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import zipfile
import time
from collections import Counter

from tools import harmonic_admission_cues as admission
from tools import harmonic_competition_cues as competition
from tools.portable_assignment_trace import digest
from tools.portable_ordinary_harmonic_admission import load_audio, verify_references

ARCHIVE_SHA = '14edb13c4711f032fe71b154fb8c7d92becc2dc63c60fdbd132f99a01be5cc5f'
ARCHIVE_BYTES = 46162661
MEMBER = 'github-results/ordinary-harmonic-fixed-competition/ordinary-current-on-512-outcome.tsv.gz'
# Predeclared diagnostic windows, not policy thresholds or training examples.
FOCUS = ((65, 650000, 680000), (74, 2960000, 3010560))


def run(corpus, manifest_path, reference_path, archive, output, all_admissions=False):
    reference = json.loads(reference_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    verify_references(reference, manifest, corpus, config=competition.CONFIG)
    if archive.stat().st_size != ARCHIVE_BYTES or digest(archive) != ARCHIVE_SHA:
        raise ValueError('Retained outcome archive identity differs')
    audio = load_audio(corpus / 'ordinary.wav')
    deadline = time.monotonic() + 2400
    counts = Counter()
    changes = []
    rows = []
    experiment_rows = []
    with zipfile.ZipFile(archive) as bundle:
        if bundle.namelist().count(MEMBER) != 1:
            raise ValueError('Retained outcome member is not unique')
        with bundle.open(MEMBER) as packed, gzip.GzipFile(fileobj=packed) as raw, io.TextIOWrapper(raw) as stream:
            # Consume the whole stream to validate its clock and length, while
            # doing numerical work only inside the two predeclared windows.
            for available, state, current in admission.causal_states(stream, len(audio)):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Admission comparison exceeded 2400 seconds')
                if all_admissions:
                    eligible = admission.eligible_notes(current)
                    if not eligible:
                        continue
                    window, prepared = admission.prediction_window(audio, available, state)
                    for note in sorted(eligible):
                        baseline = competition.evaluate_candidate(window, prepared, note, state)
                        experiment = baseline
                        if (not baseline['admitted'] and any(
                                c.get('upper_comparison', {}).get('status') == 'insufficient_supported_pairs'
                                and c.get('upper_comparison', {}).get('supported_harmonics') == [1]
                                for c in baseline['lower_comparisons'])):
                            experiment = competition.evaluate_candidate(
                                window, prepared, note, state, fundamental_veto_check=True)
                        counts[f"{int(baseline['admitted'])}->{int(experiment['admitted'])}"] += 1
                        if baseline['admitted'] != experiment['admitted']:
                            changes.append(dict(available_sample=available, note=note,
                                baseline=baseline, experiment=experiment))
                    continue
                notes = [note for note, begin, end in FOCUS if begin <= available < end]
                if not notes:
                    continue
                eligible = admission.eligible_notes(current)
                for note in notes:
                    if note not in eligible:
                        rows.append(dict(available_sample=available, note=note, status='not_eligible'))
                        continue
                    window, prepared = admission.prediction_window(audio, available, state)
                    baseline = competition.evaluate_candidate(window, prepared, note, state)
                    diagnostic = competition.evaluate_candidate(window, prepared, note, state,
                                                                 continuity_diagnostic=True)
                    without_observations = deepcopy(diagnostic)
                    for comparison in without_observations['lower_comparisons']:
                        comparison.pop('source_continuity', None)
                    if without_observations != baseline:
                        raise ValueError('Observation changed the admission decision or evidence')
                    experiment = competition.evaluate_candidate(
                        window, prepared, note, state, fundamental_veto_check=True)
                    experiment_rows.append(dict(available_sample=available, note=note,
                        baseline_admitted=baseline['admitted'], result=experiment))
                    rows.append(diagnostic)
    if all_admissions:
        output.mkdir(parents=True, exist_ok=True)
        report = dict(schema="m3_fundamental_veto_screen_v1", source=manifest["source"],
            archive_sha256=ARCHIVE_SHA, scope="all eligible ordinary saved-state admissions",
            transitions=dict(counts), changes=changes, final=True, corpus_gate_pass=None,
            limits="Admission changes only, not delivered MIDI, labels, timing or live readiness.")
        (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        return
    if not rows:
        raise ValueError('No focused observations')
    report = dict(schema='m3_source_continuity_v1', source=manifest['source'],
                  archive_sha256=ARCHIVE_SHA, archive_member=MEMBER, focus=FOCUS,
                  decision_parity=True, policy_changed=False, corpus_gate_pass=None,
                  limits='Diagnostic energy/phase only; no acoustic onset labels, score gain, native timing or live-host acceptance.',
                  rows=rows, fundamental_veto_experiment=dict(
                      enabled_in_production=False, corpus_gate_pass=None,
                      limits='Focused admission evidence only; no native replay or false-output gate.',
                      rows=experiment_rows))
    output.mkdir(parents=True, exist_ok=True)
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('corpus', 'manifest', 'reference', 'archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--all-admissions', action='store_true')
    args = parser.parse_args()
    run(args.corpus, args.manifest, args.reference, args.archive, args.output, args.all_admissions)


if __name__ == '__main__':
    main()
