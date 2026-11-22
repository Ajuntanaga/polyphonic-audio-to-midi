# Paired observation: historical model loader correction

Run **44999979901** failed before any recorded-input inference or paired
comparison. Its seven frozen artifact members and three input archives passed
their identity checks. The loader then rejected `feature_count`; the report's
`roles` object is empty. This is a harness failure, not a new model verdict.

The original writer at source `7481905c4b38bad52770c59c7b9c0fdb3eca75a0`
saved the fixed architecture without the later `feature_count`,
`input_note_count` and `output_note_count` metadata. The new loader mistakenly
required those fields. Its synthetic round trip used the current writer and
therefore missed compatibility with the historical schema.

The correction accepts all three redundant dimensions absent, or all three
present with their exact fixed values. Partial dimensions and different
values fail. Original settings, feature names, feature parameters, architecture
parameters and cutoff remain required. Normalizer shape/finite/positive checks,
strict fixed-network tensor loading, pinned artifact hashes and all reference
probability/decision/target checks remain in force. No model, cutoff, input,
label, tolerance or comparison protocol changes.

Local validation: nine synthetic/metadata tests passed; the actual model test
remains GitHub-only. That test now checks both current and historical saved
schemas. One corrected CPU replacement is justified by this concrete loader
failure under the standing job authorization. The original failed run is final
and collected; do not poll or download it again. The replacement's exact source
SHA and run ID belong in `github-paired-component-mixture-20261122.json`.

Failed small artifact: `14745114005`, 6,254 bytes, server SHA256 verified:
`5a5fd7021e5af85d3fabeffe021ae9a1e56f75132ce50c5ed7cb6b486e8ae700`.
Local report:
`build/github-results/paired-component-mixture-44999979901/artifact/paired-component-mixture-result/report/report.json`.
The original model remains rejected; installed output and measured scoreboard
are unchanged. Claude is paused; no fresh Claude review is claimed.
