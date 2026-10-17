#!/usr/bin/env python3
"""Aggregate offline M3 string-posterior decisions by known physical lane."""

from __future__ import annotations

import argparse
import csv
import pathlib
from collections.abc import Iterable


LANE_COUNT = 8
UNRESOLVED = LANE_COUNT
SPECTRAL_HEAD_FIELDS = (
    "spectral_low_best",
    "spectral_low_mid_best",
    "spectral_high_mid_best",
    "spectral_high_best",
    "spectral_overtone_separation_best",
)
M3_OPEN_NOTES = (32, 36, 40, 44, 48, 52, 56, 60)
FRET_BINS = ((0, 5), (6, 11), (12, 17), (18, 24))
LANE_OUTCOMES = (
    "absent",
    "exact",
    "subset_missing",
    "superset_extra",
    "overlap_mixed",
    "disjoint_wrong",
)
SELECTION_OUTCOME_FIELDS = {
    name: f"selection_{name}_lane_outcomes"
    for name in (
        "quiet",
        "below_threshold",
        "spectral_rejected",
        "dp_evicted",
        "selected",
        "coasting",
    )
}
POSTERIOR_OUTCOME_FIELDS = {
    name: f"posterior_{name}_lane_outcomes"
    for name in ("expected", "other", "unresolved")
}


def _indexed_histogram(text: str, size: int) -> list[int]:
    result = [0] * size
    if not text:
        return result
    for item in text.split(","):
        key_text, separator, value_text = item.partition(":")
        if not separator:
            raise ValueError("invalid indexed histogram")
        key = int(key_text)
        value = int(value_text)
        if not 0 <= key < size or value < 0:
            raise ValueError("indexed histogram value is out of range")
        result[key] += value
    return result


def _histogram(text: str) -> list[int]:
    return _indexed_histogram(text, LANE_COUNT + 1)


def audit_failure_attribution(
    paths: Iterable[pathlib.Path],
) -> dict[str, dict[str, list[int]]]:
    groups = {
        "selector": {
            name: [0] * len(LANE_OUTCOMES)
            for name in SELECTION_OUTCOME_FIELDS
        },
        "posterior": {
            name: [0] * len(LANE_OUTCOMES)
            for name in POSTERIOR_OUTCOME_FIELDS
        },
    }
    for path in paths:
        with pathlib.Path(path).open(newline="", encoding="utf-8") as stream:
            if not stream.readline() or not stream.readline():
                raise ValueError("replay detail file has no aggregate rows")
            for row in csv.DictReader(stream, delimiter="\t"):
                for name, field in SELECTION_OUTCOME_FIELDS.items():
                    observed = _indexed_histogram(
                        row.get(field, ""), len(LANE_OUTCOMES)
                    )
                    groups["selector"][name] = [
                        current + value
                        for current, value in zip(
                            groups["selector"][name], observed
                        )
                    ]
                for name, field in POSTERIOR_OUTCOME_FIELDS.items():
                    observed = _indexed_histogram(
                        row.get(field, ""), len(LANE_OUTCOMES)
                    )
                    groups["posterior"][name] = [
                        current + value
                        for current, value in zip(
                            groups["posterior"][name], observed
                        )
                    ]
    return groups


def _audit_fields(
    paths: Iterable[pathlib.Path], fields: tuple[str, ...], *, infer_unresolved: bool
) -> dict[str, list[list[int]]]:
    matrices = {
        field: [[0] * (LANE_COUNT + 1) for _ in range(LANE_COUNT)]
        for field in fields
    }
    for path in paths:
        with pathlib.Path(path).open(newline="", encoding="utf-8") as stream:
            # m3_replay writes one aggregate header/value pair before details.
            if not stream.readline() or not stream.readline():
                raise ValueError("replay detail file has no aggregate rows")
            for row in csv.DictReader(stream, delimiter="\t"):
                mask = int(row["string_mask"])
                if mask <= 0 or mask >= 1 << LANE_COUNT or mask & (mask - 1):
                    raise ValueError("posterior audit requires one physical lane")
                expected = mask.bit_length() - 1
                labeled = int(row["labeled"])
                for field in fields:
                    observed = _histogram(row[field])
                    covered = sum(observed)
                    if infer_unresolved and 0 <= covered <= labeled:
                        observed[UNRESOLVED] += labeled - covered
                        covered = labeled
                    if labeled < 0 or covered != labeled:
                        raise ValueError(f"{field} histogram does not cover label")
                    for predicted, frames in enumerate(observed):
                        matrices[field][expected][predicted] += frames
    return matrices


