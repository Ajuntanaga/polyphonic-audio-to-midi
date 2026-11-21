#!/usr/bin/env python3 -I
"""Claude: independent saved-report assessment of streaming run 44889388628.

PREDECLARED BEFORE RUNNING (run once; no tuning; saved tables only; no audio,
no model, no download, no dispatch).

Inputs (all already on disk, read once):
  S  streaming, FIFO-completion clock : build/github-results/basic-pitch-streaming-44889388628/
                                         basic-pitch-streaming-result/report/report.json
       datasets.<name>.measurement.labels
  Z  same events, zero compute delay  : datasets.<name>.zero_compute_diagnostic.measurement.labels
  O  offline Basic Pitch (run 44884737134): docs/recovery/basic-pitch-offline-reference-20261121.json
  C  saved CURRENT                    : docs/recovery/basic-pitch-baseline-20261121.json
All four carry, per label: annotated_samples A, present_samples P, longest_present_samples L,
present_segments S, first_present_delay_samples D (null when P == 0). Labels are matched by
label_index and must agree on midi_note, start_sample, end_sample, annotated_samples.

Exact identity used (checked per label, violations counted, not hidden):
  A = D + P + G   where G = samples after first presence that are not present
                  (internal gaps between segments + tail after the last segment).
  For a label present in both X and S:  Px - Ps = (Ds - Dx) + (Gs - Gx).
  (Ds - Dx) is the onset-delay part, (Gs - Gx) is the dropout-inside part (gaps + early end).
  When Ss == 1, G is purely an early end (no internal gap).

Classes, for the pair (reference X -> streaming S), for labels with Px > Ps:
  DROPOUT   Ps == 0
  FRAGMENT  Ps > 0 and Ss > Sx          (more pieces than the reference)
  SHORT     Ps > 0 and Ss <= Sx         (same or fewer pieces, less time)
A label "loses longest hold" when Ls < Lx.

Reads (each reported with its count, label-sum samples and share of the pair's gross loss):
  R1  pair S vs O and S vs C: counts and gross lost samples per class, overall and by band
      (below48 / 48to59 / 60to71 / 72plus by midi_note).
  R2  onset-delay share: sum(Ds - Dx) over labels present in both and losing, as a fraction of
      their sum(Px - Ps). I read "delay explains the loss" only if that fraction is >= 0.5.
  R3  streaming-specific vs model-level loss against CURRENT: of the labels with Pc > Ps, those
      where O also has Po < Pc ("model also loses") versus Po >= Pc ("streaming-specific").
  R4  fragmentation: pooled (sum P - sum L)/sum P per detector and per band, mean segments per
      present label, share of both-present labels with Ss > So.
  R5  scheduling effect (S vs Z): quantiles of Ds - Dz (ms), count of labels whose P differs.
  R6  by_distinct_pitch_count coverage (present/expected) for S, O, C.
  R7  extended-middle: all six labels side by side.
Units: 96 kHz; 1 ms = 96 samples; one model frame = 256/22050 s = 1114.69 samples = 11.61 ms.

No threshold, offset or window is fitted. Label-sum quantities (sum of per-label P) overlap when
labels share a pitch, so they are NOT the report's distinct-pitch totals; they are used only to
apportion loss between classes, and the script prints both so the difference is visible.
"""
import json
import statistics as st

PROJ = __import__("os").path.abspath(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))
REPORT = PROJ + "/build/github-results/basic-pitch-streaming-44889388628/basic-pitch-streaming-result/report/report.json"
OFFLINE = PROJ + "/docs/recovery/basic-pitch-offline-reference-20261121.json"
BASELINE = PROJ + "/docs/recovery/basic-pitch-baseline-20261121.json"
OUT = PROJ + "/docs/recovery/CLAUDE-M3-STREAMING-ASSESSMENT-20261121.json"

SR = 96000
MS = SR / 1000.0
FRAME = 256 / 22050 * SR
BANDS = [("below48", lambda n: n < 48), ("48to59", lambda n: 48 <= n < 60),
         ("60to71", lambda n: 60 <= n < 72), ("72plus", lambda n: n >= 72)]


def band(n):
    for name, f in BANDS:
        if f(n):
            return name


def load():
    rep = json.load(open(REPORT))
    off = json.load(open(OFFLINE))
    base = json.load(open(BASELINE))
    return rep, off, base


