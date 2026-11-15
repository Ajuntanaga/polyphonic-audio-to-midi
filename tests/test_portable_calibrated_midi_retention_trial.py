"""Keep the calibrated output-only screen separate from rejected retention."""
from tests import test_portable_pending_midi_retention_trial as contracts
from tools import portable_calibrated_midi_retention_trial as trial


class PortableCalibratedMidiRetentionTrialTests(contracts.PortablePendingMidiRetentionTrialTests):
    runner = trial
    trial_stem = 'calibrated-midi-retention-on'
