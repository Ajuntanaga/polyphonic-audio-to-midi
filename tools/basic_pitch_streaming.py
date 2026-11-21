"""Fixed causal streaming prototype. No model loading or recording I/O here.

Synthetic tests can exercise these mechanics locally. The recorded-audio driver
is remote-only. Frame positions are nominal model indices, never event clocks.
"""
import math
import time


SETTINGS = dict(source_rate=96000, source_block=640, model_rate=22050,
    up=147, down=640, filter_taps=12801, filter_kaiser_beta=5.0,
    model_samples=43844, model_frames=172, model_pitches=88, first_midi_note=21,
    frame_hop=256, window_hop=512, readout_frames=[164, 165],
    onset_threshold=0.5, frame_threshold=0.3, attack_frames=3, release_frames=3,
    intra_op_threads=2, inter_op_threads=1)
FIRST_END = SETTINGS['model_samples'] - SETTINGS['readout_frames'][0] * SETTINGS['frame_hop']
NS = 1_000_000_000


def ceil_div(a, b):
    return (a + b - 1) // b


class ForwardDecoder:
    """One active state per pitch. No backdating, future scan or retrigger."""
    def __init__(self):
        self.active = [False] * 88
        self.attack = [0] * 88
        self.release = [0] * 88
        self.next_frame = 0

    def consume(self, notes, onsets, frame):
        if frame != self.next_frame or len(notes) != 88 or len(onsets) != 88:
            raise ValueError('Decoder frames must be complete and consecutive')
        if any(not math.isfinite(float(v)) or not 0 <= v <= 1 for v in (*notes, *onsets)):
            raise ValueError('Nonfinite or out-of-range activation')
        events = []
        for i, (note, onset) in enumerate(zip(notes, onsets)):
            above = note >= SETTINGS['frame_threshold']
            self.attack[i] = self.attack[i] + 1 if above else 0
            self.release[i] = 0 if above else self.release[i] + 1
            if not self.active[i] and above and (onset >= SETTINGS['onset_threshold']
                    or self.attack[i] >= SETTINGS['attack_frames']):
                self.active[i] = True
                events.append(dict(kind='on', note=i+21, frame=frame))
            elif self.active[i] and self.release[i] >= SETTINGS['release_frames']:
                self.active[i] = False
                events.append(dict(kind='off', note=i+21, frame=frame))
        self.next_frame += 1
        return events


class CausalResampler:
    """Blockwise causal upfirdn; no delay compensation or future extension.

    A640-source-sample block spans exactly147 output samples. Keeping a whole
    prior block gives a phase-aligned history longer than the FIR support.
    A partial final block emits only m*down < input_count*up positions.
    """
    def __init__(self):
        import numpy as np
        from scipy.signal import firwin, upfirdn
        self.np, self.upfirdn = np, upfirdn
        self.h = firwin(SETTINGS['filter_taps'], 1/640,
                       window=('kaiser', SETTINGS['filter_kaiser_beta'])) * 147
        self.history = np.zeros(640, dtype=np.float32)
        self.ended = False

    def consume(self, block):
        np = self.np
        block = np.asarray(block, dtype=np.float32)
        if self.ended or block.ndim != 1 or not 0 < len(block) <= 640 or not np.isfinite(block).all():
            raise ValueError('Invalid source block or block after partial EOF')
        joined = np.concatenate((self.history, block))
        values = self.upfirdn(self.h, joined, up=147, down=640)
        count = ceil_div(len(block)*147, 640)
        result = values[147:147+count].astype(np.float32)
        self.history = block.copy()
        self.ended = len(block) < 640
        return result


class FifoClock:
    def __init__(self):
        self.finish_ns = 0

    def submit(self, source_end, service_ns):
        if source_end < 0 or service_ns < 0:
            raise ValueError('Invalid service clock')
        arrival = ceil_div(source_end*NS, SETTINGS['source_rate'])
        start = max(arrival, self.finish_ns)
        self.finish_ns = start + service_ns
        return arrival, self.finish_ns, start-arrival


