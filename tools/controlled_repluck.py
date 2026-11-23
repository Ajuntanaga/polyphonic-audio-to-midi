"""Pure fixture layout and callback comparisons for recorded-attack controls.

These constructed controls test MIDI responses to copied recorded attacks.
They do not annotate new real playing or certify acoustic re-pluck preservation.
"""
from array import array
from collections import Counter
import math


def compose(clip, *, marker_in_clip, markers, frames, gain, fade_frames):
    if (not clip or not 0 <= marker_in_clip < len(clip)
            or not markers or markers != sorted(set(markers))
            or not 0 < gain <= 1 or not 0 < fade_frames < len(clip) // 2
            or any(not math.isfinite(x) for x in clip)):
        raise ValueError('Invalid recorded-attack fixture layout')
    starts = [marker - marker_in_clip for marker in markers]
    if any(start < 0 or start + len(clip) > frames for start in starts):
        raise ValueError('Source copy exceeds fixture bounds')
    output = array('f', [0.0]) * frames
    for start in starts:
        for i, sample in enumerate(clip):
            edge = min(1.0, i / (fade_frames - 1),
                       (len(clip) - 1 - i) / (fade_frames - 1)) if fade_frames > 1 else 1.0
            output[start + i] += sample * gain * edge
    peak = max(abs(x) for x in output)
    if peak >= 1 or not math.isfinite(peak):
        raise ValueError('Constructed control clips; do not normalize or retune it')
    return output


def pitch_active_at(events, note, sample):
    owners = set()
    for event in events:
        if event['sample'] > sample:
            break
        if event['note'] == note:
            owner = event['channel']
            if event['kind'] == 'on':
                owners.add(owner)
            else:
                owners.discard(owner)
    return bool(owners)


def on_times(events, note, start, end):
    return Counter(event['sample'] for event in events
                   if event['kind'] == 'on' and event['note'] == note
                   and start <= event['sample'] < end)


def response(events, reference, *, note, marker, insertion, end, sample_rate):
    """Subtract the no-second-copy control, without matching lanes across modes."""
    observed = on_times(events, note, insertion, end)
    reference_ons = on_times(reference, note, insertion, end)
    added = observed - reference_ons
    first = min(added) if added else None
    return dict(note_ons=sum(observed.values()), control_note_ons=sum(reference_ons.values()),
                added_note_ons=sum(added.values()), added_on_samples=sorted(added.elements()),
                first_added_on_sample=first,
                first_added_delay_ms=None if first is None else 1000 * (first - marker) / sample_rate,
                pitch_active_before_insertion=pitch_active_at(events, note, insertion - 1))


def compare_attack(per_voice, stable_note):
    first = per_voice['first_added_on_sample']
    retained = first is not None and first in stable_note['added_on_samples']
    if first is None:
        verdict = ('stable_only_response' if stable_note['added_note_ons']
                   else 'neither_mode_has_a_new_attack_response')
    else:
        verdict = 'baseline_response_retained' if retained else 'baseline_response_removed_or_retimed'
    return dict(verdict=verdict, baseline_response_observed=first is not None,
                baseline_first_response_retained=retained)


def prefix(events, end):
    return [{key: event[key] for key in ('sample', 'kind', 'note', 'velocity', 'note_id', 'channel')}
            for event in events if event['sample'] < end]
