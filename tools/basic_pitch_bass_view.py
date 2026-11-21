"""Two fixed causal waveform views; synthetic mechanics only, no recording I/O."""
import time

from tools.basic_pitch_streaming import (CausalResampler, FifoClock, ForwardDecoder,
                                         SETTINGS, ceil_div)

BASS_VIEW = dict(factor=2, source_phase_block=1280, up=147, down=1280,
    filter_taps=25601, filter_kaiser_beta=5.0, readout_frames=[168,169],
    first_window_end=836, map_semitones=-12, output_min=21, split_note=60,
    output_max=108, crop_tolerance=1e-5)


class BassResampler:
    """147/1280 FIR with complete phase blocks and no right extension."""
    def __init__(self):
        import numpy as np
        from scipy.signal import firwin, upfirdn
        self.np, self.upfirdn = np, upfirdn
        self.h = firwin(25601, 1/1280, window=('kaiser',5.0))*147
        self.history = np.zeros(1280,dtype=np.float32)
        self.ended = False

    def consume(self, block):
        np = self.np
        block = np.asarray(block,dtype=np.float32)
        if self.ended or block.ndim != 1 or not 0 < len(block) <= 1280 or not np.isfinite(block).all():
            raise ValueError('Invalid bass phase block or block after EOF')
        values = self.upfirdn(self.h,np.concatenate((self.history,block)),up=147,down=1280)
        result = values[147:147+ceil_div(len(block)*147,1280)].astype(np.float32)
        self.history = block.copy()
        self.ended = len(block) < 1280
        return result


class View:
    """One independent past-only buffer and decoder; backend returns two frames."""
    def __init__(self, backend, factor):
        import numpy as np
        if factor not in (1,2):
            raise ValueError('Only fixed factors1 and2 are supported')
        self.np, self.backend, self.factor = np,backend,factor
        self.resampler = CausalResampler() if factor == 1 else BassResampler()
        self.decoder = ForwardDecoder()
        self.phase_block = 640*factor
        self.pending = np.empty(0,dtype=np.float32)
        self.buffer = np.empty(0,dtype=np.float32)
        self.buffer_start = self.produced = self.calls = 0
        self.next_end = 1860 if factor == 1 else 836
        self.events, self.frames, self.notes, self.onsets = [],[],[],[]

    def consume(self, block, source_end, final, clock_ns=time.perf_counter_ns):
        np = self.np
        started = clock_ns()
        self.pending = np.concatenate((self.pending,block))
        if len(self.pending) > self.phase_block:
            raise ValueError('Incoming blocks crossed the resampler phase boundary')
        if len(self.pending) == self.phase_block or final:
            converted = self.resampler.consume(self.pending)
            self.pending = np.empty(0,dtype=np.float32)
            self.buffer = np.concatenate((self.buffer,converted))
            self.produced += len(converted)
        resampled = clock_ns()
        events, frames, activations = [],[],None
        model_ns = decode_ns = 0
        if self.produced >= self.next_end:
            start = self.next_end-43844
            data = self.buffer[max(0,start)-self.buffer_start:self.next_end-self.buffer_start]
            window = np.pad(data,(max(0,-start),0))
            if window.shape != (43844,):
                raise ValueError('Incomplete past-only model window')
            model_start = clock_ns()
            notes,onsets = self.backend.predict(window)
            model_ns = clock_ns()-model_start
            decode_start = clock_ns()
            if notes.shape != (2,88) or onsets.shape != (2,88):
                raise ValueError('Expected exactly two cropped output frames')
            activations = notes.copy(),onsets.copy()
            for j in range(2):
                frame = self.decoder.next_frame
                events.extend(self.decoder.consume(notes[j],onsets[j],frame))
                frames.append((frame,frame*256,self.next_end,source_end))
            decode_ns = clock_ns()-decode_start
            self.calls += 1
            self.next_end += 512
            keep_from = max(0,self.next_end-43844)
            self.buffer = self.buffer[keep_from-self.buffer_start:].copy()
            self.buffer_start = keep_from
            if self.produced >= self.next_end:
                raise ValueError('More than one model window arrived in a phase block')
        return dict(events=events,frames=frames,activations=activations,
            resample_ns=resampled-started,model_ns=model_ns,decode_ns=decode_ns)

    def retain(self, batch, arrival, finish):
        for event in batch['events']:
            event.update(available_ns=arrival,emitted_ns=finish)
        self.events.extend(batch['events'])
        self.frames.extend(batch['frames'])
        if batch['activations'] is not None:
            self.notes.append(batch['activations'][0])
            self.onsets.append(batch['activations'][1])

    def result(self):
        np = self.np
        return dict(events=self.events,frames=self.frames,
            notes=np.concatenate(self.notes) if self.notes else np.empty((0,88),dtype=np.float32),
            onsets=np.concatenate(self.onsets) if self.onsets else np.empty((0,88),dtype=np.float32),
            model_calls=self.calls,resampled_samples=self.produced,next_window_end=self.next_end,
            open_decoder_pitches=[i+21 for i,on in enumerate(self.decoder.active) if on])


