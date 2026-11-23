"""Small synthetic contracts; these tests do not open audio or run native code."""
import copy
import unittest

from tools.stable_onset_freshness import compare_fixture, summarize, snapshot_identity


def event(sample, kind='on', *, ledger=False, channel=0, velocity=100):
    return dict(sample=sample, kind=kind, note=60,
                velocity=velocity if ledger else velocity / 127.0,
                channel=channel + 1 if ledger else channel)


class FreshnessComparisons(unittest.TestCase):
    def test_buffer_metadata_is_only_snapshot_exception(self):
        left = dict(block='512', fingerprint='abc', transitions='8')
        right = dict(block='32', fingerprint='abc', transitions='8')
        self.assertTrue(snapshot_identity(left, right, left_block=512, right_block=32))
        self.assertFalse(snapshot_identity(left, right, left_block=512, right_block=512))
        right['transitions'] = '9'
        self.assertFalse(snapshot_identity(left, right, left_block=512, right_block=32))

    def test_missing_fingerprint_not_identity(self):
        self.assertFalse(snapshot_identity(dict(block='512'), dict(block='32'),
                                           left_block=512, right_block=32))

    def compare(self, callbacks, *, single=False, control=None, voice=None, saved=None):
        return compare_fixture(callbacks, control or [event(10, ledger=True)],
            voice or [event(10), event(50)], [event(10)] if not single else [],
            saved or [event(10)], note=60, marker=40, insertion=30 if not single else 0,
            end=80, rate=1000, single=single)

    def test_unchanged_single(self):
        r = self.compare([event(10, ledger=True)], single=True, voice=[event(10)])
        self.assertTrue(all(r['gates'].values()))

    def test_single_extra_chatter_fails(self):
        r = self.compare([event(10, ledger=True), event(20, ledger=True)], single=True)
        self.assertFalse(r['gates']['single_copy_saved_stable_identity'])

    def test_single_channel_change_fails(self):
        r = self.compare([event(10, ledger=True, channel=1)], single=True)
        self.assertFalse(r['gates']['single_copy_saved_stable_identity'])

    def test_original_repeated_sample_retained(self):
        r = self.compare([event(10, ledger=True), event(50, ledger=True)])
        self.assertTrue(all(r['gates'].values()))

    def test_delayed_response_fails(self):
        r = self.compare([event(10, ledger=True), event(51, ledger=True)])
        self.assertFalse(r['gates']['first_response_retained'])

    def test_removed_response_fails(self):
        r = self.compare([event(10, ledger=True)])
        self.assertFalse(r['gates']['first_response_retained'])

    def test_control_flicker_is_subtracted(self):
        r = self.compare([event(10, ledger=True), event(50, ledger=True)],
                         control=[event(10, ledger=True), event(50, ledger=True)])
        self.assertFalse(r['gates']['first_response_retained'])

    def test_prefix_payload_change_fails(self):
        r = self.compare([event(10, ledger=True, velocity=99), event(50, ledger=True)])
        self.assertFalse(r['gates']['common_prefix_identity'])

    def test_missing_baseline_response_not_success(self):
        r = self.compare([event(10, ledger=True), event(50, ledger=True)], voice=[event(10)])
        self.assertFalse(r['gates']['first_response_retained'])

    def test_insert_boundary_is_not_prefix(self):
        r = self.compare([event(10, ledger=True), event(30, ledger=True), event(50, ledger=True)])
        self.assertTrue(r['gates']['common_prefix_identity'])

    def test_summary_cannot_hide_failed_gate(self):
        rows = {dataset + '/' + layout: dict(gates={'identity': True, 'timing': True},
                suppressed_pairs=1, comparison=dict(gates={'response': True},
                baseline_first_response_retained=True))
                for dataset in ('a', 'b') for layout in ('single', 'overlap', 'separated')}
        self.assertTrue(summarize(rows)['screen_pass'])
        broken = copy.deepcopy(rows)
        broken['a/overlap']['gates']['timing'] = False
        self.assertFalse(summarize(broken)['screen_pass'])
        for row in rows.values():
            row['suppressed_pairs'] = 0
        self.assertFalse(summarize(rows)['screen_pass'])
        del rows['a/single']
        with self.assertRaises(ValueError):
            summarize(rows)


if __name__ == '__main__':
    unittest.main()
