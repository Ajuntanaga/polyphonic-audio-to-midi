"""Small synthetic checks only; no recording, trace corpus or model loaded."""
import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.candidate_outcome_analysis import CANDIDATE_FIELDS
from tools.native_neural_consensus import (
    confirmation_spans, intersect_spans, read_trace, selector_confirmation)
from tools.pitch_detector_comparison import compare, score, union_spans
from tests.test_midi_lifecycle_analysis import label


class ConsensusTests(unittest.TestCase):
    def test_post_sample_boundary_and_last_observation(self):
        spans, _ = confirmation_spans([(63, {60}), (511, {64}), (512, {65})],
                                      sample_count=1600)
        self.assertEqual(spans, [(512, 1024, 64), (1024, 1536, 65)])
        # A future observation cannot make confirmation available retroactively.
        early, _ = confirmation_spans([(63, {60}), (511, {64})], sample_count=1600)
        self.assertEqual(early, [(512, 1024, 64)])

    def test_missing_callbacks_expire_and_observed_empty_clears(self):
        spans, _ = confirmation_spans([(511, {60}), (1535, {60}), (2047, set())],
                                      sample_count=3000)
        self.assertEqual(spans, [(512, 1024, 60), (1536, 2048, 60)])

    def test_horizon_and_invalid_observation_order(self):
        spans, _ = confirmation_spans([(511, {60})], sample_count=600)
        self.assertEqual(spans, [(512, 600, 60)])
        for rows in [[], [(511, {60}), (511, {60})], [(-1, {60})], [(63, {128})]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                confirmation_spans(rows, sample_count=2000)

    def test_same_pitch_intersection_never_shifts_neural_delivery(self):
        spans = intersect_spans([(100, 700, 60), (200, 800, 64)],
                                [(512, 1024, 60), (512, 1024, 65)], sample_count=1200)
        self.assertEqual(spans, [(512, 700, 60)])

    def test_evicted_pooled_direct_pitch_does_not_require_final_selection(self):
        self.assertTrue(selector_confirmation(dict(selection=3, selector_pool_member=1, direct=1)))
        for pool, direct in [(0, 1), (1, 0), (0, 0)]:
            self.assertFalse(selector_confirmation(dict(selector_pool_member=pool, direct=direct)))
        with self.assertRaises(ValueError):
            selector_confirmation(dict(direct=1))

    def test_trace_quiet_or_missing_tuple_cannot_supply_support(self):
        candidate = dict.fromkeys(CANDIDATE_FIELDS, 0)
        candidate.update(note=65, selector_pool_member=1, direct=1, selection=3)
        text = ':'.join(str(candidate[key]) for key in CANDIDATE_FIELDS)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.tsv.gz'
            with gzip.open(path, 'wt') as stream:
                stream.write('# m3_candidate_outcome_v2\nsample\ttick\tquiet\tcandidates\n')
                for quiet in range(8):
                    stream.write(f'{64 * (quiet + 1) - 1}\t{quiet + 1}\t{quiet}\t{text}\n')
                stream.write('575\t9\t0\t\n')
            audit = {}
            self.assertEqual(list(read_trace(path, selector_confirmation, audit)),
                             [(63, {65}), *[(64 * i - 1, set()) for i in range(2, 10)]])
            self.assertEqual(audit['confirmed_candidate_rows'], 1)
            self.assertEqual(audit['quiet_rows'], 7)
            self.assertEqual(audit['quiet_disposition_counts'], [2, 1, 1, 1, 1, 1, 1, 1])
            self.assertEqual(audit['raw_sha256'], hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest())
            with self.assertRaisesRegex(ValueError, 'payload differs'):
                list(read_trace(path, selector_confirmation, {}, '0' * 64))
            with gzip.open(path, 'wt') as stream:
                stream.write('# m3_candidate_outcome_v2\nsample\ttick\tquiet\tcandidates\n63\t1\t8\t\n')
            with self.assertRaisesRegex(ValueError, 'coordinates'):
                list(read_trace(path, selector_confirmation, {}))

    def test_union_preserves_current_but_false_addition_still_rejects(self):
        clock = dict(sample_count=2000, sample_rate=96000)
        labels = [label(0, 200, 1500, note=60), label(1, 200, 1500, note=64)]
        current_spans = [(200, 1500, 60)]
        current = score(current_spans, labels, **clock)
        hybrid = union_spans([*current_spans, (512, 1024, 64), (1024, 1536, 65)],
                             sample_count=2000)
        comparison = compare(current, score(hybrid, labels, **clock))
        self.assertGreater(comparison['sample_deltas']['present_pitch_samples'], 0)
        self.assertTrue(all(row['present_samples_delta'] >= 0 and row['longest_present_samples_delta'] >= 0
                            for row in comparison['label_deltas']))
        self.assertFalse(comparison['no_pitch_safety_regression'])


if __name__ == '__main__':
    unittest.main()
