#!/usr/bin/env python3 -I
"""Claude: part 2 of the saved-report assessment of streaming run 44889388628.

PREDECLARED BEFORE RUNNING (run once; saved tables only; no audio, no model, no download, no
dispatch). Part 1 (CLAUDE-M3-STREAMING-ASSESSMENT-20261121.py/.json) was already run and read;
this part exists because part 1 showed that 99.7% of the both-present loss versus offline is the
onset-delay term, so the next questions are what that delay is made of and what is left once it
is set aside. Same inputs and same label tables as part 1 (S streaming primary clock, Z zero
compute, O offline reference, C saved CURRENT). Units: 96 kHz, 1 ms = 96 samples,
one model frame = 256/22050 s = 11.610 ms.

Constants taken from Codex's frozen contract, not from the results:
  CTX_A = 84.35 ms, CTX_B = 72.74 ms   right context of the two consumed frames (1860 / 1604 model samples)
  COMPUTE = median of (Ds - Dz) over ordinary labels present in both (computed here, ~11 ms)

P2.1  Compute-free shift against offline: quantiles of (Dz - Do) in ms and in model frames, for
      labels present in S and O. Reading rule: if the median falls inside [CTX_B, CTX_A + 2 frames]
      the shift is a context-plus-attack-rule lag; I make no claim about the decoder beyond that.
P2.2  Lag arithmetic: mean annotated length (ms) of those labels, mean (Ds - Do) (ms), predicted
      share of annotated time lost = mean shift / mean length, and the observed
      sum(Ps)/sum(Po) on the same label set. Pure arithmetic, no fit.
P2.3  Loss by annotated-length quartile (edges computed from the data, not chosen): labels losing
      vs offline, mean shift (ms), mean present ratio Ps/Po.
P2.4  Dropouts against offline (Po > 0 = Ps): Po in ms and the count with Po <= CTX_B + COMPUTE
      and Po <= CTX_A + COMPUTE (a presence shorter than the lag cannot be delivered inside the
      label). Dropouts against CURRENT (Pc > 0 = Ps, 34 labels): split by Po == 0 (the model never
      produced it), 0 < Po <= CTX_A + COMPUTE, and Po above that.
P2.5  Fragmenting labels (Ss > So, both present, Ps < Po): onset part vs gap part of their loss,
      count by band, distribution of Ss.
P2.6  Three-way attribution of the 4,143,292 gross loss against CURRENT, mutually exclusive:
        model-level   = sum(Pc - Po) over labels with Pc > Ps and Po < Pc
        stream-added  = sum(Po - Ps) over the same labels (the part streaming adds on top)
        stream-only   = sum(Pc - Ps) over labels with Pc > Ps and Po >= Pc
      The three sum to the gross loss (checked). Also by band.
P2.7  Extended-middle: the per-label present loss of S against C in ms and as a share of the
      annotated length, for the labels the report counts as losing.
Nothing here is fitted, thresholded or tuned; every cut is either a frozen contract constant or a
data-derived quartile edge.
"""
import json
import statistics as st

PROJ = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))
REPORT = PROJ + "/build/github-results/basic-pitch-streaming-44889388628/basic-pitch-streaming-result/report/report.json"
OFFLINE = PROJ + "/docs/recovery/basic-pitch-offline-reference-20261121.json"
BASELINE = PROJ + "/docs/recovery/basic-pitch-baseline-20261121.json"
OUT = PROJ + "/docs/recovery/CLAUDE-M3-STREAMING-ASSESSMENT-PART2-20261121.json"

MS = 96.0
FRAME_MS = 256 / 22050 * 1000
CTX_A, CTX_B = 84.35, 72.74
BANDS = [("below48", lambda n: n < 48), ("48to59", lambda n: 48 <= n < 60),
         ("60to71", lambda n: 60 <= n < 72), ("72plus", lambda n: n >= 72)]


def band(n):
    for name, f in BANDS:
        if f(n):
            return name


def q(xs, qs=(0.05, 0.25, 0.5, 0.75, 0.95)):
    xs = sorted(xs)
    if not xs:
        return {}
    o = {str(p): xs[min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))] for p in qs}
    o.update(n=len(xs), min=xs[0], max=xs[-1], mean=sum(xs) / len(xs))
    return o


def gap(l):
    return l["annotated_samples"] - l["first_present_delay_samples"] - l["present_samples"]


