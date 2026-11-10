"""Explain captured joint string choices without replaying audio or changing policy.

Costs are added in native candidate/term order with the native packed-string tie
break. A constrained solution is an arithmetic counterfactual for this frozen
decision, not a prediction of later detector state or a proposed runtime rule.
"""
from collections import Counter, defaultdict
import math

from tools.candidate_outcome_analysis import HEADER, _candidates, _frame


TERM_NAMES = ('fret_prior', 'posterior_penalty', 'profile_bonus', 'open_bonus',
              'cents_penalty', 'fine_bonus', 'retention_bonus')
INTEGER_FIELDS = ('sample tick note observed valid selected_count ordinal playable '
                  'reserved_coasting reserved_extras prior_primary prior_mask '
                  'prior_active prior_committed prior_midi prior_spectral '
                  'dp_primary joint_strings final_primary final_mask fixed_context').split()


def solve(rows, *, pin=None):
    """Native subset DP; pin is an optional (note, string) constraint."""
    if not rows:
        return None
    reserved = rows[0]['reserved_coasting'] | rows[0]['reserved_extras']
    current = {reserved: (0.0, 0)}
    for row in rows:
        allowed = row['playable']
        if pin is not None and row['note'] == pin[0]:
            allowed &= 1 << pin[1]
        following = {}
        for used, (cost, packed) in sorted(current.items()):
            for lane in range(8):
                bit = 1 << lane
                if not allowed & bit or used & bit:
                    continue
                total = cost
                for term in row['terms'][lane]:
                    total += term
                proposal = (total, packed | (lane << (row['ordinal'] * 3)))
                mask = used | bit
                if mask not in following or proposal < following[mask]:
                    following[mask] = proposal
        current = following
    return min(current.values()) if current else None


