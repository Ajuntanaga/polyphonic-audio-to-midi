# Audio level at label ends: result of the registered read

Claude, 2026-11-22. One worker run (`Ajuntanaga/m3-offload` run 45034800737, source `814f6b0e58b313548ecde4ff9dd84e2a9052e666`), one local analysis, no reruns. Registered plan: `CLAUDE-M3-AUDIO-RELEASE-PROPOSAL-20261122.md` (5068ca0). Anything marked **post hoc** was not registered; it uses only the saved curves and the pinned ends, and its script and output are committed beside this note.

## Answer

- **My registered A1 missed.** I expected the 22 uncontested adapted-only ends to still ring at the label end (median R(0) ≥ −6 dB). The median is **−52.7 dB**. The audio does not support the adapted model's extra presence at the label end.
- **The reason is not decay (post hoc).** In **334 of 428 ordinary ends (78%)** the 80 ms after the label end is **exactly digital silence** (every sample zero), and in **all 334** the silence starts at the label end, to within the 10 ms grid. A note that sounds steadily until the end (median change over the previous 80 ms: −1.2 dB) and then goes to exact zero is a hard cut, not a ring-down. So in this corpus the label end is where the audio stops for most ends, and the model's readout at that frame already sees about 80 ms of silence.
- **The adapted-only presence is mostly presence after the sound has stopped (post hoc):** 114 of the 145 adapted-only ends (79%) are followed by exact silence. The same holds for the original model: of the 124 ends where it shows presence (121 both, 3 original-only), 88 (71%) are followed by exact silence. The adapted model keeps what the original also keeps, plus 145 more, and the extra 145 are no better supported than the 121.
- **A2 and A3 passed as registered, with one fragile and one stratum-dependent.** A2 (+46.9 dB) is a difference of medians on a distribution that sits mostly at the digital-silence floor; its registered bootstrap interval, −43.8 to +85.0 dB, includes zero, so I do not lean on it. A3 passes in the verdict stratum (gaps 9.2 and 10.4 dB), but over all 428 ends the both-over-adapted-only gap is only 1.9 dB. What is robust in both strata is that the `neither` ends are about 20 dB quieter before the label end: the ends neither model keeps are the quiet ones.
- **Checks passed:** V0 (pins, 13 tests before any audio), V1 (on its boundary, see below), V2 (median `within` −1.19 dB, n = 67).

## Registered verdicts (ordinary, verdict stratum `uncontested`: adapted-only 22, neither 29)

| Item | Registered bar | Result | Verdict |
|---|---|---|---|
| A1 median R(0), adapted-only | ≥ −6 dB | −52.71 dB | **miss** |
| A2 median R(0) adapted-only minus neither | ≥ +6 dB | +46.88 dB (neither −99.59); bootstrap 95% −43.83 to +85.02 | pass (fragile) |
| A3 median `pre`: both / adapted-only / neither | gaps ≥ 3 dB each | −48.96 / −58.11 / −68.54 (gaps 9.15, 10.43) | pass |
| V1 median rise(0) and argmax δ | ≥ +10 dB, argmax within ±20 ms | rise(0) +72.99 dB; argmax −20 ms | pass, on the boundary |
| V2 median `within`, all 67 ends | in [−8, +1] dB | −1.19 dB | pass |

My stated odds were about 55% for A1 and A2 together and 65% for A3. A1 and A2 did not pass together as I predicted; the A2 pass comes from the floor, not from the ringing I had in mind.

Registered reading rule for "A1 false": the adapted model holds presence past the audible end, which favours the boundary-fit idea more than the earlier probes did. That reading stands, and the post hoc counts below sharpen it.

## What the distribution looks like (descriptive; the share and counts rows are post hoc)

R(0) is level of `[E, E+80 ms)` minus level of `[E−80 ms, E)`. "silent" = the window is at the −180 dB floor, "ring" = R(0) ≥ −6 dB, "between" = neither.

| Ordinary ends | n | silent | ring | between |
|---|---:|---:|---:|---:|
| all, both | 121 | 85 (70%) | 33 (27%) | 3 |
| all, adapted-only | 145 | 114 (79%) | 21 (14%) | 10 |
| all, original-only | 3 | 3 | 0 | 0 |
| all, neither | 159 | 132 (83%) | 12 (8%) | 15 |
| uncontested, both | 16 | 7 | 8 | 1 |
| uncontested, adapted-only | 22 | 9 | 7 | 6 |
| uncontested, neither | 29 | 17 | 2 | 10 |

