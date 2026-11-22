"""One frozen callback-causal native/model release latch, saved events only."""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location(
    "joint_release_support", HERE / "CODEX-M3-SUPPORT-EVENTS-20261122.py")
se = importlib.util.module_from_spec(spec)
spec.loader.exec_module(se)
ad = se.ad
PLAN = HERE / "CODEX-M3-JOINT-RELEASE-PLAN-20261122.md"
OUT = HERE / "CODEX-M3-JOINT-RELEASE-20261122.json"
RAPID = HERE / "CODEX-M3-RAPID-MUTE-20261122.json"
RAPID_SHA256 = "c2008b8956223340d29aa0961f16cc0eba0e73dd648ac9c1894952a6f2c38369"
SUPPORT_SHA256 = "8e09dfa7579bb2f7c1fa5775e2eae02d804273b549dbdc7ce5a017b90b97e41f"
CALLBACK = 512


def latch(current, rapid, model, horizon, primed_at=None):
    """States at boundary b use only emitted events at or before b."""
    current = ad.union_spans(current, sample_count=horizon)
    model = ad.union_spans(model, sample_count=horizon)
    if primed_at is None:
        primed_at = min((a for a, _, _ in model), default=None)
    by_note = defaultdict(list)
    for a, b, note in model:
        by_note[note].append((a, b))
    starts = {note: [a for a, _ in spans] for note, spans in by_note.items()}
    rapid_ends = []
    previous = -1
    for a, b in rapid:
        if not (type(a) is int and type(b) is int and 0 <= a < b <= horizon
                and a % CALLBACK == 0 and a > previous
                and (b % CALLBACK == 0 or b == horizon)):
            raise ValueError("Invalid callback rapid interval")
        rapid_ends.append(b)
        previous = b

    def model_present(note, at):
        i = bisect_right(starts.get(note, []), at) - 1
        return i >= 0 and at < by_note[note][i][1]

    kept, cuts = [], []
    counters = dict(eligible_boundaries=0, warmup_vetoes=0, model_vetoes=0)
    for start, end, note in current:
        first = (start // CALLBACK + 1) * CALLBACK
        i = bisect_right(rapid_ends, first)
        cut = None
        while i < len(rapid) and rapid[i][0] < end and cut is None:
            a, b = rapid[i]
            for boundary in range(max(first, a), min(end, b), CALLBACK):
                counters["eligible_boundaries"] += 1
                if primed_at is None or boundary < primed_at:
                    counters["warmup_vetoes"] += 1
                elif model_present(note, boundary):
                    counters["model_vetoes"] += 1
                else:
                    cut = boundary
                    break
            i += 1
        kept.append((start, end if cut is None else cut, note))
        if cut is not None:
            cuts.append(dict(note=note, current_start=start, current_end=end,
                             cut_at=cut, removed_samples=end-cut))
    kept = ad.union_spans(kept, sample_count=horizon)
    if len(kept) != len(current):
        raise ValueError("Release latch changed the number of pitch starts")
    counters.update(primed_at=primed_at, shortened_spans=len(cuts),
                    removed_samples=sum(r["removed_samples"] for r in cuts))
    return kept, cuts, counters


def selftest():
    h = 4096
    current = [(0, 1800, 40), (2048, 4000, 40)]
    cue = [(512, 1536), (2048, 3584)]
    kept, cuts, _ = latch(current, cue, [(0, 512, 52)], h)
    assert kept == [(0, 512, 40), (2048, 2560, 40)]
    assert [r["cut_at"] for r in cuts] == [512, 2560]
    assert latch(current, cue, [], h)[0] == current  # unknown before priming
    assert latch(current, [], [(0, 512, 52)], h)[0] == current
    assert latch(current, cue, [(0, h, 40)], h)[0] == current
    # On at the boundary protects; Off at the following boundary permits.
    assert latch([(0, 1800, 40)], [(512, 1536)],
                 [(512, 1024, 40)], h)[0] == [(0, 1024, 40)]
    # Future model On cannot protect an earlier cut, or resurrect it.
    assert latch([(0, 1800, 40)], [(512, 1536)],
                 [(0, 64, 52), (513, 1600, 40)], h)[0] == [(0, 512, 40)]
    # A new CURRENT On at 512 is protected on that callback.
    assert latch([(512, 1800, 40)], [(512, 1536)],
                 [(0, 64, 52)], h)[0] == [(512, 1024, 40)]
    # Strictly in-span boundary: an ordinary Off at 512 is never counted a cut.
    assert latch([(0, 512, 40)], [(512, 1536)],
                 [(0, 64, 52)], h)[1] == []
    # Same-pitch model occupancy protects only that pitch, and no other one.
    assert latch([(0, 1800, 40), (0, 1800, 52)], [(512, 1536)],
                 [(0, 1800, 40)], h)[0] == [(0, 1800, 40), (0, 512, 52)]
    print("PASS: callback causality, priming, tie order, latch, reset and identity")


def run():
    if OUT.exists():
        raise SystemExit("Existing result: refusing a duplicate screen")
    report = dict(schema="m3_joint_release_latch_v1", state="running", final=False,
                  started_at=datetime.now(timezone.utc).isoformat(),
                  plan_sha256=se.digest(PLAN), implementation_sha256=se.digest(Path(__file__)),
                  datasets={}, installed_output_changed=False, promotion_accepted=False,
                  callback_samples=CALLBACK, model_clock="emitted_ns",
                  limitation="Design recordings, causal unique-pitch saved-span simulation; no native, lane, unison or host acceptance")
    try:
        if se.digest(RAPID) != RAPID_SHA256:
            raise ValueError("Rapid interval report hash mismatch")
        if se.digest(HERE / "CODEX-M3-SUPPORT-EVENTS-20261122.py") != SUPPORT_SHA256:
            raise ValueError("Shared scorer/pins changed")
        if se.digest(ROOT / se.BRIDGE_PATH) != se.BRIDGE_SHA256:
            raise ValueError("Bridge report hash mismatch")
        rapid = json.loads(RAPID.read_text())
        if rapid["state"] != "completed" or not rapid["final"]:
            raise ValueError("Rapid observation not complete")
        if se.digest(Path(ad.ce.BASELINE)) != rapid["baseline_sha256"]:
            raise ValueError("Baseline span hash mismatch")
        report["rapid_report_sha256"] = RAPID_SHA256
        report["baseline_sha256"] = rapid["baseline_sha256"]
        contexts = {}
        # Finish both input identities before any combined candidate scoring.
        for name, pin in se.PINS.items():
            ctx = ad.dataset_context(name)
            old = rapid["datasets"][name]
            if (old["trace_audit"]["raw_sha256"] != pin["raw_sha256"]
                    or old["horizon"] != ctx["horizon"] or old["rate"] != ctx["rate"]
                    or old["current"] != se.compact(ctx["current"])):
                raise ValueError(name + ": previous observation identity failed")
            event_path = se.EVENTS / pin["events"]
            if se.digest(event_path) != pin["events_sha256"]:
                raise ValueError(name + ": neural events hash mismatch")
            events = ad.read_events(str(event_path))
            model, audit = ad.spans_from_events(events, ctx["horizon"])
            if not audit["pairing_valid"]:
                raise ValueError(name + ": neural pairing invalid")
            first_on = next((e["emitted_ns"] for e in events if e["kind"] == "on"), None)
            primed_at = None if first_on is None else (first_on * ctx["rate"] + ad.NS - 1) // ad.NS
            contexts[name] = (ctx, old["marked_intervals"], model, primed_at)
            report["datasets"][name] = dict(current_identity=True,
                rapid_identity=True, event_sha256=pin["events_sha256"], event_audit=audit,
                rate=ctx["rate"], horizon=ctx["horizon"], current=se.compact(ctx["current"]))
            print(json.dumps(dict(dataset=name, integrity="passed")), flush=True)
        for name, (ctx, intervals, model, primed_at) in contexts.items():
            spans, cuts, counts = latch(ctx["cur_spans"], intervals, model, ctx["horizon"], primed_at)
            measured = ad.score(spans, ctx["labels"], **ctx["clock"])
            compared = ad.compare(ctx["current"], measured)
            for delta, before, after in zip(compared["label_deltas"],
                                           ctx["current"]["labels"], measured["labels"]):
                if not (delta["label_index"] == before["label_index"] == after["label_index"]):
                    raise ValueError("Label identity differs")
                old, new = before["first_present_delay_samples"], after["first_present_delay_samples"]
                delta.update(current_first_present_delay_samples=old,
                             candidate_first_present_delay_samples=new,
                             first_present_delay_delta_samples=None if old is None or new is None else new-old,
                             current_present_segments=before["present_segments"],
                             candidate_present_segments=after["present_segments"])
            d = compared["sample_deltas"]
            true_removed = -d["present_pitch_samples"]
            wrong_removed = -d["extra_pitch_voice_samples"]
            gap_removed = -compared["extra_gap_pitch_samples_delta"]
            if (min(true_removed, wrong_removed, gap_removed) < 0
                    or counts["removed_samples"] != true_removed + wrong_removed + gap_removed):
                raise ValueError("Removed classes do not reconcile")
            row = report["datasets"][name]
            row.update(candidate=se.compact(measured), comparison=compared,
                       budget=se.budget(compared, ctx["rate"]), mechanism=counts,
                       cuts=cuts, candidate_spans=spans,
                       removed=dict(genuine=true_removed, wrong_pitch=wrong_removed, gap=gap_removed),
                       gap_removed_share=gap_removed / ctx["current"]["pitch_sets"]["unlabeled_gap_voice_samples"],
                       occupancy_runs=dict(current=len(ctx["cur_spans"]), candidate=len(spans)))
            print(json.dumps(dict(dataset=name, removed=row["removed"],
                                  mechanism=counts, budget=row["budget"])), flush=True)
        safe = all(r["budget"]["passes"] for r in report["datasets"].values())
        useful = report["datasets"]["ordinary"]["gap_removed_share"] >= .20
        starts_preserved = all(r["occupancy_runs"]["candidate"] <= r["occupancy_runs"]["current"]
                               for r in report["datasets"].values())
        report.update(state="completed", final=True,
                      all_budget_gates_pass=safe, usefulness_pass=useful,
                      no_added_pitch_starts=starts_preserved,
                      verdict="implementation and held-out validation warranted, not accepted"
                              if safe and useful and starts_preserved else "joint release latch rejected")
    except BaseException as exc:
        report.update(state="failed", final=True, error=str(exc))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        with OUT.open("x") as out:
            json.dump(report, out, indent=1)
            out.write("\n")
    print(report["verdict"], flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif sys.argv[1:] == ["--run"]:
        run()
    else:
        raise SystemExit("Use --selftest or --run")
