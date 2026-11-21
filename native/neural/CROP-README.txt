Experimental derived model, uninstalled M3 Neural Lab only.

Parent: Spotify Basic Pitch fa5997af0a8210982619003269994a1be25eddf3
Parent nmp.onnx SHA256:
2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec
License: Apache-2.0; see MODEL-LICENSE.txt.

This derived ONNX graph keeps the full waveform, CQT and global normalization.
Only the subsequent CNN time axis is restricted to original frames [144,172).
The returned notes and onsets are original frames 164 and 165. Weights, causal
readout timing, resampling and event decoder are unchanged. MODEL-CROP.json
records the export and derived hash. Export success alone does not establish
numerical parity, real-time feasibility or musical quality; the corresponding
GitHub report supplies those separate checks. This package is not promoted.
