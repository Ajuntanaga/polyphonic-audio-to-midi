"""Fixed causal onset-confirmed experiment; no recording or model I/O."""
import math

from tools.basic_pitch_streaming import SETTINGS, emission_spans
from tools.pitch_detector_comparison import compare, score


ONSET_DECODER = dict(onset_threshold=0.5, frame_threshold=0.3,
    onset_memory_frames=3, release_frames=3, persistence_only_attack=False,
    active_note_retrigger=False)


class OnsetConfirmedDecoder:
    """A learned onset licenses one start within the existing attack horizon.

    The current frame and preceding two frames are eligible. Tokens are ignored
    while active and consumed on start. Release remains three low frames. Events
    are emitted now, never backdated to the onset or a previous high frame.
    """
    def __init__(self):
        self.active = [False] * 88
        self.release = [0] * 88
        self.onset_frame = [None] * 88
        self.next_frame = 0

    def consume(self, notes, onsets, frame):
        if frame != self.next_frame or len(notes) != 88 or len(onsets) != 88:
            raise ValueError('Decoder frames must be complete and consecutive')
        if any(not math.isfinite(float(v)) or not 0 <= v <= 1 for v in (*notes, *onsets)):
            raise ValueError('Nonfinite or out-of-range activation')
        events = []
        for i, (note, onset) in enumerate(zip(notes, onsets)):
            above = note >= ONSET_DECODER['frame_threshold']
            self.release[i] = 0 if above else self.release[i] + 1
            if self.active[i]:
                if self.release[i] >= ONSET_DECODER['release_frames']:
                    self.active[i] = False
                    events.append(dict(kind='off', note=i+21, frame=frame))
                continue
            if onset >= ONSET_DECODER['onset_threshold']:
                self.onset_frame[i] = frame
            onset_at = self.onset_frame[i]
            if onset_at is not None and frame-onset_at >= ONSET_DECODER['onset_memory_frames']:
                self.onset_frame[i] = None
            if above and self.onset_frame[i] is not None:
                self.active[i] = True
                self.onset_frame[i] = None
                events.append(dict(kind='on', note=i+21, frame=frame))
        self.next_frame += 1
        return events


def decode_onset_cached(notes, onsets):
    if len(notes) != len(onsets):
        raise ValueError('Note and onset frame counts differ')
    decoder, events = OnsetConfirmedDecoder(), []
    for frame, (note, onset) in enumerate(zip(notes, onsets)):
        events.extend(decoder.consume(note, onset, frame))
    return events, [i+21 for i, active in enumerate(decoder.active) if active]


def clock_events(events, frames, timing):
    """Reuse original availability and FIFO completion, with no fitted offset."""
    clocks = {int(row[0]): row for row in timing}
    if len(clocks) != len(timing):
        raise ValueError('Duplicate saved source clocks')
    result = []
    for event in events:
        frame = frames[event['frame']]
        if int(frame[0]) != event['frame']:
            raise ValueError('Saved frame index differs')
        tick = clocks[int(frame[3])]
        result.append(dict(event, available_ns=int(tick[1]), emitted_ns=int(tick[3])))
    return result


def candidate_measurements(events, reference, current, labels, clock):
    """Annotation enters only after candidate event production is complete."""
    result = {}
    for name, key, expected in (
            ('saved_fifo', 'emitted_ns', reference['measurement']),
            ('zero_compute', 'available_ns', reference['zero_compute_measurement'])):
        spans, audit = emission_spans(events, key, clock['sample_count'])
        measurement = score(spans, labels, **clock)
        result[name] = dict(measurement=measurement, event_audit=audit,
            comparison_to_causal_reference=compare(expected, measurement),
            comparison_to_current=compare(current, measurement))
    return result


def onset_screen(datasets):
    reference = [row['candidate']['saved_fifo']['comparison_to_causal_reference']
                 for row in datasets.values()]
    current = [row['candidate']['saved_fifo']['comparison_to_current']
               for row in datasets.values()]
    ordinary = datasets['ordinary']['candidate']['saved_fifo']
    reference_gain = ordinary['comparison_to_causal_reference']['pitch_coverage_gain_pp']
    current_gain = ordinary['comparison_to_current']['pitch_coverage_gain_pp']
    return dict(
        incremental_screen_pass=reference_gain > 0 and all(
            row['no_pitch_safety_regression'] for row in reference),
        strict_replacement_screen_pass=current_gain >= 5 and all(
            row['no_pitch_safety_regression'] for row in current),
        ordinary_gain_over_reference_pp=reference_gain,
        ordinary_gain_over_current_pp=current_gain,
        promotion_accepted=False, installed_output_changed=False,
        interpretation='Cached delivery-clock simulation using original measured FIFO completion. '
            'Candidate service, native timing, physical latency and host delivery are not measured. '
            'Every label and false output remains in the replacement decision; aggregate tradeoffs '
            'do not override failed safety gates.')
