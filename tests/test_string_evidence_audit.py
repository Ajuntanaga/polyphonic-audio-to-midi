import unittest

from tools.string_evidence_audit import age_bin, observe, rank, summarize


def row(sample=1023, note=40, mask=1, likelihood=None, prior=None, post=None):
    text = lambda values: ','.join(map(str, values))
    return dict(sample=str(sample), tick=str((sample + 1) // 64), note=str(note),
                expected_note='1', expected_mask=str(mask), playable='7',
                rendered_mask='1', fixed_context='0', use_posterior='1',
                candidate_age_ticks='16', reserved_coasting='0', reserved_extras='0',
                posterior_observation_available='1', posterior_updated='1',
                posterior_onset_strength='0.0', valid='1', dp_primary='0',
                posterior_log_likelihood=text(likelihood or [2, 1, 0, 0, 0, 0, 0, 0]),
                posterior_prior=text(prior or [0.9, 0.05, 0.05, 0, 0, 0, 0, 0]),
                posterior_probability=text(post or [0.9, 0.05, 0.05, 0, 0, 0, 0, 0]))


class StringEvidenceAuditTests(unittest.TestCase):
    def test_annotation_age_boundaries(self):
        self.assertEqual(age_bin(4799, 48000), 'attack_0_100ms')
        self.assertEqual(age_bin(4800, 48000), 'early_100_350ms')
        self.assertEqual(age_bin(16800, 48000), 'settled_350ms_plus')

    def test_history_disagreement_is_distinct_from_assignment(self):
        r = row(prior=[0.01, 0.98, 0.01, 0, 0, 0, 0, 0],
                post=[0.1, 0.8, 0.1, 0, 0, 0, 0, 0])
        counts, ranks = observe(r, 1)
        self.assertEqual(counts['prior_wrong_likelihood_correct_posterior_wrong'], 1)
        self.assertTrue(ranks['likelihood']['correct'])
        self.assertFalse(ranks['posterior']['correct'])
        self.assertEqual(counts['render_exact'], 1)
        r = row(); r.update(rendered_mask='2', dp_primary='1')
        counts, _ = observe(r, 1)
        self.assertEqual(counts['likelihood_and_posterior_correct_dp_wrong'], 1)
        self.assertEqual(counts['used_posterior_correct_render_missing'], 1)

    def test_ties_and_infeasible_lanes_do_not_count_as_correct(self):
        measured = rank([1] * 8, 7, 0)
        self.assertFalse(measured['correct']); self.assertTrue(measured['tie'])
        r = row(); r['playable'] = '6'
        counts, ranks = observe(r, 1)
        self.assertEqual(counts['infeasible_expected_lane'], 1)
        self.assertFalse(ranks)

    def test_missing_fixed_and_failed_rows_are_unavailable(self):
        self.assertEqual(observe(None, 1)[0]['missing_assignment_row'], 1)
        r = row(); r.update(fixed_context='1', posterior_observation_available='0')
        counts, ranks = observe(r, 1)
        self.assertEqual(counts['observation_unavailable'], 1); self.assertFalse(ranks)
        r = row(); r['posterior_updated'] = '0'
        counts, ranks = observe(r, 1)
        self.assertEqual(counts['update_failed'], 1); self.assertNotIn('posterior', ranks)

    def test_prior_support_and_multi_string_labels(self):
        r = row(prior=[0, 1, 0, 0, 0, 0, 0, 0])
        counts, ranks = observe(r, 1)
        self.assertEqual(counts['prior_excludes_expected'], 1)
        self.assertIsNone(ranks['prior'])
        counts, ranks = observe(r, 3)
        self.assertEqual(counts['multi_string_target_no_lane_rank'], 1)
        self.assertFalse(ranks)

    def test_note_only_labels_do_not_score_string_assignment(self):
        counts, ranks = observe(row(), 0)
        self.assertEqual(counts['note_only_label'], 1)
        self.assertNotIn('render_contains_expected', counts)
        self.assertNotIn('extra_rendered_strings', counts)
        self.assertFalse(ranks)

    def test_full_clock_counts_omitted_rows_and_label_end_is_exclusive(self):
        labels = [dict(start_sample=0, end_sample=3071, midi_note=40, string_mask=1)]
        report = summarize(iter([row()]), labels, sample_rate=48000, sample_count=4096,
                           sampled_frames=4, source_identity='test')
        self.assertEqual(report['total']['targets'], 2)
        self.assertEqual(report['total']['captured'], 1)
        self.assertEqual(report['total']['missing_assignment_row'], 1)
        self.assertEqual(report['annotations'][0]['fret'], 8)

    def test_incomplete_grid_or_wrong_join_fails(self):
        options = dict(labels=[dict(start_sample=0, end_sample=2048, midi_note=40,
                                    string_mask=1)], sample_rate=48000, sample_count=2048,
                       sampled_frames=2, source_identity='test')
        with self.assertRaisesRegex(ValueError, 'clock'):
            summarize([], **{**options, 'sampled_frames': 1})
        r = row(); r['expected_mask'] = '2'
        with self.assertRaisesRegex(ValueError, 'join mismatch'):
            summarize([r], **options)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            summarize([row(), row()], **options)
        with self.assertRaisesRegex(ValueError, 'off the decision grid'):
            summarize([row(sample=1024)], **options)

    def test_overlapping_annotation_age_is_not_invented(self):
        labels = [dict(start_sample=0, end_sample=2048, midi_note=40, string_mask=mask)
                  for mask in (1, 2)]
        report = summarize([row(mask=3)], labels, sample_rate=48000, sample_count=2048,
                           sampled_frames=2, source_identity='test')
        self.assertEqual(report['total']['targets'], 2)
        self.assertEqual(report['total']['overlapping_annotations_no_age_bucket'], 2)
        self.assertTrue(all(not counts for counts in report['age_bins'].values()))

    def test_nonfinite_and_non_normalized_posteriors_fail(self):
        for replacement in ('nan,0,0,0,0,0,0,0', '1,1,0,0,0,0,0,0'):
            r = row(); r['posterior_probability'] = replacement
            with self.assertRaises(ValueError):
                observe(r, 1)


if __name__ == '__main__':
    unittest.main()