def stream_blocks(blocks, backend, progress=None, clock_ns=time.perf_counter_ns,
                  additional_readout_start=None):
    """Single FIFO simulation, using measured compute on each incoming block.

    Iterating blocks (file read) and retaining evidence are outside service time.
    Resampling, window copies, model, validation and decoder are inside it.
    No annotation interface is exposed to this function or the backend.
    An optional earlier, even-aligned readout shares inference and service, but
    has its own decoder. Negative nominal frames at startup are not consumed.
    """
    import numpy as np
    if additional_readout_start is not None and (
            type(additional_readout_start) is not int
            or not 0 <= additional_readout_start < 164
            or additional_readout_start % 2):
        raise ValueError('Additional readout must be an earlier even frame')
    resampler, decoder, fifo = CausalResampler(), ForwardDecoder(), FifoClock()
    extra_decoder = ForwardDecoder() if additional_readout_start is not None else None
    extra_events, extra_frames, extra_notes, extra_onsets = [], [], [], []
    buffer = np.empty(0, dtype=np.float32)
    buffer_start = produced = source_end = calls = 0
    next_end = FIRST_END
    events, timing, frames, note_arrays, onset_arrays = [], [], [], [], []
    for block in blocks:
        started = clock_ns()
        block = np.asarray(block, dtype=np.float32)
        if block.ndim == 2:
            block = block.mean(axis=1, dtype=np.float32)
        source_end += len(block)
        converted = resampler.consume(block)
        buffer = np.concatenate((buffer, converted))
        produced += len(converted)
        resampled_at = clock_ns()
        batch_events, batch_frames, readout = [], [], None
        extra_batch_events, extra_batch_frames, extra_readout = [], [], None
        model_ns = decoder_ns = 0
        if produced >= next_end:
            window_start = next_end-SETTINGS['model_samples']
            left = max(0, window_start)
            data = buffer[left-buffer_start:next_end-buffer_start]
            window = np.pad(data, (max(0, -window_start), 0))
            if window.shape != (43844,):
                raise ValueError('Incomplete model input window')
            model_started = clock_ns()
            notes, onsets = backend.predict(window)
            model_ns = clock_ns()-model_started
            if notes.shape != (172, 88) or onsets.shape != (172, 88):
                raise ValueError('Unexpected model output shape')
            decoded_at = clock_ns()
            readout = notes[164:166].copy(), onsets[164:166].copy()
            for j in range(2):
                frame = decoder.next_frame
                batch_events.extend(decoder.consume(readout[0][j], readout[1][j], frame))
                batch_frames.append((frame, frame*256, next_end, source_end))
            if extra_decoder is not None:
                first_frame = calls*2 + additional_readout_start - 164
                if first_frame >= 0:
                    start = additional_readout_start
                    extra_readout = notes[start:start+2].copy(), onsets[start:start+2].copy()
                    for j in range(2):
                        frame = first_frame+j
                        extra_batch_events.extend(extra_decoder.consume(
                            extra_readout[0][j], extra_readout[1][j], frame))
                        extra_batch_frames.append((frame, frame*256, next_end, source_end))
            decoder_ns = clock_ns()-decoded_at
            calls += 1
            next_end += SETTINGS['window_hop']
            keep_from = max(0, next_end-SETTINGS['model_samples'])
            buffer = buffer[keep_from-buffer_start:].copy()
            buffer_start = keep_from
        service = clock_ns()-started
        arrival, finish, queued = fifo.submit(source_end, service)
        # Evidence logging is not part of the simulated streaming worker.
        for event in batch_events:
            event.update(available_ns=arrival, emitted_ns=finish)
        for event in extra_batch_events:
            event.update(available_ns=arrival, emitted_ns=finish)
        events.extend(batch_events)
        extra_events.extend(extra_batch_events)
        extra_frames.extend(extra_batch_frames)
        timing.append((source_end, arrival, service, finish, queued,
                       resampled_at-started, model_ns, decoder_ns, int(readout is not None)))
        frames.extend(batch_frames)
        if readout is not None:
            note_arrays.append(readout[0])
            onset_arrays.append(readout[1])
        if extra_readout is not None:
            extra_notes.append(extra_readout[0])
            extra_onsets.append(extra_readout[1])
        if progress and readout is not None and calls % 250 == 0:
            progress(calls, source_end)
    result = dict(events=events, timing=timing, frames=frames,
        notes=np.concatenate(note_arrays) if note_arrays else np.empty((0,88), dtype=np.float32),
        onsets=np.concatenate(onset_arrays) if onset_arrays else np.empty((0,88), dtype=np.float32),
        source_samples=source_end, resampled_samples=produced, model_calls=calls,
        open_decoder_pitches=[i+21 for i, active in enumerate(decoder.active) if active],
        worker_finish_ns=fifo.finish_ns, next_window_end=next_end)
    if extra_decoder is not None:
        result['additional_readout'] = dict(readout_start=additional_readout_start,
            events=extra_events, frames=extra_frames,
            notes=np.concatenate(extra_notes) if extra_notes else np.empty((0,88), dtype=np.float32),
            onsets=np.concatenate(extra_onsets) if extra_onsets else np.empty((0,88), dtype=np.float32),
            open_decoder_pitches=[i+21 for i, active in enumerate(extra_decoder.active) if active])
    return result


