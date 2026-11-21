"""Fixed dense-spectrum dictionary experiment; synthetic helpers, no audio I/O."""
import numpy as np
from scipy.optimize import nnls

from tools.direct_spectrum_learning import SETTINGS, classification_summary


PARAMETERS = dict(frequency_min=20.0, frequency_max=12000.0,
    template_windows=9, whitening_floor_fraction=0.01, ridge=0.001,
    training_precision_percent=99.0, harmonic_intervals=[12, 19, 24, 28, 31, 36])


class DenseMagnitude:
    """Every retained FFT bin, linear magnitude, from trailing Hann windows."""
    def __init__(self):
        self.windows = {n: np.hanning(n) for n in SETTINGS['windows']}
        self.bins = {}
        self.names = []
        for n in self.windows:
            frequency = np.fft.rfftfreq(n, 1/SETTINGS['sample_rate'])
            self.bins[n] = np.flatnonzero((frequency >= PARAMETERS['frequency_min']) &
                                        (frequency <= PARAMETERS['frequency_max']))
            self.names.extend(f'w{n}:bin{k}:magnitude' for k in self.bins[n])

    def __call__(self, past):
        past = np.asarray(past, dtype=np.float64)
        if past.shape != (max(SETTINGS['windows']),) or not np.isfinite(past).all():
            raise ValueError('Expected one finite trailing context')
        return np.concatenate([np.abs(np.fft.rfft(past[-n:]*window))[self.bins[n]]/window.sum()
                               for n, window in self.windows.items()])


def template_plan(takes):
    """Only pass-1 takes; all nine crops lie entirely inside each source label."""
    result = []
    seen = set()
    n = max(SETTINGS['windows'])
    for take in takes:
        if take['role'] != 'train':
            continue
        cell = (take['midi_note'], take['string_mask'])
        if cell in seen or take['end_sample']-take['start_sample'] < n:
            raise ValueError('Duplicate cell or short training take')
        seen.add(cell)
        starts = np.rint(np.linspace(take['start_sample'], take['end_sample']-n,
                                    PARAMETERS['template_windows'])).astype(int)
        result.append(dict(source_key=take['key'], stem=take['stem'], note=cell[0],
            string_mask=cell[1], crops=[(int(left), int(left+n)) for left in starts]))
    if not result:
        raise ValueError('No training templates')
    return result


def build_templates(plan, waves, extractor):
    columns = []
    for row in plan:
        features = []
        for left, right in row['crops']:
            signal = waves[row['stem']][left:right]
            if signal.shape != (max(SETTINGS['windows']),) or not np.isfinite(signal).all():
                raise ValueError('Invalid template crop')
            rms = float(np.sqrt(np.mean(signal*signal)))
            if rms <= SETTINGS['normalization_floor']:
                raise ValueError('Silent training template; no take may be excluded')
            features.append(extractor(signal*(SETTINGS['component_rms']/rms)))
        columns.append(np.median(features, axis=0))
    return np.asarray(columns).T


