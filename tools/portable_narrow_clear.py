"""One fixed redundant-clear CPU screen; native execution belongs on GitHub."""
import re

from tools.portable_exact_cell_sharing import main as _main, run as _run

FLAG = '--diagnostic-elide-narrow-clears'
SCHEMA = 'm3_narrow_clear_v1'
CLEAR_LINE = re.compile(
    r'^m3_replay: narrow_clears enabled=([01]) quiet=(\d+) updates=(\d+) performed=(\d+) skipped=(\d+)$',
    re.MULTILINE)


def clear_counts(stderr, enabled):
    matches = CLEAR_LINE.findall(stderr)
    if len(matches) != 1:
        raise ValueError('Exactly one narrow-clear summary required')
    actual, quiet, updates, performed, skipped = map(int, matches[0])
    if actual != int(enabled) or quiet <= 0 or updates != 0:
        raise ValueError('Wrong clear mode, no quiet samples or low-fret mode exercised')
    if performed + skipped != quiet:
        raise ValueError('Clear counters do not cover every quiet sample')
    if (enabled and performed != 0) or (not enabled and skipped != 0):
        raise ValueError('Unexpected clearing/skipping for the frozen max-fret-24 screen')
    # The common runner compares these invariant counts across the pair. Raw
    # performed/skipped values remain in the captured stderr for both arms.
    return dict(quiet_samples=quiet, updates=updates)


def run(binary, corpus, manifest_path, reference_path, companion_reference_path,
        output, *, timeout=900):
    return _run(binary, corpus, manifest_path, reference_path, companion_reference_path,
        output, timeout=timeout, diagnostic_flag=FLAG, report_schema=SCHEMA,
        parse_cell_counts=clear_counts)


if __name__ == '__main__':
    _main(runner=run)
