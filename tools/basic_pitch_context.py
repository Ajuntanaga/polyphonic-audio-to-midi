"""Fixed paired readout experiment; no model or recording I/O."""
from tools.basic_pitch_streaming import SETTINGS, NS, ceil_div, emission_spans
from tools.pitch_detector_comparison import compare, score


CONTEXT = dict(reference_readout=[164, 165], candidate_readout=[160, 161],
               downstream_note_future_frames=9, downstream_onset_future_frames=10,
               additional_context_model_samples=1024)


def reference_identity(result, arrays, saved_events):
    """Compare computation, not noisy service durations on different workers."""
    import numpy as np
    checks = {key: bool(np.array_equal(result[key], arrays[saved]))
              for key, saved in (('notes', 'note'), ('onsets', 'onset'), ('frames', 'frames'))}
    def stable(events):
        return [{key: event[key] for key in ('kind', 'note', 'frame', 'available_ns')}
                for event in events]
    checks['events_and_availability'] = stable(result['events']) == stable(saved_events['events'])
    checks['cleanup_state'] = result['open_decoder_pitches'] == saved_events['cleanup']['notes']
    return checks


def context_measurements(result, labels, clock, reference, offline):
    """Keep every label and the full recording, including unavailable tail frames."""
    candidate = result['additional_readout']
    views = {}
    for name, key in (('serviced', 'emitted_ns'), ('zero_compute', 'available_ns')):
        old_spans, old_audit = emission_spans(result['events'], key, clock['sample_count'])
        new_spans, new_audit = emission_spans(candidate['events'], key, clock['sample_count'])
        old, new = score(old_spans, labels, **clock), score(new_spans, labels, **clock)
        views[name] = dict(measurement=new, event_audit=new_audit,
            comparison_to_same_pass_reference=compare(old, new),
            comparison_to_current=compare(reference, new), comparison_to_offline=compare(offline, new))
    return views


def context_screen(datasets):
    comparisons = {name: row['context_candidate']['serviced']['comparison_to_same_pass_reference']
                   for name, row in datasets.items()}
    gain = comparisons['ordinary']['pitch_coverage_gain_pp']
    safe = all(row['no_pitch_safety_regression'] for row in comparisons.values())
    return dict(incremental_context_screen_pass=gain > 0 and safe,
        ordinary_coverage_gain_pp=gain, both_datasets_no_pitch_safety_regression=safe,
        extra_context_ms=CONTEXT['additional_context_model_samples']/SETTINGS['model_rate']*1000,
        promotion_accepted=False, installed_output_changed=False,
        interpretation='Paired FIFO delivery includes extra context and both decoders. '
            'A gain without per-label and false-output safety does not pass. '
            'No native callback, device, physical onset or host readiness measurement.')


def save_context(name, result, labels, clock, reference, offline, bulk, saved_folder):
    """Remote caller has finished inference before labels enter this function."""
    from tools.portable_basic_pitch_cached_diagnosis import cached_arrays
    from tools.portable_basic_pitch_comparison import save_json
    from tools.pitch_detector_comparison import digest
    import json
    import numpy as np
    arrays = cached_arrays(saved_folder/(name+'-stream.npz'), stream=True)
    saved_events = json.loads((saved_folder/(name+'-events.json')).read_text())
    checks = reference_identity(result, arrays, saved_events)
    if not all(checks.values()):
        raise ValueError('Paired reference identity failed: '+str(checks))
    candidate = result['additional_readout']
    if candidate['readout_start'] != CONTEXT['candidate_readout'][0]:
        raise ValueError('Candidate readout differs from frozen context')
    frames = candidate['frames']
    if (len(frames) != max(0, len(result['frames'])-4)
            or [r[0] for r in frames] != list(range(len(frames)))
            or any(r[1] != r[0]*256 or r[2]-r[1] not in (2884,2628) for r in frames)):
        raise ValueError('Candidate frame alignment differs from fixed readout')
    artifact = bulk/(name+'-context.npz')
    np.savez_compressed(artifact, note=candidate['notes'], onset=candidate['onsets'],
        frames=np.asarray(frames, dtype='int64'), timing=np.asarray(result['timing'], dtype='int64'))
    events_path = bulk/(name+'-context-events.json')
    cleanup_ns = max(ceil_div(clock['sample_count']*NS, clock['sample_rate']), result['worker_finish_ns'])
    save_json(events_path, dict(events=candidate['events'],
        cleanup=dict(emitted_ns=cleanup_ns, notes=candidate['open_decoder_pitches']),
        frame_columns=['frame','nominal_model_sample','window_end_exclusive','arrived_source_samples']))
    return dict(reference_identity=checks,
        **context_measurements(result, labels, clock, reference, offline),
        observed_output_frames=len(frames), startup_negative_frames_discarded=4,
        fewer_positive_tail_frames_than_reference=len(result['frames'])-len(frames),
        open_decoder_pitches_at_end=candidate['open_decoder_pitches'],
        cleanup_emitted_ns=cleanup_ns, configuration=CONTEXT,
        bulk={p.name:dict(bytes=p.stat().st_size, sha256=digest(p)) for p in (artifact,events_path)})
