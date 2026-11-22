# Decision on the label rule, the release-hold trial and the walk guard

Claude, 2026-11-22. The user left three open items to my judgement ("use your best judgement"). This note records the three decisions. It changes no code, gate, installed behaviour or earlier verdict, and no evaluation has been run under the new rule: it is frozen before any is.

## 1. Label rule for judging candidates from now on: option 2, with a frozen budget

I agree with `CODEX-M3-GATE-RECOMMENDATION-20261122.md` (option 2) and adopt its three properties. The numbers it left open are:

| Clause | Frozen value |
|---|---|
| Per-label present-time loss vs CURRENT | at most **25 ms and** at most **5%** of that label's own CURRENT present time (both must hold) |
| Per-label longest-hold loss vs CURRENT | the same: at most 25 ms and at most 5% of its own CURRENT value |
| Labels CURRENT detects | none may become completely missed |
| Wrong-pitch and gap output | no growth on any protected corpus (the existing absolute limits, unchanged) |
| First-present delay | reported per label, not gated |
| Everything else | string, unison, MIDI lifecycle, buffer, allocation, deadline and strict-numerics requirements as they stand |

Why these numbers: the budget is a response to what a player would notice, not to a candidate. I chose it knowing the adapted-support D=220 losers (largest 50.57 ms on label 364, largest share 10.18% on label 263), and set it tighter than both on purpose, so that candidate fails it on its largest loser alone. Codex warned against fitting the rule to the observed losers and I have not. A 25 ms cut is an immaterial slice of a sustained note, and 5% binds first on labels shorter than 500 ms, so short articulations are protected too. The numbers are the user's to change; if they are changed, change them before the next held-out run, not after.

Option 1 (zero-sample loss) stays the installed gate in the scorer (`no_pitch_safety_regression`) because I have not edited `tools/`. Reports from here on show **both** the strict result and the budget result, so nothing is hidden by the new rule. Earlier results are not re-judged. Option 3 (coverage and precision with no label loss) is rejected for the live default: on ordinary it adds 23.8% wrong-pitch and 43.7% gap output, and on extended-middle it does not improve all three measures (Codex's figures).

What this does not do: it does not accept the support policy, does not turn a saved availability-clock result into delivered live behaviour, and does not make any recording a validation of itself. The recordings that informed the design cannot validate the revised rule; a candidate judged by it still needs a held-out result.

## 2. Release-hold native trial: not running it

Left unclaimed, as before (Codex may claim it; nothing blocks that). My reasons, in order of weight:

- My own saved-data bound says the lever is small: about 5% of false output for one or two short label cuts, or 10% to 13% for 6 to 14 cuts (`CLAUDE-M3-LOWREG-ENERGY-RELEASE-20261122.md`, `CLAUDE-M3-LOWREG-TAIL-STATE-20261122.md`). That did not justify a GitHub job when I wrote it and nothing since changed it.
- The held-out check just run on the second corpus (`CLAUDE-M3-LOWREG-HELDOUT-RESULT-20261122.md`) removed the one low-register lever that looked cheap: the ungated octave re-render lost 7.53 coverage points there, and its best gate never fired.
- Under the new budget, the cases where a release hold helps most (long tails, a clipped note or two) are the ones most likely to spend the loss allowance on a single label.
- The standing approval covers scoped frozen CPU comparison jobs on M3, not a native behaviour change on a weak prior.

I would reopen it if a trace-side release cue (power or envelope decay) shows separation on held-out data, since the tail-state note says only a note-off cue could clip the acoustically supported tail ticks.

## 3. Walk guard

A PreToolUse guard is now installed in the user's Claude settings, for Bash, Grep and Glob: it refuses recursive `find`, `grep -r`, `rg`, `du`, `ls -R`, `tree`, `fd` and `ncdu` on `/`, `/home`, the home directory and its Archive folder (hard-reset hazard on the NTFS volume), and allows named roots and `-maxdepth 0/1`. Tested on 37 cases and fails open on any parsing problem. It covers Claude sessions only. **Codex's shells are not covered**; the standing rule for Codex stays: no unscoped `find`, `grep -r`, `du` or `ls -R` over `/` or the home directory, and never walk the Archive.
