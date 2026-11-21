#!/usr/bin/env python3
"""Independent check of Codex's upstream clock-mismatch finding against saved tables.

Predeclared before running (run once, saved tables only; no audio, no model, no download):

Codex (CODEX-M3-EIGHT-HOUR-WORK-20261121.md) reports that upstream Basic Pitch's
unwrap keeps 142 frames per 36164-sample window while model_frames_to_time applies
its per-window correction every 172 frames. If the offline reference timestamps come
from that function, the offline times drift EARLIER than the true position as the
position in the single 111 s recording grows.

Derivation, using only Codex's two numbers plus the pinned constants
(22,050 Hz, hop 256, window 43,844 samples) and the upstream correction constant
0.0018 s that I recall from the upstream source and could not check locally:
  true window advance per retained 142 frames: 36164 samples
  naive advance per 142 frames: 142 * 256 = 36352 samples -> need 188 samples per 142 frames
  applied: (256/22050 + 0.0018) s = 13.410 ms per 172 frames
  error per frame = 188/22050/142 - 0.013410/172 = -1.78e-5 s -> -1.533 ms per second of audio
So the offline time is predicted to be 1.533 ms earlier per second of position.

Predictions (written now, no free parameters, nothing fitted):
  slope of (Ds - Do) vs label start (ms per s of position): about +1.53
  slope of (Ds - Dc): about 0 (CURRENT is native-sample-clocked, streaming is sample-clocked)
  slope of (Do - Dc): about -1.53
If (Ds - Do) shows no slope, the offline reference does not carry the upstream drift, and
the model_frames_to_time finding does not explain any of the +106.6 ms shift.

Reads:
  T1 OLS slope with analytic SE and Theil-Sen slope, labels present in both.
  T2 median of each shift in five equal-count position bins.
  T3 count of labels whose first presence is at or before the label start, per bin (early
     placement signature), for S, O, C.
  T4 with the predicted drift e(t) = 1.533 ms/s * t added to Do (a fixed correction from
     the derivation, not a fit): median and quartiles of Ds - Do', and the share of the
     +106.6 ms median shift it removes.
Limits: first-present delay is label-relative, position is the label start sample, only the
ordinary recording is long enough (10,689,600 samples = 111.35 s); extended-middle is one
short file and is not analysed here.
"""
import json
import math
import sys

PROJ = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))
REPORT = PROJ + "/build/github-results/basic-pitch-streaming-44889388628/basic-pitch-streaming-result/report/report.json"
OFFLINE = PROJ + "/docs/recovery/basic-pitch-offline-reference-20261121.json"
BASELINE = PROJ + "/docs/recovery/basic-pitch-baseline-20261121.json"
OUT = PROJ + "/docs/recovery/CLAUDE-M3-OFFLINE-CLOCK-DRIFT-CHECK-20261121.json"

SR = 96000
MS = SR / 1000.0
PRED_MS_PER_S = (0.013410 / 172 - 188 / 22050 / 142) * 86.1328125 * 1000  # = 1.533 (sign: offline earlier)


def ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    res = [y - a - b * x for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in res) / (n - 2)
    se = math.sqrt(s2 / sxx)
    return {"slope": b, "intercept": a, "se": se, "n": n, "resid_sd": math.sqrt(s2)}


def theil_sen(xs, ys):
    sl = []
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            if xs[j] != xs[i]:
                sl.append((ys[j] - ys[i]) / (xs[j] - xs[i]))
    sl.sort()
    return sl[len(sl) // 2]


def q(xs, qs=(0.25, 0.5, 0.75)):
    xs = sorted(xs)
    return {str(p): xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] for p in qs}


def main():
    rep = json.load(open(REPORT))
    off = json.load(open(OFFLINE))
    base = json.load(open(BASELINE))
    S = rep["datasets"]["ordinary"]["measurement"]["labels"]
    O = off["datasets"]["ordinary"]["labels"]
    C = base["datasets"]["ordinary"]["measurement"]["labels"]
    assert len(S) == len(O) == len(C) == 499
    for i in range(499):
        assert S[i]["start_sample"] == O[i]["start_sample"] == C[i]["start_sample"], i
    out = {"schema": "claude_m3_offline_clock_drift_check_v1", "predicted_ms_per_s_offline_early": PRED_MS_PER_S}

    def D(l):
        return None if l["present_samples"] == 0 or l["first_present_delay_samples"] is None else l["first_present_delay_samples"] / MS

    rows = []
    for i in range(499):
        ds, do, dc = D(S[i]), D(O[i]), D(C[i])
        rows.append({"i": i, "t": S[i]["start_sample"] / SR, "ds": ds, "do": do, "dc": dc})
    out["position_range_s"] = [min(r["t"] for r in rows), max(r["t"] for r in rows)]

    pairs = {"Ds-Do": ("ds", "do"), "Ds-Dc": ("ds", "dc"), "Do-Dc": ("do", "dc")}
    t1 = {}
    for name, (a, b) in pairs.items():
        sel = [r for r in rows if r[a] is not None and r[b] is not None]
        xs = [r["t"] for r in sel]
        ys = [r[a] - r[b] for r in sel]
        o = ols(xs, ys)
        o["theil_sen_slope"] = theil_sen(xs, ys)
        o["slope_over_se"] = o["slope"] / o["se"]
        t1[name] = o
    out["T1_slope_ms_per_s"] = t1
    out["T1_prediction_check"] = {
        "Ds-Do predicted": PRED_MS_PER_S, "Ds-Dc predicted": 0.0, "Do-Dc predicted": -PRED_MS_PER_S}

    # T2/T3 position bins
    order = sorted(range(499), key=lambda i: rows[i]["t"])
    bins = []
    for k in range(5):
        idx = order[k * 499 // 5:(k + 1) * 499 // 5]
        sel = [rows[i] for i in idx]
        entry = {"bin": k, "t_range_s": [sel[0]["t"], sel[-1]["t"]], "n_labels": len(sel)}
        for name, (a, b) in pairs.items():
            v = [r[a] - r[b] for r in sel if r[a] is not None and r[b] is not None]
            entry["median_" + name.replace("-", "_minus_") + "_ms"] = q(v)["0.5"] if v else None
            entry["n_" + name.replace("-", "_minus_")] = len(v)
        for k2, key in (("S", "ds"), ("O", "do"), ("C", "dc")):
            d = [r[key] for r in sel if r[key] is not None]
            entry["early_at_or_before_start_" + k2] = sum(1 for x in d if x <= 0)
            entry["median_first_delay_" + k2 + "_ms"] = q(d)["0.5"] if d else None
        bins.append(entry)
    out["T2_T3_position_bins"] = bins

    # T4 fixed correction
    sel = [r for r in rows if r["ds"] is not None and r["do"] is not None]
    raw = [r["ds"] - r["do"] for r in sel]
    cor = [r["ds"] - (r["do"] + PRED_MS_PER_S * r["t"]) for r in sel]
    med_raw, med_cor = q(raw)["0.5"], q(cor)["0.5"]
    out["T4_fixed_correction"] = {
        "n": len(sel), "raw_Ds_minus_Do_ms": q(raw), "corrected_Ds_minus_Do_ms": q(cor),
        "share_of_median_removed": 1 - med_cor / med_raw,
        "mean_correction_ms": sum(PRED_MS_PER_S * r["t"] for r in sel) / len(sel)}
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    sys.exit(main())
