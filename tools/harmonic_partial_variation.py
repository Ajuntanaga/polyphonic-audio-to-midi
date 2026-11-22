"""Fixed training-only partial envelopes; recorded execution belongs on GitHub."""
from copy import deepcopy
import gzip
import hashlib
import json

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture
from tools.harmonic_source_variation import encoded_plan


PARTIAL_VARIATION = dict(name='independent_partial_envelope_v1', seed=20261127,
    identity_probability=0.5, gain_db_min=-6.0, gain_db_max=6.0,
    partials=[1, 2, 3, 4, 5], unity_anchors=[0.0, 0.5, 6.0],
    interpolation='raised-cosine interpolation of dB between frequency anchors',
    filter='positive real rFFT multiplier on the complete 16384-sample crop; phase retained',
    anchor_pitch='original training annotation; no pitch estimator or held-out information',
    placement='after crop, before component RMS normalization',
    cutoff_and_training_gates='original unaugmented training plan',
    held_out='unchanged, never augmented')


def augment_training_plan(plan):
    """Independent RNG changes envelopes only, without editing the source plan."""
    if not plan or any(row['role'] != 'train' for row in plan):
        raise ValueError('Partial variation is restricted to the training role')
    result = deepcopy(plan)
    rng = np.random.default_rng(PARTIAL_VARIATION['seed'])
    for row in result:
        for component in row['components']:
            if 'partial_gain_db' in component:
                raise ValueError('Training component was already augmented')
            identity = rng.random() < PARTIAL_VARIATION['identity_probability']
            gains = rng.uniform(PARTIAL_VARIATION['gain_db_min'],
                                PARTIAL_VARIATION['gain_db_max'], 5)
            component['partial_gain_db'] = [0.0]*5 if identity else gains.tolist()
    return result


def frequency_gain(frequency, note, gains):
    """Unity below 0.5*f0 and above 6*f0; bounded positive partial multipliers."""
    frequency = np.asarray(frequency, dtype=np.float64)
    gains = np.asarray(gains, dtype=np.float64)
    if (gains.shape != (5,) or not np.isfinite(gains).all() or
            np.any(gains < PARTIAL_VARIATION['gain_db_min']) or
            np.any(gains > PARTIAL_VARIATION['gain_db_max'])):
        raise ValueError('Partial gains exceed frozen bounds')
    if (not isinstance(note, (int, np.integer)) or isinstance(note, bool) or
            not SETTINGS['note_low'] <= note <= SETTINGS['note_high']):
        raise ValueError('Invalid training annotation pitch')
    if (not np.isfinite(frequency).all() or np.any(frequency < 0) or
            np.any(frequency > SETTINGS['sample_rate']/2)):
        raise ValueError('Invalid FFT frequencies')
    fundamental = 440.0*2.0**((note-69)/12.0)
    anchors = fundamental*np.array([0., 0.5, 1., 2., 3., 4., 5., 6.])
    anchor_db = np.r_[0., 0., gains, 0.]
    interval = np.clip(np.searchsorted(anchors, frequency, side='right')-1, 0, 6)
    fraction = np.clip((frequency-anchors[interval])/
                       (anchors[interval+1]-anchors[interval]), 0., 1.)
    weight = 0.5*(1.-np.cos(np.pi*fraction))
    db = anchor_db[interval]+weight*(anchor_db[interval+1]-anchor_db[interval])
    return 10.0**(db/20.0)


def partial_component(clip, component):
    """Offline crop envelope; exact bypass. This is not a realtime audio filter."""
    values = np.asarray(clip, dtype=np.float64)
    if values.shape != (max(SETTINGS['windows']),) or not np.isfinite(values).all():
        raise ValueError('Expected a finite complete training crop')
    gains = np.asarray(component['partial_gain_db'], dtype=np.float64)
    frequencies = np.fft.rfftfreq(len(values), 1.0/SETTINGS['sample_rate'])
    multiplier = frequency_gain(frequencies, component['note'], gains)
    if np.all(gains == 0.0):
        return clip
    return np.fft.irfft(np.fft.rfft(values)*multiplier, n=len(values))


def partial_examples(plan_path, waves, extractor, bulk):
    from tools.portable_basic_pitch_comparison import remote_only
    remote_only()  # Synthetic utilities above never open recorded inputs.
    plan = augment_training_plan(json.loads(gzip.decompress(plan_path.read_bytes())))
    encoded = encoded_plan(plan)
    path = bulk/'train-partial-mixture-plan.json.gz'
    path.write_bytes(gzip.compress(encoded, mtime=0))
    x = np.empty((len(plan), len(extractor.names)), dtype=np.float64)
    y = np.empty((len(plan), SETTINGS['note_high']-SETTINGS['note_low']+1), dtype=bool)
    for i, row in enumerate(plan):
        audio, target = render_mixture(row, waves, component_transform=partial_component)
        x[i], y[i] = extractor(audio), target
    gains = np.array([c['partial_gain_db'] for row in plan for c in row['components']])
    identities = int(np.all(gains == 0.0, axis=1).sum())
    return x, y, dict(parameters=PARTIAL_VARIATION, plan_file=path.name,
        decoded_sha256=hashlib.sha256(encoded).hexdigest(), components=len(gains),
        identity_components=identities, varied_components=len(gains)-identities,
        gain_db_min=float(gains.min()), gain_db_max=float(gains.max()),
        fitting='partial-varied training features only',
        cutoff_and_gates='original clean training plan', held_out_augmented=False)