- The only audio-based separation of adapted-only from `neither` that I can call robust is the ring share: uncontested 7/22 against 2/29 (post hoc one-sided Fisher p = 0.026), all 21/145 against 12/159 (p = 0.039). It is a difference of 25 and 7 percentage points, not a different regime: most ends in both groups are silent.
- `extended-middle`: all 6 ends are `both` and all 6 are exactly silent after the end (median R(0) −145.8 dB).
- Medians of `pre` over all 428 ends: both −39.8, adapted-only −41.8, original-only −40.0, neither −61.3 dB.
- R(40), R(100), R(200) are in the JSON but are **not** interpretable as ring: R(40) is higher than R(0) in two of the three uncontested groups (adapted-only −16.4 against −52.7 dB, neither −8.2 against −99.6 dB), which a decay cannot do. After a silent gap the window reaches the attack of the next sound, whose broadband onset shows up at this pitch's harmonics. R(0), whose window ends 80 ms after the label end, is the only horizon I use.
- V1 by δ (median rise, 68 clean starts with a defined curve of 70): −60 ms +3.4 dB, −40 +24.1, −20 +129.5, 0 +73.0, +20 +16.2. The previous window is exactly silent before most onsets, so the audio onset lies about 0 to 20 ms before the label start (post hoc reading); labels and audio are aligned within that, which is what V1 needed, but the largest rise sits at the edge of the registered band.

## What this does and does not bear on

- **Label rule (open question to the user).** For the 78% of ends followed by silence, the audio really stops at the label end, so a strict end clause is not unfair on audio grounds, and a per-label tolerance cannot be justified by the string still sounding. A tolerance, if used, has to rest on the model's own causal delivery lag, not on the audio. The remaining 22% of ends are followed by other sound (other notes, ring, sympathetic partials) and this read cannot tell which.
- **Lag levers.** The readout at the label-end frame sees the cut and still reports presence in about three quarters of the ends where it is present. That is inertia in the network and the decoder (three-frame release, +11.6 ms later adapted release), not missing information.
- **Prediction for the frame 166/167 contrast (stated now, before that run exists).** The 23.22 ms of right context it removes is silence at the 78% of ends that are followed by a gap, so I expect it to leave label-end presence in that subset essentially unchanged (within a few percentage points) and to differ, if at all, in the remaining ends. About 65%. A real change in the silent subset would contradict "the lateness is inertia".
- **No gate on digital silence.** The corpus audio goes to exact zero, which real guitar audio does not. A release rule keyed to that would score well here and transfer nowhere. I am not proposing one, and nothing here is a promotion, an installed-tracker change or a change to any frozen gate.

## Caveats

- Exact silence of the mono mix means every note is silent, so these ends are followed by gaps in the playing. The 94 non-silent ends are followed by other sound; their ring cannot be separated from other notes' partials (the contested flag only removes the label-known part). I have not checked how the corpus audio was produced; "hard cut" describes the measurement, not its origin.
- The uncontested stratum is small and high-pitched (median MIDI 74); one recording per corpus; ends within a take are not independent (the p-values are descriptive only).
- Not available by registered rule: 80 ordinary start levels (starts too near the beginning of the recording) and 13 `extended-middle` end levels (the tail of the recording), and R(100) and R(200) are undefined for the six `extended-middle` ends, whose windows run past the usable recording.
- The floor values make the median differences in dB larger than any physical ratio; use the counts.

## Pins

- Run: `Ajuntanaga/m3-offload` 45034800737 (workflow commit 35c2ba8), worker report committed as `CLAUDE-M3-AUDIO-RELEASE-WORKER-REPORT-20261122.json` (sha256 `ef2b75bf574a19bdb15fb7001afc8af386ffd929e6f2ae51b468737365448ef2`); 13 tests passed on the worker before any audio was read; runtime 2.6 s.
- Ends file sha256 `3465031b7b6c90da94d658c933116b161550e87648330d70fc8d412b96df3784`; curves (uncompressed) sha256 `196e64634620ac38367fae834f079f6fbac61cf9506ac6c59441da4fcd3fdda3`, committed gzipped as `CLAUDE-M3-AUDIO-RELEASE-CURVES-20261122.json.gz`.
- Registered analysis output `CLAUDE-M3-AUDIO-RELEASE-RESULT-20261122.json` (sha256 `a2ed2a805bb726f90c1104fa35008ed8e75b0375b393b60f1ba84c55655ddc20`), produced once by `CLAUDE-M3-AUDIO-RELEASE-20261122.py analyse`.
- Post hoc: `CLAUDE-M3-AUDIO-RELEASE-POSTHOC-20261122.py`, output `CLAUDE-M3-AUDIO-RELEASE-POSTHOC-RESULT-20261122.json` (sha256 `8d31f9393418beb01b4ca0745223768d2708ece8a800f9e98cde26a3e28bf6c0`).
- Before writing this note I looked at about ten raw curves to check that the analysis indexed the grid as registered; that check changed nothing in the registered output.
