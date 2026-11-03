"""Join existing replay diagnostics without equating absent rows with silence."""
from collections import Counter
from statistics import median


SELECTIONS = ('quiet', 'below_threshold', 'spectral_rejected', 'dp_evicted',
              'selected', 'coasting')


def summarize_selection(candidate_rows, outcome_rows, assignment_rows, *,
                        note, start, end, sample_count, assignment_stride=1024):
    if not (0 <= start < end <= sample_count) or assignment_stride % 64:
        raise ValueError('invalid capture geometry')
    expected = {sample for sample in range(63, sample_count, 64) if start <= sample < end}
    candidates, outcomes, assignments = {}, {}, set()
    for row in candidate_rows:
        sample = int(row['sample'])
        if (sample not in expected or sample in candidates or int(row['note']) != note
                or int(row['tick']) * 64 - 1 != sample):
            raise ValueError('candidate trace clock, note or duplicate mismatch')
        candidates[sample] = row
    if set(candidates) != expected:
        raise ValueError('incomplete candidate trace')
    for row in outcome_rows:
        sample = int(row['sample'])
        if (sample in outcomes or int(row['tick']) * 64 - 1 != sample):
            raise ValueError('outcome trace clock or duplicate mismatch')
        entries = {}
        for item in filter(None, row['candidates'].split(',')):
            fields = item.split(':')
            if len(fields) != 42 or int(fields[0]) in entries:
                raise ValueError('incompatible outcome candidate schema')
            entries[int(fields[0])] = fields
        outcomes[sample] = entries.get(note)
    if set(outcomes) != set(range(63, sample_count, 64)):
        raise ValueError('incomplete outcome trace')
    seen = set()
    for row in assignment_rows:
        sample, current_note = int(row['sample']), int(row['note'])
        identity = (sample, current_note)
        if (identity in seen or int(row['tick']) * 64 - 1 != sample
                or (sample + 1) % assignment_stride or not 0 <= sample < sample_count):
            raise ValueError('assignment trace clock or duplicate mismatch')
        seen.add(identity)
        # The native writer emits observed, replacement or fixed-context rows.
        # Preserve its presence contract; do not count only eligible likelihoods.
        if current_note == note:
            assignments.add(sample)

    def group(samples):
        stages, quiet, competitors = Counter(), Counter(), Counter()
        scores, fundamentals = [], []
        flags = Counter()
        for sample in sorted(samples):
            row, outcome = candidates[sample], outcomes[sample]
            selection = int(row['selection'])
            if selection not in range(len(SELECTIONS)):
                raise ValueError('unknown selection disposition')
            stage = SELECTIONS[selection]
            if outcome is not None:
                if int(outcome[1]) != selection:
                    raise ValueError('candidate/outcome disposition mismatch')
                if stage == 'dp_evicted':
                    stage += ('_in_selector_pool' if int(outcome[34])
                              else '_not_in_selector_pool')
            elif stage == 'dp_evicted':
                stage += '_pool_not_reported'
            stages[stage] += 1
            quiet[str(int(row['quiet']))] += 1
            scores.append(float(row['score_ratio']))
            fundamentals.append(float(row['fund_ratio']))
            for key in ('direct', 'local', 'evidence', 'active', 'phase_valid'):
                flags[key] += bool(int(row[key]))
            for item in filter(None, row['selected_or_coasting'].split(',')):
                other = int(item.split(':')[0])
                if other != note:
                    competitors[str(other)] += 1
        def bounds(values):
            return dict(min=min(values), median=median(values), max=max(values)) if values else None
        return dict(frames=len(samples), selection=dict(stages), quiet=dict(quiet),
                    positive_flags=dict(flags), score_ratio=bounds(scores),
                    fundamental_ratio=bounds(fundamentals),
                    other_selected_or_coasting=dict(competitors))

    sampled = {sample for sample in expected if (sample + 1) % assignment_stride == 0}
    return dict(note=note, start=start, end=end, sample_count=sample_count,
                all_labeled_frames=group(expected),
                sampled_assignment_present=group(sampled & assignments),
                sampled_assignment_absent=group(sampled - assignments),
                interpretation='Disposition and selector-pool membership locate the observed loss. '
                               'Missing assignment rows are not zero spectral evidence or MIDI error counts.')
