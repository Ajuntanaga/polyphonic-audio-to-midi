#!/usr/bin/env python3
"""Index real note performances and plan bounded M3 combinations."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import itertools
import json
import math
import pathlib
import wave
from collections.abc import Mapping, Sequence

import numpy
from scipy.io import wavfile


OPEN_NOTES = {8: 32, 7: 36, 6: 40, 5: 44, 4: 48, 3: 52, 2: 56, 1: 60}
FRET_COUNT = 25
MAX_OFFSET_SAMPLES = 256
DEFAULT_HOLD_SECONDS = 2.30
DEFAULT_GAP_SECONDS = 0.10


@dataclasses.dataclass(frozen=True)
class NoteExample:
    physical_string: int
    fret: int
    midi_note: int
    string_mask: int
    calibration_pass: int
    start_sample: int
    end_sample: int
    expected_cents: float | None


@dataclasses.dataclass(frozen=True)
class NoteClass:
    physical_string: int
    fret: int
    midi_note: int


@dataclasses.dataclass(frozen=True)
class MaterializedNote:
    physical_string: int
    fret: int
    midi_note: int
    string_mask: int
    calibration_pass: int
    start_sample: int
    end_sample: int
    expected_cents: float | None
    offset_samples: int


NoteCatalog = dict[tuple[int, int], tuple[NoteExample, ...]]


def read_note_catalog(label_directory: pathlib.Path) -> NoteCatalog:
    pending: dict[tuple[int, int], list[NoteExample]] = {}
    for physical_string in range(1, 9):
        path = label_directory / f"string-{physical_string:02d}.tsv"
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                midi_note = int(row["midi_note"])
                fret = midi_note - OPEN_NOTES[physical_string]
                start = int(row["start_sample"])
                end = int(row["end_sample"])
                mask = int(row["string_mask"])
                cents_text = row.get("expected_cents", "")
                if not 0 <= fret < FRET_COUNT:
                    raise ValueError(f"note outside string range: {path}:{midi_note}")
                if mask != 1 << (8 - physical_string):
                    raise ValueError(f"wrong string mask: {path}:{mask}")
                if start < 0 or end <= start:
                    raise ValueError(f"invalid sample interval: {path}:{start}:{end}")
                item = NoteExample(
                    physical_string=physical_string,
                    fret=fret,
                    midi_note=midi_note,
                    string_mask=mask,
                    calibration_pass=int(row["calibration_pass"]),
                    start_sample=start,
                    end_sample=end,
                    expected_cents=float(cents_text) if cents_text else None,
                )
                pending.setdefault((physical_string, fret), []).append(item)
    return {
        key: tuple(sorted(items, key=lambda item: (item.calibration_pass, item.start_sample)))
        for key, items in pending.items()
    }


def build_pairwise_fret_plan() -> tuple[tuple[int, ...], ...]:
    """Return a deterministic pairwise covering array over off plus 25 frets."""
    states = tuple(range(-1, FRET_COUNT))
    rows = [list(pair) for pair in itertools.product(states, repeat=2)]
    for new_column in range(2, 8):
        uncovered = {
            (old_column, old_value, new_value)
            for old_column in range(new_column)
            for old_value in states
            for new_value in states
        }
        # Horizontal growth: choose the new value that covers the most still
        # missing pairs for each existing row.
        for row in rows:
            new_value = max(
                states,
                key=lambda value: (
                    sum(
                        (column, row[column], value) in uncovered
                        for column in range(new_column)
                    ),
                    -value,
                ),
            )
            row.append(new_value)
            for column in range(new_column):
                uncovered.discard((column, row[column], new_value))
        # Vertical growth: add the minimum extra rows needed by the remaining
        # pairs. Earlier-column pairs stay covered by the rows already built.
        while uncovered:
            seed_column, seed_value, new_value = min(uncovered)
            row: list[int | None] = [None] * (new_column + 1)
            row[seed_column] = seed_value
            row[new_column] = new_value
            for column in range(new_column):
                if row[column] is None:
                    row[column] = max(
                        states,
                        key=lambda value: (
                            (column, value, new_value) in uncovered,
                            -value,
                        ),
                    )
            completed = [int(value) for value in row]
            for column in range(new_column):
                uncovered.discard((column, completed[column], new_value))
            rows.append(completed)
    return tuple(tuple(row) for row in rows)


def build_unison_plan(
    catalog: Mapping[tuple[int, int], Sequence[NoteExample]],
) -> tuple[tuple[NoteClass, ...], ...]:
    rows: list[tuple[NoteClass, ...]] = []
    for midi_note in range(min(OPEN_NOTES.values()), max(OPEN_NOTES.values()) + 25):
        playable = [
            NoteClass(string, midi_note - open_note, midi_note)
            for string, open_note in sorted(OPEN_NOTES.items(), reverse=True)
            if (string, midi_note - open_note) in catalog
        ]
        for size in range(2, min(4, len(playable)) + 1):
            rows.extend(itertools.combinations(playable, size))
    return tuple(rows)


def select_balanced_unison_plan(
    rows: Sequence[tuple[NoteClass, ...]], maximum_cases: int
) -> tuple[tuple[NoteClass, ...], ...]:
    """Greedily retain broad string/fret, pitch, size, and string-pair coverage."""
    if maximum_cases <= 0 or maximum_cases >= len(rows):
        return tuple(rows)

    def features(row: tuple[NoteClass, ...]) -> frozenset[tuple[object, ...]]:
        strings = tuple(item.physical_string for item in row)
        found: set[tuple[object, ...]] = {
            ("size", len(row)),
            ("midi", row[0].midi_note),
        }
        found.update(("class", item.physical_string, item.fret) for item in row)
        found.update(("pair", *pair) for pair in itertools.combinations(strings, 2))
        return frozenset(found)

    row_features = tuple(features(row) for row in rows)
    uncovered = set().union(*row_features)
    remaining = set(range(len(rows)))
    chosen: list[int] = []
    while remaining and len(chosen) < maximum_cases:
        best = max(
            remaining,
            key=lambda index: (
                len(row_features[index] & uncovered),
                len(rows[index]),
                -index,
            ),
        )
        chosen.append(best)
        uncovered.difference_update(row_features[best])
        remaining.remove(best)
    return tuple(rows[index] for index in sorted(chosen))


def filter_unison_plan(
    rows: Sequence[tuple[NoteClass, ...]], sizes: Sequence[int]
) -> tuple[tuple[NoteClass, ...], ...]:
    requested = frozenset(int(size) for size in sizes)
    if not requested:
        return tuple(rows)
    if not requested <= {2, 3, 4}:
        raise ValueError("unison sizes must be two, three, or four")
    return tuple(row for row in rows if len(row) in requested)


def filter_consecutive_unison_plan(
    rows: Sequence[tuple[NoteClass, ...]],
) -> tuple[tuple[NoteClass, ...], ...]:
    """Keep only physical-string groups with no gap between their members."""
    selected: list[tuple[NoteClass, ...]] = []
    for row in rows:
        strings = sorted(item.physical_string for item in row)
        if len(strings) >= 2 and strings == list(
            range(strings[0], strings[0] + len(strings))
        ):
            selected.append(row)
    return tuple(selected)


def build_contextual_unison_plan(
    catalog: Mapping[tuple[int, int], Sequence[NoteExample]],
    unison_size: int = 3,
    context_voice_count: int = 3,
) -> tuple[tuple[NoteClass, ...], ...]:
    """Place a consecutive unison inside distinct simultaneous pitch context.

    Context voices use other physical strings and three different interval
    targets above the unison where the string range permits. The nearest real
    labeled note class is used; no audio is synthesized or pitch shifted.
    """
    if unison_size not in (2, 3, 4):
        raise ValueError("unison size must be two, three, or four")
    if context_voice_count <= 0 or unison_size + context_voice_count > 8:
        raise ValueError("context voices must fit the eight-string bank")
    interval_targets = (3, 7, 10, 14, 17, 21)
    base_rows = filter_consecutive_unison_plan(
        filter_unison_plan(build_unison_plan(catalog), (unison_size,))
    )
    rows: list[tuple[NoteClass, ...]] = []
    for base in base_rows:
        occupied = {item.physical_string for item in base}
        remaining = [
            string for string in range(8, 0, -1) if string not in occupied
        ]
        for context_strings in itertools.combinations(
            remaining, context_voice_count
        ):
            used_notes = {base[0].midi_note}
            context: list[NoteClass] = []
            for position, physical_string in enumerate(context_strings):
                target = base[0].midi_note + interval_targets[position]
                candidates = [
                    NoteClass(
                        physical_string,
                        fret,
                        OPEN_NOTES[physical_string] + fret,
                    )
                    for fret in range(FRET_COUNT)
                    if (physical_string, fret) in catalog
                    and OPEN_NOTES[physical_string] + fret not in used_notes
                ]
                if not candidates:
                    context = []
                    break
                chosen = min(
                    candidates,
                    key=lambda item: (
                        abs(item.midi_note - target),
                        item.fret,
                        item.midi_note,
                    ),
                )
                context.append(chosen)
                used_notes.add(chosen.midi_note)
            if len(context) == context_voice_count:
                rows.append(base + tuple(context))
    return tuple(rows)


def materialize_assignment(
    catalog: Mapping[tuple[int, int], Sequence[NoteExample]],
    frets: Sequence[int],
    variation: int = 0,
) -> tuple[MaterializedNote, ...]:
    if len(frets) != 8:
        raise ValueError("an M3 assignment must contain exactly eight fret values")
    output: list[MaterializedNote] = []
    for index, fret_value in enumerate(frets):
        physical_string = index + 1
        fret = int(fret_value)
        if fret == -1:
            continue
        examples = catalog.get((physical_string, fret))
        if not examples:
            raise ValueError(f"missing string/fret class: {physical_string}/{fret}")
        example = examples[(variation + index) % len(examples)]
        output.append(
            MaterializedNote(
                **dataclasses.asdict(example),
                offset_samples=(variation * 53 + index * 31)
                % (MAX_OFFSET_SAMPLES + 1),
            )
        )
    return tuple(output)


def materialize_note_classes(
    catalog: Mapping[tuple[int, int], Sequence[NoteExample]],
    classes: Sequence[NoteClass],
    variation: int = 0,
) -> tuple[MaterializedNote, ...]:
    output: list[MaterializedNote] = []
    for index, note_class in enumerate(classes):
        examples = catalog[(note_class.physical_string, note_class.fret)]
        example = examples[(variation + index) % len(examples)]
        output.append(
            MaterializedNote(
                **dataclasses.asdict(example),
                offset_samples=(variation * 53 + index * 31)
                % (MAX_OFFSET_SAMPLES + 1),
            )
        )
    return tuple(output)


def mix_real_excerpts(
    sources: Mapping[int, numpy.ndarray],
    assignments: Sequence[MaterializedNote],
    sample_count: int,
) -> numpy.ndarray:
    """Mix real labeled excerpts without altering pitch or spectral shape."""
    if sample_count <= 0 or not assignments:
        raise ValueError("a mixture needs assignments and a positive sample count")
    mixed = numpy.zeros(sample_count, dtype=numpy.float64)
    for item in assignments:
        source = numpy.asarray(sources[item.physical_string])
        available = available_sample_count(source, item, sample_count)
        if available <= 0:
            raise ValueError("labeled excerpt is outside its source audio")
        mixed[item.offset_samples : item.offset_samples + available] += source[
            item.start_sample : item.start_sample + available
        ]
    mixed *= 1.0 / math.sqrt(len(assignments))
    peak = float(numpy.max(numpy.abs(mixed), initial=0.0))
    if peak > 1.0:
        mixed *= 0.999 / peak
    return mixed.astype(numpy.float32)


def available_sample_count(
    source: numpy.ndarray,
    item: MaterializedNote,
    sample_count: int,
) -> int:
    return min(
        sample_count - item.offset_samples,
        item.end_sample - item.start_sample,
        len(source) - item.start_sample,
    )


def synchronized_label_rows(
    sources: Mapping[int, numpy.ndarray],
    assignments: Sequence[MaterializedNote],
    sample_count: int,
    cursor: int,
) -> list[tuple[int, int, MaterializedNote]]:
    """Label only the interval where every intended note has real audio."""
    if not assignments:
        return []
    common_start = max(item.offset_samples for item in assignments)
    common_end = min(
        item.offset_samples
        + available_sample_count(sources[item.physical_string], item, sample_count)
        for item in assignments
    )
    if common_end <= common_start:
        raise ValueError("mixture has no common simultaneous audio interval")
    return [
        (cursor + common_start, cursor + common_end, item)
        for item in assignments
    ]


def order_label_rows(rows):
    return sorted(
        rows,
        key=lambda row: (row[0], row[1], row[2].physical_string),
    )


def build_manifest(label_directory: pathlib.Path) -> dict[str, object]:
    catalog = read_note_catalog(label_directory)
    pairwise = build_pairwise_fret_plan()
    unisons = build_unison_plan(catalog)
    return {
        "schema": 1,
        "source_kind": "real_labeled_note_excerpts",
        "note_class_count": len(catalog),
        "performance_count": sum(len(items) for items in catalog.values()),
        "pairwise_assignment_count": len(pairwise),
        "unison_assignment_count": len(unisons),
        "pairwise_frets": pairwise,
        "unisons": [[dataclasses.asdict(item) for item in row] for row in unisons],
    }


def render_replay_corpus(
    label_directory: pathlib.Path,
    audio_directory: pathlib.Path,
    wave_output: pathlib.Path,
    label_output: pathlib.Path,
    hold_seconds: float = DEFAULT_HOLD_SECONDS,
    gap_seconds: float = DEFAULT_GAP_SECONDS,
    plan: str = "all",
    maximum_cases: int = 0,
    unison_sizes: Sequence[int] = (),
    context_voice_count: int = 3,
    consecutive_unisons_only: bool = False,
) -> dict[str, int]:
    """Stream the bounded pairwise and unison plans into one replay corpus."""
    if hold_seconds <= 0.0 or gap_seconds < 0.0:
        raise ValueError("invalid render duration")
    catalog = read_note_catalog(label_directory)
    sources: dict[int, numpy.ndarray] = {}
    sample_rate = 0
    for physical_string in range(1, 9):
        rate, samples = wavfile.read(
            audio_directory / f"string-{physical_string:02d}-raw.wav", mmap=True
        )
        if sample_rate not in (0, rate):
            raise ValueError("source sample rates differ")
        if samples.ndim != 1:
            raise ValueError("source audio must be mono")
        sample_rate = int(rate)
        if numpy.issubdtype(samples.dtype, numpy.integer):
            scale = float(max(abs(numpy.iinfo(samples.dtype).min), numpy.iinfo(samples.dtype).max))
            sources[physical_string] = samples.astype(numpy.float32) / scale
        else:
            sources[physical_string] = samples
    hold = int(round(hold_seconds * sample_rate))
    gap = int(round(gap_seconds * sample_rate))
    if plan not in {"all", "pairwise", "unison", "contextual-unison"}:
        raise ValueError("unknown replay plan")
    pairwise = build_pairwise_fret_plan() if plan in {"all", "pairwise"} else ()
    unisons = build_unison_plan(catalog) if plan in {"all", "unison"} else ()
    if plan == "contextual-unison":
        requested_sizes = tuple(unison_sizes) or (3,)
        if len(requested_sizes) != 1:
            raise ValueError("contextual unison rendering requires one unison size")
        unisons = build_contextual_unison_plan(
            catalog,
            unison_size=requested_sizes[0],
            context_voice_count=context_voice_count,
        )
    else:
        unisons = filter_unison_plan(unisons, unison_sizes)
        if consecutive_unisons_only:
            unisons = filter_consecutive_unison_plan(unisons)
    if maximum_cases:
        if pairwise:
            raise ValueError("maximum_cases is supported only for the unison plan")
        unisons = select_balanced_unison_plan(unisons, maximum_cases)
    wave_output.parent.mkdir(parents=True, exist_ok=True)
    label_output.parent.mkdir(parents=True, exist_ok=True)
    cursor = 0
    label_rows: list[tuple[int, int, MaterializedNote]] = []
    with wave.open(str(wave_output), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        silence = numpy.zeros(gap, dtype="<i2").tobytes()
        case_index = 0
        for frets in pairwise:
            notes = materialize_assignment(catalog, frets, case_index % 3)
            mixed = (
                mix_real_excerpts(sources, notes, hold)
                if notes
                else numpy.zeros(hold, dtype=numpy.float32)
            )
            stream.writeframesraw(numpy.rint(mixed * 32767.0).astype("<i2").tobytes())
            label_rows.extend(synchronized_label_rows(sources, notes, hold, cursor))
            stream.writeframesraw(silence)
            cursor += hold + gap
            case_index += 1
        for classes in unisons:
            notes = materialize_note_classes(catalog, classes, case_index % 3)
            mixed = mix_real_excerpts(sources, notes, hold)
            stream.writeframesraw(numpy.rint(mixed * 32767.0).astype("<i2").tobytes())
            label_rows.extend(synchronized_label_rows(sources, notes, hold, cursor))
            stream.writeframesraw(silence)
            cursor += hold + gap
            case_index += 1
    with label_output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(("start_sample", "end_sample", "midi_note", "string_mask", "calibration_pass", "expected_cents"))
        # The replay parser requires monotonically ordered start samples.  Phase
        # offsets can make a later string in one case start before an earlier
        # string, so order the completed projection rather than changing the
        # intended offsets in the audio.
        for start, end, note in order_label_rows(label_rows):
            writer.writerow((start, end, note.midi_note, note.string_mask, note.calibration_pass, f"{note.expected_cents or 0.0:.6f}"))
    return {
        "sample_rate": sample_rate,
        "samples": cursor,
        "cases": len(pairwise) + len(unisons),
        "labels": len(label_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True, type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--audio", type=pathlib.Path)
    parser.add_argument("--render-wave", type=pathlib.Path)
    parser.add_argument("--render-labels", type=pathlib.Path)
    parser.add_argument(
        "--plan",
        choices=("all", "pairwise", "unison", "contextual-unison"),
        default="all",
    )
    parser.add_argument("--hold-seconds", type=float, default=DEFAULT_HOLD_SECONDS)
    parser.add_argument("--gap-seconds", type=float, default=DEFAULT_GAP_SECONDS)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument(
        "--unison-size", type=int, choices=(2, 3, 4), action="append", default=[]
    )
    parser.add_argument("--context-voices", type=int, default=3)
    parser.add_argument("--consecutive-unisons-only", action="store_true")
    args = parser.parse_args()
    manifest = build_manifest(args.labels)
    if args.render_wave is not None or args.render_labels is not None:
        if args.audio is None or args.render_wave is None or args.render_labels is None:
            parser.error("rendering requires --audio, --render-wave, and --render-labels")
        manifest["render"] = render_replay_corpus(
            args.labels,
            args.audio,
            args.render_wave,
            args.render_labels,
            hold_seconds=args.hold_seconds,
            gap_seconds=args.gap_seconds,
            plan=args.plan,
            maximum_cases=args.max_cases,
            unison_sizes=args.unison_size,
            context_voice_count=args.context_voices,
            consecutive_unisons_only=args.consecutive_unisons_only,
        )
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if args.output is None:
        print(encoded)
    else:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