def summarize_costs(raw_rows, outcomes, *, note, start, end):
    expected = set(range(((start + 64) // 64) * 64 - 1, end, 64))
    states, groups = {}, defaultdict(list)
    columns = HEADER.rstrip('\n').split('\t')
    for outcome in outcomes:
        sample = int(outcome['sample'])
        if sample in states or sample not in expected or int(outcome['tick']) * 64 - 1 != sample:
            raise ValueError('Invalid assignment outcome clock or duplicate')
        states[sample] = _candidates(_frame('\t'.join(outcome[key] for key in columns)))
    if set(states) != expected:
        raise ValueError('Incomplete assignment outcome window')
    seen = set()
    for raw in raw_rows:
        row = {key: int(raw[key]) for key in INTEGER_FIELDS}
        key = row['sample'], row['note']
        if (key in seen or row['sample'] not in expected or
                row['tick'] * 64 - 1 != row['sample'] or not 0 <= row['note'] <= 127):
            raise ValueError('Invalid assignment clock, note or duplicate')
        seen.add(key)
        if not row['observed']:
            continue  # Fixed context/replacement rows are not selected DP peers.
        if row['fixed_context'] or not 0 <= row['ordinal'] < row['selected_count'] <= 8:
            raise ValueError('Invalid selected assignment peer')
        row['terms'] = [[float(value) for value in lane.split(':')]
                        for lane in raw['lane_terms'].split(',')]
        row['totals'] = [float(value) for value in raw['lane_totals'].split(',')]
        row['joint_cost'] = float(raw['joint_cost'])
        if (len(row['terms']) != 8 or any(len(lane) != 7 for lane in row['terms'])
                or len(row['totals']) != 8
                or not all(math.isfinite(value) for lane in row['terms'] for value in lane)
                or not all(math.isfinite(value) for value in row['totals'] + [row['joint_cost']])):
            raise ValueError('Invalid assignment cost vector')
        for terms, total in zip(row['terms'], row['totals']):
            # Sequential addition matches native code, including cancellation.
            accumulated = 0.0
            for term in terms:
                accumulated += term
            if accumulated != total:
                raise ValueError('Assignment lane total differs from its signed terms')
        if any(not 0 <= row[key] <= 255 for key in
               ('playable', 'reserved_coasting', 'reserved_extras')):
            raise ValueError('Invalid assignment mask')
        groups[row['sample']].append(row)
    reasons, switches = Counter(), []
    valid_frames = invalid_frames = empty_frames = target_frames = 0
    for sample in sorted(expected):
        peers = sorted(groups.get(sample, []), key=lambda row: row['ordinal'])
        selected = {n for n, state in states[sample].items() if state['selection'] == 4}
        if {row['note'] for row in peers} != selected:
            raise ValueError(f'Incomplete selected assignment peers at sample {sample}')
        if not peers:
            empty_frames += 1
            continue
        first = peers[0]
        if ([row['ordinal'] for row in peers] != list(range(first['selected_count']))
                or any(row[key] != first[key] for row in peers for key in
                       ('selected_count', 'valid', 'joint_strings', 'joint_cost',
                        'reserved_coasting', 'reserved_extras'))):
            raise ValueError('Inconsistent complete joint assignment')
        solution = solve(peers)
        if bool(solution is not None) != bool(first['valid']):
            raise ValueError('Assignment feasibility does not reproduce')
        if solution is None:
            invalid_frames += 1
            continue
        if solution != (first['joint_cost'], first['joint_strings']):
            raise ValueError(f'Assignment optimum does not reproduce at sample {sample}')
        if any(row['dp_primary'] != (solution[1] >> (row['ordinal'] * 3)) & 7 for row in peers):
            raise ValueError('Assignment winner differs from packed solution')
        valid_frames += 1
        target = next((row for row in peers if row['note'] == note), None)
        if target is None:
            continue
        target_frames += 1
        prior = target['prior_primary']
        if not target['prior_active'] or prior >= 8 or prior == target['dp_primary']:
            continue
        constrained = solve(peers, pin=(note, prior))
        if constrained is None:
            reason = 'prior_string_infeasible_for_complete_joint_assignment'
        elif constrained[0] == solution[0]:
            reason = 'equal_cost_packed_string_tie_break'
        else:
            reason = 'lower_total_joint_cost'
        reasons[reason] += 1
        switches.append(dict(sample=sample, tick=target['tick'], prior_string=prior,
            chosen_string=target['dp_primary'], final_mask=target['final_mask'], reason=reason,
            joint_cost=solution[0], joint_strings=solution[1],
            prior_constrained_cost=None if constrained is None else constrained[0],
            prior_constrained_strings=None if constrained is None else constrained[1],
            prior_constraint_extra_cost=None if constrained is None else constrained[0] - solution[0],
            reserved_coasting=first['reserved_coasting'], reserved_extras=first['reserved_extras'],
            peers=[dict(note=row['note'], ordinal=row['ordinal'],
                prior_active=row['prior_active'], prior_committed=row['prior_committed'],
                prior_midi=row['prior_midi'], prior_spectral=row['prior_spectral'],
                prior_primary=row['prior_primary'], chosen_string=row['dp_primary'],
                final_mask=row['final_mask'], playable=row['playable'],
                lane_costs={str(lane): dict(total=row['totals'][lane], signed_terms=row['terms'][lane])
                            for lane in range(8) if row['playable'] & (1 << lane)})
                   for row in peers]))
    return dict(schema='m3_assignment_cost_diagnosis_v1', term_order=TERM_NAMES,
        expected_frames=len(expected), valid_joint_frames=valid_frames,
        invalid_joint_frames=invalid_frames, empty_selected_frames=empty_frames,
        target_selected_valid_frames=target_frames, complete_peers_verified=True,
        native_joint_decisions_reproduced=True, active_target_string_changes=len(switches),
        reasons=dict(reasons), switches=switches,
        interpretation='Costs reproduce complete joint decisions before output policy. '
        'Prior-string constraints use frozen evidence only; they do not measure a runtime '
        'change, labeled-note gain, held-duration gain, timing, or live readiness.')
