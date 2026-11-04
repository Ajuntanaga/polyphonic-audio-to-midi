"""Join frozen cue intervals with complete native selection and outcome traces."""
from collections import Counter
import math
from statistics import median

from tools.selection_trace_diagnosis import SELECTIONS


def summarize_cues(candidate_rows, outcome_rows, intervals, *, note, start, end,
                   sample_count, label_index=0, string_mask=1):
    if not 0 <= start < end <= sample_count:
        raise ValueError('invalid label geometry')
    expected = set(range(63, sample_count, 64))
    labeled = {s for s in expected if start <= s < end}
    candidates = {}
    for row in candidate_rows:
        sample = int(row['sample'])
        if (sample not in labeled or sample in candidates or int(row['note']) != note
                or int(row['tick']) * 64 - 1 != sample):
            raise ValueError('candidate clock, note or duplicate mismatch')
        candidates[sample] = row
    if set(candidates) != labeled:
        raise ValueError('incomplete candidate trace')

    active_samples, last_end = set(), {}
    previous = (-1, -1)
    for begin, finish, cue_note in intervals:
        if (not 0 <= begin < finish <= sample_count or not 0 <= cue_note < 128
                or (begin, cue_note) <= previous or begin < last_end.get(cue_note, 0)):
            raise ValueError('invalid cue interval ordering or geometry')
        previous, last_end[cue_note] = (begin, cue_note), finish
        if cue_note == note:
            # A cue starts before consuming begin; a decision at begin-1 cannot use it.
            first = ((begin + 1 + 63) // 64) * 64 - 1
            active_samples.update(range(first, finish, 64))

    outcomes, voices, matched = {}, {}, set()
    for row in outcome_rows:
        sample = int(row['sample'])
        if (sample not in expected or sample in outcomes
                or int(row['tick']) * 64 - 1 != sample):
            raise ValueError('outcome clock or duplicate mismatch')
        entries = {}
        for item in filter(None, row['candidates'].split(',')):
            fields = item.split(':')
            if len(fields) != 42 or int(fields[0]) in entries:
                raise ValueError('incompatible outcome candidate schema')
            entries[int(fields[0])] = fields
        outcomes[sample] = entries.get(note)
        voice_entries = []
        for item in filter(None, row['voices'].split(',')):
            fields = tuple(int(value) for value in item.split(':'))
            if len(fields) != 8:
                raise ValueError('incompatible outcome voice schema')
            voice_entries.append(fields)
        voices[sample] = voice_entries
        labels = {int(parts[0]): (int(parts[1]), int(parts[2]))
                  for parts in (item.split(':') for item in row['labels'].split(',') if item)}
        match_ids = {int(i) for i in row['matched_labels'].split(',') if i}
        if not match_ids <= labels.keys():
            raise ValueError('matched label absent from current annotations')
        if sample in labeled:
            if labels.get(label_index) != (note, string_mask):
                raise ValueError('target label identity mismatch')
            if label_index in match_ids:
                matched.add(sample)
            # Native snapshot_matches_label compares the complete rendered
            # string set. A correct member plus an extra same-pitch string is
            # not an exact match; an unconstrained label only needs the note.
            note_voices = [v for v in voice_entries if v[1] == note]
            rendered_mask = 0
            for voice in note_voices:
                if 0 <= voice[2] < 8:
                    rendered_mask |= 1 << voice[2]
            voice_match = (bool(note_voices) if string_mask == 0
                           else rendered_mask == string_mask)
            if voice_match != (label_index in match_ids):
                raise ValueError('native match and voice output mismatch')
        elif label_index in labels:
            raise ValueError('target label outside its saved span')
    if set(outcomes) != expected:
        raise ValueError('incomplete outcome trace')

    def group(samples):
        stages, failures, flags, shadows, competitors = (Counter() for _ in range(5))
        scores, fundamentals, prerequisites_pass = [], [], 0
        output_classes, stage_details = Counter(), {}
        output_strings, remapped_notes = Counter(), Counter()
        descriptor_strings, competing_string_notes = Counter(), Counter()
        descriptor_preferred_expected = occupied_expected = 0
        for sample in sorted(samples):
            row, outcome = candidates[sample], outcomes[sample]
            selection = int(row['selection'])
            if selection not in range(len(SELECTIONS)):
                raise ValueError('unknown selection disposition')
            stage = SELECTIONS[selection]
            if outcome is not None and int(outcome[1]) != selection:
                raise ValueError('candidate/outcome disposition mismatch')
            if stage == 'dp_evicted':
                stage += ('_pool_unreported' if outcome is None else
                          '_in_pool' if int(outcome[34]) else '_outside_pool')
            stages[stage] += 1
            details = stage_details.setdefault(stage, dict(frames=0,
                admission_prerequisite_combinations=Counter(), output=Counter()))
            details['frames'] += 1
            frame_voices = voices[sample]
            if sample in matched:
                output_class = 'target_matched'
            elif any(v[1] == note for v in frame_voices):
                output_class = 'target_note_string_set_mismatch'
            elif any(v[0] == note for v in frame_voices):
                output_class = 'target_detected_but_output_note_changed'
            else:
                output_class = 'no_target_voice_output'
            output_classes[output_class] += 1
            details['output'][output_class] += 1
            if outcome is not None:
                best_string = int(outcome[18])
                descriptor_strings[str(best_string)] += 1
                descriptor_preferred_expected += bool(0 <= best_string < 8 and
                    string_mask & (1 << best_string))
            competing = [v for v in frame_voices if v[1] != note and
                         0 <= v[2] < 8 and string_mask & (1 << v[2])]
            occupied_expected += bool(competing)
            competing_string_notes.update(str(v[1]) for v in competing)
            for voice in frame_voices:
                if voice[1] == note:
                    output_strings[str(voice[2])] += 1
                if voice[0] == note and voice[1] != note:
                    remapped_notes[str(voice[1])] += 1
            score, fundamental = float(row['score_ratio']), float(row['fund_ratio'])
            if not math.isfinite(score) or not math.isfinite(fundamental):
                raise ValueError('nonfinite admission evidence')
            scores.append(score)
            fundamentals.append(fundamental)
            failed = {'score_not_above_threshold': score <= 1.0,
                      'fundamental_below_0.85': fundamental < 0.85,
                      'no_direct_peak': not int(row['direct'])}
            failures.update(k for k, value in failed.items() if value)
            prerequisites_pass += not any(failed.values())
            combination = '+'.join(k for k, value in failed.items() if value) or 'all_pass'
            details['admission_prerequisite_combinations'][combination] += 1
            for key in ('direct', 'local', 'evidence', 'active'):
                flags[key] += bool(int(row[key]))
            if int(row['shadow_kind']):
                shadows[f"interval_{row['shadow_interval']}_kind_{row['shadow_kind']}"] += 1
            for item in filter(None, row['selected_or_coasting'].split(',')):
                other = int(item.split(':')[0])
                if other != note:
                    competitors[str(other)] += 1

        def bounds(values):
            return dict(min=min(values), median=median(values), max=max(values)) if values else None

        return dict(frames=len(samples), target_matched=len(samples & matched),
                    selection=dict(stages), positive_flags=dict(flags),
                    admission_prerequisite_failures=dict(failures),
                    admission_prerequisites_pass=prerequisites_pass,
                    output=dict(output_classes), selection_detail=stage_details,
                    target_output_string_voice_counts=dict(output_strings),
                    target_remapped_note_voice_counts=dict(remapped_notes),
                    descriptor_best_string_frames=dict(descriptor_strings),
                    descriptor_prefers_expected_string_frames=descriptor_preferred_expected,
                    expected_string_occupied_by_other_note_frames=occupied_expected,
                    competing_notes_on_expected_string_voice_counts=dict(competing_string_notes),
                    score_ratio=bounds(scores), fundamental_ratio=bounds(fundamentals),
                    recorded_shadow=dict(shadows), other_selected_or_coasting=dict(competitors))

    cue_on = labeled & active_samples
    return dict(note=note, string_mask=string_mask, start=start, end=end,
                sample_count=sample_count, all_labeled=group(labeled),
                cue_on=group(cue_on), cue_off=group(labeled - cue_on),
                cue_on_matched=group(cue_on & matched), cue_on_unmatched=group(cue_on - matched),
                interpretation='Matches use native matched-label flags. Cue membership is causal. '
                'Prerequisites use logged ratios; overlapping failures are not exclusive causes. '
                'Output classes are exclusive per frame; string and remapped-note counts are voices. '
                'A missing outcome candidate is not zero evidence. No live-use result is inferred.')