def emission_spans(events, clock, sample_count):
    """Score delivered occupancy, clipping only to the recording boundary."""
    if clock not in ('available_ns', 'emitted_ns'):
        raise ValueError('Only causal event clocks may be scored')
    active, spans = {}, []
    previous = -1
    after_eof = 0
    for event in events:
        when = event[clock]
        if when < previous:
            raise ValueError('Nonmonotonic event delivery')
        previous = when
        sample = ceil_div(when*SETTINGS['source_rate'], NS)
        after_eof += sample >= sample_count
        note = event['note']
        if event['kind'] == 'on':
            if note in active:
                raise ValueError('Duplicate live note')
            active[note] = sample
        elif event['kind'] == 'off':
            if note not in active:
                raise ValueError('Release without live note')
            start = active.pop(note)
            end = min(sample, sample_count)
            if start < end:
                spans.append((start, end, note))
        else:
            raise ValueError('Invalid event kind')
    for note, start in active.items():
        if start < sample_count:
            spans.append((start, sample_count, note))
    eof_active = set()
    for event in events:
        if ceil_div(event[clock]*SETTINGS['source_rate'], NS) >= sample_count:
            break
        if event['kind'] == 'on':
            eof_active.add(event['note'])
        else:
            eof_active.remove(event['note'])
    return spans, dict(event_count=len(events), events_at_or_after_eof=after_eof,
        pitches_active_at_recording_end=sorted(eof_active), pairing_valid=True,
        eof_policy='Open occupancy clipped at EOF for scoring; explicit worker cleanup is separate.')


def timing_summary(rows):
    def distribution(values):
        ordered = sorted(values)
        return dict(count=len(values), total=sum(values),
            p50=ordered[math.ceil(.5*len(values))-1] if values else None,
            p99=ordered[math.ceil(.99*len(values))-1] if values else None,
            maximum=max(values) if values else None)
    model_rows = [r for r in rows if r[8]]
    return dict(all_block_service_ns=distribution([r[2] for r in rows]),
        inference_block_service_ns=distribution([r[2] for r in model_rows]),
        model_call_ns=distribution([r[6] for r in model_rows]),
        queued_before_service_ns=distribution([r[4] for r in rows]),
        delivery_delay_from_block_arrival_ns=distribution([r[3]-r[1] for r in rows]),
        inference_block_arrival_intervals_ns=distribution(
            [b[1]-a[1] for a,b in zip(model_rows, model_rows[1:])]))
