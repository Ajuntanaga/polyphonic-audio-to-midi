import tempfile
from pathlib import Path
import unittest

from tools.portable_octave_phase_trace import phase_rows, paired_summary, check_identity
from tools.portable_assignment_trace import digest


class OctavePhaseTests(unittest.TestCase):
    def rows(self):
        return [dict(sample=str(s), note='74', independent_phase_valid=str(v),
                     independent_phase_cents=str(c), independent_phase_updates='8')
                for s, v, c in ((63, 1, 3), (127, 0, 0), (191, 1, -2))]

    def test_invalid_is_unavailable_and_cents_remove_octave(self):
        target = phase_rows(self.rows(), 74, 63, 192)
        result = paired_summary(target, {63: 1, 127: 9, 191: -3}, 63, 192)
        self.assertEqual(result['jointly_valid'], 2)
        self.assertEqual(result['upper_minus_parent_octave_cents'],
                         dict(min=1, median=1.5, max=2))
        self.assertIsNone(paired_summary(target, {}, 63, 192)['upper_minus_parent_octave_cents'])

    def test_missing_duplicate_wrong_note_and_nonfinite_rejected(self):
        for rows in (self.rows()[:-1], self.rows() + self.rows()[:1],
                     [dict(r, note='62') for r in self.rows()],
                     [dict(r, independent_phase_cents='nan') for r in self.rows()]):
            with self.assertRaises(ValueError):
                phase_rows(rows, 74, 63, 192)

    def test_snapshot_and_midi_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / 'a', Path(directory) / 'b'
            a.write_text('snapshot'); b.write_text('midi')
            saved = dict(tsv_sha256=digest(a), midi_trace_sha256=digest(b))
            check_identity(a, b, saved)
            b.write_text('changed')
            with self.assertRaises(ValueError):
                check_identity(a, b, saved)
            b.write_text('midi'); a.write_text('changed')
            with self.assertRaises(ValueError):
                check_identity(a, b, saved)