def main():
    rep = json.load(open(REPORT))
    off = json.load(open(OFFLINE))
    base = json.load(open(BASELINE))
    d = rep["datasets"]["ordinary"]
    S = d["measurement"]["labels"]
    Z = d["zero_compute_diagnostic"]["measurement"]["labels"]
    O = off["datasets"]["ordinary"]["labels"]
    C = base["datasets"]["ordinary"]["measurement"]["labels"]
    n = len(S)
    res = {"schema": "claude_m3_streaming_assessment_part2_v1"}

    both_sz = [i for i in range(n) if S[i]["present_samples"] > 0 and Z[i]["present_samples"] > 0]
    COMPUTE = st.median((S[i]["first_present_delay_samples"] - Z[i]["first_present_delay_samples"]) / MS for i in both_sz)
    res["compute_median_ms"] = COMPUTE
    LAG_LO, LAG_HI = CTX_B + COMPUTE, CTX_A + COMPUTE

    both_zo = [i for i in range(n) if Z[i]["present_samples"] > 0 and O[i]["present_samples"] > 0]
    shift = [(Z[i]["first_present_delay_samples"] - O[i]["first_present_delay_samples"]) / MS for i in both_zo]
    res["P2_1_compute_free_shift_vs_offline"] = {
        "ms_quantiles": q(shift), "frames_quantiles": q([v / FRAME_MS for v in shift]),
        "share_between_CTX_B_and_CTX_A_plus_2_frames": sum(1 for v in shift if CTX_B <= v <= CTX_A + 2 * FRAME_MS) / len(shift),
        "share_below_CTX_B": sum(1 for v in shift if v < CTX_B) / len(shift),
        "share_above_CTX_A_plus_2_frames": sum(1 for v in shift if v > CTX_A + 2 * FRAME_MS) / len(shift),
        "labels": len(shift)}

    both_so = [i for i in range(n) if S[i]["present_samples"] > 0 and O[i]["present_samples"] > 0]
    ml = st.mean(S[i]["annotated_samples"] for i in both_so) / MS
    ms_ = st.mean((S[i]["first_present_delay_samples"] - O[i]["first_present_delay_samples"]) / MS for i in both_so)
    res["P2_2_lag_arithmetic"] = {
        "labels": len(both_so), "mean_annotated_ms": ml, "mean_shift_ms": ms_,
        "predicted_share_lost": ms_ / ml,
        "observed_share_lost_sumPs_over_sumPo": 1 - sum(S[i]["present_samples"] for i in both_so) / sum(O[i]["present_samples"] for i in both_so)}

    A = sorted(S[i]["annotated_samples"] for i in range(n))
    edges = [A[int(len(A) * f)] for f in (0.25, 0.5, 0.75)]
    qs = []
    for k in range(4):
        lo = edges[k - 1] if k else -1
        hi = edges[k] if k < 3 else 10 ** 12
        ii = [i for i in both_so if lo < S[i]["annotated_samples"] <= hi]
        lose = [i for i in ii if S[i]["present_samples"] < O[i]["present_samples"]]
        qs.append({"annotated_ms_range": [(lo + 1) / MS if lo >= 0 else 0, hi / MS if hi < 10 ** 12 else None],
                   "labels": len(ii), "losing": len(lose),
                   "mean_shift_ms": st.mean((S[i]["first_present_delay_samples"] - O[i]["first_present_delay_samples"]) / MS for i in ii),
                   "mean_Ps_over_Po": st.mean(S[i]["present_samples"] / O[i]["present_samples"] for i in ii)})
    res["P2_3_by_annotated_length_quartile"] = qs

    drop_o = [i for i in range(n) if O[i]["present_samples"] > 0 and S[i]["present_samples"] == 0]
    res["P2_4_dropouts_vs_offline"] = {
        "labels": len(drop_o),
        "Po_ms_quantiles": q([O[i]["present_samples"] / MS for i in drop_o]),
        "annotated_ms_quantiles": q([O[i]["annotated_samples"] / MS for i in drop_o]),
        "Po_le_CTX_B_plus_compute": sum(1 for i in drop_o if O[i]["present_samples"] / MS <= LAG_LO),
        "Po_le_CTX_A_plus_compute": sum(1 for i in drop_o if O[i]["present_samples"] / MS <= LAG_HI),
        "by_band": {b: sum(1 for i in drop_o if band(S[i]["midi_note"]) == b) for b, _ in BANDS},
        "Pz_positive": sum(1 for i in drop_o if Z[i]["present_samples"] > 0)}
    drop_c = [i for i in range(n) if C[i]["present_samples"] > 0 and S[i]["present_samples"] == 0]
    res["P2_4_dropouts_vs_current"] = {
        "labels": len(drop_c),
        "offline_zero": sum(1 for i in drop_c if O[i]["present_samples"] == 0),
        "offline_present_le_lag": sum(1 for i in drop_c if 0 < O[i]["present_samples"] / MS <= LAG_HI),
        "offline_present_above_lag": sum(1 for i in drop_c if O[i]["present_samples"] / MS > LAG_HI),
        "zero_compute_present": sum(1 for i in drop_c if Z[i]["present_samples"] > 0),
        "by_band": {b: sum(1 for i in drop_c if band(S[i]["midi_note"]) == b) for b, _ in BANDS},
        "current_present_ms_quantiles": q([C[i]["present_samples"] / MS for i in drop_c]),
        "annotated_ms_quantiles": q([C[i]["annotated_samples"] / MS for i in drop_c])}

    frag = [i for i in both_so if S[i]["present_segments"] > O[i]["present_segments"]
            and S[i]["present_samples"] < O[i]["present_samples"]]
    onset = sum(S[i]["first_present_delay_samples"] - O[i]["first_present_delay_samples"] for i in frag)
    gp = sum(gap(S[i]) - gap(O[i]) for i in frag)
    res["P2_5_fragmenting_vs_offline"] = {
        "labels": len(frag), "total_loss": sum(O[i]["present_samples"] - S[i]["present_samples"] for i in frag),
        "onset_part": onset, "gap_part": gp,
        "segments_S_quantiles": q([S[i]["present_segments"] for i in frag]),
        "by_band": {b: sum(1 for i in frag if band(S[i]["midi_note"]) == b) for b, _ in BANDS},
        "all_both_present_by_band_with_more_segments": {b: sum(1 for i in both_so if band(S[i]["midi_note"]) == b and S[i]["present_segments"] > O[i]["present_segments"]) for b, _ in BANDS}}

    lose_c = [i for i in range(n) if C[i]["present_samples"] > S[i]["present_samples"]]
    mod = [i for i in lose_c if O[i]["present_samples"] < C[i]["present_samples"]]
    only = [i for i in lose_c if O[i]["present_samples"] >= C[i]["present_samples"]]
    gross = sum(C[i]["present_samples"] - S[i]["present_samples"] for i in lose_c)
    a = sum(C[i]["present_samples"] - O[i]["present_samples"] for i in mod)
    b = sum(O[i]["present_samples"] - S[i]["present_samples"] for i in mod)
    c = sum(C[i]["present_samples"] - S[i]["present_samples"] for i in only)
    res["P2_6_three_way_attribution_vs_current"] = {
        "gross_loss": gross, "model_level": a, "stream_added_on_model_labels": b, "stream_only": c,
        "sums_to_gross": a + b + c == gross, "labels_model": len(mod), "labels_stream_only": len(only),
        "shares": {"model_level": a / gross, "stream_added": b / gross, "stream_only": c / gross},
        "by_band": {}}
    for bn, _ in BANDS:
        m = [i for i in mod if band(S[i]["midi_note"]) == bn]
        o = [i for i in only if band(S[i]["midi_note"]) == bn]
        res["P2_6_three_way_attribution_vs_current"]["by_band"][bn] = {
            "model_level": sum(C[i]["present_samples"] - O[i]["present_samples"] for i in m),
            "stream_added": sum(O[i]["present_samples"] - S[i]["present_samples"] for i in m),
            "stream_only": sum(C[i]["present_samples"] - S[i]["present_samples"] for i in o),
            "labels_model": len(m), "labels_stream_only": len(o)}

    e = rep["datasets"]["extended-middle"]
    ES = e["measurement"]["labels"]
    EC = base["datasets"]["extended-middle"]["measurement"]["labels"]
    res["P2_7_extended_middle"] = [
        {"label": s["label_index"], "annotated_ms": s["annotated_samples"] / MS,
         "loss_ms": (c_["present_samples"] - s["present_samples"]) / MS,
         "loss_share": (c_["present_samples"] - s["present_samples"]) / s["annotated_samples"],
         "S_delay_ms": s["first_present_delay_samples"] / MS, "C_delay_ms": c_["first_present_delay_samples"] / MS,
         "S_segments": s["present_segments"], "C_segments": c_["present_segments"]}
        for s, c_ in zip(ES, EC)]
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
