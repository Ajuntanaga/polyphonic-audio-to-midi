"""Measured pitch context replaces zero boundaries; output targets stay MIDI32..84.

The 36-row halo is the exact radius of the four dilated residual convolutions.
It adds measured context as well as removing padding, so their effects cannot
be isolated by this one comparison. No additional labels or output pitches.
"""
import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.shared_harmonic_learning import HarmonicFeatures, FEATURE_COUNT, NOTE_COUNT, candidate_rows
from tools.harmonic_context_learning import SETWISE_PARAMS


HALO = sum(SETWISE_PARAMS['dilations'])
INPUT_NOTE_COUNT = NOTE_COUNT+2*HALO
HALO_PARAMETERS = dict(name='measured_pitch_halo_valid_context_v1',
    halo_rows_each_side=HALO, input_note_low=SETTINGS['note_low']-HALO,
    input_note_high=SETTINGS['note_high']+HALO, input_note_count=INPUT_NOTE_COUNT,
    output_note_low=SETTINGS['note_low'], output_note_high=SETTINGS['note_high'],
    output_note_count=NOTE_COUNT, features_per_candidate=FEATURE_COUNT,
    scaler_fit='central training rows only; same frozen scaler applied to halo',
    residual='crop d rows at each end before adding each valid dilated convolution',
    target_expansion=False, training_plan_changed=False)
HALO_MODEL_PARAMS = dict(SETWISE_PARAMS, padding='valid',
    normalization='training-only central MIDI32..84 mean/std per coordinate; apply to full measured halo')


class HarmonicHaloFeatures(HarmonicFeatures):
    halo_parameters = HALO_PARAMETERS

    def __init__(self):
        super().__init__(note_low=HALO_PARAMETERS['input_note_low'],
                         note_high=HALO_PARAMETERS['input_note_high'])


def central_features(features):
    rows = candidate_rows(features, note_count=INPUT_NOTE_COUNT)
    values = rows.reshape(-1, INPUT_NOTE_COUNT, FEATURE_COUNT)
    return np.ascontiguousarray(values[:, HALO:HALO+NOTE_COUNT, :]).reshape(len(values), NOTE_COUNT*FEATURE_COUNT)
