import unittest
from tools import portable_ordinary_harmonic_admission as t


class PersistentCandidateScreenTests(unittest.TestCase):
    def result(self, held=47000, longest=45953, attacks=3, frames=729):
        def row(h, length, a):
            return dict(midi_lifecycle=dict(labels=[dict(t.PERSISTENCE_TARGET,
                exact_held_samples=h, longest_exact_hold_samples=length,
                note_ons_inside_label=a)]))
        def replay(f):
            return dict(labels=[dict(t.PERSISTENCE_TARGET, matched=f, labeled=1122)])
        return t.target_result(row(46529, 45953, 3), row(held, longest, attacks),
                               replay(729), replay(frames), target=t.PERSISTENCE_TARGET)

    def test_real_hold_gain_passes(self):
        self.assertTrue(self.result()['improved'])

    def test_parity_and_fragmented_or_retriggered_gain_fail(self):
        for change in ({'held': 46529}, {'longest': 45952}, {'attacks': 4}, {'frames': 728}):
            with self.subTest(change=change):
                self.assertFalse(self.result(**change)['improved'])

    def test_trial_cannot_mix_other_policies_or_wrong_trace_window(self):
        for option in ('supported_sustain_renewal', 'local_onset_evidence',
                       'fundamental_veto_check', 'calibrated_assignment_prior',
                       'joint_rescue_eligibility', 'pending_string_posterior',
                       'posterior_loss_diagnostic', 'energy_weighted_descriptor',
                       'common_detuning_support', 'assignment_diagnostic'):
            with self.subTest(option=option), self.assertRaisesRegex(ValueError, 'must be isolated'):
                t.run(None, None, None, None, None,
                      persistent_candidate_admission=True, **{option: True})
