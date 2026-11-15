"""Decode the optional, same-decision offline admission observer."""
import math


ADMISSION_FIELDS = tuple('''note tick enabled raw_before raw_after self_qualifies qualifies
ticks_before ticks_after required peer prior_active prior_suppressed
prior_assigned prior_midi group prior_attack prior_release
phase_cents phase_valid phase_settled direct local evidence
selector_pool selector_raw selector_best selector_options selector_positive
selector_used selector_voices selector_open selection
post_active post_suppressed post_assigned post_midi post_attack post_release'''.split())
REAL_FIELDS = {'phase_cents', 'selector_raw', 'selector_best'}
BOOL_FIELDS = set('''enabled raw_before raw_after self_qualifies qualifies prior_active
prior_suppressed phase_valid phase_settled direct local evidence selector_pool
post_active post_suppressed'''.split())
MASK_FIELDS = set('''prior_assigned prior_midi group selector_options selector_positive
selector_used post_assigned post_midi'''.split())


def admission_peers(cell, *, tick):
    # Old traces and skipped stages have no measurement, not zero-valued peers.
    if cell is None or cell == '':
        return None
    result = {}
    for packed in cell.split(','):
        values = packed.split(':')
        if len(values) != len(ADMISSION_FIELDS):
            raise ValueError('Invalid admission observer field count')
        row = {key: float(value) if key in REAL_FIELDS else int(value)
               for key, value in zip(ADMISSION_FIELDS, values)}
        note = row['note']
        if not 0 <= note < 128 or note in result or row['tick'] != tick:
            raise ValueError('Invalid admission observer clock or duplicate note')
        if any(not math.isfinite(row[key]) for key in REAL_FIELDS):
            raise ValueError('Non-finite admission observer value')
        if (any(row[key] not in (0, 1) for key in BOOL_FIELDS)
                or any(not 0 <= row[key] <= 255 for key in MASK_FIELDS)
                or any(row[key] < 0 for key in ADMISSION_FIELDS if key not in REAL_FIELDS)
                or row['peer'] > 128
                or row['selection'] > 5 or row['selector_voices'] > 8
                or row['selector_open'] > 8):
            raise ValueError('Invalid admission observer state')
        result[note] = row
    return result
