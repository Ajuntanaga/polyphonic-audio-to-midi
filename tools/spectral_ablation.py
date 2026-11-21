"""Cross-fitted pitch-group ablation; pure helpers, no recorded-audio I/O."""
import numpy as np
from scipy.linalg import solve_triangular
from scipy.optimize import nnls

from tools.direct_spectrum_learning import SETTINGS, representation_gate
from tools.spectral_dictionary import stratified_summary


PARAMETERS = dict(frequency_min=20.0, frequency_max=12000.0,
    power_windows=[4096, 8192], power_hop_fraction=0.5,
    template_windows=9, whitening_floor_fraction=0.01, ridge=0.001,
    residual_floor_fraction=1e-12, training_precision_percent=99.0,
    mixture_counts=dict(train=4096, calibration=1024, test=1024),
    crossfit='alternating retained bins within each window; swap fit and evaluation halves',
    support='min over folds of max(0, (ablated_SSE-full_SSE)/ablated_SSE)',
    harmonic_intervals=[12, 19, 24, 28, 31, 36])


class AveragedPower:
    """Average overlapping Hann periodograms within the same trailing 16384 samples.

    Spectral folds are a prediction check, not independent observations; source
    passes remain the generalization split. No phase-additivity claim is made.
    """
    def __init__(self):
        self.windows = {n: np.hanning(n) for n in PARAMETERS['power_windows']}
        self.bins, self.starts, self.names, folds = {}, {}, [], []
        frequencies, bin_widths = [], []
        context = max(SETTINGS['windows'])
        for n in self.windows:
            frequency = np.fft.rfftfreq(n, 1/SETTINGS['sample_rate'])
            self.bins[n] = np.flatnonzero((frequency >= PARAMETERS['frequency_min']) &
                                        (frequency <= PARAMETERS['frequency_max']))
            self.starts[n] = range(0, context-n+1, int(n*PARAMETERS['power_hop_fraction']))
            self.names.extend(f'w{n}:bin{k}:mean_power' for k in self.bins[n])
            folds.extend((np.arange(len(self.bins[n])) % 2).tolist())
            frequencies.extend(frequency[self.bins[n]].tolist())
            bin_widths.extend([SETTINGS['sample_rate']/n]*len(self.bins[n]))
        self.folds = np.asarray(folds, dtype=np.int8)
        self.frequency_hz = np.asarray(frequencies)
        self.bin_width_hz = np.asarray(bin_widths)

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        result = []
        for n, window in self.windows.items():
            power = [np.abs(np.fft.rfft(past[start:start+n]*window)/window.sum())**2
                     for start in self.starts[n]]
            result.append(np.mean(power, axis=0)[self.bins[n]])
        return np.concatenate(result)


