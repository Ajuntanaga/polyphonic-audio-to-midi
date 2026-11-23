"""Toy arrays and callback contracts only; no local audio or native execution."""
import unittest
import hashlib
from pathlib import Path
import tempfile
import zipfile

from tools.controlled_repluck import compose, response, compare_attack, prefix
from tools.portable_vst3_controlled_repluck import extract_binary


def event(sample, kind='on', note=60, channel=0):
    return dict(sample=sample, kind=kind, note=note, channel=channel,
                note_id=-1000-channel*128-note, velocity=.7 if kind == 'on' else 0.)


class ControlledRepluckTests(unittest.TestCase):
    def test_saved_binary_extraction_checks_archive_member_and_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'saved.zip'
            payload = b'nonexecutable toy payload'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('build/m3_vst3_corpus_replay', payload)
                zipped.writestr('elsewhere/ignored', 'unused evidence')
            expected = dict(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                            sha256=hashlib.sha256(payload).hexdigest())
            target = root / 'binary'
            self.assertEqual(extract_binary(archive, expected, target), 'build/m3_vst3_corpus_replay')
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse((root / 'elsewhere').exists())
            with self.assertRaisesRegex(ValueError, 'archive hash'):
                extract_binary(archive, dict(expected, archive_sha256='0'*64), root / 'bad-archive')
            with self.assertRaisesRegex(ValueError, 'binary hash'):
                extract_binary(archive, dict(expected, sha256='0'*64), root / 'bad-payload')

    def test_layout_preserves_common_prefix_and_adds_only_scheduled_copy(self):
        args = dict(clip=[0., .125, .25, .125, 0.], marker_in_clip=2,
                    frames=20, gain=.5, fade_frames=1)
        one = compose(markers=[4], **args)
        two = compose(markers=[4, 10], **args)
        self.assertEqual(one[:8], two[:8])
        self.assertEqual(two[8:13], one[2:7])
        self.assertEqual(two[4], .125)

    def test_invalid_or_clipped_fixtures_fail_instead_of_adaptive_gain(self):
        args = dict(clip=[0., 1., 1., 1., 0.], marker_in_clip=2,
                    frames=20, gain=1., fade_frames=1, markers=[4, 5])
        with self.assertRaisesRegex(ValueError, 'clips'):
            compose(**args)
        for change in ({'markers': [1]}, {'markers': [4, 4]},
                       {'gain': 0}, {'clip': [0., float('nan'), 0.]},
                       {'markers': [19]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                compose(**dict(args, **change))

    def test_control_flicker_is_not_credited_as_a_second_attack(self):
        control = [event(10), event(60, 'off'), event(60)]
        r = response(control, control, note=60, marker=50, insertion=40,
                     end=90, sample_rate=1000)
        self.assertEqual(r['note_ons'], 1)
        self.assertEqual(r['added_note_ons'], 0)
        self.assertTrue(r['pitch_active_before_insertion'])
        self.assertEqual(compare_attack(r, r)['verdict'], 'neither_mode_has_a_new_attack_response')

    def test_retained_and_removed_responses_are_distinguished(self):
        control = [event(10)]
        trial = control + [event(55, 'off'), event(55, channel=1)]
        kwargs = dict(note=60, marker=50, insertion=40, end=90, sample_rate=1000)
        original = response(trial, control, **kwargs)
        kept = response(control + [event(55, 'off'), event(55)], control, **kwargs)
        lost = response(control, control, **kwargs)
        self.assertEqual(original['first_added_delay_ms'], 5.)
        self.assertTrue(compare_attack(original, kept)['baseline_first_response_retained'])
        self.assertEqual(compare_attack(original, lost)['verdict'], 'baseline_response_removed_or_retimed')
        self.assertEqual(prefix(trial, 40), prefix(control, 40))

    def test_note_ownership_and_window_edges_are_not_discarded(self):
        events = [event(10), event(20, 'off'), event(40, note=61), event(90)]
        r = response(events, [], note=60, marker=50, insertion=40, end=90, sample_rate=1000)
        self.assertFalse(r['pitch_active_before_insertion'])
        self.assertEqual(r['added_note_ons'], 0)


if __name__ == '__main__':
    unittest.main()
