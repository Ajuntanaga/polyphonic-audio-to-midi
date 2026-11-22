"""Suppress two absolute-level inputs without changing the context model shape."""
import numpy as np

from tools.direct_spectrum_learning import SETTINGS
from tools.shared_harmonic_learning import FEATURE_COUNT, NOTE_COUNT, HarmonicFeatures


SUPPRESSION = dict(name='harmonic_level_suppression_v1',
    coordinate_indices=[30, 61], replacement=0.0, features_per_candidate=62,
    base_coordinate_names=['w4096:rms_db', 'w16384:rms_db'],
    relative_coordinates='All 60 unchanged, including existing numeric floors and clipping',
    scope='All training, held-out and continuous inputs; no extra level gate',
    normalization='Training-only scaler; constant zero columns have mean=0 and scale=1')


class HarmonicLevelBlindFeatures(HarmonicFeatures):
    """Keep relative coordinates bit-identical; replace both RMS slots with zero.

    These are not fully level-invariant features: the unchanged relative-power
    numeric floors still matter at very low levels. No silence rule is added.
    """
    suppression_parameters = SUPPRESSION

    def __init__(self):
        super().__init__()
        indices = SUPPRESSION['coordinate_indices']
        if (FEATURE_COUNT != SUPPRESSION['features_per_candidate'] or
                [self.coordinate_names[i] for i in indices] != SUPPRESSION['base_coordinate_names']):
            raise ValueError('Absolute-level coordinate layout changed')
        for index in indices:
            self.coordinate_names[index] += ':suppressed_zero'
        self.names = [f'note{note}:{name}'
            for note in range(SETTINGS['note_low'], SETTINGS['note_high']+1)
            for name in self.coordinate_names]

    def __call__(self, past):
        values = super().__call__(past).reshape(NOTE_COUNT, FEATURE_COUNT)
        values[:, SUPPRESSION['coordinate_indices']] = np.float32(SUPPRESSION['replacement'])
        return values.ravel()
