"""Fixed teacher objective and window-screen arithmetic; no audio/model I/O."""
import numpy as np

from tools.basic_pitch_adaptation import SETTINGS


TEACHER = dict(note_label_weight=1.0, note_preservation_weight=1.0,
               onset_preservation_weight=1.0, probability_clip=1e-7,
               target_source='original weights before any optimizer step',
               target_gradient=False)
SCREEN = dict(test_recall_gain_pp=5.0, occurrence_loss_ms=25.0,
              occurrence_loss_fraction=0.05)


def objective_terms(truth, note, onset, teacher_note, teacher_onset, *,
                    clip=np.clip, log=np.log, mean=np.mean):
    """Shared NumPy/TF expression. The caller stops gradients into the teacher."""
    eps = TEACHER['probability_clip']
    note, onset, qn, qo = [clip(x, eps, 1-eps) for x in
                           (note, onset, teacher_note, teacher_onset)]
    bce = -mean(truth*log(note)+(1-truth)*log(1-note))
    def kl(q, p):
        return mean(q*(log(q)-log(p))+(1-q)*(log(1-q)-log(1-p)))
    note_kl, onset_kl = kl(qn, note), kl(qo, onset)
    return dict(note_bce=bce, note_teacher_kl=note_kl, onset_teacher_kl=onset_kl,
                total=TEACHER['note_label_weight']*bce
                + TEACHER['note_preservation_weight']*note_kl
                + TEACHER['onset_preservation_weight']*onset_kl)


def occurrence_budget(rows):
    """Apply BOTH frozen limits; nominal model-frame time, not delivered MIDI."""
    if not rows:
        raise ValueError('No source occurrences to check')
    frame_ms = 1000*SETTINGS['frame_hop']/SETTINGS['model_rate']
    failures, missed = [], 0
    for row in rows:
        new_miss = row['baseline_present'] > 0 and row['adapted_present'] == 0
        missed += int(new_miss)
        reasons = []
        for field in ('present', 'longest'):
            before, after = row['baseline_'+field], row['adapted_'+field]
            loss = max(0, before-after)
            if (loss*frame_ms > SCREEN['occurrence_loss_ms']
                    or loss > SCREEN['occurrence_loss_fraction']*before):
                reasons.append(field)
        if new_miss:
            reasons.append('newly_missing')
        if reasons:
            failures.append(dict(example=row['example'], source_key=row['source_key'],
                note=row['note'], reasons=reasons,
                baseline_present=row['baseline_present'], adapted_present=row['adapted_present'],
                baseline_longest=row['baseline_longest'], adapted_longest=row['adapted_longest']))
    return dict(pass_budget=not failures, occurrences=len(rows),
                newly_missing=missed, failure_count=len(failures), failures=failures,
                nominal_frame_ms=frame_ms, limits=SCREEN)


def assess(roles, integrity):
    complete = set(roles) == {'train', 'calibration', 'test'}
    integrity_pass = bool(integrity) and all(integrity.values())
    gates = {}
    for role, row in roles.items():
        before, after = row['original'], row['teacher']
        gates[role] = dict(
            no_extra_growth=after['overall']['extra_note_frames'] <= before['overall']['extra_note_frames'],
            no_silence_extra_growth=after['silence_extra_note_frames'] <= before['silence_extra_note_frames'],
            exact_frames_preserved=after['overall']['exact_frames'] >= before['overall']['exact_frames'],
            occurrence_budget=row['paired']['original']['budget']['pass_budget'])
    gain = None
    if 'test' in roles:
        row = roles['test']
        gain = row['teacher']['overall']['recall_percent'] - row['original']['overall']['recall_percent']
    advance = (complete and integrity_pass and gain is not None
               and gain >= SCREEN['test_recall_gain_pp']
               and all(all(g.values()) for g in gates.values()))
    return dict(complete=complete, integrity_pass=integrity_pass, role_gates=gates,
        test_recall_gain_pp=gain, minimum_gain_pp=SCREEN['test_recall_gain_pp'],
        window_advancement_pass=advance,
        strict_original_occurrence_preservation=complete and all(
            r['paired']['original']['no_occurrence_loss'] for r in roles.values()),
        absolute_representation_target_met=complete and all(r['representation_pass'] for r in roles.values()),
        verdict='ADVANCE_TO_CONTINUOUS_SCREEN' if advance else 'REJECTED_WINDOW_SCREEN',
        installed_output_changed=False, promotion_accepted=False,
        continuous_corpus_and_live_readiness='not measured')


def probability_drift(before, after, cutoff):
    if before.shape != after.shape or not before.size:
        raise ValueError('Probability comparison shape differs')
    absolute, maximum, crossings, divergence = 0.0, 0.0, 0, 0.0
    for left in range(0, len(before), 32):
        q, p = [np.asarray(x[left:left+32], dtype=np.float64) for x in (before, after)]
        if not all(np.isfinite(x).all() and ((0 <= x) & (x <= 1)).all() for x in (q, p)):
            raise ValueError('Invalid probability comparison')
        delta = np.abs(q-p)
        absolute += float(delta.sum())
        maximum = max(maximum, float(delta.max()))
        crossings += int(np.count_nonzero((q >= cutoff) != (p >= cutoff)))
        eps = TEACHER['probability_clip']
        q, p = np.clip(q, eps, 1-eps), np.clip(p, eps, 1-eps)
        divergence += float((q*np.log(q/p)+(1-q)*np.log((1-q)/(1-p))).sum())
    return dict(bins=int(before.size), mean_absolute=absolute/before.size,
                max_absolute=maximum, teacher_kl_mean=divergence/before.size,
                threshold=cutoff, threshold_crossings=crossings)