def quant(xs, qs=(0.05, 0.25, 0.5, 0.75, 0.95)):
    if not xs:
        return {}
    xs = sorted(xs)
    out = {}
    for q in qs:
        i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
        out[str(q)] = xs[i]
    out["n"] = len(xs)
    out["min"] = xs[0]
    out["max"] = xs[-1]
    return out


def gap(lab):
    """G = A - D - P; None when there is no presence."""
    if lab["present_samples"] == 0 or lab["first_present_delay_samples"] is None:
        return None
    return lab["annotated_samples"] - lab["first_present_delay_samples"] - lab["present_samples"]


def check_match(tabs, names):
    n = len(tabs[0])
    bad = []
    for t in tabs[1:]:
        if len(t) != n:
            bad.append(("length", len(t), n))
    for i in range(n):
        keys = {(t[i]["label_index"], t[i]["midi_note"], t[i]["start_sample"], t[i]["end_sample"],
                 t[i]["annotated_samples"]) for t in tabs}
        if len(keys) != 1:
            bad.append(("mismatch", i))
    return bad


def pair_read(X, S, label_x, tag):
    """Classify losing labels of S relative to X and decompose the loss."""
    cls = {"DROPOUT": [], "FRAGMENT": [], "SHORT": []}
    gains = []
    ident_bad = 0
    both_lose = []
    for i, (x, s) in enumerate(zip(X, S)):
        Px, Ps = x["present_samples"], s["present_samples"]
        if Px > Ps:
            if Ps == 0:
                c = "DROPOUT"
            elif s["present_segments"] > x["present_segments"]:
                c = "FRAGMENT"
            else:
                c = "SHORT"
            cls[c].append(i)
            if Ps > 0 and Px > 0:
                dx, ds = x["first_present_delay_samples"], s["first_present_delay_samples"]
                gx, gs = gap(x), gap(s)
                lhs = Px - Ps
                rhs = (ds - dx) + (gs - gx)
                if lhs != rhs:
                    ident_bad += 1
                both_lose.append(i)
        elif Ps > Px:
            gains.append(i)
    gross = sum(X[i]["present_samples"] - S[i]["present_samples"] for c in cls.values() for i in c)
    gross_gain = sum(S[i]["present_samples"] - X[i]["present_samples"] for i in gains)
    out = {"pair": tag, "labels": len(X),
           "lose_present": sum(len(c) for c in cls.values()),
           "gain_present": len(gains), "gross_loss_samples": gross, "gross_gain_samples": gross_gain,
           "lose_longest": sum(1 for x, s in zip(X, S) if s["longest_present_samples"] < x["longest_present_samples"]),
           "identity_violations": ident_bad, "classes": {}, "by_band": {}}
    for c, idx in cls.items():
        loss = sum(X[i]["present_samples"] - S[i]["present_samples"] for i in idx)
        out["classes"][c] = {"labels": len(idx), "lost_samples": loss,
                             "share_of_gross": loss / gross if gross else None,
                             "also_lose_longest": sum(1 for i in idx if S[i]["longest_present_samples"] < X[i]["longest_present_samples"])}
    for b, _ in BANDS:
        bi = [i for i in range(len(X)) if band(X[i]["midi_note"]) == b]
        entry = {"labels": len(bi), "X_present": sum(X[i]["present_samples"] for i in bi),
                 "S_present": sum(S[i]["present_samples"] for i in bi), "classes": {}}
        for c, idx in cls.items():
            ii = [i for i in idx if band(X[i]["midi_note"]) == b]
            entry["classes"][c] = {"labels": len(ii),
                                   "lost_samples": sum(X[i]["present_samples"] - S[i]["present_samples"] for i in ii)}
        entry["gain_labels"] = sum(1 for i in gains if band(X[i]["midi_note"]) == b)
        entry["gain_samples"] = sum(S[i]["present_samples"] - X[i]["present_samples"] for i in gains if band(X[i]["midi_note"]) == b)
        out["by_band"][b] = entry
    # R2: onset-delay vs gap decomposition over both-present losers
    onset = sum(S[i]["first_present_delay_samples"] - X[i]["first_present_delay_samples"] for i in both_lose)
    gapd = sum(gap(S[i]) - gap(X[i]) for i in both_lose)
    tot = sum(X[i]["present_samples"] - S[i]["present_samples"] for i in both_lose)
    out["decomposition_both_present_losers"] = {
        "labels": len(both_lose), "total_lost": tot, "onset_delay_part": onset, "gap_part": gapd,
        "onset_fraction": onset / tot if tot else None}
    single = [i for i in both_lose if S[i]["present_segments"] == 1]
    out["decomposition_both_present_losers"]["single_segment_streaming_labels"] = len(single)
    out["decomposition_both_present_losers"]["single_segment_gap_part_samples"] = sum(gap(S[i]) - gap(X[i]) for i in single)
    shifts = [(S[i]["first_present_delay_samples"] - X[i]["first_present_delay_samples"]) / MS
              for i in range(len(X))
              if X[i]["present_samples"] > 0 and S[i]["present_samples"] > 0]
    out["onset_shift_ms_all_both_present"] = quant(shifts)
    out["onset_shift_buckets_ms"] = {
        "le0": sum(1 for v in shifts if v <= 0), "0_to_35": sum(1 for v in shifts if 0 < v <= 35),
        "35_to_100": sum(1 for v in shifts if 35 < v <= 100), "gt100": sum(1 for v in shifts if v > 100)}
    out["_class_indices"] = {c: idx for c, idx in cls.items()}
    return out


