"""GHA-only, matched-channel octave observations; no detector policy changes."""
import argparse
from collections import Counter
import csv
import gzip
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import wave

from tools.controlled_descriptor_overlap import read_float_wave, write_float_wave
from tools.frozen_cue_corpus_gate import compare_replays, read_replay
from tools.portable_assignment_trace import digest, read_rows
from tools.portable_corpus_replay import SETTINGS
from tools.portable_octave_parent_measurement import validate_inventory

CELL_COUNTS = {(44, 0): 5, (48, 1): 6, (48, 2): 4, (60, 2): 4, (62, 6): 2}
CHANNELS = ('parent_h2_over_h1_db', 'upper_h1_over_parent_h1_db')


# Final partial report from run44819076437; all21 parent takes completed.
PARENT_REPORT_SHA256 = '7829fd1c1cb87072e1153b785695dae2a70c8cc5d364c90c229f2b8090e6accc'


def read_pcm16_wave(path):
    """Exact native PCM16 scaling; no normalization or resampling."""
    import numpy as np
    with wave.open(str(path), 'rb') as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2 or stream.getcomptype() != 'NONE':
            raise ValueError('Expected mono PCM16 waveform')
        rate = stream.getframerate()
        count = stream.getnframes()
        payload = stream.readframes(count)
    if rate <= 0 or len(payload) != count * 2:
        raise ValueError('Invalid or truncated PCM16 waveform')
    return rate, np.frombuffer(payload, dtype='<i2').astype(np.float32) / 32768.0


def retained_parents(path, current):
    if digest(path) != PARENT_REPORT_SHA256:
        raise ValueError('Retained parent report hash mismatch')
    previous = json.loads(path.read_text())
    for key in ('protocol', 'binary_sha256', 'inventory_sha256', 'sources_sha256', 'plan_sha256'):
        if previous[key] != current[key]:
            raise ValueError('Retained parent provenance mismatch: ' + key)
    items = previous['measurements']
    if len(items) != 21 or any(r['kind'] != 'parent_only' for r in items):
        raise ValueError('Incomplete retained parent measurements')
    return items


def select_takes(inventory, plan):
    takes = validate_inventory(inventory)
    if (plan['sample_rate_hz'] != 96000 or plan['prefix_ms'] != 250 or
            plan['window_ms'] != [320, 480] or plan['block_samples'] != 512 or
            plan['settings'] != SETTINGS or
            {tuple(c) for c in plan['parent_cells']} != set(CELL_COUNTS)):
        raise ValueError('Changed frozen measurement protocol')
    selected = [t for t in takes if (t['note'], t['lane']) in CELL_COUNTS]
    if Counter((t['note'], t['lane']) for t in selected) != CELL_COUNTS or plan['expected_parent_takes'] != 21:
        raise ValueError('Missing parent cell-mates')
    expected = [(32,29,44,0),(41,42,48,2),(113,112,60,2),
                (245,244,48,1),(354,351,48,1),(162,None,62,6)]
    if [(c['parent_label'], c['upper_label'], c['parent'], c['lane']) for c in plan['cases']] != expected:
        raise ValueError('Changed frozen controls')
    if len({c['id'] for c in plan['cases']}) != 6 or any(c['upper'] != c['parent'] + 12 for c in plan['cases']):
        raise ValueError('Invalid control identities')
    return selected


def expected_samples(begin, end):
    # Replay emits after each 64th sample; indices are zero-based.
    return list(range(begin + (63 - begin) % 64, end, 64))


def checked_rows(path, note, begin, end):
    rows = [r for r in read_rows(path) if begin <= int(r['sample']) < end]
    if [int(r['sample']) for r in rows] != expected_samples(begin, end):
        raise ValueError('Missing, duplicated or misaligned observation ticks')
    if any(int(r['note']) != note for r in rows):
        raise ValueError('Wrong observed note')
    return rows


def nonnegative(row, key):
    value = float(row[key])
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid energy: ' + key)
    return value


def flag(row, key):
    value = int(row[key])
    if value not in (0, 1):
        raise ValueError('Invalid flag: ' + key)
    return value


