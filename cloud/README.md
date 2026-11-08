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
