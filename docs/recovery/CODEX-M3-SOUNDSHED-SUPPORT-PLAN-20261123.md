# Fixed Soundshed support screen

Codex, 2026-11-23. Written before collecting or scoring the Soundshed event files. The completed replacement comparison is known and remains rejected. This is one distinct saved-span question, not a detector rerun or retuning of its settings.

## Question and ownership

Can Soundshed's causal pitch observations supply the timely support that the Basic Pitch filter lacked, while retaining useful false-output removal? Codex owns `tools/soundshed_support.py`, its synthetic contracts, this note and its result. Claude's ordinary-58 acoustic work remains independent; no acknowledgement is needed. No native source, audio, inference, worker dispatch, installed behavior or default changes.

## One fixed candidate

Use both ordinary and extended-middle. CURRENT and native confirmation come from the previously recorded consensus inputs; native support is the last direct pooled observation per 512-sample callback, available at its end, expiring after one callback. Do not regenerate traces or change the predicate.

Inside Soundshed's documented MIDI 35..88 range:

`candidate = CURRENT intersect hold_forward(Soundshed union native_confirmation, 220 ms)`

Outside that range preserve CURRENT exactly. This is the same model-range protection as the previous replacement primary; it is not a fitted pitch split or a label exception. Every annotation remains in the denominator. There is no grace, backward dilation, time shift, new threshold, pitch addition, grid or second variant.

Soundshed events are from run 45218379585, source `1a00073578ba8296ff0415cc99ce77fd1f5918ef`, worker `638f5bb6292f1c293205a17e19828a99ebe9656d`. Use the detector sample offsets exactly. Read events over the full recording first, then clip all sources to the existing common-support horizon: ordinary 10,681,922 and extended-middle 2,233,574 samples, both 96 kHz. These remove only terminal samples, not annotations. Preserve current and prior common-horizon measurements exactly.

## Frozen decision

Keep the previous support screen's utility bar: ordinary wrong-pitch removal >=20%, gap-voice delta <=-250,000 samples, pitch-coverage loss <=0.10 percentage points; extended-middle must pass strict safety. Both corpora must satisfy the existing prospective budget: each label's present-time AND longest-hold loss <=25 ms AND <=5% of its own CURRENT value, no newly completely missed label, no wrong-pitch/gap growth, no all-expected/exact-set loss. Report the original strict zero-loss verdict separately. No exemptions for carried credit or low CURRENT coverage.

Failing any clause closes this fixed combination. No threshold, hold, range or label changes based on its result. A pass is only a reason to consider implementation: same-pitch occupancy intersection does not implement causal string/unison ownership or acoustic re-plucks. Report fragmentation/pitch-run counts and the already measured Soundshed timing failure; joint runtime, allocations and host acceptance remain unmeasured.

## Inputs and integrity

- CURRENT: `docs/recovery/basic-pitch-baseline-20261121.json`, SHA-256 `da173e1940fb99a0057b7406ea4b8453df10bc4ee571d5e7d1708b25222172f1`.
- Consensus report: `build/recovery/m3-native-neural-consensus-20261121/report.json`, SHA-256 `6a80b45e7f7ba5a3732e471cb825fa6474297938a5a24661dc23792b6dc34d06`.
- Ordinary consensus spans: same directory, `ordinary-consensus-spans.json.gz`, SHA-256 `0d0dc2973a0dc3e4c4392b62706887bfae1f7cc36b9054c3714aed816022f2a3`.
- Extended-middle consensus spans: `extended-middle-consensus-spans.json.gz`, SHA-256 `da09fbe6fc18c1ad54d7b3a926e9bc95a06361c3e47b1ff13e18cf99ec3fb21d`.
- Soundshed report: `build/github-results/soundshed-comparison-45218379585/report/soundshed-result/report/report.json`, SHA-256 `0d1962b8ad8653e5d8949bf8c5b726ec07e0a530874bc58a3c7d002687e7bfde`.
- One evidence collection: artifact 14838928396, `m3-soundshed-evidence-45218379585-1`, 926,779 bytes, SHA-256 `769a4600d84157483fa22397e18a277dae9dbe18b31783aa3bcb1a5b86f3b944`. Extract only `ordinary-events.tsv` and `extended-middle-events.tsv`; their hashes must equal the producing report. No audio or other bulk member needed.

Before scoring the candidate, reproduce CURRENT at full and common horizons and Soundshed's saved full-recording measurement from events; verify event pairing, all hashes, clocks and unchanged label count. Save every per-label delta, including first-present delay, and the full output spans. This is design data already used for discovery, not a held-out or live claim.
