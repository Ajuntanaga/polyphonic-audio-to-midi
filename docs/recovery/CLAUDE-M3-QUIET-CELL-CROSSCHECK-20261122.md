# POST HOC cross-check: Codex's quiet-cell restart numbers reproduce, but they are not an independent second reading

Claude, 2026-11-22. **POST HOC and descriptive: nothing here was pre-registered, no threshold or combination was tuned, no rule was tested.** Saved data only: no audio, model run, job, native edit or promotion, and no download (I read Codex's report where its job left it in the local `build/` folder).
Script `CLAUDE-M3-QUIET-CELL-CROSSCHECK-20261122.py` (sha256 prefix `e0f709e35fea`), output `CLAUDE-M3-QUIET-CELL-CROSSCHECK-20261122.json` (`84d745460bd9`). It stops before computing anything unless all three inputs match their pinned SHA-256: Codex's per-unit report for job 45087140206 (`edfcaad6ea99...`, the digest its note gives), its compact result JSON (`7404e5c90800...`) and my census JSON (`8ab2ca37a5e4...`). Run with `python3 -I ... --run`.
Both recordings were already seen by both analyses: this is design data, not a held-out check.

## Answer

1. **Codex's eight AUCs reproduce exactly.** Recomputed from its own per-unit maxima (23 positive against 254 negative units, no missing value), every AUC equals the reported one: worst difference 0.00e+00. Inside the run: 0.608 (primary interval fundamental share), 0.584, 0.609, 0.477. Through the 25 ms deadline: 0.684 (primary), 0.633, 0.428, 0.688. Nothing in its note needs correcting on these numbers.
2. **Its units and my pairs are the same events.** All 23 positives and 224 of its 254 negatives are the same (pitch, run) as my primary pairs, with identical spans and identical runs on all 247. The other 30 negative units are accounted for: 16 are my secondary pairs (a further run inside a negative span) and 14 are further runs inside positive spans, which my census leaves out by design. It also holds 2 "continuing" units that I do not. No unit is unexplained.
3. **On the 247 shared pairs the AUCs are close.** Mine: F2 0.694, F3 0.625, F1 0.556. Codex's through the deadline: primary 0.686, raw fundamental share 0.686, harmonic share 0.641, recent-to-raw harmonics 0.424. Inside the run, where my F2 has no counterpart: 0.603, 0.595, 0.616, 0.454.
4. **The closeness is not independent confirmation.** My F2 (the fundamental's fast energy over the pre reference, from the detector's decision-level trace) and Codex's primary feature (the 20 ms interval fundamental share, from raw cells) rank the shared pairs alike: Spearman +0.692 over all 247, +0.743 over the 23 positives, +0.669 over the 224 negatives. They are largely the same quantity, the pitch's own energy relative to what came before, read from two sources. The result note's sentence that the two "agree on the best scalar to within about 0.01" is true, but it should not be counted as two confirmations of one finding: see the pointer added there.
5. **One feature is nearly unrelated to F2.** The raw fundamental share against F2: +0.069 over the negatives, +0.559 over the positives, +0.144 over all. Yet it reaches the same AUC (0.686). The harmonic share is in between (+0.255, +0.626, +0.304) and the recent-to-raw harmonic ratio is unrelated (+0.039, -0.063, -0.069). I did not combine anything: picking a pair after seeing these numbers, on 23 positives, would be selection, and an AUC in the 0.7 to 0.8 range would still be far from the 0.90 (lower bound 0.80) bar the quiet-cell design was held to and from the near-complete restart coverage the label budget needs.
6. **Nothing changes in the decisions.** The scalar restart route stays closed. The census and the quiet-cell analysis are two reads of overlapping evidence about the same 23 labels, not two experiments.

## What this does not show

- It does not re-derive Codex's bootstrap intervals or its frozen rule; only the point AUCs and the pair identity.
- Rank correlation says the two features move together, not that they carry the same information at the boundary; they could still differ on individual pairs (they do: +0.69, not +1).
- 23 positives in 21 spans: every number is small-sample, and both recordings are design data.

## Provenance

Codex's report is untracked (the `build/` folder is ignored), so a reader without it must fetch the job's artifact; its digest is pinned in the script. The Spearman uses average ranks for ties; missing values are dropped from a correlation and rank lowest in an AUC (none are missing here). Plumbing checks (known AUC and rank cases) run before any real data.
