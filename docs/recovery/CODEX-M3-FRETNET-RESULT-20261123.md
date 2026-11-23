# Fixed FretNet comparison: rejected — 2026-11-23

FretNet reproduces the pinned runtime references but fails the fixed offline
pitch screen. It finds substantially less of the ordinary recording than
CURRENT. Combining outputs recovers some complementary pitches but fails the
false-output or per-label protections. This setting is closed; no tuning,
rerun or runtime integration follows from it. Installed output is unchanged.

Run **45207778894** completed successfully at 15:41:20 UTC. Source
`c054a09dab9db765a6d869777f100667937b22d6`, worker
`5c4e63660db528b46ce9b5876787a70b55c8f7b2`. The prior run **45206977346**
failed on a lazy submodule import before any corpus measurement. The recovery
only changed that import; frozen spec SHA-256 remains
`4e092ed584e31ba6acd69d9c89409afd8e479c8efda262c2f5aa21257e2b5826`.

## Primary result

These are expected **pitch-samples found**, independent of string assignment,
on an offline nominal frame clock. Durations overlap for simultaneous pitches;
they are not labeled-frame match scores, unique audio time or delivered MIDI.
Extra pitches over annotations and extra outputs in unlabeled gaps are separate.

| Corpus | CURRENT found / expected | FretNet found / expected | Coverage change | Label budget failures |
|---|---:|---:|---:|---:|
| Ordinary | 13,525,345 / 33,819,101 (39.9932%) | 7,513,808 / 33,819,101 (22.2176%) | -17.7756 pp | 187 / 499 |
| Extended-middle | 2,021,510 / 2,073,600 (97.4879%) | 2,016,176 / 2,073,600 (97.2307%) | -0.2572 pp | 5 / 6 |

Ordinary: 193 labels lose present time, 194 lose longest hold and 122 become
entirely missed. Wrong-pitch samples fall 7,808,309 -> 1,696,143 and gap samples
3,629,163 -> 647,192, at the cost of 6,011,537 genuine pitch-samples. The
ordinary +5 pp gain gate is missed. Extended-middle loses 5,334 genuine samples;
three labels lose present time and five lose longest hold, despite zero
wrong-pitch output over annotations and gap output falling to 10,089 samples.

The six-string standard-tuning model covers MIDI 40..83. All 47 ordinary labels
outside that range (3,189,372 label-samples) remain in the primary denominator;
none is excluded. There are no out-of-range extended-middle labels. Training
fold and original checkpoint provenance for the community export remain unknown.

## Frozen report-only combinations

| Ordinary arm | Pitch coverage | Wrong-pitch change | Gap change | Budget failures |
|---|---:|---:|---:|---:|
| CURRENT union FretNet | 49.1797% (+9.1865 pp) | +1,318,699 | +196,885 | 0 / 499 |
| CURRENT below 60; FretNet at 60+ | 45.5829% (+5.5897 pp) | -223,504 | +21,777 | 6 / 499 |

The union preserves every label but grows both false-output classes. The fixed
pitch split loses six labels, including two newly entirely missed, and grows
gap output. Both combinations pass their extended-middle safety comparisons,
but neither passes across both recordings. These diagnostic span combinations
are not deployable fusion policies. No cutoff or threshold is selected from
the result, and none of the three arms is accepted.

## Verification and limits

All **18/18** pinned reference gates pass before corpus processing: HCQT,
window preparation, all three raw heads, exact decoded positions, nominal times
and chunked inference. Both saved CURRENT measurements reproduce exactly.
All **66** synthetic worker tests pass. Source CI **45207704916** passes native
tests, replay contracts and synthetic buffer parity. This verifies the adapter
and comparison; it does not establish causal latency or live musical quality.

The frontend normalizes and transforms the complete file and uses centered
context. Recorded runtime is offline throughput only. No string identity,
unison multiplicity, acoustic re-pluck, native deadline, external device or
live-guitar acceptance follows. Earlier batch-cell core, component and REAPER
passes remain separate and unchanged. Claude's ordinary 58-event acoustic lane
also remains independent; this result does not require a duplicate analysis.

## Retained evidence

- Checkpoint: `docs/recovery/github-fretnet-comparison-recovery-20261123.json`.
- Small artifact **14834473023**, 131,903 bytes, collected once with archive
  SHA-256 `70521d894dfc3e9bab2e2e7e17d96432f2c27d338c473a4c5a218639cc7f7f17`
  equal to the server digest.
- Report: `build/github-results/fretnet-comparison-45207778894/report/fretnet-result/report/report.json`;
  SHA-256 `7dc2f2527de2f179c378b3186e6acf13b283a4116c0603cd2a83e069c273dde4`.
- Collection receipt: `build/github-results/fretnet-comparison-45207778894/collection.json`.
- Bulk artifact **14835840150**, 6,425,549 bytes, remains remote through
  2026-12-07; no model or audio was transferred to the laptop.

Next work must be a distinct tracking or articulation design, using this
negative transfer result rather than repeating the fixed pretrained-model
screen. Reliable live use and acoustic re-pluck preservation remain open.
