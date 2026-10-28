import copy
import unittest

from tools.harmonic_fit_inputs import validate_coupled_inputs


class HarmonicFitInputTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'dataset': 'physical-long', 'capture_path': 'results/capture.jsonl',
                         'capture_sha256': 'capture', 'calibration_sha256': 'calibration',
                         'prepared_npz_sha256': 'prepared-arrays',
                         'sample_rate': 96000, 'sources': [{'string': 0}, {'string': 1}],
                         'windows': [{'note': 40, 'training_samples': 200}] * 2}
        self.control_hashes = {'joint.py': 'a', 'drift.py': 'b'}
        self.profile_hashes = {**self.control_hashes, 'balance.py': 'c'}
        self.control = {'metadata': copy.deepcopy(self.metadata),
                        'fit_source_sha256': self.control_hashes.copy(), 'results': [
                            {'index': i, 'note': 40, 'training_samples': 200,
                             'models': [{'mask': mask, 'fit_family': family} for mask in (1, 2, 3)
                                        for family in ('static', 'pitch_drift', 'gain_drift', 'pitch_and_gain')]}
                            for i in range(2)]}
        self.profiles = {'source_sha256': self.profile_hashes.copy(),
                         'isolated': {'prototypes': {'0': [0.9, 0.1, 0], '1': [0.3, 0.6, 0.1]}},
                         'manifest': {'note': 40, 'clips': [{'string': i, 'pass': 1} for i in (0, 1)]}}

    def validate(self, control=None, profiles=None):
        validate_coupled_inputs(self.metadata, self.control if control is None else control,
                                self.profiles if profiles is None else profiles,
                                self.control_hashes, self.profile_hashes)

    def test_matching_inputs_are_accepted(self):
        self.validate()

    def test_stale_capture_or_model_identity_is_rejected(self):
        for field in self.metadata:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.control)
                changed['metadata'][field] = None
                with self.assertRaises(ValueError): self.validate(control=changed)
        mutations = [lambda c: c['fit_source_sha256'].update({'drift.py': 'changed'}),
                     lambda c: c['results'][1].update(index=0),
                     lambda c: c['results'][0]['models'].pop(),
                     lambda c: c['results'][0]['models'][0].update(fit_family='unknown'),
                     lambda c: c['results'][0]['models'][0].update(mask=7),
                     lambda c: c['results'][0].update(note=41),
                     lambda c: c['results'][0].update(training_samples=199)]
        for mutate in mutations:
            changed = copy.deepcopy(self.control); mutate(changed)
            with self.assertRaises(ValueError): self.validate(control=changed)

    def test_wrong_profile_source_is_rejected(self):
        mutations = [lambda p: p['source_sha256'].update({'balance.py': 'changed'}),
                     lambda p: p['isolated']['prototypes'].update({'2': [1, 0, 0]}),
                     lambda p: p['isolated']['prototypes'].pop('1'),
                     lambda p: p['manifest'].update(note=41),
                     lambda p: p['manifest']['clips'][1].update(string=2)]
        for mutate in mutations:
            changed = copy.deepcopy(self.profiles); mutate(changed)
            with self.assertRaises(ValueError): self.validate(profiles=changed)
