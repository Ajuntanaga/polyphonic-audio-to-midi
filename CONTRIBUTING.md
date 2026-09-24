# Contributing

M3 accepts focused fixes, tests, documentation corrections, and proposals that
preserve real-time audio safety and complete MIDI note cleanup.

## Set up the repository

Clone the pinned VSTGUI dependency with the repository:

```bash
git clone --recurse-submodules \
  https://github.com/Ajuntanaga/polyphonic-audio-to-midi.git
cd polyphonic-audio-to-midi
```

For an existing clone:

```bash
git submodule update --init --recursive
```

The native build requires CMake 3.25 or newer, a C++17 compiler, and the Linux
development libraries used by VSTGUI. The CI workflow lists the Ubuntu package
set.

## Verify a change

Run the source and contract checks from the repository root:

```bash
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B tools/validate_source.py .
python3 -B tools/validate_native_source.py .
git diff --check
```

For native code, also configure and run the C++ suite:

```bash
cmake -S . -B build/contributor -DCMAKE_BUILD_TYPE=Release
cmake --build build/contributor --target m3_native_tests --parallel 2
ctest --test-dir build/contributor --output-on-failure -R '^m3_native_tests$'
```

Add a regression test for behavior changes. Keep deterministic host tests
separate from claims about a physical instrument, audio interface, or DAW
session. A synthetic pass does not establish tracking quality for a particular
guitar or performance.

## Submit a change

Keep each commit limited to one logical change. In the pull request, state the
commands you ran and any manual validation that remains. Do not commit build
outputs, credentials, personal paths, private projects, or audio you cannot
redistribute.