class DictionaryModel:
    """Ridge NNLS in a QR-reduced system, then sum activity by MIDI pitch.

    QR preserves the minimizer of ||D a-y||^2 + ridge*||a||^2, a>=0.
    It is not NNLS on a Gram matrix incorrectly treated as the design matrix.
    Grouped coefficients are divided by the largest pitch activity per frame.
    """
    def __init__(self, templates, notes):
        templates = np.asarray(templates, dtype=np.float64)
        self.notes = np.asarray(notes, dtype=np.int64)
        if (templates.ndim != 2 or templates.shape[1] != len(self.notes)
                or not len(self.notes) or not np.isfinite(templates).all()
                or (templates < 0).any() or (self.notes < 32).any() or (self.notes > 84).any()):
            raise ValueError('Invalid dictionary')
        power = np.mean(templates**2, axis=1)
        if power.max() <= 0:
            raise ValueError('Empty dictionary')
        self.weights = 1/np.sqrt(power+PARAMETERS['whitening_floor_fraction']*power.max())
        weighted = templates*self.weights[:, None]
        norms = np.linalg.norm(weighted, axis=0)
        if (norms <= 0).any():
            raise ValueError('Empty dictionary atom')
        self.design = weighted/norms
        augmented = np.vstack([self.design, np.sqrt(PARAMETERS['ridge'])*np.eye(len(notes))])
        q, self.r = np.linalg.qr(augmented, mode='reduced')
        self.projector = q[:len(self.weights)].T*self.weights[None, :]
        self.cutoff = None

    def coefficients(self, features):
        features = np.asarray(features, dtype=np.float64)
        if features.ndim != 2 or features.shape[1] != len(self.weights) or not np.isfinite(features).all():
            raise ValueError('Invalid feature matrix')
        rhs = features @ self.projector.T
        return np.asarray([nnls(self.r, row, maxiter=3*len(self.notes))[0] for row in rhs])

    def activity(self, features):
        coefficients = self.coefficients(features)
        activity = np.zeros((len(coefficients), 53), dtype=np.float64)
        for column, note in enumerate(self.notes):
            activity[:, note-32] += coefficients[:, column]
        maximum = activity.max(axis=1, keepdims=True)
        return np.divide(activity, maximum, out=np.zeros_like(activity), where=maximum > 0)

    def predict_proba(self, features):
        """Compatibility with the existing clock/scorer; returns occupancy, not probability."""
        if self.cutoff is None:
            raise ValueError('Training cutoff not frozen')
        return (self.activity(features) >= self.cutoff).astype(np.float64)


class IdentityTransform:
    def transform(self, features):
        return features


def fit_training_cutoff(activity, truth):
    """One train-only fit: maximize TP with >=99% precision; ties choose stricter.

    Equal activity values are indivisible. Zero is never a positive detection.
    If no nonempty prediction meets the criterion, the model fails closed.
    """
    activity, truth = np.asarray(activity), np.asarray(truth, dtype=bool)
    if activity.shape != truth.shape or not np.isfinite(activity).all() or (activity < 0).any() or (activity > 1).any():
        raise ValueError('Invalid training activities')
    values, labels = activity.ravel(), truth.ravel()
    order = np.argsort(-values, kind='stable')
    values, labels = values[order], labels[order]
    ends = np.r_[np.flatnonzero(np.diff(values) != 0), len(values)-1]
    tp = np.cumsum(labels, dtype=np.int64)[ends]
    predicted = ends+1
    precision = 100*tp/predicted
    valid = (values[ends] > 0) & (precision >= PARAMETERS['training_precision_percent'])
    indices = np.flatnonzero(valid)
    if not len(indices):
        return dict(cutoff=float(np.nextafter(1.0, 2.0)), feasible=False,
                    true_positive=0, false_positive=0, training_only=True)
    # Descending thresholds mean the first maximizing TP is the strictest tie.
    chosen = indices[np.argmax(tp[indices])]
    return dict(cutoff=float(values[ends[chosen]]), feasible=True,
        true_positive=int(tp[chosen]), false_positive=int(predicted[chosen]-tp[chosen]),
        training_only=True, selection='maximum train TP at >=99% precision; stricter tie')


def stratified_summary(activity, truth, cutoff):
    predicted = (np.asarray(activity) >= cutoff).astype(np.float64)
    truth = np.asarray(truth, dtype=bool)
    related = np.zeros(len(truth), dtype=bool)
    for interval in PARAMETERS['harmonic_intervals']:
        related |= (truth[:, :-interval] & truth[:, interval:]).any(axis=1)
    return dict(summary=classification_summary(predicted, truth),
        harmonic_relation_strata={name: classification_summary(predicted[mask], truth[mask])
            for name, mask in [('related', related), ('not_related', ~related)] if mask.any()},
        activity_semantics='Relative grouped NNLS coefficient, not probability or labeled-frame match.')
