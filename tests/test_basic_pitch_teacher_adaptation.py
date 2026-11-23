import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from tools.basic_pitch_teacher_adaptation import (
    assess, objective_terms, occurrence_budget, probability_drift)


def occurrence(before=100, after=100, longest_before=None, longest_after=None):
    return dict(example=0, source_key='test:one', note=60,
        baseline_present=before, adapted_present=after,
        baseline_longest=before if longest_before is None else longest_before,
        adapted_longest=after if longest_after is None else longest_after)


def role():
    return dict(original=dict(overall=dict(extra_note_frames=10, exact_frames=20,
                    recall_percent=40), silence_extra_note_frames=2),
        teacher=dict(overall=dict(extra_note_frames=9, exact_frames=21,
                    recall_percent=45), silence_extra_note_frames=1),
        paired=dict(original=dict(budget=dict(pass_budget=True), no_occurrence_loss=False)),
        representation_pass=False)


class TeacherAdaptationTest(unittest.TestCase):
    def test_objective_equals_label_bce_at_teacher(self):
        truth = np.array([1., 0.])
        note, onset = np.array([.8, .1]), np.array([.6, .2])
        terms = objective_terms(truth, note, onset, note, onset)
        self.assertEqual(terms['note_teacher_kl'], 0)
        self.assertEqual(terms['onset_teacher_kl'], 0)
        self.assertAlmostEqual(terms['total'], -(np.log(.8)+np.log(.9))/2)

    def test_each_head_has_its_own_preservation_cost(self):
        q = np.array([.1, .9])
        terms = objective_terms(q, 1-q, q, q, q)
        self.assertGreater(terms['note_teacher_kl'], 0)
        self.assertEqual(terms['onset_teacher_kl'], 0)
        moved = objective_terms(q, 1-q, 1-q, q, q)
        self.assertAlmostEqual(moved['total']-terms['total'], moved['onset_teacher_kl'])
        self.assertGreater(moved['onset_teacher_kl'], 0)

    def test_clipped_extreme_probabilities_stay_finite(self):
        p = np.array([0, 1], dtype=np.float32)
        terms = objective_terms(p, 1-p, 1-p, p, p)
        self.assertTrue(all(np.isfinite(x) for x in terms.values()))
        self.assertTrue(all(x >= 0 for x in terms.values()))

    def test_budget_requires_both_limits_without_rounding(self):
        self.assertTrue(occurrence_budget([occurrence(40, 38)])['pass_budget'])
        self.assertFalse(occurrence_budget([occurrence(39, 37)])['pass_budget'])
        # Three frames fit 5% of 100 but exceed 25 ms.
        self.assertFalse(occurrence_budget([occurrence(100, 97)])['pass_budget'])
        # One frame fits 25 ms but exceeds 5% of a short original hold.
        self.assertFalse(occurrence_budget([occurrence(19, 18)])['pass_budget'])

    def test_hold_loss_is_independent_of_present_gain(self):
        result = occurrence_budget([occurrence(100, 110, 50, 40)])
        self.assertFalse(result['pass_budget'])
        self.assertEqual(result['failures'][0]['reasons'], ['longest'])

    def test_new_miss_cannot_hide_in_other_occurrence_gain(self):
        result = occurrence_budget([occurrence(1, 0), occurrence(0, 100)])
        self.assertEqual(result['newly_missing'], 1)
        self.assertEqual(result['failure_count'], 1)
        with self.assertRaises(ValueError):
            occurrence_budget([])

    def test_window_advance_separate_from_strict_and_representation(self):
        roles = {key: role() for key in ('train', 'calibration', 'test')}
        result = assess(roles, dict(identity=True))
        self.assertEqual(result['verdict'], 'ADVANCE_TO_CONTINUOUS_SCREEN')
        self.assertFalse(result['strict_original_occurrence_preservation'])
        self.assertFalse(result['absolute_representation_target_met'])
        self.assertFalse(result['promotion_accepted'])

    def test_each_role_safety_and_integrity_blocks_advancement(self):
        good = {key: role() for key in ('train', 'calibration', 'test')}
        for name in good:
            for field in ('extra_note_frames', 'exact_frames', 'silence', 'budget'):
                rows = copy.deepcopy(good)
                row = rows[name]
                if field == 'silence':
                    row['teacher']['silence_extra_note_frames'] = 3
                elif field == 'budget':
                    row['paired']['original']['budget']['pass_budget'] = False
                else:
                    row['teacher']['overall'][field] = 11 if field == 'extra_note_frames' else 19
                with self.subTest(role=name, field=field):
                    self.assertFalse(assess(rows, dict(identity=True))['window_advancement_pass'])
        for integrity in ({}, dict(identity=False)):
            self.assertFalse(assess(good, integrity)['window_advancement_pass'])
        self.assertFalse(assess({'test': role()}, dict(identity=True))['window_advancement_pass'])
        good['test']['teacher']['overall']['recall_percent'] = 44.999
        self.assertFalse(assess(good, dict(identity=True))['window_advancement_pass'])

    def test_drift_counts_threshold_crossings_without_weighting_by_labels(self):
        before = np.array([[.1, .3, .9]], dtype=np.float32)
        after = np.array([[.31, .29, .91]], dtype=np.float32)
        result = probability_drift(before, after, .3)
        self.assertEqual(result['threshold_crossings'], 2)
        self.assertAlmostEqual(result['mean_absolute'], .23/3, places=6)
        self.assertGreater(result['teacher_kl_mean'], 0)
        self.assertEqual(probability_drift(before, before, .3)['teacher_kl_mean'], 0)
        with self.assertRaises(ValueError):
            probability_drift(before, after[:, :1], .3)
        for bad in (np.nan, -1, 2):
            with self.assertRaises(ValueError):
                probability_drift(before, np.full_like(before, bad), .3)

    def test_frozen_spec_and_remote_guard(self):
        from tools.portable_basic_pitch_teacher_adaptation import run, validate_spec
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root/'docs/recovery/basic-pitch-teacher-adaptation-20261123.json').read_text())
        validate_spec(spec)
        changed = copy.deepcopy(spec)
        changed['teacher']['note_preservation_weight'] = 0
        with self.assertRaises(ValueError):
            validate_spec(changed)
        changed = copy.deepcopy(spec)
        changed['protocol']['continuous_replays'] = 1
        with self.assertRaises(ValueError):
            validate_spec(changed)
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
            with self.assertRaises(RuntimeError):
                run(Path('must-not-read'), Path('must-not-create'))

    def test_metadata_reproduces_all_original_plans(self):
        from tools.basic_pitch_adaptation import SETTINGS, window_plan
        from tools.direct_spectrum_learning import validate_manifest
        from tools.portable_basic_pitch_teacher_adaptation import canonical_hash
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root/'docs/recovery/basic-pitch-teacher-adaptation-20261123.json').read_text())
        manifest = json.loads((root/spec['references']['sources']['path']).read_text())
        takes, counts = validate_manifest(manifest)
        self.assertEqual(counts, dict(train=200, calibration=200, test=155))
        for role in counts:
            plan = window_plan(takes, role, SETTINGS[role+'_examples'], SETTINGS[role+'_seed'])
            self.assertEqual(canonical_hash(plan), spec['training_plan_sha256'][role])


if __name__ == '__main__':
    unittest.main()