def ratio_db(numerator, denominator):
    # No numerical floor and no removal of zero-energy ticks from coverage.
    return 10 * (math.log10(numerator) - math.log10(denominator)) if numerator > 0 and denominator > 0 else None


def join_rows(parent, upper, begin, end):
    expected = expected_samples(begin, end)
    if [int(r['sample']) for r in parent] != expected or [int(r['sample']) for r in upper] != expected:
        raise ValueError('Unpaired observation ticks')
    joined = []
    for p, u in zip(parent, upper):
        ph1 = nonnegative(p, 'corrected_harmonic_energy_1')
        ph2 = nonnegative(p, 'corrected_harmonic_energy_2')
        uh1 = nonnegative(u, 'corrected_harmonic_energy_1')
        row = dict(sample=int(p['sample']), parent_h1=ph1, parent_h2=ph2, upper_h1=uh1,
                   parent_h2_over_h1_db=ratio_db(ph2, ph1),
                   upper_h1_over_parent_h1_db=ratio_db(uh1, ph1))
        for prefix, source in (('parent', p), ('upper', u)):
            for key in ('phase_valid', 'independent_phase_valid', 'active', 'candidate_evidence'):
                row[prefix + '_' + key] = flag(source, 'evidence' if key == 'candidate_evidence' else key)
            for key in ('selection_disposition', 'assigned_mask'):
                row[prefix + '_' + key] = int(source['selection' if key == 'selection_disposition' else key])
            for key in ('phase_cents', 'independent_phase_cents'):
                value = float(source[key])
                if not math.isfinite(value):
                    raise ValueError('Nonfinite phase')
                row[prefix + '_' + key] = value
        joined.append(row)
    return joined


def distribution(values):
    return dict(count=len(values), min=min(values), median=statistics.median(values), max=max(values)) if values else None


def summarize(rows):
    result = dict(ticks=len(rows), channels={}, energies={key: distribution([r[key] for r in rows]) for key in ('parent_h1', 'parent_h2', 'upper_h1')})
    for key in CHANNELS:
        values = [r[key] for r in rows if r[key] is not None]
        result['channels'][key] = dict(valid_ticks=len(values), unavailable_ticks=len(rows)-len(values),
            complete=bool(rows) and len(values)==len(rows), distribution=distribution(values))
    for prefix in ('parent', 'upper'):
        result[prefix] = {
            key: sum(r[prefix+'_'+key] for r in rows)
            for key in ('phase_valid', 'independent_phase_valid', 'active', 'candidate_evidence')}
        result[prefix]['selection_dispositions'] = dict(Counter(r[prefix+'_selection_disposition'] for r in rows))
    return result


def channel_value(item, key):
    channel = item.get('summary', {}).get('channels', {}).get(key, {})
    return channel['distribution']['median'] if channel.get('complete') else None


def comparisons(measurements):
    """Fixed per-take medians; leave whole passes out. No fitted cutoff."""
    parents = [m for m in measurements if m['kind'] == 'parent_only']
    held, controls = [], []
    for item in measurements:
        cell = (item['parent'], item['lane'])
        peers = [p for p in parents if (p['parent'], p['lane']) == cell and
                 (item['kind'] != 'parent_only' or p['held_pass'] != item['held_pass'])]
        row = dict(id=item['id'], parent=cell[0], lane=cell[1], channels={})
        for key in CHANNELS:
            training = [(p['id'], channel_value(p,key)) for p in peers]
            eligible = [(name,value) for name,value in training if value is not None]
            value = channel_value(item,key)
            values = [v for _,v in eligible]
            prediction = statistics.median(values) if values else None
            row['channels'][key] = dict(measured_db=value,
                training_count=len(values), training_ids=[name for name,_ in eligible],
                unavailable_training_ids=[name for name,value in training if value is None],
                training_distribution=distribution(values), prediction_db=prediction,
                difference_db=value-prediction if value is not None and prediction is not None else None)
        (held if item['kind']=='parent_only' else controls).append(row)
    return dict(estimator='Median of per-tick corrected energy-ratio dB over complete fixed windows; prediction is median over eligible take medians.',
        held_pass=held, controls=controls,
        limitation='Same-session, correct lane supplied. Control comparison uses all cell-mates and is descriptive, not held-out classification or a fitted operating point.')


