"""Candidate-local residual evidence; pure numerical helpers, no recorded I/O."""
import numpy as np
from scipy.linalg import solve_triangular
from scipy.optimize import nnls

from tools.spectral_ablation import PARAMETERS as BASE_PARAMETERS
from tools.spectral_dictionary import stratified_summary


PARAMETERS = dict(BASE_PARAMETERS, nuisance_ridge=0.0,
    support_half_width_fft_bins=2.0, support_overlap_weight='inverse_sqrt_pitch_count',
    candidate_ridge='ridge * number_of_same_pitch_atoms_after_fit_fold_unit_norm',
    support='min over folds of positive candidate-local residual reduction / null residual SSE',
    nuisance_fit='unregularized NNLS, all other pitches, global training-only whitening',
    inactive_group_rule='test local residual even when global joint coefficient is zero')


def harmonic_masks(frequency_hz, bin_width_hz):
    """Nominal A440 harmonic support, fixed without waveform, template or labels.

    Every retained bin within two FFT bins of an integer harmonic is included.
    Shared bins receive 1/sqrt(number of supported pitches), over MIDI 32..84.
    Alternating Hann bins remain correlated; this is not independent validation.
    """
    frequency = np.asarray(frequency_hz, dtype=np.float64)
    width = np.asarray(bin_width_hz, dtype=np.float64)
    if (frequency.ndim != 1 or width.shape != frequency.shape or not len(frequency)
            or not np.isfinite(frequency).all() or not np.isfinite(width).all()
            or (frequency <= 0).any() or (width <= 0).any()):
        raise ValueError('Invalid frequency geometry')
    masks = np.zeros((53, len(frequency)), dtype=bool)
    for i, note in enumerate(range(32, 85)):
        fundamental = 440.0*2**((note-69)/12)
        harmonic = np.maximum(1, np.rint(frequency/fundamental))
        centers = harmonic*fundamental
        masks[i] = ((np.abs(frequency-centers) <= PARAMETERS['support_half_width_fft_bins']*width)
                    & (centers <= PARAMETERS['frequency_max']))
    overlap = masks.sum(axis=0)
    return masks/np.sqrt(np.maximum(overlap, 1))[None, :]


