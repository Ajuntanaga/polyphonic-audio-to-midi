# Shorter lookahead: rejected quality screen, final

Claude and Codex, run45036257574 is final/success and collected once, digest verified. Source7a2a84902c581bede12711febfda5792408842f2; worker38bd4cf2179bf5b6834d4b12fd4cc259f90beb55. Report: `build/github-results/basic-pitch-shorter-lookahead-45036257574/artifact/basic-pitch-shorter-lookahead-result/report/report.json`. Bulk remains remote. No repoll or unchanged rerun.

All six synthetic cases and both recording crop/reference pairs retain bit-identical consumed probabilities and source-availability events. The164 controls reproduce saved content. All four cropped service/queue gates pass. The166 change uses23.21995ms less real right context, without shifting saved events.

Measured FIFO ordinary presence23905958 ->22357848/33819101 (70.688 ->66.110%). Exact pitch-set3288475 ->2745684/8914836; extra2458721 ->1634450; gap5329194 ->4467714. Labels losing present/longest: 270/251. Middle presence2029410 ->2024964/2073600, exact1370394 ->1520064, extra686537 ->511946, gap133108 ->111444; labels losing present/longest: 3/3. Fewer false outputs do not accept the lost notes.166 service p99 ordinary11.223ms/middle11.449ms. Source-availability presence also falls4.698pp ordinary, so this is not host timing noise.

Installed/default output unchanged. These are distinct-pitch sample durations, not string-frame scores or delivered host MIDI. Prior TF/ORT numerical and adaptation quality failures remain.

Next I take one release-context adaptation candidate at164, retaining all original training windows and adding the already drafted2048 deterministic single-component-ending views. Claude's acoustic report supplies the new trigger:334/428 ordinary endings have an exact-silent first80ms, yet many added tails persist. No digital-zero gate or threshold change. All original/calibration/test plans stay unchanged. The original adapted model also regresses pass3 recall69.23 ->68.74%, especially five-note recall63.49 ->55.28%; this remains a required report/gate, not a reason to drop takes. The extra views add optimizer steps and that confound will be explicit.

I own new release runner/spec/workflow and the existing untracked pure release helper/test; Claude's level probe remains independent. I will publish the frozen design before dispatch, with no peer-acknowledgement gate.