class CrossfitAblation:
    """Fit nonnegative coefficients on one spectral half, test removals on the other.

    All atoms for one MIDI pitch are removed together, then ALL remaining
    competitors are refitted. The score is unique fractional residual reduction,
    not coefficient/strongest-pitch. Ridge makes the fitted solution unique.
    Removing an exactly inactive group leaves that solution unchanged, so such
    a group has zero support and needs no redundant refit.
    """
    def __init__(self, templates, notes, folds):
        templates = np.asarray(templates, dtype=np.float64)
        self.notes = np.asarray(notes, dtype=np.int64)
        self.folds = np.asarray(folds)
        if (templates.ndim != 2 or templates.shape[1] != len(self.notes)
                or len(self.notes) == 0 or not np.isfinite(templates).all()
                or (templates < 0).any() or (self.notes < 32).any() or (self.notes > 84).any()
                or self.folds.shape != (templates.shape[0],)
                or set(self.folds.tolist()) != {0, 1}):
            raise ValueError('Invalid dictionary or spectral folds')
        scale = np.mean(templates**2, axis=1)
        if scale.max() <= 0:
            raise ValueError('Empty dictionary')
        self.weights = 1/np.sqrt(scale+PARAMETERS['whitening_floor_fraction']*scale.max())
        weighted = templates*self.weights[:, None]
        norms = np.linalg.norm(weighted, axis=0)
        if (norms <= 0).any():
            raise ValueError('Empty dictionary atom')
        self.design = weighted/norms
        self.groups = {int(note): np.flatnonzero(self.notes == note) for note in np.unique(self.notes)}
        self.systems, self.grams = [], []
        self.nnls_calls = 0
        self.cutoff = None
        for fold in (0, 1):
            design = self.design[self.folds == fold]
            gram = design.T @ design
            self.grams.append(gram)
            systems = {}
            for removed in (None, *self.groups):
                keep = np.flatnonzero(self.notes != removed) if removed is not None else np.arange(len(notes))
                # R.T @ R is D.T @ D + ridge I. NNLS uses R with the
                # corresponding triangularly solved RHS, never the Gram as D.
                regularized = gram[np.ix_(keep, keep)]+PARAMETERS['ridge']*np.eye(len(keep))
                systems[removed] = (keep, np.linalg.cholesky(regularized).T)
            self.systems.append(systems)

    def _solve(self, fold, cross, removed=None):
        keep, r = self.systems[fold][removed]
        result = np.zeros(len(self.notes), dtype=np.float64)
        if len(keep):
            rhs = solve_triangular(r.T, cross[keep], lower=True, check_finite=False)
            result[keep] = nnls(r, rhs, maxiter=3*len(keep))[0]
            self.nnls_calls += 1
        return result

    def activity(self, features):
        features = np.asarray(features, dtype=np.float64)
        if (features.ndim != 2 or features.shape[1] != len(self.weights)
                or not np.isfinite(features).all() or (features < 0).any()):
            raise ValueError('Invalid power feature matrix')
        weighted = features*self.weights
        cross = [weighted[:, self.folds == f] @ self.design[self.folds == f] for f in (0, 1)]
        energy = [np.sum(weighted[:, self.folds == f]**2, axis=1) for f in (0, 1)]
        scores = np.zeros((len(features), 53))
        for i in range(len(features)):
            if energy[0][i] == 0 or energy[1][i] == 0:
                continue
            full = [self._solve(f, cross[f][i]) for f in (0, 1)]
            # Compute held-coordinate residuals directly, avoiding catastrophic
            # cancellation in y'y - 2a'D'y + a'D'Da for nearly perfect fits.
            residual = [weighted[i, self.folds == 1-f] -
                        self.design[self.folds == 1-f] @ full[f] for f in (0, 1)]
            full_sse = [float(r @ r) for r in residual]
            for note, columns in self.groups.items():
                if any(not np.any(c[columns] > 0) for c in full):
                    continue
                support = []
                for fit in (0, 1):
                    evaluation = 1-fit
                    ablated = self._solve(fit, cross[fit][i], note)
                    error = (weighted[i, self.folds == evaluation] -
                             self.design[self.folds == evaluation] @ ablated)
                    ablated_sse = float(error @ error)
                    if ablated_sse <= PARAMETERS['residual_floor_fraction']*energy[evaluation][i]:
                        support.append(0.0)
                    else:
                        support.append(float(np.clip((ablated_sse-full_sse[fit])/ablated_sse, 0, 1)))
                scores[i, note-32] = min(support)
        return scores

    def predict_proba(self, features):
        if self.cutoff is None:
            raise ValueError('Training cutoff not frozen')
        return (self.activity(features) >= self.cutoff).astype(float)


def summarize(activity, truth, cutoff):
    result = stratified_summary(activity, truth, cutoff)
    result['activity_semantics'] = 'Minimum cross-fitted pitch-group residual reduction; not probability or audibility.'
    return result


def complete_chord_gate(summary):
    """Existing aggregate gates plus EACH of 3/4/5 distinct pitches and silence."""
    by_count = summary['by_distinct_pitch_count']
    return (representation_gate(summary) and summary['silence_false_predictions'] == 0
        and all(str(n) in by_count and by_count[str(n)]['examples'] > 0
                and by_count[str(n)]['exact_set_percent'] >= 70 for n in (3, 4, 5)))
