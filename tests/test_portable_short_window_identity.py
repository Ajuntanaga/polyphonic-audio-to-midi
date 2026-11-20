"""Vector-only evaluation contracts; recorded audio runs on GitHub."""
import unittest
from tools.portable_short_window_identity import evaluate


def rows():
    return [dict(clip=f"{p}-{lane}-{take}", string=lane, **{"pass": p},
                 features={"shape": [float(lane), float(lane * 2)]})
            for p in (1, 2, 3) for lane in (0, 1)
            for take in range(2 if p == 3 else 1)]


class EvaluationContracts(unittest.TestCase):
    def test_separation_and_repeated_takes(self):
        result = evaluate(rows(), [0, 1], ["shape"])
        self.assertEqual((result["correct"], result["total"]), (8, 8))
        self.assertEqual([f["total"] for f in result["folds"]], [2, 2, 4])
        self.assertEqual(len({p["clip"] for p in result["predictions"]}), 8)

    def test_ties_abstain_and_remain_in_denominator(self):
        data = rows()
        for row in data:
            row["features"]["shape"] = [0., 0.]
        result = evaluate(data, [0, 1], ["shape"])
        self.assertEqual((result["correct"], result["total"]), (0, 8))
        self.assertTrue(all(p["predicted"] is None for p in result["predictions"]))
        self.assertEqual(sum(f["abstained"] for f in result["folds"]), 8)

    def test_held_out_values_cannot_change_training_scaling(self):
        data = rows()
        before = evaluate(data, [0, 1], ["shape"])["folds"][2]
        for row in data:
            if row["pass"] == 3:
                row["features"]["shape"] = [1000., -1000.]
        after = evaluate(data, [0, 1], ["shape"])["folds"][2]
        for key in ("training_center", "training_scale", "training_clips"):
            self.assertEqual(before[key], after[key])
        self.assertFalse(set(after["training_clips"]) & set(after["test_clips"]))

    def test_missing_class_rejected(self):
        data = [r for r in rows() if not (r["pass"] == 3 and r["string"] == 1)]
        with self.assertRaisesRegex(ValueError, "Missing class"):
            evaluate(data, [0, 1], ["shape"])


if __name__ == "__main__":
    unittest.main()
