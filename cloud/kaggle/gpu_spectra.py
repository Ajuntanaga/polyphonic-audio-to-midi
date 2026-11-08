"""Bounded GPU spectral research probe. Not a MIDI or live-timing acceptance test.

Runs offline with generated audio by default. Set M3_WAV to an explicitly
attached private mono PCM16/float32 WAV to analyze recovered audio instead.
No credentials, network, downloads, or training are needed inside the kernel.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import time
import wave

import numpy as np
import torch


def read_wave(path):
    try:
        with wave.open(str(path), 'rb') as stream:
            if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
                raise ValueError('Expected mono PCM16 or float32 WAV')
            rate = stream.getframerate()
            # A bounded six-second prefix, not whole-corpus acceptance.
            data = stream.readframes(min(stream.getnframes(), rate * 6))
            return rate, np.frombuffer(data, '<i2').astype(np.float32) / np.float32(32768)
    except wave.Error:
        with path.open('rb') as stream:
            header = stream.read(12)
            if header[:4] != b'RIFF' or header[8:] != b'WAVE':
                raise ValueError('Expected RIFF WAVE')
            fmt = None
            while chunk := stream.read(8):
                if len(chunk) != 8:
                    raise ValueError('Truncated RIFF chunk')
                name, size = struct.unpack('<4sI', chunk)
                if name == b'fmt ':
                    if size < 16:
                        raise ValueError('Short WAV format')
                    fmt = struct.unpack('<HHIIHH', stream.read(16))
                    stream.seek(size - 16 + size % 2, 1)
                elif name == b'data':
                    if not fmt or fmt[0] != 3 or fmt[1] != 1 or fmt[5] != 32 or fmt[2] <= 0:
                        raise ValueError('Expected mono float32 WAV')
                    count = min(size, fmt[2] * 6 * 4)
                    data = stream.read(count)
                    if len(data) != count or count % 4:
                        raise ValueError('Truncated float32 WAV')
                    return fmt[2], np.frombuffer(data, '<f4').copy()
                else:
                    stream.seek(size + size % 2, 1)
        raise ValueError('Missing WAV data')


def main():
    output = Path('/kaggle/working') if Path('/kaggle/working').is_dir() else Path('build/gpu-probe')
    output.mkdir(parents=True, exist_ok=True)
    if not torch.cuda.is_available():
        raise RuntimeError('GPU unavailable: enable Kaggle GPU access; CPU fallback is not a GPU verification')
    rate = 96000
    source = os.environ.get('M3_WAV')
    if source:
        rate, samples = read_wave(Path(source))
        provenance = dict(kind='private-input-prefix', filename=Path(source).name)
    else:
        clock = np.arange(rate * 3, dtype=np.float64) / rate
        # Known harmonic mixture with a nearby pitch; this is not a recovered recording.
        samples = np.zeros(clock.size, dtype=np.float64)
        for frequency, gain in ((65.40639132514966, .2), (69.29565774421802, .1)):
            for harmonic in range(1, 7):
                samples += gain / harmonic * np.sin(2 * np.pi * frequency * harmonic * clock)
        samples = samples.astype(np.float32)
        provenance = dict(kind='generated-harmonic-mixture', filename=None)
    if not np.isfinite(samples).all() or len(samples) < 16384:
        raise ValueError('Need finite audio with at least one complete analysis window')
    window, fft, hop, batch = 16384, 65536, 1024, 16
    taper = np.hanning(window)
    normalizer = 2.0 / float(taper.sum())
    stops = list(range(window, len(samples) + 1, hop))
    frequencies = np.fft.rfftfreq(fft, 1.0 / rate)
    max_error, cpu_seconds, gpu_seconds = 0.0, 0.0, 0.0
    peaks = []
    # Warm up once; timings below exclude initialization and host/device transfer.
    torch.fft.rfft(torch.zeros((batch, window), dtype=torch.float64, device='cuda'), n=fft)
    torch.cuda.synchronize()
    for start in range(0, len(stops), batch):
        positions = stops[start:start + batch]
        frames = np.stack([samples[stop-window:stop] * taper for stop in positions])
        began = time.perf_counter()
        reference = np.abs(np.fft.rfft(frames, n=fft) * normalizer) ** 2
        cpu_seconds += time.perf_counter() - began
        tensor = torch.as_tensor(frames, dtype=torch.float64, device='cuda')
        torch.cuda.synchronize()
        began = time.perf_counter()
        result = torch.abs(torch.fft.rfft(tensor, n=fft) * normalizer) ** 2
        torch.cuda.synchronize()
        gpu_seconds += time.perf_counter() - began
        actual = result.cpu().numpy()
        max_error = max(max_error, float(np.max(np.abs(actual - reference))))
        if not np.allclose(actual, reference, rtol=1e-9, atol=1e-12):
            raise RuntimeError('CPU/GPU spectral tolerance failed; do not substitute this calculation')
        for stop, power in zip(positions, actual):
            index = int(np.argmax(power))
            peaks.append(dict(end_sample_exclusive=stop, strongest_bin_hz=float(frequencies[index]),
                              power=float(power[index])))
    report = dict(schema=1, passed=True, provenance=provenance, sample_rate=rate,
        sample_count=len(samples), analyzed_sample_sha256=hashlib.sha256(samples.astype('<f4').tobytes()).hexdigest(),
        gpu=torch.cuda.get_device_name(0), torch=torch.__version__, numpy=np.__version__, python=platform.python_version(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() if '__file__' in globals() else None,
        geometry=dict(window=window, fft=fft, hop=hop, batch=batch, symmetric_hann=True),
        frames=len(stops), max_absolute_power_error=max_error, rtol=1e-9, atol=1e-12,
        cpu_fft_power_seconds=cpu_seconds, gpu_fft_power_seconds=gpu_seconds,
        timing_scope='FFT and power only; excludes input transfer, initialization, native detector and MIDI',
        native_cue_parity='not measured', labeled_frame_matches='not measured', live_readiness='not measured')
    (output / 'gpu-report.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'spectral-peaks.json').write_text(json.dumps(peaks) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
