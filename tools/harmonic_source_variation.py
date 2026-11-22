"""Fixed training-only component envelopes; recorded execution belongs on GitHub."""
from copy import deepcopy
import gzip
import hashlib
import json
import math

import numpy as np

from tools.direct_spectrum_learning import SETTINGS, render_mixture


VARIATION = dict(name='component_shelf_v1', seed=20261124, identity_probability=0.5,
    gain_db_min=-6.0, gain_db_max=6.0, corner_hz=1000.0,
    filter='g*x + (1-g)*one_pole_lowpass(x); pole=exp(-2*pi*corner/sample_rate); steady initial state',
    placement='after crop, before component RMS normalization',
    cutoff_and_training_gates='original unaugmented training plan',
    held_out='unchanged, never augmented')


def augment_training_plan(plan):
    """Independent RNG; base source choices, crops, gains and labels remain intact."""
    if not plan or any(row['role'] != 'train' for row in plan):
        raise ValueError('Source variation is restricted to the training role')
    result = deepcopy(plan)
    rng = np.random.default_rng(VARIATION['seed'])
    for row in result:
        for component in row['components']:
            if 'shelf_gain_db' in component:
                raise ValueError('Training component was already augmented')
            identity = rng.random() < VARIATION['identity_probability']
            gain = float(rng.uniform(VARIATION['gain_db_min'], VARIATION['gain_db_max']))
            component['shelf_gain_db'] = 0.0 if identity else gain
    return result


def shelf_component(clip, component):
    """Smooth first-order shelf, steady initialization; exact bypass at zero gain."""
    gain_db = float(component['shelf_gain_db'])
    if not math.isfinite(gain_db) or not VARIATION['gain_db_min'] <= gain_db <= VARIATION['gain_db_max']:
        raise ValueError('Component shelf gain exceeds frozen bounds')
    if gain_db == 0.0:
        return clip
    from scipy.signal import lfilter
    pole = math.exp(-2*math.pi*VARIATION['corner_hz']/SETTINGS['sample_rate'])
    gain = 10**(gain_db/20)
    # g*x + (1-g)*L(x), with L's state equal to the first input sample.
    numerator = [gain+(1-gain)*(1-pole), -gain*pole]
    return lfilter(numerator, [1.0, -pole], clip,
                   zi=[pole*(1-gain)*float(clip[0])])[0]


def encoded_plan(plan):
    return json.dumps(plan, separators=(',', ':'), allow_nan=False).encode('utf-8')


def variation_examples(plan_path, waves, extractor, bulk):
    from tools.portable_basic_pitch_comparison import remote_only
    remote_only()  # Synthetic plan/filter utilities above do not open recorded inputs.
    plan = augment_training_plan(json.loads(gzip.decompress(plan_path.read_bytes())))
    encoded = encoded_plan(plan)
    path = bulk/'train-varied-mixture-plan.json.gz'
    path.write_bytes(gzip.compress(encoded, mtime=0))
    x = np.empty((len(plan), len(extractor.names)), dtype=np.float64)
    y = np.empty((len(plan), SETTINGS['note_high']-SETTINGS['note_low']+1), dtype=bool)
    for i, row in enumerate(plan):
        audio, target = render_mixture(row, waves, component_transform=shelf_component)
        x[i], y[i] = extractor(audio), target
    gains = [c['shelf_gain_db'] for row in plan for c in row['components']]
    return x, y, dict(parameters=VARIATION, plan_file=path.name,
        decoded_sha256=hashlib.sha256(encoded).hexdigest(), components=len(gains),
        identity_components=sum(g == 0.0 for g in gains),
        varied_components=sum(g != 0.0 for g in gains),
        gain_db_min=min(gains), gain_db_max=max(gains),
        fitting='varied training features only', cutoff_and_gates='original clean training plan',
        held_out_augmented=False)
