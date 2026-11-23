"""Pure comparisons for the single, post-hoc adjacent-onset guard screen."""
from tools.controlled_repluck import response, compare_attack
from tools.repluck_onset_analysis import require_callback_identity


def snapshot_identity(left, right, *, left_block, right_block):
    """Only the declared callback size may differ across buffer companions."""
    return (left.get('block') == str(left_block) and right.get('block') == str(right_block)
            and bool(left.get('fingerprint')) and bool(right.get('fingerprint'))
            and {k: v for k, v in left.items() if k != 'block'}
                == {k: v for k, v in right.items() if k != 'block'})


def prefix(events, end):
    # Source sequence / ledger slot can differ; delivered payload may not.
    keys = ('sample', 'kind', 'note', 'velocity', 'channel')
    return [tuple(event[key] for key in keys) for event in events if event['sample'] < end]


def compare_fixture(callbacks, control, saved_voice, saved_voice_control,
                    saved_stable, *, note, marker, insertion, end, rate, single):
    kwargs = dict(note=note, marker=marker, insertion=insertion, end=end, sample_rate=rate)
    baseline = response(saved_voice, saved_voice_control, **kwargs)
    candidate = response(callbacks, [] if single else control, **kwargs)
    old = response(saved_stable, [], **kwargs) if single else None
    first = compare_attack(baseline, candidate)
    same_single = None
    if single:
        try:
            require_callback_identity(callbacks, saved_stable, stable=True)
            same_single = True
        except ValueError:
            same_single = False
    gates = dict(first_response_retained=first['baseline_first_response_retained'])
    if single:
        gates['single_copy_saved_stable_identity'] = same_single
    else:
        gates['common_prefix_identity'] = prefix(callbacks, insertion) == prefix(control, insertion)
    return dict(gates=gates, per_voice_response=baseline, candidate_response=candidate,
                saved_single_stable_response=old, candidate_callbacks=len(callbacks),
                saved_stable_callbacks=len(saved_stable), saved_per_voice_callbacks=len(saved_voice),
                **first)


def summarize(fixtures):
    if len(fixtures) != 6 or sum(key.endswith('/single') for key in fixtures) != 2:
        raise ValueError('The frozen screen requires all six fixtures and two single controls')
    checks = [value for entry in fixtures.values() for value in entry['gates'].values()]
    checks.extend(value for entry in fixtures.values()
                  for value in entry['comparison']['gates'].values())
    suppressed = sum(entry['suppressed_pairs'] for entry in fixtures.values())
    checks.append(suppressed > 0)
    return dict(screen_pass=all(checks), gates_passed=sum(checks), gates_total=len(checks),
                suppressed_pairs=suppressed, suppression_retained=suppressed > 0,
                repeated_responses_retained=sum(entry['comparison']['baseline_first_response_retained']
                    for key, entry in fixtures.items() if not key.endswith('/single')),
                repeated_responses_total=4)