def audit_detail_files(paths: Iterable[pathlib.Path]) -> list[list[int]]:
    return _audit_fields(
        paths, ("string_fret_posterior_best",), infer_unresolved=False
    )[
        "string_fret_posterior_best"
    ]


def audit_spectral_head_files(
    paths: Iterable[pathlib.Path],
) -> dict[str, list[list[int]]]:
    return _audit_fields(paths, SPECTRAL_HEAD_FIELDS, infer_unresolved=True)


def audit_fret_bin_accuracy(
    paths: Iterable[pathlib.Path], fields: tuple[str, ...]
) -> dict[str, list[tuple[int, int]]]:
    result = {field: [[0, 0] for _ in FRET_BINS] for field in fields}
    for path in paths:
        with pathlib.Path(path).open(newline="", encoding="utf-8") as stream:
            if not stream.readline() or not stream.readline():
                raise ValueError("replay detail file has no aggregate rows")
            for row in csv.DictReader(stream, delimiter="\t"):
                mask = int(row["string_mask"])
                if mask <= 0 or mask >= 1 << LANE_COUNT or mask & (mask - 1):
                    raise ValueError("fret audit requires one physical lane")
                expected = mask.bit_length() - 1
                fret = int(row["midi_note"]) - M3_OPEN_NOTES[expected]
                bin_index = next(
                    (
                        index
                        for index, (lower, upper) in enumerate(FRET_BINS)
                        if lower <= fret <= upper
                    ),
                    None,
                )
                if bin_index is None:
                    continue
                labeled = int(row["labeled"])
                for field in fields:
                    observed = _histogram(row[field])
                    result[field][bin_index][0] += observed[expected]
                    result[field][bin_index][1] += labeled
    return {
        field: [(correct, total) for correct, total in bins]
        for field, bins in result.items()
    }


def _print_matrix(name: str, matrix: list[list[int]]) -> None:
    print(f"[{name}]")
    print("expected\tp0\tp1\tp2\tp3\tp4\tp5\tp6\tp7\tunresolved\taccuracy")
    for expected, row in enumerate(matrix):
        total = sum(row)
        accuracy = row[expected] / total if total else 0.0
        print(
            "\t".join(
                [str(expected), *(str(value) for value in row), f"{accuracy:.6f}"]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", nargs="+", type=pathlib.Path)
    args = parser.parse_args()
    _print_matrix("posterior", audit_detail_files(args.details))
    for name, matrix in audit_spectral_head_files(args.details).items():
        _print_matrix(name, matrix)
    print("[fret_bins]")
    for name, bins in audit_fret_bin_accuracy(
        args.details, ("string_fret_posterior_best", *SPECTRAL_HEAD_FIELDS)
    ).items():
        values = []
        for (lower, upper), (correct, total) in zip(FRET_BINS, bins):
            accuracy = correct / total if total else 0.0
            values.append(f"{lower}-{upper}:{accuracy:.6f}")
        print(f"{name}\t" + "\t".join(values))
    print("[failure_attribution]")
    for family, rows in audit_failure_attribution(args.details).items():
        for name, values in rows.items():
            print(
                f"{family}:{name}\t"
                + "\t".join(
                    f"{outcome}:{value}"
                    for outcome, value in zip(LANE_OUTCOMES, values)
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
