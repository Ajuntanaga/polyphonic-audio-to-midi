"""Clock and fixture scoring for a frozen standalone attack detector.

Pure metadata functions: no waveform access, detector import or inference.
"""
from __future__ import annotations

import math


def event_record(hop_start, hop_samples, real_samples, nominal_sample, duration_ns):
    if not (hop_start >= 0 and 0 < real_samples <= hop_samples and duration_ns >= 0):
        raise ValueError("Invalid hop metadata")
    return {
        "available_sample": hop_start + hop_samples,
        "nominal_sample": int(nominal_sample),
        "call_ns": int(duration_ns),
        "padded_samples": hop_samples - real_samples,
    }


def event_identity(events, through_sample):
    """Compare only causally available events, ignoring variable CPU duration."""
    return [(e["available_sample"], e["nominal_sample"], e["padded_samples"])
            for e in events if e["available_sample"] <= through_sample]


def score_fixture(events, insertions, markers, deadlines, sample_rate, samples):
    if not (len(insertions) == len(markers) == len(deadlines) and insertions):
        raise ValueError("One deadline per inserted copy is required")
    if not (sample_rate > 0 and samples > 0 and
            insertions == sorted(set(insertions))):
        raise ValueError("Invalid fixture geometry")
    if any(not (0 <= a <= m < samples and a < d < samples)
           for a, m, d in zip(insertions, markers, deadlines)):
        raise ValueError("Invalid insertion, marker or deadline")
    positions = [e["available_sample"] for e in events]
    if positions != sorted(set(positions)) or any(s <= 0 for s in positions):
        raise ValueError("Events must have unique increasing causal samples")
    windows = []
    for i, (start, marker, deadline) in enumerate(zip(insertions, markers, deadlines)):
        end = insertions[i + 1] if i + 1 < len(insertions) else math.inf
        cues = [e for e in events if start < e["available_sample"] <= end]
        first = cues[0]["available_sample"] if cues else None
        windows.append({
            "copy": i + 1, "insertion_sample": start, "marker_sample": marker,
            "deadline_sample": deadline, "cue_count": len(cues),
            "cue_available_samples": [e["available_sample"] for e in cues],
            "first_available_sample": first,
            "first_delay_from_marker_ms": (first - marker) * 1000 / sample_rate
            if first is not None else None,
            "headroom_to_baseline_samples": deadline - first if first is not None else None,
            "exactly_one_cue": len(cues) == 1,
            "cue_by_baseline_response": first is not None and first <= deadline,
        })
    pre = [e for e in events if e["available_sample"] <= insertions[0]]
    return {
        "events": events, "cue_count": len(events), "expected_cues": len(insertions),
        "pre_insertion_cues": len(pre), "copies": windows,
        "fixed_screen_pass": not pre and len(events) == len(insertions) and
        all(w["exactly_one_cue"] and w["cue_by_baseline_response"] for w in windows),
    }
