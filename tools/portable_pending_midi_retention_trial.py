"""Screen output-only MIDI retention without changing detector inference."""
from tools.portable_forced_pending_string_trial import (
    COLLISION_FLAG, HELD_BASELINE, HELD_LABEL, main, run as run_screen)


FLAG = '--diagnostic-pending-midi-retention'
CONDITIONS = (('reference-off', ()), ('current-on', (COLLISION_FLAG,)),
              ('midi-retention-on', (COLLISION_FLAG, FLAG)))


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    return run_screen(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, conditions=CONDITIONS, schema='m3_pending_midi_retention_trial_v1',
        preserve_inference=True, held_label=HELD_LABEL, held_baseline=HELD_BASELINE,
        policy='Retain an actual sounding singleton MIDI lane only while a selected '
            'inactive, unready, single-playable-string candidate claims it. Yield to '
            'active claims, attack readiness, fresh spectral evidence, groups, '
            'retunes and atomic handoffs. Physical assignment, candidate maturation '
            'and virtual MIDI trajectory must remain identical to current ON. '
            'Reject any passage held-sample loss or growth in raw wrong-note, '
            'wrong-string or unlabeled-gap voice-samples. Independent MIDI '
            'ownership remains enabled. This screen cannot establish live readiness.')


if __name__ == '__main__':
    main(run)