class PitchLocalResidual:
    """Fit competing pitches globally; test a target addition in its own support.

    Null/nuisance fits have NO ridge: otherwise an exact parent leaves a positive
    shrinkage residual which a false upper pitch could 'explain'. QR reduction
    preserves ordinary NNLS, including rank-deficient dictionaries. The target
    group's local fit has unit atom norms measured on the fitting fold only;
    its ridge is multiplied by the atom count to preserve duplicate invariance.
    Neither a global positive coefficient nor a target annotation is required.
    """
    def __init__(self, templates, notes, folds, frequency_hz, bin_width_hz):
        templates = np.asarray(templates, dtype=np.float64)
        self.notes = np.asarray(notes, dtype=np.int64)
        self.folds = np.asarray(folds)
        self.frequency_hz = np.asarray(frequency_hz, dtype=np.float64)
        self.bin_width_hz = np.asarray(bin_width_hz, dtype=np.float64)
        if (templates.ndim != 2 or templates.shape[1] != len(self.notes)
                or not len(self.notes) or not np.isfinite(templates).all()
                or (templates < 0).any() or (self.notes < 32).any() or (self.notes > 84).any()
                or self.folds.shape != (templates.shape[0],)
                or self.frequency_hz.shape != self.folds.shape
                or self.bin_width_hz.shape != self.folds.shape
                or set(self.folds.tolist()) != {0, 1}):
            raise ValueError('Invalid local-residual dictionary or spectral folds')
        scale = np.mean(templates**2, axis=1)
        if scale.max() <= 0:
            raise ValueError('Empty dictionary')
        self.weights = 1/np.sqrt(scale+PARAMETERS['whitening_floor_fraction']*scale.max())
        weighted = templates*self.weights[:, None]
        norms = np.linalg.norm(weighted, axis=0)
        if (norms <= 0).any():
            raise ValueError('Empty dictionary atom')
        self.design = weighted/norms
        self.masks = harmonic_masks(self.frequency_hz, self.bin_width_hz)
        self.groups = {int(n): np.flatnonzero(self.notes == n) for n in np.unique(self.notes)}
        self.systems, self.local_systems = [], []
        self.nnls_calls = 0
        self.cutoff = None
        self.diagnostics = dict(global_inactive_pitch_frames=0,
            positive_local_support_from_global_inactive=0, null_fit_reuses=0,
            local_fits=0, numerical_floor_skips=0)
        for fold in (0, 1):
            fit, evaluation = self.folds == fold, self.folds == 1-fold
            systems, local = {}, {}
            for removed in (None, *self.groups):
                keep = np.arange(len(self.notes)) if removed is None else np.flatnonzero(self.notes != removed)
                q, r = np.linalg.qr(self.design[fit][:, keep], mode='reduced')
                systems[removed] = (keep, q, r)
            for note, columns in self.groups.items():
                mask = self.masks[note-32]
                fitting = self.design[fit][:, columns]*mask[fit, None]
                norms = np.linalg.norm(fitting, axis=0)
                if (norms <= 0).any():
                    # No evidence on this half; no fabricated target support.
                    local[note] = None
                    continue
                fitting = fitting/norms
                held = self.design[evaluation][:, columns]*mask[evaluation, None]/norms
                ridge = PARAMETERS['ridge']*len(columns)
                r = np.linalg.cholesky(fitting.T@fitting+ridge*np.eye(len(columns))).T
                local[note] = (fitting, held, r, norms)
            self.systems.append(systems)
            self.local_systems.append(local)

    def _nuisance(self, fold, weighted, removed=None):
        keep, q, r = self.systems[fold][removed]
        result = np.zeros(len(self.notes))
        if len(keep):
            result[keep] = nnls(r, q.T@weighted, maxiter=3*len(keep))[0]
            self.nnls_calls += 1
        return result

    def activity(self, features):
        features = np.asarray(features, dtype=np.float64)
        if (features.ndim != 2 or features.shape[1] != len(self.weights)
                or not np.isfinite(features).all() or (features < 0).any()):
            raise ValueError('Invalid power feature matrix')
        scores = np.zeros((len(features), 53))
        for i, weighted in enumerate(features*self.weights):
            pieces = [weighted[self.folds == f] for f in (0, 1)]
            if any(not np.any(x > 0) for x in pieces):
                continue
            full = [self._nuisance(f, pieces[f]) for f in (0, 1)]
            for note, columns in self.groups.items():
                inactive = any(not np.any(c[columns] > 0) for c in full)
                self.diagnostics['global_inactive_pitch_frames'] += int(inactive)
                support = []
                for fit in (0, 1):
                    local = self.local_systems[fit][note]
                    if local is None:
                        support.append(0.0)
                        continue
                    if np.any(full[fit][columns] > 0):
                        null = self._nuisance(fit, pieces[fit], note)
                    else:
                        # The full optimum is feasible after removing this zero
                        # group, so its fitted spectrum also solves the null.
                        null = full[fit]
                        self.diagnostics['null_fit_reuses'] += 1
                    residual = weighted-self.design@null
                    mask = self.masks[note-32]
                    evaluation = 1-fit
                    held_residual = (residual*mask)[self.folds == evaluation]
                    null_sse = float(held_residual@held_residual)
                    observed = (weighted*mask)[self.folds == evaluation]
                    if null_sse <= PARAMETERS['residual_floor_fraction']*float(observed@observed):
                        support.append(0.0)
                        self.diagnostics['numerical_floor_skips'] += 1
                        continue
                    fitting, held, r, _ = local
                    rhs = solve_triangular(r.T, fitting.T@(residual*mask)[self.folds == fit],
                                           lower=True, check_finite=False)
                    addition = nnls(r, rhs, maxiter=3*len(columns))[0]
                    self.nnls_calls += 1
                    self.diagnostics['local_fits'] += 1
                    error = held_residual-held@addition
                    support.append(float(np.clip((null_sse-float(error@error))/null_sse, 0, 1)))
                scores[i, note-32] = min(support)
                self.diagnostics['positive_local_support_from_global_inactive'] += int(inactive and scores[i, note-32] > 0)
        return scores

    def predict_proba(self, features):
        if self.cutoff is None:
            raise ValueError('Training cutoff not frozen')
        return (self.activity(features) >= self.cutoff).astype(float)

    def frozen_state(self):
        return dict(frequency_hz=self.frequency_hz, bin_width_hz=self.bin_width_hz,
                    harmonic_support_weights=self.masks)


def summarize(activity, truth, cutoff):
    result = stratified_summary(activity, truth, cutoff)
    result['activity_semantics'] = 'Minimum cross-fitted local residual reduction after unregularized nuisance fit; not probability or audibility.'
    return result