def frag(labels):
    present = [l for l in labels if l["present_samples"] > 0]
    sp, sl = sum(l["present_samples"] for l in present), sum(l["longest_present_samples"] for l in present)
    out = {"present_labels": len(present), "mean_segments_per_present_label":
           st.mean(l["present_segments"] for l in present) if present else None,
           "non_longest_share": (sp - sl) / sp if sp else None, "by_band": {}}
    for b, _ in BANDS:
        pb = [l for l in present if band(l["midi_note"]) == b]
        p, ll = sum(l["present_samples"] for l in pb), sum(l["longest_present_samples"] for l in pb)
        out["by_band"][b] = {"present_labels": len(pb),
                             "mean_segments": st.mean(l["present_segments"] for l in pb) if pb else None,
                             "non_longest_share": (p - ll) / p if p else None}
    return out


def by_count(ps):
    res = {}
    for k, v in ps["by_distinct_pitch_count"].items():
        res[k] = {"expected": v["expected_pitch_samples"], "present": v["present_pitch_samples"],
                  "coverage": v["present_pitch_samples"] / v["expected_pitch_samples"]
                  if v["expected_pitch_samples"] else None}
    return res


def main():
    rep, off, base = load()
    result = {"schema": "claude_m3_streaming_assessment_v1", "run_id": "44889388628",
              "report_sha256_expected": "a56b822b669ffa1510880d20f138819434751489a8dd74a81fe1939761ebec32",
              "units": {"sample_rate": SR, "ms_samples": MS, "frame_samples": FRAME}}
    for name in ("ordinary", "extended-middle"):
        d = rep["datasets"][name]
        S = d["measurement"]["labels"]
        Z = d["zero_compute_diagnostic"]["measurement"]["labels"]
        O = off["datasets"][name]["labels"]
        C = base["datasets"][name]["measurement"]["labels"]
        bad = check_match([S, Z, O, C], "SZOC")
        res = {"label_match_problems": bad, "n_labels": len(S)}
        res["label_sum_present"] = {k: sum(l["present_samples"] for l in t)
                                    for k, t in (("S", S), ("Z", Z), ("O", O), ("C", C))}
        res["distinct_pitch_present_reported"] = {
            "S": d["measurement"]["pitch_sets"]["totals"]["present_pitch_samples"],
            "O": off["datasets"][name]["pitch_sets"]["totals"]["present_pitch_samples"],
            "C": base["datasets"][name]["measurement"]["pitch_sets"]["totals"]["present_pitch_samples"]}
        if name == "ordinary":
            so = pair_read(O, S, "O", "streaming vs offline")
            sc = pair_read(C, S, "C", "streaming vs CURRENT")
            # R3: streaming-specific vs model-level loss against CURRENT
            lose_c = [i for i in range(len(S)) if C[i]["present_samples"] > S[i]["present_samples"]]
            model_also = [i for i in lose_c if O[i]["present_samples"] < C[i]["present_samples"]]
            stream_spec = [i for i in lose_c if O[i]["present_samples"] >= C[i]["present_samples"]]
            r3 = {"labels_losing_vs_current": len(lose_c),
                  "model_also_loses_labels": len(model_also),
                  "model_also_loses_samples_streaming_loss": sum(C[i]["present_samples"] - S[i]["present_samples"] for i in model_also),
                  "model_ceiling_loss_samples": sum(C[i]["present_samples"] - O[i]["present_samples"] for i in model_also),
                  "streaming_specific_labels": len(stream_spec),
                  "streaming_specific_samples": sum(C[i]["present_samples"] - S[i]["present_samples"] for i in stream_spec),
                  "streaming_specific_classes": {}}
            for c in ("DROPOUT", "FRAGMENT", "SHORT"):
                ii = [i for i in stream_spec if i in set(sc["_class_indices"][c])]
                r3["streaming_specific_classes"][c] = {
                    "labels": len(ii), "lost_samples": sum(C[i]["present_samples"] - S[i]["present_samples"] for i in ii)}
            by = {}
            for b, _ in BANDS:
                ii = [i for i in stream_spec if band(S[i]["midi_note"]) == b]
                jj = [i for i in model_also if band(S[i]["midi_note"]) == b]
                by[b] = {"streaming_specific_labels": len(ii),
                         "streaming_specific_samples": sum(C[i]["present_samples"] - S[i]["present_samples"] for i in ii),
                         "model_also_loses_labels": len(jj)}
            r3["by_band"] = by
            res["R1_stream_vs_offline"] = {k: v for k, v in so.items() if k != "_class_indices"}
            res["R1_stream_vs_current"] = {k: v for k, v in sc.items() if k != "_class_indices"}
            res["R3_streaming_specific_vs_model_loss"] = r3
            res["R4_fragmentation"] = {"S": frag(S), "O": frag(O), "C": frag(C), "Z": frag(Z)}
            both = [i for i in range(len(S)) if S[i]["present_samples"] > 0 and O[i]["present_samples"] > 0]
            res["R4_fragmentation"]["share_both_present_S_more_segments_than_O"] = (
                sum(1 for i in both if S[i]["present_segments"] > O[i]["present_segments"]) / len(both))
            res["R4_fragmentation"]["share_both_present_S_fewer_segments_than_O"] = (
                sum(1 for i in both if S[i]["present_segments"] < O[i]["present_segments"]) / len(both))
            res["R4_fragmentation"]["segment_delta_S_minus_O_quantiles"] = quant(
                [S[i]["present_segments"] - O[i]["present_segments"] for i in both])
            # R5 scheduling
            dd = [(S[i]["first_present_delay_samples"] - Z[i]["first_present_delay_samples"]) / MS
                  for i in range(len(S))
                  if S[i]["present_samples"] > 0 and Z[i]["present_samples"] > 0]
            res["R5_scheduling_S_vs_Z"] = {
                "onset_delay_ms_quantiles": quant(dd),
                "labels_present_differs": sum(1 for i in range(len(S)) if S[i]["present_samples"] != Z[i]["present_samples"]),
                "labels_lose_present_vs_Z": sum(1 for i in range(len(S)) if S[i]["present_samples"] < Z[i]["present_samples"]),
                "labels_gain_present_vs_Z": sum(1 for i in range(len(S)) if S[i]["present_samples"] > Z[i]["present_samples"]),
                "gross_loss_samples": sum(Z[i]["present_samples"] - S[i]["present_samples"] for i in range(len(S)) if S[i]["present_samples"] < Z[i]["present_samples"]),
                "gross_gain_samples": sum(S[i]["present_samples"] - Z[i]["present_samples"] for i in range(len(S)) if S[i]["present_samples"] > Z[i]["present_samples"])}
            res["R6_by_distinct_pitch_count"] = {
                "S": by_count(d["measurement"]["pitch_sets"]),
                "O": by_count(off["datasets"][name]["pitch_sets"]),
                "C": by_count(base["datasets"][name]["measurement"]["pitch_sets"])}
        else:
            keys = ("present_samples", "longest_present_samples", "present_segments", "first_present_delay_samples")
            res["R7_labels"] = [{"label_index": S[i]["label_index"], "midi_note": S[i]["midi_note"],
                                 "annotated": S[i]["annotated_samples"],
                                 **{t: {k: L[i][k] for k in keys} for t, L in (("S", S), ("Z", Z), ("O", O), ("C", C))}}
                                for i in range(len(S))]
        result[name] = res
    json.dump(result, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
