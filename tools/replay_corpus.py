"""Portable corpus paths shared by local and cloud runners; no service login."""
from pathlib import Path
import os

REPO_ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_ROOT = Path(
    os.environ.get(
        "M3_PHYSICAL_RECORDINGS",
        str(REPO_ROOT / "build/physical-capture/source-recordings"),
    )
)
REPLAY_BINARY = REPO_ROOT / "build/contributor/m3_replay"

CORPUS_FILES: dict[str, Path] = {
    "calibration.m3cb": REPO_ROOT
    / "build/physical-capture/unison-spectral-shadow/factory-current-20261012/factory-calibration-v2.m3cb",
    "templates.tsv": Path(
        os.environ.get(
            "M3_SPECTRAL_TEMPLATES",
            REPO_ROOT
            / "build/physical-capture/unison-spectral-shadow/final-review-fixes/blended-template-bank.tsv",
        )
    ),
    "ordinary.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.wav",
    "ordinary.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-practical-chords/combinations.tsv",
    "constructed.wav": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.wav",
    "constructed.tsv": REPO_ROOT
    / "build/physical-capture/note-combination-corpus-tuning/combinations.tsv",
    "isolated-08.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.wav",
    "isolated-08.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-08.tsv",
    "isolated-05.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.wav",
    "isolated-05.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-05.tsv",
    "isolated-02.wav": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.wav",
    "isolated-02.tsv": REPO_ROOT
    / "build/physical-capture/control-sweep/representative/string-02.tsv",
    "physical-long.wav": PHYSICAL_ROOT
    / "string8-fret8_string7-fret4_string6-open_unison.wav",
    "physical-long.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06/unison-labels.tsv",
    "physical-middle.wav": PHYSICAL_ROOT
    / "string3-open_string4-fret4_string5-fret8.wav",
    "physical-middle.tsv": REPO_ROOT
    / "build/physical-capture/unison-05-04-03/unison-labels.tsv",
    "physical-highmid.wav": PHYSICAL_ROOT
    / "string2-open_string3-fret4_string4-fret8.wav",
    "physical-highmid.tsv": REPO_ROOT
    / "build/physical-capture/unison-04-03-02/unison-labels.tsv",
    "physical-high.wav": PHYSICAL_ROOT
    / "string1-open_strin2-fret4_string3-fret8.wav",
    "physical-high.tsv": REPO_ROOT
    / "build/physical-capture/unison-03-02-01/unison-labels.tsv",
    "extended-middle.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.wav",
    "extended-middle.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-middle.tsv",
    "extended-highmid.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.wav",
    "extended-highmid.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-highmid.tsv",
    "extended-high.wav": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.wav",
    "extended-high.tsv": REPO_ROOT
    / "build/physical-capture/extended-upper-unison/physical-high.tsv",
    "physical-four.wav": PHYSICAL_ROOT
    / "string4-open_string5-fret4_string6-fret8_string7-fret12_string8-fret16.wav",
    "physical-four.tsv": REPO_ROOT
    / "build/physical-capture/unison-08-07-06-05-04/diagnostic-spans.tsv",
    "synthetic-four.wav": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.wav",
    "synthetic-four.tsv": REPO_ROOT
    / "build/physical-capture/stability-evaluation-3plus3-4unison/four-unison.tsv",
}

DATASETS = {
    name: {"wav": f"corpus/{name}.wav", "labels": f"corpus/{name}.tsv"}
    for name in (
        "ordinary",
        "constructed",
        "isolated-08",
        "isolated-05",
        "isolated-02",
        "physical-long",
        "physical-middle",
        "physical-highmid",
        "physical-high",
        "extended-middle",
        "extended-highmid",
        "extended-high",
        "physical-four",
        "synthetic-four",
    )
}