def clip_labels(labels, offset, stop):
    result=[]
    for label in labels:
        start=max(offset,int(label['start_sample']))
        end=min(stop,int(label['end_sample']))
        if start<end:
            result.append({**label,'start_sample':start-offset,'end_sample':end-offset})
    return result


def measure(binary, audio, labels, item, output, rate):
    prefix=round(.250*rate)
    begin, end=prefix+round(.320*rate), prefix+round(.480*rate)
    start=item['start_sample']; offset=start-prefix
    if offset<0 or item['end_sample']>len(audio):
        raise ValueError('Invalid source bounds')
    if start+round(.480*rate)>item['end_sample']:
        return dict(**item, available=False, unavailable_reason='incomplete_fixed_window')
    folder=output/item['id']; folder.mkdir()
    wave=folder/'clip.wav'; write_float_wave(wave,rate,audio[offset:offset+end])
    target=folder/'labels.tsv'
    clipped=clip_labels(labels,offset,offset+end)
    with target.open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(labels[0]),delimiter='\t')
        writer.writeheader(); writer.writerows(clipped)
    base=[str(binary.resolve()),'--wav',str(wave.resolve()),'--labels',str(target.resolve()),'--block','512','--label-details']
    for key,value in SETTINGS.items(): base+=['--'+key,str(value)]
    identities={}; traces={}
    for mode,note in (('reference',None),('parent',item['parent']),('upper',item['upper'])):
        command=base+['--midi-event-trace',str((folder/(mode+'-midi.tsv')).resolve())]
        trace=folder/(mode+'-candidate.tsv')
        if note is not None:
            command+=['--candidate-trace',str(trace.resolve()),'--candidate-trace-note',str(note),
                      '--candidate-trace-start','0','--candidate-trace-end',str(end/rate)]
        with (folder/(mode+'.tsv')).open('x') as stdout,(folder/(mode+'.stderr')).open('x') as stderr:
            subprocess.run(command,stdout=stdout,stderr=stderr,check=True,timeout=90)
        if note is not None:
            comparison=compare_replays(read_replay(folder/'reference.tsv'),read_replay(folder/(mode+'.tsv')))
            midi_same=digest(folder/'reference-midi.tsv')==digest(folder/(mode+'-midi.tsv'))
            if not comparison['output_bit_identical'] or comparison['changed_labels'] or not midi_same:
                raise ValueError('Observation changed snapshot or raw MIDI')
            identities[mode]=dict(comparison=comparison,midi_bit_identical=midi_same)
            traces[mode]=checked_rows(trace,note,begin,end)
    rows=join_rows(traces['parent'],traces['upper'],begin,end)
    paired=folder/'paired-energies.tsv.gz'
    with gzip.open(paired,'wt') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t'); writer.writeheader(); writer.writerows(rows)
    result=dict(**item,available=True,clip_sha256=digest(wave),clip_source_offset=offset,
        window_clip_samples=[begin,end],window_source_samples=[offset+begin,offset+end],
        identity=identities,summary=summarize(rows),
        halves=[summarize([r for r in rows if begin+i*(end-begin)//2<=r['sample']<begin+(i+1)*(end-begin)//2]) for i in range(2)],
        paired_trace=dict(path=str(paired.relative_to(output)),sha256=digest(paired)))
    # This runner's temporary audio is neither evidence nor an upload artifact.
    wave.unlink()
    return result


def run(binary, inputs, corpus, inventory, sources, plan, output, parent_report=None):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('Recorded processing must run on GitHub Actions')
    data=json.loads(inventory.read_text()); protocol=json.loads(plan.read_text()); pins=json.loads(sources.read_text())
    takes=select_takes(data,protocol)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(schema='m3_octave_common_estimator_v1',state='running',final=False,measurements=[],
        protocol=protocol,source_revision=os.environ.get('M3_SOURCE_SHA'),binary_sha256=digest(binary),
        inventory_sha256=digest(inventory),sources_sha256=digest(sources),plan_sha256=digest(plan),
        installed_output_changed=False,promotion_accepted=False,
        limitation='No production policy, timing, allocation, full-continuous-reference or live-host acceptance. Corrected energies can depend on phase validity; report flags without filtering.')
    def save(): (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        if parent_report is not None:
            report['measurements'] = retained_parents(parent_report, report)
            report['retained_parent_provenance'] = dict(run_id=44819076437, source_revision='b8268b9bdb95db87a263896e9f311ad370210498', report_sha256=PARENT_REPORT_SHA256, paired_traces_remote=True)
            save()
        for label_file in sorted({t['label_file'] for t in takes} if parent_report is None else set()):
            name=Path(label_file).name; label_path=inputs/'labels'/name
            if digest(label_path)!=data['label_sha256'][label_file]: raise ValueError('Label hash mismatch')
            with label_path.open() as stream: labels=list(csv.DictReader(stream,delimiter='\t'))
            raw_name=Path(name).stem+'-raw.wav'; raw=inputs/'raw'/raw_name
            if digest(raw)!=pins[raw_name]['sha256']: raise ValueError('Raw hash mismatch')
            rate,audio=read_float_wave(raw)
            if rate!=protocol['sample_rate_hz'] or rate!=pins[raw_name]['sample_rate_hz']: raise ValueError('Rate mismatch')
            for take in (t for t in takes if t['label_file']==label_file):
                label=labels[take['label_index']]
                expected={'start_sample':take['start_sample'],'end_sample':take['end_sample'],
                    'midi_note':take['note'],'string_mask':1<<take['lane'],'calibration_pass':take['held_pass']}
                if any(int(label[k])!=v for k,v in expected.items()) or float(label['expected_cents'])!=take['expected_cents']:
                    raise ValueError('Parent inventory/label mismatch')
                item=dict(**take,id=f'{Path(name).stem}-label{take["label_index"]}',kind='parent_only',parent=take['note'],upper=take['note']+12,
                    raw_sha256=pins[raw_name]['sha256'])
                report['stage']=item['id']; save()
                report['measurements'].append(measure(binary,audio,labels,item,output,rate)); save()
            del audio
        for name,sha in protocol['ordinary_inputs'].items():
            if digest(corpus/name)!=sha: raise ValueError('Ordinary hash mismatch: '+name)
        with (corpus/'ordinary.tsv').open() as stream: labels=list(csv.DictReader(stream,delimiter='\t'))
        rate,audio=read_pcm16_wave(corpus/'ordinary.wav')
        if rate!=protocol['sample_rate_hz']: raise ValueError('Ordinary rate mismatch')
        for case in protocol['cases']:
            parent=labels[case['parent_label']]
            if any(int(parent[k])!=case[v] for k,v in (('midi_note','parent'),('start_sample','start_sample'),('end_sample','end_sample'))) or int(parent['string_mask'])!=1<<case['lane']:
                raise ValueError('Control parent label mismatch')
            if case['upper_label'] is not None:
                upper=labels[case['upper_label']]
                if any(int(upper[k])!=case[v] for k,v in (('midi_note','upper'),('start_sample','start_sample'),('end_sample','end_sample'))): raise ValueError('Control upper mismatch')
            elif any(int(r['midi_note'])==case['upper'] and int(r['start_sample'])<case['end_sample'] and int(r['end_sample'])>case['start_sample'] for r in labels):
                raise ValueError('Negative control contains annotated upper')
            report['stage']=case['id']; save()
            report['measurements'].append(measure(binary,audio,labels,case,output,rate)); save()
        report['comparison']=comparisons(report['measurements'])
        report.update(state='completed',final=True,stage='matched observations collected')
    except Exception as error:
        report.update(state='failed',final=True,error=str(error)); raise
    finally: save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('binary','inputs','corpus','inventory','sources','plan','output'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--parent-report',type=Path)
    run(**vars(parser.parse_args()))
