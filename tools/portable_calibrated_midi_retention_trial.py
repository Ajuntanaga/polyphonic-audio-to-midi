"""Screen output-only retention qualified by independent calibrated string evidence."""
from tools.portable_forced_pending_string_trial import (
    COLLISION_FLAG, HELD_BASELINE, HELD_LABEL, main, run as run_screen)


FLAG = '--diagnostic-calibrated-midi-retention'
CONDITIONS = (('reference-off', ()), ('current-on', (COLLISION_FLAG,)),
              ('calibrated-midi-retention-on', (COLLISION_FLAG, FLAG)))


def run(binary, corpus, manifest_path, reference_path, output, *, timeout=900):
    return run_screen(binary, corpus, manifest_path, reference_path, output,
        timeout=timeout, conditions=CONDITIONS, schema='m3_calibrated_midi_retention_trial_v1',
        preserve_inference=True, held_label=HELD_LABEL, held_baseline=HELD_BASELINE,
        policy='Retain an actual sounding singleton MIDI lane through an immature '
            'single-playable-string claim only when its current harmonic profile '
            'uniquely favors the retained lane among all playable calibrated strings. '
            'Missing, invalid or tied calibration yields. Preserve active claims, '
            'attack readiness, spectral evidence, groups, retunes and handoffs. '
            'Complete inference must remain identical to current ON. Reject any '
            'label held-sample loss or increased raw false voice-samples or onsets. '
            'Independent MIDI ownership remains enabled. This ordinary screen '
            'cannot establish corpus timing or live readiness.')


if __name__ == '__main__':
    main(run)
