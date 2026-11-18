"""One ordinary-corpus admission screen; recorded audio and native work run on GHA.

Generate past-only cues from a separately frozen current-detector shadow. This
tests an offline admission hypothesis, not a native feedback implementation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from scipy.io import wavfile

from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.harmonic_admission_cues import CONFIG, generate
from tools.portable_assignment_trace import compress_trace_window, digest
from tools.portable_calibrated_midi_retention_corpus import (
    analyze_midi, compare_notes, saved_identity)
from tools.portable_corpus_replay import SETTINGS, command_for, now


OFF, CURRENT, TRIAL = 'reference-off', 'current-on', 'harmonic-admission-on'
COLLISION = '--diagnostic-spectral-lane-collision'
REFERENCE_FLAGS = {OFF: [], CURRENT: [COLLISION]}
REFERENCE_SCHEMA = 'm3_ordinary_harmonic_admission_references_v1'
RATE, SAMPLES = 96000, 10689600
INPUTS = {'ordinary.wav', 'ordinary.tsv', 'calibration.m3cb', 'templates.tsv'}
TARGET = dict(label_index=10, midi_note=75, string_mask=128,
              start_sample=163306, end_sample=235200)


def verify_references(reference, manifest, corpus, config=CONFIG):
    if (reference['schema'] != REFERENCE_SCHEMA or reference['dataset'] != 'ordinary'
            or reference['settings'] != SETTINGS or reference['block_samples'] != 512
            or reference['reference_flags'] != REFERENCE_FLAGS
            or reference['config'] != config or reference['target'] != TARGET
            or set(reference['inputs']) != INPUTS
            or set(reference['runs']) != {OFF, CURRENT}):
        raise ValueError('Invalid frozen harmonic-admission reference selection')
    for key in ('input_release', 'input_bundle_sha256', 'original_input_manifest_sha256'):
        if manifest['source'][key] != reference['source'][key]:
            raise ValueError('Saved input provenance differs: ' + key)
    for name in sorted(INPUTS):
        spec = reference['inputs'][name]
        if (manifest['files'][name]['sha256'] != spec['sha256']
                or (corpus / name).stat().st_size != spec['bytes']
                or digest(corpus / name) != spec['sha256']):
            raise ValueError('Saved input identity differs: ' + name)
    for row in reference['runs'].values():
        if (row['sample_count'], row['sample_rate']) != (SAMPLES, RATE):
            raise ValueError('Saved ordinary sample clock differs')
    return len(INPUTS)


def load_audio(path):
    rate, audio = wavfile.read(path, mmap=True)
    if rate != RATE or audio.ndim != 1 or len(audio) != SAMPLES or audio.dtype != np.int16:
        raise ValueError('Expected complete ordinary PCM16 mono 96kHz recording')
    return audio


LOCAL_ONSET_TARGET = dict(label_index=451, midi_note=65, string_mask=64,
    start_sample=9220937, end_sample=9292800)


SUSTAIN_TARGET = dict(label_index=252, midi_note=55, string_mask=2,
    start_sample=4569706, end_sample=4641600)


PERSISTENCE_TARGET = dict(label_index=306, midi_note=42, string_mask=1,
    start_sample=5630617, end_sample=5702400)


def target_result(current, trial, current_replay, trial_replay, target=TARGET):
    result = {}
    for name, row, replay in (('before', current, current_replay), ('after', trial, trial_replay)):
        held = [label for label in row['midi_lifecycle']['labels']
                if label['label_index'] == target['label_index']]
        snapshots = [label for label in replay['labels']
                     if label['label_index'] == target['label_index']]
        if (len(held) != 1 or len(snapshots) != 1
                or any(held[0][key] != value or snapshots[0][key] != value
                       for key, value in target.items())):
            raise ValueError('Missing-note target identity differs')
        result[name] = dict(held[0], snapshot_matched=snapshots[0]['matched'],
                            snapshot_labeled=snapshots[0]['labeled'])
    before, after = result['before'], result['after']
    if target in (SUSTAIN_TARGET, PERSISTENCE_TARGET):
        result['improved'] = bool(
            after['exact_held_samples'] > before['exact_held_samples']
            and after['note_ons_inside_label'] <= before['note_ons_inside_label']
            and after['snapshot_matched'] >= before['snapshot_matched'])
        if target == PERSISTENCE_TARGET:
            result['improved'] = bool(result['improved'] and
                after['longest_exact_hold_samples'] >= before['longest_exact_hold_samples'])
        return result
    if before['exact_held_samples'] != 0 or before['note_ons_inside_label'] != 0:
        raise ValueError('Missing-note baseline no longer matches the declared target')
    snapshot_gain = (after['snapshot_matched'] >= before['snapshot_matched']
                     if target == LOCAL_ONSET_TARGET else
                     after['snapshot_matched'] > before['snapshot_matched'])
    result['improved'] = bool(after['exact_held_samples'] > 0
        and after['note_ons_inside_label'] > 0 and snapshot_gain)
    return result


def trace_posterior_losses(binary, corpus, output, flags, trial_replay, trial_midi_hash, deadline):
    """Observe both policies with identical cues; labels only select trace windows."""
    result = {}
    for enabled in (False, True):
        name = 'posterior-loss-' + ('on' if enabled else 'off')
        selected = [flag for flag in flags
                    if enabled or flag != '--diagnostic-pending-string-posterior']
        baseline, midi = output / (name + '.tsv'), output / (name + '-midi.tsv')
        command = command_for(binary, corpus, 'ordinary', 'off', 512, None, midi_trace=midi)
        command.extend(selected)
        def execute(args, target, suffix):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Posterior loss diagnostic budget exhausted')
            with target.open('w') as out, (output / (name + suffix + '.stderr')).open('w') as err:
                subprocess.run(args, stdout=out, stderr=err, timeout=min(900, remaining), check=True)
        if enabled:
            reference, midi_hash = trial_replay, trial_midi_hash
        else:
            execute(command, baseline, '-reference')
            reference, midi_hash = read_replay(baseline), digest(midi)
        rows = []
        for start, end in ((23.5, 24.6), (46.5, 47.6)):
            trace = output / (name + '-' + str(start) + '-costs.tsv')
            traced = output / (name + '-traced.tsv')
            args = command + ['--assignment-trace', str(trace),
                              '--assignment-trace-start', str(start),
                              '--assignment-trace-end', str(end)]
            execute(args, traced, '-' + str(start))
            comparison = compare_replays(reference, read_replay(traced))
            identical = digest(midi) == midi_hash
            if not comparison['output_bit_identical'] or comparison['changed_labels'] or not identical:
                raise ValueError('Posterior loss tracing changed output or MIDI')
            rows.append(dict(start_seconds=start, end_seconds=end, comparison=comparison,
                midi_bit_identical=identical, trace=compress_trace_window(
                    trace, start=round(start * RATE), end=round(end * RATE))))
            trace.unlink()
        result[name] = dict(command=command, windows=rows)
    return result


def trace_local_onset_assignments(binary, corpus, output, conditions, cached, runs, deadline,
                                  start=47.5, end=48.5, prefix="assignment"):
    """Observe both policies in a bounded window; require full replay/MIDI parity."""
    start_sample, end_sample = round(start * 96000), round(end * 96000)
    result = {}
    for mode, flags in conditions:
        if mode == OFF:
            continue
        stem = output / (prefix + '-' + mode)
        tsv = stem.with_suffix('.tsv')
        midi = output / (stem.name + '-midi.tsv')
        costs = output / (stem.name + '-costs.tsv')
        command = command_for(binary, corpus, 'ordinary', 'off', 512, None, midi_trace=midi)
        command.extend(flags)
        command.extend(('--assignment-trace', str(costs),
                        '--assignment-trace-start', str(start), '--assignment-trace-end', str(end)))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Local onset assignment diagnostic budget exhausted')
        with tsv.open('w') as stdout, stem.with_suffix('.stderr').open('w') as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr,
                           timeout=min(900, remaining), check=True)
        comparison = compare_replays(cached[mode], read_replay(tsv))
        identical = digest(midi) == runs[mode]['midi_trace_sha256']
        if (not comparison['output_bit_identical'] or comparison['changed_labels']
                or not identical):
            raise ValueError('Local onset assignment tracing changed output: ' + mode)
        result[mode] = dict(command=command, comparison=comparison,
            midi_bit_identical=identical, start_sample=start_sample, end_sample=end_sample,
            trace=compress_trace_window(costs, start=start_sample, end=end_sample))
        costs.unlink()
        midi.unlink()
    return result


def run(binary, corpus, manifest_path, reference_path, output, max_seconds=2400, competition=False, fundamental_veto_check=False, assignment_diagnostic=False, calibrated_assignment_prior=False, joint_rescue_eligibility=False, pending_string_posterior=False, posterior_loss_diagnostic=False, energy_weighted_descriptor=False, common_detuning_support=False, local_onset_evidence=False, supported_sustain_renewal=False, persistent_candidate_admission=False, contradicted_retention=False):
    if contradicted_retention and any((persistent_candidate_admission, supported_sustain_renewal,
            local_onset_evidence, fundamental_veto_check, calibrated_assignment_prior,
            joint_rescue_eligibility, pending_string_posterior, posterior_loss_diagnostic,
            energy_weighted_descriptor, common_detuning_support)):
        raise ValueError("Contradicted retention trial must be isolated")
    if persistent_candidate_admission and any((supported_sustain_renewal,
            local_onset_evidence, fundamental_veto_check, calibrated_assignment_prior,
            joint_rescue_eligibility, pending_string_posterior, posterior_loss_diagnostic,
            energy_weighted_descriptor, common_detuning_support, assignment_diagnostic)):
        raise ValueError('Persistent admission trial must be isolated')
    if supported_sustain_renewal and any((local_onset_evidence,
            fundamental_veto_check, calibrated_assignment_prior, joint_rescue_eligibility,
            pending_string_posterior, posterior_loss_diagnostic, energy_weighted_descriptor,
            common_detuning_support)):
        raise ValueError('Sustain renewal trial must be isolated')
    if local_onset_evidence and any((fundamental_veto_check,
            calibrated_assignment_prior, joint_rescue_eligibility, pending_string_posterior,
            posterior_loss_diagnostic, energy_weighted_descriptor, common_detuning_support)):
        raise ValueError('Local onset trial must be isolated from rescue policies')
    if posterior_loss_diagnostic and not pending_string_posterior:
        raise ValueError('posterior loss diagnostic requires pending posterior')
    if max_seconds <= 0:
        raise ValueError('max_seconds must be positive')
    if fundamental_veto_check and not competition:
        raise ValueError('fundamental veto check requires competition')
    config, cue_generate = CONFIG, generate
    if competition:
        from tools import harmonic_competition_cues
        config, cue_generate = harmonic_competition_cues.CONFIG, harmonic_competition_cues.generate
    if fundamental_veto_check:
        from functools import partial
        cue_generate = partial(cue_generate, fundamental_veto_check=True)
    output.mkdir(parents=True, exist_ok=False)
    binary, corpus = binary.resolve(), corpus.resolve()
    manifest = json.loads(manifest_path.read_text())
    references = json.loads(reference_path.read_text())
    report = dict(schema='m3_ordinary_harmonic_admission_v1', started_at=now(),
        state='running', final=False, stage='verify frozen inputs and references',
        source=manifest.get('source', {}), reference_source=references['source'],
        reference_manifest_sha256=digest(reference_path),
        input_manifest_sha256=digest(manifest_path), binary_sha256=digest(binary),
        dataset='ordinary', settings=SETTINGS, block_samples=512, config=config,
        target=PERSISTENCE_TARGET if (persistent_candidate_admission or contradicted_retention) else (SUSTAIN_TARGET if supported_sustain_renewal else (LOCAL_ONSET_TARGET if local_onset_evidence else TARGET)),
        contradicted_retention=contradicted_retention,
        persistent_candidate_admission=persistent_candidate_admission,
        supported_sustain_renewal=supported_sustain_renewal,
        local_onset_evidence=local_onset_evidence, common_detuning_support=common_detuning_support, energy_weighted_descriptor=energy_weighted_descriptor, pending_string_posterior=pending_string_posterior, joint_rescue_eligibility=joint_rescue_eligibility, calibrated_assignment_prior=calibrated_assignment_prior, fundamental_veto_check=fundamental_veto_check, runs={}, installed_output_changed=False, promotion_accepted=False,
        native_timing='not measured', allocations='not measured',
        buffer_identity='not measured', live_readiness='not measured',
        metric_scope='Snapshot assignments, overlapping held label-samples and false '
            'voice-samples/onsets are separate. Gap outputs are extra notes, not missing notes.',
        limitations='Offline frozen-shadow cues do not establish a native feedback path or '
            'real-time cost. Conditional prediction contributions can still explain model '
            'mismatch rather than independent notes. The prediction-gain guard excludes '
            'numerical roundoff; it is not an audibility or noise threshold. Labels are '
            'used only after cue generation for scoring.')
    deadline = time.monotonic() + max_seconds
    cue_path = output / 'ordinary-harmonic-admission-cues.tsv'
    evidence_path = output / 'ordinary-harmonic-admission-evidence.jsonl.gz'
    conditions = ((OFF, ()), (CURRENT, (COLLISION,)), (TRIAL, (COLLISION,
        '--candidate-rescue-score-ratio', str(config['score_ratio']),
        '--candidate-rescue-fundamental-ratio', str(config['fundamental_ratio']),
        '--candidate-rescue-harmonic-cues', str(cue_path.resolve()))))
    if calibrated_assignment_prior:
        conditions = tuple((mode, flags + ('--diagnostic-calibrated-assignment-prior',)
                            if mode == TRIAL else flags) for mode, flags in conditions)
    if joint_rescue_eligibility:
        conditions = tuple((mode, flags + ('--diagnostic-joint-rescue-eligibility',)
                            if mode == TRIAL else flags) for mode, flags in conditions)
    if pending_string_posterior:
        conditions = tuple((mode, flags + ('--diagnostic-pending-string-posterior',)
                            if mode == TRIAL else flags) for mode, flags in conditions)
    if energy_weighted_descriptor:
        conditions = tuple((mode, flags + ('--diagnostic-energy-weighted-descriptor',)
                            if mode == TRIAL else flags) for mode, flags in conditions)
    if common_detuning_support:
        conditions = tuple((mode, flags + ('--diagnostic-common-detuning-support',)
                            if mode == TRIAL else flags) for mode, flags in conditions)
    if local_onset_evidence:
        conditions = ((OFF, ()), (CURRENT, (COLLISION,)),
                      (TRIAL, (COLLISION, '--diagnostic-local-onset-evidence')))
        report['limitations'] = ('Native offline onset policy; timing, allocations, full corpus '
                                'and live host acceptance remain unmeasured.')
    if supported_sustain_renewal:
        conditions = ((OFF, ()), (CURRENT, (COLLISION,)),
                      (TRIAL, (COLLISION, '--diagnostic-supported-sustain-renewal')))
        report['limitations'] = ('Native offline sustain renewal policy; timing, allocations, '
                                'full corpus and live host acceptance remain unmeasured.')
    if persistent_candidate_admission:
        conditions = ((OFF, ()), (CURRENT, (COLLISION,)),
                      (TRIAL, (COLLISION, '--diagnostic-persistent-candidate-admission')))
        report['limitations'] = ('Native offline admission policy; added onset delay is possible. '
                                'Timing, allocations, full corpus and live host acceptance remain unmeasured.')
    if contradicted_retention:
        conditions = ((OFF, ()), (CURRENT, (COLLISION,)),
                      (TRIAL, (COLLISION, '--diagnostic-contradicted-retention')))
        report['limitations'] = ('Offline provisional retention diagnostic. Timing, allocations, '
                                'full corpus and live host acceptance remain unmeasured.')
    report['conditions'] = {mode: list(flags) for mode, flags in conditions}

    def save():
        report['updated_at'] = now()
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        temporary.replace(output / 'report.json')

    save()
    cached = {}
    try:
        report['verified_inputs'] = verify_references(references, manifest, corpus, config)
        for mode, flags in conditions:
            stem = 'ordinary-' + mode + '-512'
            report.update(stage='bounded replay', current_run=stem)
            save()
            tsv, stderr, timing = (output / (stem + suffix)
                                  for suffix in ('.tsv', '.stderr', '-timing.json'))
            midi, outcome = (output / (stem + suffix + '.tsv')
                             for suffix in ('-midi', '-outcome'))
            command = command_for(binary, corpus, 'ordinary', 'off', 512, timing, midi_trace=midi)
            command.extend(flags)
            if mode == CURRENT:
                command.extend(('--outcome-trace', str(outcome)))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Bounded screen wall-clock budget exhausted')
            started = time.monotonic()
            with tsv.open('w') as out, stderr.open('w') as err:
                subprocess.run(command, stdout=out, stderr=err,
                               timeout=min(900, remaining), check=True)
            replay = read_replay(tsv)
            lifecycle = analyze_midi(midi, tsv, replay)
            row = dict(elapsed_seconds=time.monotonic() - started, output=replay['output'],
                exact_matches_by_string_count=replay['exact_matches_by_string_count'],
                tsv_sha256=digest(tsv), command=command, midi_lifecycle=lifecycle,
                sample_count=lifecycle['sample_count'], sample_rate=lifecycle['sample_rate'])
            report['runs'][mode] = row
            row['midi_trace'] = compress_trace_window(midi, start=0, end=row['sample_count'])
            row['midi_trace_sha256'] = row['midi_trace']['raw_sha256']
            midi.unlink()
            if mode in REFERENCE_FLAGS:
                row['saved_reference_bit_identical'] = saved_identity(row, references['runs'][mode])
                if not row['saved_reference_bit_identical']:
                    raise ValueError('Saved reference identity drift: ' + mode)
            cached[mode] = replay
            save()
            if mode == CURRENT:
                row['outcome_sha256'] = digest(outcome)
                row['saved_outcome_bit_identical'] = (
                    row['outcome_sha256'] == references['current_outcome_sha256'])
                if not row['saved_outcome_bit_identical']:
                    raise ValueError('Saved current outcome identity drift')
                if not (local_onset_evidence or supported_sustain_renewal or persistent_candidate_admission or contradicted_retention):
                    report.update(stage='generate past-only frozen-shadow cues')
                    save()
                    started = time.monotonic()
                    cue_summary = cue_generate(load_audio(corpus / 'ordinary.wav'), outcome,
                                               cue_path, evidence_path, deadline)
                    cue_summary.update(elapsed_seconds=time.monotonic() - started,
                        complete=True, cue_sha256=digest(cue_path), cue_bytes=cue_path.stat().st_size,
                        evidence_sha256=digest(evidence_path), evidence_bytes=evidence_path.stat().st_size)
                    report['cue_generation'] = cue_summary
                row['outcome_trace'] = compress_trace_window(outcome, start=0, end=row['sample_count'])
                outcome.unlink()
                save()
        if assignment_diagnostic and contradicted_retention:
            report.update(stage='paired contradicted retention assignment trace')
            save()
            report['contradicted_retention_assignment_diagnostic'] = {}
            for label, start, end in ((165, 30.6, 31.4), (306, 58.6, 59.5), (367, 73.9, 74.8)):
                report['contradicted_retention_assignment_diagnostic'][str(label)] = trace_local_onset_assignments(
                    binary, corpus, output, conditions, cached, report['runs'], deadline,
                    start=start, end=end, prefix='retention-assignment-' + str(label))
                save()
        if assignment_diagnostic and local_onset_evidence:
            report.update(stage='paired local onset assignment trace')
            save()
            report['local_onset_assignment_diagnostic'] = trace_local_onset_assignments(
                binary, corpus, output, conditions, cached, report['runs'], deadline)
            save()
        if assignment_diagnostic and supported_sustain_renewal:
            report.update(stage='paired supported sustain assignment trace')
            save()
            report['supported_sustain_assignment_diagnostic'] = {}
            for label, start, end in ((252, 47.5, 48.5), (306, 58.6, 59.5)):
                report['supported_sustain_assignment_diagnostic'][str(label)] = trace_local_onset_assignments(
                    binary, corpus, output, conditions, cached, report['runs'], deadline,
                    start=start, end=end, prefix='sustain-assignment-' + str(label))
                save()
        if assignment_diagnostic and not (local_onset_evidence or supported_sustain_renewal or persistent_candidate_admission or contradicted_retention):
            # Observation only: replay identical cues, then compare complete output
            # and raw MIDI before retaining the bounded assignment evidence.
            report.update(stage='trace experimental initial assignment',
                          current_run='ordinary-assignment-diagnostic')
            save()
            stem = output / 'ordinary-assignment-diagnostic'
            traced_tsv = stem.with_suffix('.tsv')
            traced_midi = output / 'ordinary-assignment-diagnostic-midi.tsv'
            assignment = output / 'ordinary-assignment-diagnostic-costs.tsv'
            trace_command = command_for(binary, corpus, 'ordinary', 'off', 512,
                                        None, midi_trace=traced_midi)
            trace_command.extend(conditions[-1][1])
            trace_command.extend(('--assignment-trace', str(assignment),
                                  '--assignment-trace-start', '6.7',
                                  '--assignment-trace-end', '7.3'))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Assignment diagnostic wall-clock budget exhausted')
            with traced_tsv.open('w') as out, stem.with_suffix('.stderr').open('w') as err:
                subprocess.run(trace_command, stdout=out, stderr=err,
                               timeout=min(900, remaining), check=True)
            comparison = compare_replays(cached[TRIAL], read_replay(traced_tsv))
            midi_identical = digest(traced_midi) == report['runs'][TRIAL]['midi_trace_sha256']
            report['assignment_diagnostic'] = dict(command=trace_command,
                comparison=comparison, midi_bit_identical=midi_identical,
                start_sample=643200, end_sample=700800)
            if (not comparison['output_bit_identical'] or comparison['changed_labels']
                    or not midi_identical):
                raise ValueError('Assignment tracing changed experimental output')
            report['assignment_diagnostic']['trace'] = compress_trace_window(
                assignment, start=643200, end=700800)
            assignment.unlink()
            traced_midi.unlink()
            save()
        if posterior_loss_diagnostic:
            report['posterior_loss_diagnostic'] = trace_posterior_losses(
                binary, corpus, output, conditions[-1][1], cached[TRIAL],
                report['runs'][TRIAL]['midi_trace_sha256'], deadline)
            save()
        report['comparison'] = compare_notes(report['runs'][CURRENT], report['runs'][TRIAL],
            cached[CURRENT], cached[TRIAL], require_inference=False)
        report['snapshot_vs_off'] = compare_replays(cached[OFF], cached[TRIAL])
        report['note_safety_pass'] = bool(report['comparison']['note_safety_pass']
                                        and report['snapshot_vs_off']['gate_pass'])
        report['target_result'] = target_result(report['runs'][CURRENT], report['runs'][TRIAL],
                                               cached[CURRENT], cached[TRIAL],
                                               target=report['target'])
        passed = report['note_safety_pass'] and report['target_result']['improved']
        report.update(state='completed' if passed else 'rejected', stage='final bounded screen')
    except Exception as error:
        report.update(state='failed', stage='failed', error=str(error), error_type=type(error).__name__)
        stem = report.get('current_run')
        if stem and (output / (stem + '.stderr')).exists():
            report['failure_stderr'] = stem + '.stderr'
            report['failure_stderr_tail'] = (output / (stem + '.stderr')).read_text()[-2048:]
        raise
    finally:
        report['reference_identity_pass'] = all(report['runs'].get(mode, {}).get(
            'saved_reference_bit_identical', False) for mode in REFERENCE_FLAGS) and bool(
                report['runs'].get(CURRENT, {}).get('saved_outcome_bit_identical', False))
        report['bounded_screen_pass'] = bool(report['state'] == 'completed'
            and report['reference_identity_pass'] and (local_onset_evidence or supported_sustain_renewal or persistent_candidate_admission or contradicted_retention or
                report.get('cue_generation', {}).get('complete')))
        report['decision'] = ('offline screen passed; corpus timing and live acceptance remain'
            if report['bounded_screen_pass'] else 'rejected or incomplete; do not widen this policy')
        report.update(final=True, finished_at=now())
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('binary', 'corpus', 'manifest', 'references', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--max-seconds', type=int, default=2400)
    parser.add_argument('--competition', action='store_true',
                        help='Condition admission on independently supported unowned lower notes')
    parser.add_argument('--fundamental-veto-check', action='store_true',
                        help='Offline experiment; preserve the default competition policy')
    parser.add_argument('--assignment-diagnostic', action='store_true',
                        help='Trace initial assignment with full untraced output parity')
    parser.add_argument('--calibrated-assignment-prior', action='store_true',
                        help='Offline complete-calibration assignment fret-prior experiment')
    parser.add_argument('--joint-rescue-eligibility', action='store_true',
                        help='Offline owner-protected rescue assignment alternatives')
    parser.add_argument('--pending-string-posterior', action='store_true',
                        help='Offline pending singleton posterior assignment cost')
    parser.add_argument('--posterior-loss-diagnostic', action='store_true')
    parser.add_argument('--energy-weighted-descriptor', action='store_true')
    parser.add_argument('--common-detuning-support', action='store_true')
    parser.add_argument('--local-onset-evidence', action='store_true')
    parser.add_argument('--supported-sustain-renewal', action='store_true')
    parser.add_argument('--contradicted-retention', action='store_true')
    parser.add_argument('--persistent-candidate-admission', action='store_true')
    args = parser.parse_args()
    run(args.binary, args.corpus, args.manifest, args.references, args.output,
        args.max_seconds, competition=args.competition,
        fundamental_veto_check=args.fundamental_veto_check,
        assignment_diagnostic=args.assignment_diagnostic,
        calibrated_assignment_prior=args.calibrated_assignment_prior,
        joint_rescue_eligibility=args.joint_rescue_eligibility,
        pending_string_posterior=args.pending_string_posterior,
        posterior_loss_diagnostic=args.posterior_loss_diagnostic,
        energy_weighted_descriptor=args.energy_weighted_descriptor,
        common_detuning_support=args.common_detuning_support,
        local_onset_evidence=args.local_onset_evidence,
        supported_sustain_renewal=args.supported_sustain_renewal,
        persistent_candidate_admission=args.persistent_candidate_admission,
        contradicted_retention=args.contradicted_retention)


if __name__ == '__main__':
    main()
