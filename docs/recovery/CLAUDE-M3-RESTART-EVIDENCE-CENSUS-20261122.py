"""Restart-evidence census: after a rapid-mute release, which saved causal cue restarts a re-struck note and which restarts a sustained tail?  Saved data only.

Plan, definitions, identity checks I0-I3, predictions P1-P8 and the reading rule are fixed in
CLAUDE-M3-RESTART-EVIDENCE-CENSUS-PREREGISTRATION-20261122.md, committed before the real run.

Context.  CLAUDE-M3-RAPID-MUTE-CHECK-RESULT-20261122.md showed that truncating every CURRENT span at the first rapid-mute interval ("cut") removes 59% of the false
output but loses 1,077,990 present samples, all of it in 23 labels whose CURRENT span ran on across the mute (a same-pitch re-strike or a stale pitch of the
previous chord) and nothing resumed.  This script asks the question that remained: with a release at every marked run and a restart on a saved causal cue, which
cue restarts those 23 labels (positives) without restarting the sustained tails of the other truncated spans (negatives)?

Release.  Every CURRENT span is released at the start of each marked run (the rapid-mute check's own runs).  Restart.  A released pitch resumes at the first
instant t >= the end of the marked run (and outside every marked run) at which a cue supports that pitch, and stays on (sticky) until the next marked run or the
end of its CURRENT span.  No cue means the pitch stays off (the cut); a cue that is always on resumes at the run end (the mask).  Nothing is tuned: there is no
threshold, hold or debounce.  Cues are the frozen arms of CODEX-M3-SUPPORT-EVENTS-PLAN-20261122.md (L: the last decision's direct observation of the callback,
E: every direct observation, A: E plus a selected active pooled onset-observed note), the saved cropped-adapted model spans (M), A united with M (AM) and, as a
comparator that uses the labels, a label-timed restart (ORACLE).

Usage: python3 -P -E CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py --selftest     (plumbing only: no cue-versus-class numbers are printed)
       python3 -P -E CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py --dry          (runs every code path, writes and prints no result)
       python3 -P -E CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.py --run
No audio, model run, job or native edit.
"""
import bisect
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rm = load('rm', 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.py')       # importing does not run its main
chk, fr, ad = rm.chk, rm.fr, rm.ad
from tools.candidate_outcome_analysis import _candidates  # noqa: E402  (the repo's own trace parser, as in the support check)

OUT = os.path.join(HERE, 'CLAUDE-M3-RESTART-EVIDENCE-CENSUS-20261122.json')
COMMITTED_CHECK = os.path.join(HERE, 'CLAUDE-M3-RAPID-MUTE-CHECK-20261122.json')
COMMITTED_ANATOMY = os.path.join(HERE, 'CLAUDE-M3-RAPID-MUTE-CUT-ANATOMY-20261122.json')
CALLBACK, ORDINARY = rm.CALLBACK, rm.ORDINARY
CUES = ('L', 'E', 'A', 'M', 'AM', 'ORACLE')                      # ORACLE uses the labels: a comparator, never a candidate
CANDIDATE_CUES = ('L', 'E', 'A', 'M', 'AM')
EARLY_MS = 25                                                   # the frozen label budget's present-time limit, used to read "restarted in time"


# ---------------------------------------------------------------- the restart machine (sorted disjoint [lo, hi) lists)
def first_restart(free, after, limit):
    """First instant t >= after, inside the support intervals `free` (which already exclude every marked run), with t < limit; None when there is none."""
    k = bisect.bisect_right([hi for _, hi in free], after)
    if k >= len(free):
        return None
    t = max(after, free[k][0])
    return t if t < limit else None


def restart_spans(spans, marked, support):
    """Release at every marked run, restart sticky on `support`.  support=None is the cut, support covering everything is the mask."""
    starts = [m[0] for m in marked]
    ends = [m[1] for m in marked]
    free = rm.subtract(support, marked) if support else []
    out = []
    for lo, hi in spans:
        cur = lo
        i = bisect.bisect_right(ends, lo)               # first marked run ending after the span starts
        if i < len(marked) and marked[i][0] <= lo:      # born inside a run: blanked until it ends, as in the cut and the mask
            cur = marked[i][1]
            i += 1
            if cur >= hi:
                continue
        while True:
            if i < len(marked) and marked[i][0] < hi:
                m0, m1 = marked[i]
                if m0 > cur:
                    out.append([cur, m0])
                t = first_restart(free, m1, hi)
                if t is None:
                    break
                cur = t
                i = bisect.bisect_right(starts, t)      # t lies outside every run, so the next run starts after it
            else:
                out.append([cur, hi])
                break
    return out


def first_cut(span, marked):
    """For the first flagged start inside a span: where its output resumes after head blanking, the cut instant and the end of that marked run; None if no cut."""
    lo, hi = span
    i = bisect.bisect_right([m[1] for m in marked], lo)
    cur = lo
    if i < len(marked) and marked[i][0] <= lo:
        cur = marked[i][1]
        i += 1
        if cur >= hi:
            return None
    if i < len(marked) and marked[i][0] < hi:
        return dict(start=cur, cut=marked[i][0], run_end=marked[i][1])
    return None


# ---------------------------------------------------------------- cue supports
def by_pitch_of(triples, horizon):
    return fr.by_pitch(triples, horizon)


def cue_supports(name, ctx, callbacks):
    """Per cue, per pitch sorted disjoint intervals.  L/E/A are the callback supports of the support check (no hold), M the saved cropped-adapted model spans on the
    measured emitted clock, AM their union, ORACLE the merged label intervals of the pitch."""
    horizon = ctx['horizon']
    pin = chk.PINS[name]
    events_path = os.path.join(chk.EVENTS_DIR, pin['events'])
    if ad.sha256(events_path) != pin['events_sha']:
        raise SystemExit(f'{name}: event hash differs from the pin')
    model = ad.spans_from_events(ad.read_events(events_path), horizon, 'emitted_ns')[0]
    native = chk.arm_support(callbacks, horizon)
    cues = {arm: by_pitch_of(native[arm], horizon) for arm in chk.ARMS}
    cues['M'] = by_pitch_of(model, horizon)
    cues['AM'] = by_pitch_of(fr.union_spans([*native['A'], *model], sample_count=horizon), horizon)
    labels = {}
    for lab in ctx['labels']:
        labels.setdefault(lab['midi_note'], []).append([lab['start_sample'], lab['end_sample']])
    labels = {p: rm.merge_runs(v) for p, v in labels.items()}
    cues['ORACLE'] = labels
    return cues, labels, model, native


# ---------------------------------------------------------------- structure (spans, truncation, positives and negatives; no cue values)
def span_structure(cur_p, marked, labels_p):
    """Every CURRENT span the cut changes, by kind, and every span with a flagged start inside it (a truncation), classified by the present output in its removed part."""
    kinds = dict(changed=0, removed_entirely=0, truncated=0, head_blank_only=0)
    trunc = []
    for p, spans in sorted(cur_p.items()):
        for span in spans:
            res = rm.cut_at_first_flag([span], marked)
            if res == [list(span)]:
                continue
            kinds['changed'] += 1
            fc = first_cut(span, marked)
            if not res:
                kinds['removed_entirely'] += 1
            elif fc is not None:
                kinds['truncated'] += 1
            else:
                kinds['head_blank_only'] += 1
            if fc is None:
                continue
            removed = [[fc['cut'], span[1]]]
            labs = labels_p.get(p, [])
            present = fr.isect(removed, labs)
            first = min((max(a, fc['cut']) for a, b in labs if b > fc['cut'] and a < span[1]), default=None)
            trunc.append(dict(pitch=p, span=list(span), **fc, present_in_removed=fr.size(present), first_label_start_in_removed=first,
                              cls='positive' if present else 'negative'))
    return kinds, trunc


# ---------------------------------------------------------------- scoring
def label_loss(cmp):
    return {r['label_index']: -r['present_samples_delta'] for r in cmp['label_deltas']}


def per_pitch_restart(cur_p, marked, support_p):
    return {p: restart_spans(v, marked, support_p.get(p, [])) for p, v in cur_p.items()}


def census_row(trunc, restarts, cur_p, marked, cue_p, rate):
    """Per cue: for the positives the restart instant against the label start, for the negatives whether they restart and the volume re-admitted (exact)."""
    pos, neg = [t for t in trunc if t['cls'] == 'positive'], [t for t in trunc if t['cls'] == 'negative']
    free_cache = {}

    def restart_time(t):
        free = free_cache.get(t['pitch'])
        if free is None:
            free = free_cache[t['pitch']] = rm.subtract(cue_p.get(t['pitch'], []), marked) if cue_p.get(t['pitch']) else []
        return first_restart(free, t['run_end'], t['span'][1])

    lat = []
    for t in pos:
        r = restart_time(t)
        lat.append(None if r is None else r - t['first_label_start_in_removed'])
    ms = lambda x: round(x * 1000 / rate, 2)
    restarted = [x for x in lat if x is not None]
    early_limit = EARLY_MS * rate // 1000
    pos_row = dict(spans=len(pos), restarted=len(restarted), never=len(lat) - len(restarted),
                   before_label_start=sum(1 for x in restarted if x < 0),
                   within_25ms_of_label_start=sum(1 for x in restarted if 0 <= x <= early_limit),
                   later_than_25ms=sum(1 for x in restarted if x > early_limit),
                   latency_ms=sorted(ms(x) for x in restarted))
    readmitted, neg_restarted = 0, 0
    for t in neg:
        span = [t['span']]
        cut = rm.cut_at_first_flag(span, marked)
        full = restart_spans(span, marked, cue_p.get(t['pitch'], []))
        extra = fr.size(full) - fr.size(cut)
        readmitted += extra
        neg_restarted += int(restart_time(t) is not None)
    neg_row = dict(spans=len(neg), restarted=neg_restarted, not_restarted=len(neg) - neg_restarted, readmitted_samples=readmitted,
                   removed_by_cut=sum(fr.size([[t['cut'], t['span'][1]]]) for t in neg))
    return pos_row, neg_row


def variant_summary(row):
    return dict(present=row['present'], wrong=row['wrong'], gap=row['gap'], false=row['false'], precision_pct=row['precision_pct'], runs=row['runs'], volume=row['volume'],
                over_budget=[o['label_index'] for o in row['budget']['over_budget_labels']], newly_missed=row['budget']['newly_missed_labels'],
                aggregate_pitch_safety=row['budget']['aggregate_pitch_safety'], passes=row['budget']['passes'])


# ---------------------------------------------------------------- coverage of per-pitch candidate records (plumbing: is an absent record a missing value?)
def coverage(name, cur_p, trunc):
    """Over every decision whose sample lies inside a CURRENT span of a pitch: how often the trace carries a candidate record for that pitch.  Counts only."""
    pin, sha = chk.PINS[name], hashlib.sha256()
    pos_r = {}
    neg_r = {}
    for t in trunc:
        (pos_r if t['cls'] == 'positive' else neg_r).setdefault(t['pitch'], []).append([t['cut'], t['span'][1]])
    cover = dict(current=[0, 0], positive_removed=[0, 0], negative_removed=[0, 0])
    pointers = {p: 0 for p in cur_p}
    with gzip.open(os.path.join(ROOT, pin['trace']), 'rb') as stream:
        def lines():
            for raw in stream:
                sha.update(raw)
                yield raw.decode('utf-8')
        text = lines()
        if next(text).strip() != '# m3_candidate_outcome_v5':
            raise SystemExit('not the complete v5 trace')
        for row in csv.DictReader(text, delimiter='\t'):
            s = int(row['sample'])
            cands = _candidates({'candidate_text': row['candidates']})
            for p, spans in cur_p.items():
                k = pointers[p]
                while k < len(spans) and spans[k][1] <= s:
                    k += 1
                pointers[p] = k
                if k < len(spans) and spans[k][0] <= s:
                    have = int(p in cands)
                    cover['current'][0] += 1
                    cover['current'][1] += have
                    for key, table in (('positive_removed', pos_r), ('negative_removed', neg_r)):
                        if any(a <= s < b for a, b in table.get(p, [])):
                            cover[key][0] += 1
                            cover[key][1] += have
    if sha.hexdigest() != pin['sha']:
        raise SystemExit(f'{name}: raw trace hash differs from the pin')
    return {k: dict(decisions=v[0], with_record=v[1], share=(round(v[1] / v[0], 6) if v[0] else None)) for k, v in cover.items()}


# ---------------------------------------------------------------- plumbing checks
def unit_checks():
    ok = []
    marked = [[100, 150], [300, 320]]
    full = [[0, 1000]]
    ok.append(restart_spans([[0, 90]], marked, None) == [[0, 90]])                              # no window
    ok.append(restart_spans([[0, 200]], marked, None) == [[0, 100]])                            # cut, nothing resumed
    ok.append(restart_spans([[0, 200]], marked, full) == [[0, 100], [150, 200]])                # always-on: resumes at the run end (the mask)
    ok.append(restart_spans([[0, 400]], marked, full) == [[0, 100], [150, 300], [320, 400]])    # a second window cuts again and resumes again
    ok.append(restart_spans([[0, 400]], marked, [[170, 180]]) == [[0, 100], [170, 300]])        # resumes at the first support instant, stays on until the next run
    ok.append(restart_spans([[0, 400]], marked, [[170, 180], [330, 340]]) == [[0, 100], [170, 300], [330, 400]])
    ok.append(restart_spans([[0, 400]], marked, [[110, 140]]) == [[0, 100]])                    # support only inside the run: no restart, the run is not a restart instant
    ok.append(restart_spans([[0, 400]], marked, [[120, 160]]) == [[0, 100], [150, 300]])        # support overlapping the run end resumes exactly at the end
    ok.append(restart_spans([[0, 400]], marked, [[305, 400]]) == [[0, 100], [320, 400]])        # support through the second run resumes at its end
    ok.append(restart_spans([[0, 400]], marked, [[450, 500]]) == [[0, 100]])                    # support after the span ends
    ok.append(restart_spans([[120, 400]], marked, None) == [[150, 300]])                        # born inside the first run: blanked, then cut at the second
    ok.append(restart_spans([[120, 400]], marked, full) == [[150, 300], [320, 400]])
    ok.append(restart_spans([[120, 140]], marked, full) == [])
    ok.append(restart_spans([[150, 250]], marked, None) == [[150, 250]])
    ok.append(restart_spans([[0, 50], [200, 400]], marked, [[330, 340]]) == [[0, 50], [200, 300], [330, 400]])
    for support in (None, [[170, 180]], full):                                                   # random-ish consistency: the cut and the mask bracket every restart
        for spans in ([[0, 400]], [[0, 90], [120, 260], [310, 500]]):
            r = restart_spans(spans, marked, support)
            cut = rm.cut_at_first_flag(spans, marked)
            mask = rm.subtract(spans, marked)
            ok.append(fr.size(fr.isect(cut, r)) == fr.size(cut) and fr.size(fr.isect(r, mask)) == fr.size(r))
    ok.append(first_restart([[170, 180], [330, 340]], 150, 400) == 170 and first_restart([[170, 180]], 175, 400) == 175
              and first_restart([[170, 180]], 181, 400) is None and first_restart([[170, 180]], 150, 170) is None and first_restart([], 0, 10) is None)
    ok.append(first_cut([0, 400], marked) == dict(start=0, cut=100, run_end=150) and first_cut([120, 400], marked) == dict(start=150, cut=300, run_end=320)
              and first_cut([0, 90], marked) is None and first_cut([120, 140], marked) is None and first_cut([150, 250], marked) is None)
    return all(ok), ok


def identities_on_data(name, ctx, cur_p, marked, cues):
    """Without looking at any cue's behaviour: no cue is the cut, an everywhere cue is the mask, and every cue's output sits between them and nests L < E < A < AM, M < AM."""
    horizon = ctx['horizon']
    cut_p = {p: rm.cut_at_first_flag(v, marked) for p, v in cur_p.items()}
    mask_p = {p: rm.subtract(v, marked) for p, v in cur_p.items()}
    none_p = per_pitch_restart(cur_p, marked, {})
    always_p = per_pitch_restart(cur_p, marked, {p: [[0, horizon]] for p in cur_p})
    same = lambda a, b: all(a.get(p, []) == b.get(p, []) for p in set(a) | set(b))
    outs = {cue: per_pitch_restart(cur_p, marked, cues[cue]) for cue in CUES}
    inside = lambda a, b: all(fr.size(fr.isect(a.get(p, []), b.get(p, []))) == fr.size(a.get(p, [])) for p in a)
    return dict(none_is_cut=same(none_p, cut_p), always_is_mask=same(always_p, mask_p),
                between_cut_and_mask=all(inside(cut_p, outs[c]) and inside(outs[c], mask_p) for c in CUES),
                nested=inside(outs['L'], outs['E']) and inside(outs['E'], outs['A']) and inside(outs['A'], outs['AM']) and inside(outs['M'], outs['AM']),
                cut_p=cut_p, mask_p=mask_p, outs=outs)


def selftest():
    good, parts = unit_checks()
    print('unit checks', 'PASS' if good else 'FAIL', parts)
    ok = good
    committed = json.load(open(COMMITTED_CHECK))
    for name in chk.PINS:
        ctx = ad.dataset_context(name)
        horizon = ctx['horizon']
        last, audit = rm.read_quiet(name)
        marked = rm.marked_runs(last, horizon)
        cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
        callbacks, caudit = chk.read_trace(name)
        cues, labels_p, _, _ = cue_supports(name, ctx, callbacks)
        ident = identities_on_data(name, ctx, cur_p, marked, cues)
        kinds, trunc = span_structure(cur_p, marked, labels_p)
        ch = committed['datasets'][name]['cut_changes']
        kinds_ok = kinds['changed'] == ch['spans_changed'] and kinds['removed_entirely'] == ch['spans_removed_entirely'] and kinds['changed'] == kinds['removed_entirely'] + kinds['truncated'] + kinds['head_blank_only']
        pos = [t for t in trunc if t['cls'] == 'positive']
        lost = sum(t['present_in_removed'] for t in pos)
        cut_row = committed['datasets'][name]['variants']['cut']
        cur_row = committed['datasets'][name]['variants']['CURRENT']
        lost_ok = lost == cur_row['present'] - cut_row['present']
        cover = coverage(name, cur_p, trunc)
        ident_ok = ident['none_is_cut'] and ident['always_is_mask'] and ident['between_cut_and_mask'] and ident['nested']
        print(f"{name}: trace sha ok ({audit['rows']:,} rows; support-check pass {caudit['rows']:,} rows); marked runs {len(marked)}; cut changes {kinds} match the committed cut: {kinds_ok}")
        print(f"  structure: truncated spans {len(trunc)} = positive {len(pos)} + negative {len(trunc) - len(pos)}; present in the removed parts of the positives {lost:,} equals the committed cut's loss: {lost_ok}")
        print(f"  identities: no cue = cut {ident['none_is_cut']}; everywhere cue = mask {ident['always_is_mask']}; cut <= every restart <= mask {ident['between_cut_and_mask']}; L <= E <= A <= AM, M <= AM {ident['nested']}")
        print(f"  candidate-record coverage (plumbing: decisions inside CURRENT spans that carry a record for the span's pitch): {json.dumps(cover)}")
        ok = ok and kinds_ok and lost_ok and ident_ok
    print('SELFTEST', 'PASS' if ok else 'FAIL')
    return ok


# ---------------------------------------------------------------- the run
def compute():
    committed = json.load(open(COMMITTED_CHECK))
    anatomy = json.load(open(COMMITTED_ANATOMY))
    out = dict(schema='m3_restart_evidence_census_v1', callback_samples=CALLBACK, early_ms=EARLY_MS, cues=list(CUES), datasets={}, identity={})
    for name in chk.PINS:
        ctx = ad.dataset_context(name)
        horizon, rate = ctx['horizon'], ctx['rate']
        last, audit = rm.read_quiet(name)
        marked = rm.marked_runs(last, horizon)
        cur_p = fr.by_pitch(ctx['cur_spans'], horizon)
        callbacks, caudit = chk.read_trace(name)
        cues, labels_p, model, native = cue_supports(name, ctx, callbacks)
        ident = identities_on_data(name, ctx, cur_p, marked, cues)
        geo_bundle = fr.geometry(ctx['cur_spans'], ctx['labels'], horizon) if name == ORDINARY else None
        kinds, trunc = span_structure(cur_p, marked, labels_p)
        cover = coverage(name, cur_p, trunc)
        cut_p, mask_p, outs = ident['cut_p'], ident['mask_p'], ident['outs']
        rows, cmps = {}, {}
        for key, per_pitch in (('CURRENT', cur_p), ('mask', mask_p), ('cut', cut_p)):
            rows[key], _, cmps[key] = rm.variant(ctx, per_pitch, geo_bundle)
        l_p = fr.by_pitch(chk.filtered_spans(ctx, model, native['L']), horizon)
        rows['filter_L'], _, cmps['filter_L'] = rm.variant(ctx, l_p, geo_bundle)
        for cue in CUES:
            rows['restart_' + cue], _, cmps['restart_' + cue] = rm.variant(ctx, outs[cue], geo_bundle)
            stack = {p: fr.isect(l_p.get(p, []), outs[cue].get(p, [])) for p in cur_p}
            rows['filter_L&restart_' + cue], _, cmps['filter_L&restart_' + cue] = rm.variant(ctx, stack, geo_bundle)
        # the label-timed present-only restart of the rapid-mute cut anatomy (cut plus every present sample): a ceiling that uses the labels
        oracle_p = {p: rm.merge_runs(list(cut_p.get(p, [])) + list(fr.isect(cur_p[p], labels_p.get(p, [])))) for p in cur_p}
        rows['oracle_restart'], _, cmps['oracle_restart'] = rm.variant(ctx, oracle_p, geo_bundle)
        entry = dict(horizon=horizon, rate=rate, audit=audit, support_audit=caudit, marked_runs=len(marked), cut_kinds=kinds, coverage=cover,
                     variants={k: variant_summary(v) for k, v in rows.items()}, census={})
        pos_labels = sorted(i for i, v in label_loss(cmps['cut']).items() if v > 0)
        mask_loss = label_loss(cmps['mask'])
        mask_over = {o['label_index'] for o in rows['mask']['budget']['over_budget_labels']}
        cut_d_p, cut_d_f = rows['mask']['present'] - rows['cut']['present'], rows['mask']['false'] - rows['cut']['false']
        for cue in CUES:
            pos_row, neg_row = census_row(trunc, outs[cue], cur_p, marked, cues[cue], rate)
            loss = label_loss(cmps['restart_' + cue])
            extra = {i: loss[i] - mask_loss[i] for i in pos_labels}
            sens = sum(1 for i in pos_labels if extra[i] <= EARLY_MS * rate // 1000)
            over = {o['label_index'] for o in rows['restart_' + cue]['budget']['over_budget_labels']}
            d_p, d_f = rows['mask']['present'] - rows['restart_' + cue]['present'], rows['mask']['false'] - rows['restart_' + cue]['false']
            spec = (neg_row['not_restarted'] / neg_row['spans']) if neg_row['spans'] else None
            entry['census'][cue] = dict(
                positives=pos_row, negatives=neg_row, sens25=sens, positives_total=len(pos_labels),
                spec=None if spec is None else round(spec, 6),
                J=None if spec is None or not pos_labels else round(sens / len(pos_labels) + spec - 1, 6),
                present_lost_vs_mask=d_p, false_removed_vs_mask=d_f,
                G=round(d_f / cut_d_f, 6) if cut_d_f else None, C=round(d_p / cut_d_p, 6) if cut_d_p else None,
                J_vol=round(d_f / cut_d_f - d_p / cut_d_p, 6) if cut_d_f and cut_d_p else None,
                new_over_budget_vs_mask=sorted(over - mask_over),
                new_missed_vs_mask=sorted(set(rows['restart_' + cue]['budget']['newly_missed_labels']) - set(rows['mask']['budget']['newly_missed_labels'])),
                positive_label_loss_samples={str(i): loss[i] for i in pos_labels}, positive_label_extra_vs_mask_samples={str(i): extra[i] for i in pos_labels})
        entry['positive_labels'] = pos_labels
        free = {c: {p: (rm.subtract(v, marked) if v else []) for p, v in cues[c].items()} for c in CUES}
        entry['truncated_spans'] = [dict(t, restart={c: first_restart(free[c].get(t['pitch'], []), t['run_end'], t['span'][1]) for c in CUES}) for t in trunc]
        out['datasets'][name] = entry
        cc = committed['datasets'][name]['variants']
        same = lambda key, keys, ref=None: all(entry['variants'][key][k] == cc[ref or key][k] for k in keys)
        loss_sum = {k: sum(label_loss(cmps[k]).values()) == rows['CURRENT']['present'] - rows[k]['present'] for k in rows}
        o = entry['census']['ORACLE']
        out['identity'][name] = dict(
            none_is_cut=ident['none_is_cut'], always_is_mask=ident['always_is_mask'], between_cut_and_mask=ident['between_cut_and_mask'], nested=ident['nested'],
            cut_row_equals_committed=same('cut', ('present', 'wrong', 'gap', 'runs')), mask_row_equals_committed=same('mask', ('present', 'wrong', 'gap', 'runs')),
            filter_L_row_equals_committed=same('filter_L', ('present', 'wrong', 'gap', 'runs'), 'L'), CURRENT_row_equals_committed=same('CURRENT', ('present', 'wrong', 'gap', 'runs')),
            loss_accounting_gating={k: loss_sum[k] for k in ('cut', 'mask', 'restart_ORACLE', 'oracle_restart')}, loss_accounting_all_variants=all(loss_sum.values()),
            oracle_cue_perfect=(o['sens25'] == len(pos_labels) and o['present_lost_vs_mask'] == 0 and (o['spec'] == 1.0 or o['spec'] is None)))
        if name == ORDINARY:
            a = anatomy['oracle_restart']
            out['identity'][name]['oracle_restart_equals_anatomy'] = all(entry['variants']['oracle_restart'][k] == a[k] for k in ('present', 'wrong', 'gap', 'false', 'runs'))
            out['identity'][name]['positives_equal_anatomy'] = pos_labels == sorted(r['label'] for r in anatomy['rows'])
        print(name, 'identity', json.dumps(out['identity'][name]))
    cen, ext = out['datasets'][ORDINARY]['census'], out['datasets']['extended-middle']['census']
    gating = [v for r in out['identity'].values() for k, v in r.items() if k != 'loss_accounting_gating' and k != 'loss_accounting_all_variants']
    gating += [v for r in out['identity'].values() for v in r['loss_accounting_gating'].values()]
    preds = {
        'P1 cue A: at least 12 of the 23 positive labels lose no more than 25 ms of present beyond the mask (sens25 >= 12)': cen['A']['sens25'] >= 12,
        'P2 cue A leaves at least 50% of the 224 negative spans unrestarted (spec >= 0.50)': cen['A']['spec'] is not None and cen['A']['spec'] >= 0.50,
        'P3 cue A is not informative: J < 0.20': cen['A']['J'] is not None and cen['A']['J'] < 0.20,
        'P4 the model cue M and A united with M are both not informative (J < 0.20 for M and for AM)': all(cen[c]['J'] is not None and cen[c]['J'] < 0.20 for c in ('M', 'AM')),
        'P5 cue A keeps at least half of the cut false-output removal beyond the mask (G >= 0.50)': cen['A']['G'] is not None and cen['A']['G'] >= 0.50,
        'P6 no candidate cue (L, E, A, M, AM) reaches J >= 0.50': all(cen[c]['J'] is None or cen[c]['J'] < 0.50 for c in CANDIDATE_CUES),
        'P7 cue A leaves at least one new over-budget label beyond the mask (31 and 70)': len(cen['A']['new_over_budget_vs_mask']) >= 1,
        'P8 extended-middle: cue A leaves at least 5 of the 9 negative spans unrestarted': ext['A']['negatives']['not_restarted'] >= 5,
    }
    reading = dict(identity_all_pass=bool(all(gating)), positive_labels=len(out['datasets'][ORDINARY]['positive_labels']), positive_spans=cen['A']['positives']['spans'],
                   negative_spans=cen['A']['negatives']['spans'], extended_middle_negative_spans=ext['A']['negatives']['spans'],
                   J={c: cen[c]['J'] for c in CUES}, J_vol={c: cen[c]['J_vol'] for c in CUES}, sens25={c: cen[c]['sens25'] for c in CUES}, spec={c: cen[c]['spec'] for c in CUES},
                   informative=[c for c in CANDIDATE_CUES if (cen[c]['J'] if cen[c]['J'] is not None else -1) >= 0.20 and (cen[c]['J_vol'] if cen[c]['J_vol'] is not None else -1) >= 0.20],
                   strongly_informative=[c for c in CANDIDATE_CUES if (cen[c]['J'] if cen[c]['J'] is not None else -1) >= 0.50 and (cen[c]['J_vol'] if cen[c]['J_vol'] is not None else -1) >= 0.50])
    out.update(predictions=preds, reading=reading,
               inputs={n: dict(trace_sha256=chk.PINS[n]['sha'], events_sha256=chk.PINS[n]['events_sha']) for n in chk.PINS},
               committed_inputs={k: hashlib.sha256(open(p, 'rb').read()).hexdigest() for k, p in (('rapid_mute_check_json', COMMITTED_CHECK), ('cut_anatomy_json', COMMITTED_ANATOMY))})
    return out


def report(out):
    print('predictions', json.dumps(out['predictions'], indent=1))
    print('reading', json.dumps(out['reading']))
    for name, e in out['datasets'].items():
        print(f'--- {name}: marked runs {e["marked_runs"]}, cut kinds {e["cut_kinds"]}, coverage {json.dumps(e["coverage"])}')
        for k, v in e['variants'].items():
            print(f'  {k:16s} present {v["present"]:>11,} wrong {v["wrong"]:>11,} gap {v["gap"]:>10,} precision {v["precision_pct"]:7.3f} runs {v["runs"]:>4} over {v["over_budget"]} missed {v["newly_missed"]} passes {v["passes"]}')
        for cue, c in e['census'].items():
            print(f'  cue {cue:7s} sens25 {c["sens25"]}/{c["positives_total"]} spec {c["spec"]} J {c["J"]} | present lost vs mask {c["present_lost_vs_mask"]:,} false removed vs mask {c["false_removed_vs_mask"]:,} G {c["G"]} C {c["C"]} J_vol {c["J_vol"]} | pos {json.dumps(c["positives"])} | neg {json.dumps(c["negatives"])} | new over budget {c["new_over_budget_vs_mask"]} new missed {c["new_missed_vs_mask"]}')


def main():
    if os.path.exists(OUT):
        raise SystemExit('refusing to overwrite ' + OUT)
    out = compute()
    with open(OUT, 'w') as stream:
        json.dump(out, stream, indent=1)
    report(out)


def dry():
    """Exercise every code path of the run without writing or printing any cue-versus-class number (plumbing only)."""
    out = compute()
    print('DRY RUN OK: nothing written, no result printed; identity gates', 'PASS' if out['reading']['identity_all_pass'] else 'FAIL')
    return out['reading']['identity_all_pass']


if __name__ == '__main__':
    if sys.argv[1:] == ['--selftest']:
        raise SystemExit(0 if selftest() else 1)
    if sys.argv[1:] == ['--dry']:
        raise SystemExit(0 if dry() else 1)
    if sys.argv[1:] == ['--run']:
        main()
    else:
        raise SystemExit(__doc__)
