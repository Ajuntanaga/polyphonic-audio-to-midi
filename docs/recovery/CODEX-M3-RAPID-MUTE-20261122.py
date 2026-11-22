"""One frozen observation of existing rapid-mute quiet=5, saved spans only."""
from bisect import bisect_right
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location(
    "rapid_mute_support", HERE / "CODEX-M3-SUPPORT-EVENTS-20261122.py")
se = importlib.util.module_from_spec(spec)
spec.loader.exec_module(se)
ad = se.ad
PLAN = HERE / "CODEX-M3-RAPID-MUTE-PLAN-20261122.md"
OUT = HERE / "CODEX-M3-RAPID-MUTE-20261122.json"


def observations(pin, audit):
    hashed = hashlib.sha256()
    previous = (-1, 0)
    audit.update(rows=0, quiet_counts=[0] * 8)
    with gzip.open(ROOT / pin["trace"], "rb") as stream:
        def lines():
            for raw in stream:
                hashed.update(raw)
                yield raw.decode("utf-8")
        rows = lines()
        if next(rows).strip() != "# m3_candidate_outcome_v5":
            raise ValueError("Wrong trace version")
        for row in csv.DictReader(rows, delimiter="\t"):
            sample, tick, quiet = (int(row[k]) for k in ("sample", "tick", "quiet"))
            if (sample, tick) != (previous[0] + 64, previous[1] + 1):
                raise ValueError("Incomplete decision grid")
            if quiet not in range(8):
                raise ValueError("Unknown quiet disposition")
            audit["rows"] += 1
            audit["quiet_counts"][quiet] += 1
            previous = sample, tick
            yield sample, quiet
    audit.update(raw_sha256=hashed.hexdigest(), last_sample=previous[0])
    if audit["raw_sha256"] != pin["raw_sha256"]:
        raise ValueError("Raw trace hash mismatch")


def project(rows, horizon):
    cuts, boundary, quiet = [], None, None

    def emit():
        if boundary is not None and boundary < horizon and quiet == 5:
            end = min(boundary + 512, horizon)
            if cuts and cuts[-1][1] == boundary:
                cuts[-1] = (cuts[-1][0], end)
            else:
                cuts.append((boundary, end))

    for sample, observed_quiet in rows:
        at = ((sample + 1 + 511) // 512) * 512
        if at != boundary:
            emit()
            boundary = at
        quiet = observed_quiet
    emit()
    return cuts


def subtract(spans, cuts, horizon):
    ends = [end for _, end in cuts]
    kept = []
    for start, end, note in spans:
        cursor = start
        i = bisect_right(ends, start)
        while i < len(cuts) and cuts[i][0] < end:
            left, right = cuts[i]
            if cursor < left:
                kept.append((cursor, min(left, end), note))
            cursor = max(cursor, right)
            i += 1
        if cursor < end:
            kept.append((cursor, end, note))
    return ad.union_spans(kept, sample_count=horizon)


def selftest():
    rows = [(63, 5), (511, 0), (575, 5), (1023, 5),
            (1087, 5), (1535, 5), (1599, 0), (2047, 0)]
    assert project(rows, 2304) == [(1024, 2048)]
    assert project([(2559, 5)], 2600) == [(2560, 2600)]
    spans = [(0, 2304, 40), (1000, 1500, 52), (2048, 2200, 60)]
    actual = sorted(subtract(spans, [(1024, 2048)], 2304))
    assert actual == sorted([(0, 1024, 40), (2048, 2304, 40),
                             (1000, 1024, 52), (2048, 2200, 60)])
    assert subtract(spans, [], 2304) == ad.union_spans(spans, sample_count=2304)
    print("PASS: completed callback, last disposition, clipping and span subtraction")


def run():
    if OUT.exists():
        raise SystemExit("Existing result: no duplicate run")
    report = dict(schema="m3_rapid_mute_overlap_v1", state="running", final=False,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  plan_sha256=se.digest(PLAN), implementation_sha256=se.digest(Path(__file__)),
                  datasets={}, installed_output_changed=False, promotion_accepted=False,
                  limitation="Optimistic saved pitch occupancy mask; no causal MIDI or new held-out validation")
    try:
        if se.digest(ROOT / se.BRIDGE_PATH) != se.BRIDGE_SHA256:
            raise ValueError("Bridge report hash mismatch")
        report["baseline_sha256"] = se.digest(Path(ad.ce.BASELINE))
        contexts = {}
        for name, pin in se.PINS.items():
            ctx = ad.dataset_context(name)  # Full CURRENT scorer identity.
            audit = {}
            cuts = project(observations(pin, audit), ctx["horizon"])
            if audit["last_sample"] + 1 < ctx["horizon"]:
                raise ValueError("Trace does not cover scoring horizon")
            contexts[name] = (ctx, cuts)
            report["datasets"][name] = dict(
                trace=pin["trace"], source_run=pin["run"], trace_audit=audit,
                current_identity=True, rate=ctx["rate"], horizon=ctx["horizon"],
                marked_samples=sum(b-a for a, b in cuts), marked_runs=len(cuts),
                marked_intervals=cuts, current=se.compact(ctx["current"]))
            print(json.dumps(dict(dataset=name, integrity="passed", rows=audit["rows"])), flush=True)
        for name, (ctx, cuts) in contexts.items():
            masked = subtract(ctx["cur_spans"], cuts, ctx["horizon"])
            measured = ad.score(masked, ctx["labels"], **ctx["clock"])
            compared = ad.compare(ctx["current"], measured)
            delta = compared["sample_deltas"]
            present = -delta["present_pitch_samples"]
            wrong = -delta["extra_pitch_voice_samples"]
            gap = -compared["extra_gap_pitch_samples_delta"]
            removed = sum(b-a for a, b, _ in ctx["cur_spans"]) - sum(b-a for a, b, _ in masked)
            if removed != present + wrong + gap or min(present, wrong, gap) < 0:
                raise ValueError("Overlap classes do not reconcile")
            row = report["datasets"][name]
            row.update(masked=se.compact(measured), comparison=compared,
                       budget=se.budget(compared, ctx["rate"]),
                       overlap=dict(present=present, wrong_pitch=wrong, gap=gap,
                                    total=removed, false_share=(wrong+gap)/removed if removed else None),
                       occupancy_runs=dict(current=len(ctx["cur_spans"]), masked=len(masked)))
            print(json.dumps(dict(dataset=name, overlap=row["overlap"],
                                  budget=row["budget"], occupancy_runs=row["occupancy_runs"])), flush=True)
        safe = all(r["budget"]["passes"] for r in report["datasets"].values())
        useful = any(r["overlap"]["wrong_pitch"] + r["overlap"]["gap"] > 0 for r in report["datasets"].values())
        report.update(state="completed", final=True,
                      verdict="cue alone rejected" if not safe else
                              "causal design warranted, not accepted" if useful else "no measured benefit")
    except BaseException as exc:
        report.update(state="failed", final=True, error=str(exc))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        with OUT.open("x") as stream:
            json.dump(report, stream, indent=1)
            stream.write("\n")
    print(report["verdict"], flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif sys.argv[1:] == ["--run"]:
        run()
    else:
        raise SystemExit("Use --selftest or --run")
