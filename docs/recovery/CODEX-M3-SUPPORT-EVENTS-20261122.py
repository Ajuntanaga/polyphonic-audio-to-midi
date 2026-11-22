"""Frozen saved-data L/E/A screen; no audio, inference or native execution.

See CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md. Run --selftest first, then
--run once. Refuses to overwrite its result. One streaming pass per trace.
"""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "support_events_ad", HERE / "CLAUDE-M3-ADAPTED-SUPPORT-20261122.py")
ad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ad)

from tools.candidate_outcome_analysis import _candidates
from tools.native_neural_consensus import (
    BRIDGE_PATH, BRIDGE_SHA256, compact, confirmation_spans, selector_confirmation)
from tools.pitch_detector_comparison import digest

OUT = HERE / "CODEX-M3-SUPPORT-EVENTS-20261122.json"
PLAN = HERE / "CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md"
PINS = {
    "ordinary": {
        "trace": "build/github-results/unfiltered-observation-44835727027/evidence/github-results/unfiltered-observation/ordinary-current-on-512-outcome-v5.tsv.gz",
        "raw_sha256": "b664c7ff0ce80bd4e544b647ce48688ecf181918cb7e36643370bab2eccfbd93",
        "run": 44835727027,
        "events": "adapted_cropped__ordinary-events.json",
        "events_sha256": "4e0601c42dbdccffe32c245a74ce80a9ae24be825f0b21e010b37f33f8ac9e92",
    },
    "extended-middle": {
        "trace": "build/github-results/extended-middle-unfiltered-45062999189/evidence/github-results/unfiltered-observation/extended-middle-current-on-512-outcome-v5.tsv.gz",
        "raw_sha256": "78929974b9cc914f71ef3fa58759728dda93f4a53fea16af17f3217adb6ac267",
        "run": 45062999189,
        "events": "adapted_cropped__extended-middle-events.json",
        "events_sha256": "1eea72fdc62b0d2e1f09f871d3a0f1b6cf8b4490cb4413f7862fa42986f688e3",
    },
}
EVENTS = ROOT / "build/github-results/basic-pitch-temporal-crop-45034216124/claude-range-members"
ARMS = ("L", "E", "A")


def observed_support(candidates, quiet):
    direct, onset = set(), set()
    for note, c in candidates.items():
        valid_direct = selector_confirmation(c)
        if c["active"] not in (0, 1) or c["onset_observed"] not in (0, 1):
            raise ValueError("Missing or invalid active/onset validity")
        if not quiet:
            if valid_direct:
                direct.add(note)
            if (c["selector_pool_member"] == 1 and c["active"] == 1
                    and c["selection"] == 4 and c["onset_observed"] == 1
                    and c["onset"] > 0):
                onset.add(note)
    return direct, onset


def observations(pin, audit):
    raw_hash = hashlib.sha256()
    audit.update(rows=0, candidate_rows=0, quiet_rows=0)
    previous = None
    with gzip.open(ROOT / pin["trace"], "rb") as stream:
        def lines():
            for raw in stream:
                raw_hash.update(raw)
                yield raw.decode("utf-8")
        rows = lines()
        if next(rows).strip() != "# m3_candidate_outcome_v5":
            raise ValueError("Expected the complete v5 trace")
        reader = csv.DictReader(rows, delimiter="\t")
        for row in reader:
            sample, tick, quiet = (int(row[k]) for k in ("sample", "tick", "quiet"))
            if sample < 0 or tick < 0 or quiet not in range(8):
                raise ValueError("Invalid decision coordinates")
            if previous is not None and (sample != previous[0] + 64 or tick != previous[1] + 1):
                raise ValueError("Non-contiguous decision grid")
            candidates = _candidates({"candidate_text": row["candidates"]})
            direct, onset = observed_support(candidates, quiet)
            audit["rows"] += 1
            audit["candidate_rows"] += len(candidates)
            audit["quiet_rows"] += int(quiet != 0)
            if previous is None:
                audit["first_sample"], audit["first_tick"] = sample, tick
            previous = sample, tick
            yield sample, direct, onset
    audit.update(raw_sha256=raw_hash.hexdigest(), last_sample=previous[0], last_tick=previous[1])
    if audit["raw_sha256"] != pin["raw_sha256"]:
        raise ValueError("Raw trace hash mismatch")


