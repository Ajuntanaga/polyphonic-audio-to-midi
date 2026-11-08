# Portable offline research

GitHub Actions builds and tests the native replay executable. Kaggle runs a
bounded GPU spectral probe. Neither depends on Modal or changes the installed
plugin. Recordings and credentials stay out of this public repository.

## Native replay on GitHub Actions

The `Portable offline replay` workflow runs on tuner-stability branch pushes,
pull requests to main, and manual dispatch. It builds the existing native
detector and frozen cue code with the offline diagnostic flags, runs the replay,
cue and detector tests, and compares generated-audio outputs at buffer sizes
32, 512 and 1024. Artifacts are retained for seven days.

The standalone CMake entry point is `cloud/native`. It requires Linux x86-64
with AVX, CMake, and a C/C++ compiler; it does not require the VST3 SDK or GUI
libraries. The production build continues to use the root CMake project.

```sh
cmake -S cloud/native -B build/portable -DCMAKE_BUILD_TYPE=Release
cmake --build build/portable --parallel 2
ctest --test-dir build/portable --output-on-failure
python3 -B -m tools.portable_replay_smoke --binary build/portable/m3_replay --output build/cloud-smoke
```

The smoke check verifies transport and buffer parity on generated audio. It
does not establish physical-corpus acceptance or real-time host performance.
Shared-runner timing cannot replace measurements in the intended audio host.

## Private Kaggle GPU probe

Install the official Kaggle CLI in an isolated environment and configure its
credential locally. Do not put a token in a notebook, metadata file, or commit.
The tested CLI installation used `uv tool install --with six kaggle`; the extra
dependency resolved an import failure in the installed CLI version.

```sh
python3 cloud/kaggle/prepare.py --username YOUR_USERNAME --output build/kaggle-m3
kaggle kernels push -p build/kaggle-m3 --accelerator NvidiaTeslaT4 --timeout 600
kaggle kernels status YOUR_USERNAME/m3-portable-gpu-spectra
kaggle kernels output YOUR_USERNAME/m3-portable-gpu-spectra -p build/kaggle-results
```

Preparation does not upload anything. Push submits one private notebook with
Internet disabled and no attached datasets. The notebook generates its own
audio, requires CUDA, and compares float64 FFT power with NumPy. It fails rather
than claiming GPU success after a CPU fallback. Free accelerator availability
depends on the account and current service limits.

The first completed Tesla T4 run analyzed 266 windows of generated audio.
Maximum absolute power error was 8.326672684688674e-17, within relative tolerance
1e-9 and absolute tolerance 1e-12. Measured FFT-and-power time was 0.274 seconds
on CPU and 0.636 seconds on GPU. This small workload showed no GPU speedup;
timings exclude transfer and startup. Native cue parity, labeled matches and
live MIDI behavior were not measured.

The script optionally accepts `M3_WAV` for a deliberately attached private mono
PCM16 or float32 recording and reads at most six seconds. No recording is
attached by default. The next research step is a bounded comparison of the
existing cue algorithm on recovered inputs, preserving its windows, thresholds
and output format; a matching FFT alone is insufficient to replace it.

## Recover replay inputs

The service-independent `tools/replay_corpus.py` preserves the existing corpus
mapping. `M3_PHYSICAL_RECORDINGS` and `M3_SPECTRAL_TEMPLATES` can override local
paths. The Modal runner imports the same mapping.

```sh
python3 -B -m tools.portable_recovery --hash --output build/recovery/inventory.json
python3 -B -m tools.portable_recovery --hash --expected build/recovery/inventory.json --output build/recovery/recheck.json
python3 -B -m tools.portable_recovery --dataset physical-long --output build/recovery/selected.json --bundle build/recovery/physical-long.tar
```

The last command creates a local archive only. It refuses missing inputs and
known hash mismatches and will not overwrite an existing archive. Check its
manifest before any separately authorized upload. A new hash records the
current bytes; it does not prove identity with an inaccessible historical copy.

Recovery on November 8 located all five original recordings on the workstation
and copied 138,675,436 bytes into the expected local source-recordings directory.
Source and destination SHA-256 hashes match. Current filenames match the shared
map, including the existing spelling of the high-string recording; no aliases
or label substitutions were needed. All 30 declared inputs are now present and
hashed: 307,122,490 bytes, covering 14 dataset pairs plus calibration and templates.
This is complete recovery of the declared input list, not complete recovery of
every Modal artifact.

Local records are `build/recovery/source-recovery.json` and
`build/recovery/inventory.json`. Original controlled calibration crops and saved
Modal OFF/ON replay TSVs remain unavailable locally. Summary reports cannot
replace those exact outputs. Reconstructed references must have new provenance
and must not be presented as recovered historical baselines.

Native corpus acceptance remains zero of fourteen. Before promotion, require no
lost labeled match, no increased false output, buffer parity, zero processing
allocations, p99 at most 166666 ns, maximum at most 333333 ns, and zero overruns,
followed by the remaining host and MIDI lifecycle checks. The installed plugin
is unchanged; reliable live use and overall completion are not measured.

## Private corpus replay on replacement compute

The recovery runner rebuilds the native detector on Kaggle CPU and creates new
OFF/ON references from the surviving recordings. The GPU probe above remains a
separate numerical check; it does not accelerate this native C++ replay.

```sh
python3 -B -m cloud.kaggle.prepare_recovery --username YOUR_USERNAME --output build/kaggle-recovery-UNIQUE
kaggle datasets create -p build/kaggle-recovery-UNIQUE/dataset --keep-tabular
kaggle kernels push -p build/kaggle-recovery-UNIQUE/kernel --timeout 11400
kaggle kernels status YOUR_USERNAME/m3-recovered-corpus
kaggle kernels output YOUR_USERNAME/m3-recovered-corpus -p build/kaggle-results/recovered-corpus
```

Preparation copies the declared inputs and snapshots the native source, build
entry point and replay tools. The manifests record SHA-256 hashes and the base
commit, including the exact bytes of any uncommitted source changes. Creation
is exclusive: choose a new local output directory for each attempt. Dataset
creation is private by default; do not add `--public`. The kernel is explicitly
private, with Internet and GPU disabled. The license field is `other`, with a
description retaining the original authors' rights and granting no public
redistribution license; the service rejected its documented `copyright-authors` value.
The [official dataset metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
and [kernel metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
describe these fields. Dataset uploads and kernel launches are separate actions.

The cloud bootstrap verifies source and input hashes, builds with two compiler
workers, and runs the native tests before replaying. It first saves all fourteen
OFF references. Physical-long is the first ON screen; ON enables both native
partial cues and free-lane reassignment. Wider ON recovery proceeds only after
no label loss or extra false output, zero C/C++ processing allocations and frees,
and exact OFF/ON buffer consistency at 32, 512 and 1024 samples. A later regression
stops wider ON work and preserves completed results.

Timing is measured at 32 samples and 96 kHz. ON must meet p99 <=166666 ns,
maximum <=333333 ns and zero deadline overruns. A timing failure is recorded as
a failed native gate; reference recovery may continue, but promotion remains
false. The replay budget is three hours with a thirty-minute per-process cap.
Each completed replay updates `corpus-results/report.json` and retains its TSV,
command, source/binary/input hashes, stderr and available timing JSON. These new
references do not restore historical Modal identity, missing control crops, or
the unavailable final Modal report. They do not establish live-host readiness.
