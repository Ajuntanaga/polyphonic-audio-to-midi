"""Deterministic single-component release views; no files, audio I/O or models.

Original window plans are retained verbatim. An additional view ends one
component before the causal readout while preserving its original gain and
every other component. These are known artificial ends, not acoustic offsets.
"""
from copy import deepcopy

import numpy as np

from tools.basic_pitch_adaptation import SETTINGS, component_frames, render_window


RELEASE = dict(additional_train_examples=2048, seed=2026112205,
               readout_frame=164, end_offsets_frames=[0, 1, 2, 4, 8, 16],
               minimum_prefix_frames=8)


def release_plan(original, count=None, seed=None):
    """Choose distinct parent windows and one eligible component/end per view.

Selection depends only on frozen metadata. Short components that cannot span
an end in the fixed range remain in the original plan, but are not augmented.
The returned list contains only additional views; callers retain the originals.
"""
    count = RELEASE['additional_train_examples'] if count is None else count
    seed = RELEASE['seed'] if seed is None else seed
    if not isinstance(count, int) or count <= 0:
        raise ValueError('Positive release-view count required')
    ids = [row['example'] for row in original]
    if len(set(ids)) != len(ids) or ids != list(range(len(original))):
        raise ValueError('Original examples must have consecutive unique IDs')
    eligible = []
    for row in original:
        if row['role'] != 'train' or 'release' in row:
            raise ValueError('Only original training windows may be augmented')
        options = []
        for index, component in enumerate(row['components']):
            left = component['placement']
            old_end = left + component['length']
            for offset in RELEASE['end_offsets_frames']:
                end = (RELEASE['readout_frame'] - offset) * SETTINGS['frame_hop']
                if (end - left >= RELEASE['minimum_prefix_frames'] * SETTINGS['frame_hop']
                        and old_end - end >= SETTINGS['edge_taper_samples']):
                    options.append((index, end))
        if options:
            eligible.append((row, options))
    if len(eligible) < count:
        raise ValueError('Insufficient distinct eligible parent windows')
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(eligible))[:count]
    result = []
    for i, parent_index in enumerate(order):
        parent, options = eligible[int(parent_index)]
        index, end = options[int(rng.integers(len(options)))]
        row = deepcopy(parent)
        row.update(example=len(original) + i, parent_example=parent['example'],
                   view='single_component_release',
                   release=dict(component=index, end_sample=end))
        result.append(row)
    return result


def render_release_window(row, clips):
    """Keep the original crop RMS and prefix; end only the selected component."""
    if 'release' not in row:
        return render_window(row, clips)
    release = row['release']
    selected = release['component']
    if not isinstance(selected, int) or not 0 <= selected < len(row['components']):
        raise ValueError('Invalid release component')
    signal = np.zeros(SETTINGS['input_samples'], np.float64)
    labels = np.zeros((SETTINGS['frames'], SETTINGS['notes']), bool)
    levels = []
    for index, component in enumerate(row['components']):
        begin, length = component['crop_begin'], component['length']
        left = component['placement']
        clip = np.asarray(clips[component['source_key']][begin:begin+length], np.float64).copy()
        if clip.shape != (length,) or not np.isfinite(clip).all() or length <= 0:
            raise ValueError('Invalid original source crop')
        rms = float(np.sqrt(np.mean(clip * clip)))
        taper = min(SETTINGS['edge_taper_samples'], length // 2)
        ramp = np.linspace(0, 1, taper, endpoint=True)
        if taper:
            clip[:taper] *= ramp
            clip[-taper:] *= ramp[::-1]
        gain = SETTINGS['component_rms'] / max(rms, SETTINGS['normalization_floor'])
        gain *= 10 ** (component['gain_db'] / 20)
        effective = component
        provenance = dict(source_key=component['source_key'], crop_rms=rms,
                          normalization_gain=gain)
        if index == selected:
            kept = release['end_sample'] - left
            if (not isinstance(kept, int) or kept < RELEASE['minimum_prefix_frames'] * SETTINGS['frame_hop']
                    or length - kept < SETTINGS['edge_taper_samples']):
                raise ValueError('Invalid release boundary')
            clip[kept-taper:kept] *= ramp[::-1]
            clip[kept:] = 0
            effective = dict(component, length=kept)
            provenance.update(artificial_end_sample=release['end_sample'],
                              original_end_sample=left+length)
        signal[left:left+length] += clip * gain
        col = component['note'] - SETTINGS['first_note']
        if not 0 <= col < SETTINGS['notes']:
            raise ValueError('Source note outside model output')
        labels[component_frames(effective), col] = True
        levels.append(provenance)
    signal *= 10 ** (row['gain_db'] / 20)
    if not np.isfinite(signal).all():
        raise ValueError('Nonfinite rendered window')
    return signal.astype(np.float32), labels, levels