def project(rows, horizon):
    """L overwrites; E/A OR positive events until the completed callback."""
    spans = {arm: [] for arm in ARMS}
    counts = dict(observed_callbacks=0, direct_observations=0, onset_observations=0,
                  onset_only_observations=0, E_added_note_callbacks=0,
                  E_changed_callbacks=0, A_added_note_callbacks=0, A_changed_callbacks=0,
                  positive_note_callbacks={arm: 0 for arm in ARMS})
    boundary, previous = None, -1
    pending = {arm: set() for arm in ARMS}

    def emit():
        if boundary is None or boundary >= horizon:
            return
        assert pending["L"] <= pending["E"] <= pending["A"]
        counts["observed_callbacks"] += 1
        for arm in ARMS:
            counts["positive_note_callbacks"][arm] += len(pending[arm])
            spans[arm].extend((boundary, min(boundary + 512, horizon), note)
                              for note in sorted(pending[arm]))
        for first, second in (("L", "E"), ("E", "A")):
            added = pending[second] - pending[first]
            counts[second + "_added_note_callbacks"] += len(added)
            counts[second + "_changed_callbacks"] += bool(added)

    for sample, direct, onset in rows:
        if sample <= previous:
            raise ValueError("Observations out of order")
        next_boundary = ((sample + 512) // 512) * 512
        if next_boundary != boundary:
            emit()
            boundary = next_boundary
            pending = {arm: set() for arm in ARMS}
        pending["L"] = set(direct)
        pending["E"].update(direct)
        pending["A"].update(direct | onset)
        if boundary < horizon:
            counts["direct_observations"] += len(direct)
            counts["onset_observations"] += len(onset)
            counts["onset_only_observations"] += len(onset - direct)
        previous = sample
    emit()
    return {arm: ad.union_spans(items, sample_count=horizon) for arm, items in spans.items()}, counts


def budget(comparison, rate):
    over, missed = [], []
    for row in comparison["label_deltas"]:
        violations = []
        for field in ("present_samples", "longest_present_samples"):
            lost = max(0, -row[field + "_delta"])
            before = row["current_" + field]
            if lost * 1000 > 25 * rate:
                violations.append(field + ":25ms")
            if lost * 100 > 5 * before:
                violations.append(field + ":5pct")
        if violations:
            over.append(dict(label_index=row["label_index"], violations=violations))
        if row["current_present_samples"] > 0 and row["model_present_samples"] == 0:
            missed.append(row["label_index"])
    d = comparison["sample_deltas"]
    aggregate = (d["extra_pitch_voice_samples"] <= 0
                 and comparison["extra_gap_pitch_samples_delta"] <= 0
                 and d["exact_pitch_set_samples"] >= 0
                 and d["all_expected_pitches_samples"] >= 0)
    return dict(over_budget_labels=over, newly_missed_labels=missed,
                aggregate_pitch_safety=aggregate,
                passes=not over and not missed and aggregate,
                arithmetic="Integer sample counts; <=25ms AND <=5% for each metric")


def evaluate(ctx, model, native):
    horizon = ctx["horizon"]
    support = ad.union_spans([*model, *native], sample_count=horizon)
    held = ad.dil.dilate(support, 220 * ctx["rate"] // 1000, horizon)
    filtered = ad.intersect_spans(ctx["cur_spans"], held, sample_count=horizon)
    measured = ad.score(filtered, ctx["labels"], **ctx["clock"])
    compared = ad.compare(ctx["current"], measured)
    for row, before, after in zip(compared["label_deltas"], ctx["current"]["labels"], measured["labels"]):
        old, new = before["first_present_delay_samples"], after["first_present_delay_samples"]
        row.update(current_first_present_delay_samples=old, candidate_first_present_delay_samples=new,
                   first_present_delay_delta_samples=None if old is None or new is None else new - old,
                   current_present_segments=before["present_segments"],
                   candidate_present_segments=after["present_segments"])
    totals = ctx["current"]["pitch_sets"]["totals"]
    wrong_delta = compared["sample_deltas"]["extra_pitch_voice_samples"]
    return dict(compact=compact(measured), comparison=compared, budget=budget(compared, ctx["rate"]),
                wrong_removed_share=-wrong_delta / totals["extra_pitch_voice_samples"],
                pitch_occupancy_runs=len(filtered), current_pitch_occupancy_runs=len(ctx["cur_spans"]),
                pitch_occupancy_runs_delta=len(filtered) - len(ctx["cur_spans"])), filtered


def verify_control(name, row, saved):
    old = saved[name]["sources"]["cropped adapted"]["by_d"]["220"]["filter"]
    cmp = row["comparison"]
    losing = sum(r["present_samples_delta"] < 0 or r["longest_present_samples_delta"] < 0
                 for r in cmp["label_deltas"])
    checks = dict(coverage_pct=round(row["compact"]["present_percent"], 4),
                  wrong_delta=cmp["sample_deltas"]["extra_pitch_voice_samples"],
                  gap_delta=cmp["extra_gap_pitch_samples_delta"],
                  present_delta=cmp["sample_deltas"]["present_pitch_samples"],
                  exact_set_delta=cmp["sample_deltas"]["exact_pitch_set_samples"],
                  all_expected_delta=cmp["sample_deltas"]["all_expected_pitches_samples"],
                  labels_losing_present_or_longest=losing,
                  no_pitch_safety_regression=cmp["no_pitch_safety_regression"])
    if any(old[key] != value for key, value in checks.items()):
        raise ValueError(name + ": L filter differs from saved result")
    return checks


def run():
    if OUT.exists():
        raise SystemExit("Result already exists; refusing a duplicate screen")
    report = dict(schema="m3_support_events_screen_v1", state="running", final=False,
                  started_at=datetime.now(timezone.utc).isoformat(), datasets={},
                  plan_sha256=digest(PLAN), implementation_sha256=digest(Path(__file__)),
                  predicate_note="L last-direct; E any-direct; A any-direct or pooled active selected positive observed onset",
                  support_hold_ms=220, callback_samples=512, model_clock="emitted_ns",
                  installed_output_changed=False, promotion_accepted=False,
                  limit="Saved pitch spans on design recordings; no native, lane, unison, raw retrigger, deadline or live host result")
    try:
        if digest(ROOT / BRIDGE_PATH) != BRIDGE_SHA256:
            raise ValueError("Bridge report hash differs")
        saved = json.loads((HERE / "CLAUDE-M3-ONNX-SUPPORT-20261122.json").read_text())
        consensus = json.loads((Path(ad.ce.CONSENSUS) / "report.json").read_text())
        report["baseline_sha256"] = digest(Path(ad.ce.BASELINE))
        contexts, models = {}, {}
        # Finish every integrity gate on both corpora before candidate scoring.
        for name, pin in PINS.items():
            ctx = ad.dataset_context(name)
            contexts[name] = ctx
            saved_pin = consensus["datasets"][name]["spans_evidence"]
            if digest(Path(ad.ce.CONSENSUS) / saved_pin["name"]) != saved_pin["sha256"]:
                raise ValueError(name + ": saved native support hash differs")
            event_path = EVENTS / pin["events"]
            if digest(event_path) != pin["events_sha256"]:
                raise ValueError(name + ": model event hash differs")
            models[name], event_audit = ad.spans_from_events(ad.read_events(str(event_path)), ctx["horizon"])
            if not event_audit["pairing_valid"]:
                raise ValueError(name + ": invalid model event pairing")
            audit = {}
            projected, counts = project(observations(pin, audit), ctx["horizon"])
            if projected["L"] != ctx["native"]:
                raise ValueError(name + ": L native support identity failed")
            control, control_filtered = evaluate(ctx, models[name], projected["L"])
            control_identity = verify_control(name, control, saved)
            report["datasets"][name] = dict(pin=pin, trace=audit, projection=counts,
                current_identity=True, native_L_identity=True, control_filter_identity=control_identity,
                event_audit=event_audit, horizon=ctx["horizon"], rate=ctx["rate"],
                current=compact(ctx["current"]), arms={"L": control})
            contexts[name]["projected"] = projected
            contexts[name]["control_filtered"] = control_filtered
            print(json.dumps(dict(dataset=name, integrity="passed", rows=audit["rows"], projection=counts)), flush=True)
        for name, ctx in contexts.items():
            row = report["datasets"][name]
            evidence = {"native_support": ctx["projected"], "filtered": {}}
            for arm in ARMS:
                if arm == "L":
                    spans = ctx["control_filtered"]
                else:
                    row["arms"][arm], spans = evaluate(ctx, models[name], ctx["projected"][arm])
                evidence["filtered"][arm] = spans
            evidence_path = HERE / ("CODEX-M3-SUPPORT-EVENTS-20261122-" + name + "-spans.json.gz")
            with evidence_path.open("xb") as raw:
                with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as out:
                    out.write(json.dumps(evidence, separators=(",", ":")).encode())
            row["span_evidence"] = dict(path=evidence_path.name, sha256=digest(evidence_path))
        readings = {}
        for arm in ARMS:
            ordinary = report["datasets"]["ordinary"]["arms"][arm]
            ext = report["datasets"]["extended-middle"]["arms"][arm]
            cmp = ordinary["comparison"]
            utility = (ordinary["wrong_removed_share"] >= .20
                       and cmp["extra_gap_pitch_samples_delta"] <= -250000
                       and cmp["pitch_coverage_gain_pp"] >= -.10
                       and ext["comparison"]["no_pitch_safety_regression"])
            both_budget = ordinary["budget"]["passes"] and ext["budget"]["passes"]
            readings[arm] = dict(cleanup_utility_retained=utility, both_corpora_budget_pass=both_budget,
                                 design_screen_pass=utility and both_budget)
        report.update(state="completed", final=True, reading=readings,
                      verdict="candidate passes design screen only" if readings["A"]["design_screen_pass"]
                              else "candidate rejected; no tuning in this screen")
    except BaseException as exc:
        report.update(state="failed", final=True, error=str(exc))
        raise
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(dict(reading=report["reading"], verdict=report["verdict"])), flush=True)


def selftest():
    # A brief positive pulse followed by quiet must survive E/A, never L;
    # no support before completion, and a missing callback cannot renew it.
    rows = [(63, {40}, set()), (511, set(), set()), (1023, set(), {42}),
            (1535, set(), set()), (2559, {45}, set())]
    spans, _ = project(iter(rows), 3072)
    assert spans["L"] == [(2560, 3072, 45)]
    assert spans["E"] == [(512, 1024, 40), (2560, 3072, 45)]
    assert spans["A"] == [(512, 1024, 40), (1024, 1536, 42), (2560, 3072, 45)]
    reference, _ = confirmation_spans(((s, d) for s, d, _ in rows), sample_count=3072)
    assert spans["L"] == reference
    c = dict(selector_pool_member=1, direct=0, active=1, selection=4, onset_observed=1, onset=.001)
    assert observed_support({42: c}, 0) == (set(), {42})
    assert observed_support({42: c}, 1) == (set(), set())
    assert observed_support({42: dict(c, onset_observed=0)}, 0) == (set(), set())
    assert observed_support({42: dict(c, selection=5)}, 0) == (set(), set())
    row = dict(label_index=0, current_present_samples=48000, model_present_samples=45600,
               current_longest_present_samples=48000, model_longest_present_samples=45600,
               present_samples_delta=-2400, longest_present_samples_delta=-2400)
    cmp = dict(label_deltas=[row], sample_deltas=dict(extra_pitch_voice_samples=-1,
               exact_pitch_set_samples=1, all_expected_pitches_samples=1), extra_gap_pitch_samples_delta=-1)
    assert budget(cmp, 96000)["passes"]
    row["present_samples_delta"] = -2401
    assert not budget(cmp, 96000)["passes"]
    print("PASS: callback causality, quiet/validity/selection, control projection and exact budget edge")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    elif sys.argv[1:] == ["--run"]:
        run()
    else:
        raise SystemExit(__doc__)