def mapped_bass_event(event):
    note = event['note']-12
    return dict(event,note=note,view='bass2x') if 21 <= note < 60 else None


def stream_pair(blocks, source_samples, reference_backend, bass_backend,
                progress=None, clock_ns=time.perf_counter_ns):
    """Measured joint FIFO, original source clock, with no annotations exposed."""
    import numpy as np
    if type(source_samples) is not int or source_samples <= 0:
        raise ValueError('A positive complete source length is required')
    views = (View(reference_backend,1),View(bass_backend,2))
    fifo, timing, combined = FifoClock(),[],[]
    source_end = 0
    for block in blocks:
        started = clock_ns()
        block = np.asarray(block,dtype=np.float32)
        if block.ndim == 2:
            block = block.mean(axis=1,dtype=np.float32)
        if (block.ndim != 1 or not 0 < len(block) <= 640 or not np.isfinite(block).all()
                or source_end+len(block) > source_samples
                or (len(block) != 640 and source_end+len(block) != source_samples)):
            raise ValueError('Incomplete or invalid original source block')
        source_end += len(block)
        batches = [v.consume(block,source_end,source_end==source_samples,clock_ns) for v in views]
        selected = [dict(e,view='reference1x') for e in batches[0]['events'] if e['note'] >= 60]
        selected.extend(mapped for e in batches[1]['events'] if (mapped:=mapped_bass_event(e)) is not None)
        service = clock_ns()-started
        arrival,finish,queued = fifo.submit(source_end,service)
        # Evidence copies and serialization are outside simulated service.
        for view,batch in zip(views,batches):
            view.retain(batch,arrival,finish)
        for event in selected:
            event.update(available_ns=arrival,emitted_ns=finish)
        combined.extend(selected)
        timing.append((source_end,arrival,service,finish,queued,
            sum(b['resample_ns'] for b in batches),sum(b['model_ns'] for b in batches),
            sum(b['decode_ns'] for b in batches),int(any(b['activations'] is not None for b in batches))))
        if progress and batches[0]['activations'] is not None and views[0].calls%250==0:
            progress(views[0].calls,views[1].calls,source_end)
    if source_end != source_samples or any(len(v.pending) for v in views):
        raise ValueError('Source ended before the promised complete recording')
    result = dict(reference=views[0].result(),bass=views[1].result(),combined_events=combined,
                  timing=timing,source_samples=source_end,worker_finish_ns=fifo.finish_ns)
    result['combined_open_pitches'] = sorted(
        [n for n in result['reference']['open_decoder_pitches'] if n>=60]
        +[n-12 for n in result['bass']['open_decoder_pitches'] if 21<=n-12<60])
    return result
