import unittest
from tools import portable_ordinary_harmonic_admission as t


class SupportedSustainScreenTests(unittest.TestCase):
    def result(self, held=49000, attacks=5, frames=760):
        def row(h, a):
            return dict(midi_lifecycle=dict(labels=[dict(t.SUSTAIN_TARGET,
                exact_held_samples=h, note_ons_inside_label=a)]))
        def replay(f):
            return dict(labels=[dict(t.SUSTAIN_TARGET, matched=f, labeled=1124)])
        return t.target_result(row(48577, 5), row(held, attacks),
            replay(760), replay(frames), target=t.SUSTAIN_TARGET)

    def test_longer_hold_without_retrigger_or_frame_loss_is_improvement(self):
        self.assertTrue(self.result()['improved'])

    def test_parity_is_not_improvement(self):
        self.assertFalse(self.result(held=48577)['improved'])

    def test_extra_retrigger_rejects_target_gain(self):
        self.assertFalse(self.result(attacks=6)['improved'])

    def test_snapshot_loss_rejects_target_gain(self):
        self.assertFalse(self.result(frames=759)['improved'])

    def test_rejected_onset_policy_cannot_be_combined(self):
        with self.assertRaisesRegex(ValueError, 'must be isolated'):
            t.run(None, None, None, None, None,
                  supported_sustain_renewal=True, local_onset_evidence=True)

    def test_rescue_assignment_policy_cannot_be_combined(self):
        with self.assertRaisesRegex(ValueError, 'must be isolated'):
            t.run(None, None, None, None, None,
                  supported_sustain_renewal=True, calibrated_assignment_prior=True)
