"""The bounded replacement must satisfy every original no-regression gate."""
from tests import test_portable_pending_string_trial as contracts
from tools import portable_forced_pending_string_trial as trial


class PortableForcedPendingStringTrialTests(contracts.PortablePendingStringTrialTests):
    runner = trial
    trial_stem = 'forced-trial-on'

    def test_trial_route_is_distinct_from_rejected_policy(self):
        self.assertEqual(trial.FLAG, '--diagnostic-forced-pending-string-reservation')
        self.assertEqual(trial.CONDITIONS[2][0], self.trial_stem)
        self.assertEqual(contracts.trial.CONDITIONS[2][0], 'trial-on')
        self.assertNotEqual(trial.FLAG, contracts.trial.FLAG)
