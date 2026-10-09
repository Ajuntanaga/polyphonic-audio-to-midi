import importlib.util
import itertools
import pathlib
import sys
import unittest

import numpy


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "generate_note_combination_corpus.py"


def load_module():
    spec = importlib.util.spec_from_file_location("note_combination_corpus", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class NoteCombinationCorpusTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.labels = (
            ROOT
            / "build"
            / "physical-capture"
            / "calibration-bank-experiment-cents16-final"
            / "labels"
            / "raw"
        )

    def test_real_catalog_retains_every_string_fret_and_performance(self):
        catalog = self.module.read_note_catalog(self.labels)
        self.assertEqual(len(catalog), 200)
        self.assertEqual(sum(len(value) for value in catalog.values()), 555)
        for physical_string in range(1, 9):
            self.assertEqual(
                {fret for string, fret in catalog if string == physical_string},
                set(range(25)),
            )
            for fret in range(25):
                examples = catalog[(physical_string, fret)]
                self.assertGreaterEqual(len(examples), 2)
                self.assertTrue(all(item.string_mask == 1 << (8 - physical_string) for item in examples))

    def test_pairwise_plan_covers_every_silent_or_fretted_pair(self):
        plan = self.module.build_pairwise_fret_plan()
        self.assertGreaterEqual(len(plan), 26 * 26)
        self.assertLessEqual(len(plan), 1200)
        self.assertTrue(all(len(row) == 8 for row in plan))
        states = set(range(-1, 25))
        for left, right in itertools.combinations(range(8), 2):
            observed = {(row[left], row[right]) for row in plan}
            self.assertEqual(observed, set(itertools.product(states, repeat=2)))

    def test_unison_plan_contains_every_playable_two_to_four_string_subset(self):
        catalog = self.module.read_note_catalog(self.labels)
        plan = self.module.build_unison_plan(catalog)
        expected = set()
        for midi_note in range(32, 85):
            strings = [
                physical_string
                for physical_string, open_note in self.module.OPEN_NOTES.items()
                if 0 <= midi_note - open_note <= 24
            ]
            for size in range(2, min(4, len(strings)) + 1):
                expected.update((midi_note, subset) for subset in itertools.combinations(strings, size))
        actual = {(row[0].midi_note, tuple(item.physical_string for item in row)) for row in plan}
        self.assertEqual(actual, expected)

    def test_balanced_unison_subset_is_bounded_and_covers_each_size(self):
        catalog = self.module.read_note_catalog(self.labels)
        plan = self.module.build_unison_plan(catalog)
        selected = self.module.select_balanced_unison_plan(plan, 128)
        self.assertEqual(len(selected), 128)
        self.assertEqual({len(row) for row in selected}, {2, 3, 4})
        self.assertEqual(
            {item.physical_string for row in selected for item in row},
            set(range(1, 9)),
        )
        self.assertEqual(selected, self.module.select_balanced_unison_plan(plan, 128))

    def test_unison_size_filter_selects_exact_requested_group_sizes(self):
        catalog = self.module.read_note_catalog(self.labels)
        plan = self.module.build_unison_plan(catalog)
        selected = self.module.filter_unison_plan(plan, (3,))
        self.assertEqual(len(selected), 410)
        self.assertTrue(all(len(row) == 3 for row in selected))
        with self.assertRaises(ValueError):
            self.module.filter_unison_plan(plan, (1, 3))

    def test_consecutive_unison_filter_keeps_only_adjacent_physical_strings(self):
        catalog = self.module.read_note_catalog(self.labels)
        triples = self.module.filter_unison_plan(
            self.module.build_unison_plan(catalog), (3,)
        )
        selected = self.module.filter_consecutive_unison_plan(triples)
        self.assertGreaterEqual(len(selected), 3)
        self.assertTrue(
            all(
                max(item.physical_string for item in row)
                - min(item.physical_string for item in row)
                + 1
                == len(row)
                for row in selected
            )
        )

    def test_contextual_triple_plan_adds_three_distinct_interval_voices(self):
        catalog = self.module.read_note_catalog(self.labels)
        plan = self.module.build_contextual_unison_plan(
            catalog, unison_size=3, context_voice_count=3
        )
        self.assertGreaterEqual(len(plan), 3)
        for row in plan:
            self.assertEqual(len(row), 6)
            unison = row[:3]
            context = row[3:]
            self.assertEqual(len({item.midi_note for item in unison}), 1)
            self.assertEqual(
                max(item.physical_string for item in unison)
                - min(item.physical_string for item in unison)
                + 1,
                3,
            )
            self.assertEqual(len({item.physical_string for item in row}), 6)
            self.assertEqual(len({item.midi_note for item in context}), 3)
            self.assertNotIn(unison[0].midi_note, {item.midi_note for item in context})
            self.assertTrue(
                all((item.physical_string, item.fret) in catalog for item in row)
            )
        self.assertEqual(
            plan,
            self.module.build_contextual_unison_plan(
                catalog, unison_size=3, context_voice_count=3
            ),
        )

    def test_materialization_rotates_real_passes_and_uses_bounded_offsets(self):
        catalog = self.module.read_note_catalog(self.labels)
        assignments = self.module.materialize_assignment(
            catalog, (0, 4, 8, 12, 16, 20, 24, 0), variation=2
        )
        self.assertEqual([item.physical_string for item in assignments], list(range(1, 9)))
        self.assertEqual([item.fret for item in assignments], [0, 4, 8, 12, 16, 20, 24, 0])
        self.assertTrue(all(item.offset_samples <= 256 for item in assignments))
        self.assertTrue(all(item.end_sample > item.start_sample for item in assignments))

    def test_materialization_omits_silent_string_states(self):
        catalog = self.module.read_note_catalog(self.labels)
        assignments = self.module.materialize_assignment(
            catalog, (-1, 0, -1, 4, -1, 8, -1, 12), variation=0
        )
        self.assertEqual(
            [item.physical_string for item in assignments], [2, 4, 6, 8]
        )

    def test_real_excerpt_mixer_preserves_offsets_and_normalizes_voice_energy(self):
        note = self.module.MaterializedNote
        assignments = (
            note(1, 0, 60, 128, 1, 2, 10, 0.0, 0),
            note(2, 0, 56, 64, 1, 1, 10, 0.0, 2),
        )
        sources = {
            1: numpy.full(16, 0.25, dtype=numpy.float32),
            2: numpy.full(16, 0.50, dtype=numpy.float32),
        }
        mixed = self.module.mix_real_excerpts(sources, assignments, 6)
        scale = 2.0 ** -0.5
        numpy.testing.assert_allclose(
            mixed,
            numpy.array([0.25, 0.25, 0.75, 0.75, 0.75, 0.75]) * scale,
            atol=1e-7,
        )
        self.assertLessEqual(float(numpy.max(numpy.abs(mixed))), 1.0)

    def test_rendered_labels_are_ordered_for_the_replay_parser(self):
        note = self.module.MaterializedNote
        rows = [
            (31, 100, note(1, 0, 60, 128, 1, 0, 100, 0.0, 31)),
            (0, 100, note(2, 0, 56, 64, 1, 0, 100, 0.0, 0)),
        ]
        ordered = self.module.order_label_rows(rows)
        self.assertEqual([row[0] for row in ordered], [0, 31])

    def test_available_sample_count_never_labels_zero_padding(self):
        note = self.module.MaterializedNote(1, 0, 60, 128, 1, 2, 7, 0.0, 2)
        source = numpy.zeros(16, dtype=numpy.float32)
        self.assertEqual(self.module.available_sample_count(source, note, 10), 5)
        self.assertEqual(self.module.available_sample_count(source, note, 4), 2)

    def test_synchronized_labels_cover_only_common_simultaneous_audio(self):
        note = self.module.MaterializedNote
        assignments = (
            note(1, 0, 60, 128, 1, 0, 100, 0.0, 0),
            note(2, 4, 60, 64, 1, 0, 49, 0.0, 31),
        )
        sources = {
            1: numpy.zeros(100, dtype=numpy.float32),
            2: numpy.zeros(80, dtype=numpy.float32),
        }
        rows = self.module.synchronized_label_rows(
            sources, assignments, sample_count=100, cursor=1000
        )
        self.assertEqual([(row[0], row[1]) for row in rows], [(1031, 1080)] * 2)


if __name__ == "__main__":
    unittest.main()
