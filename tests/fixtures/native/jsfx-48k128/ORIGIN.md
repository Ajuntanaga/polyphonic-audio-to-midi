# Frozen JSFX 48 kHz / 128-Sample Oracle

- Source checkpoint: `0be04d3`
- Source directory: `build/test-results/task13-v232-final-jsfx-48k128-slice/`
- Capture date: 2026-08-28
- Runtime fingerprint: `7f2724003de54d623b434abf263e6dae3e571d4064194440094ed4367aa29ac4`
- Copy rule: the four TSV files are byte-identical copies of the accepted Task 13 evidence and must not be regenerated during the native port.
- Parity cohort: the 45 rows whose `mode` field is `m3`.

This fixture is the behavioral oracle for the test-only legacy 128-sample
schedule. It does not authorize changing or installing the production JSFX.
