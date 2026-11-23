"""One fixed SoA SSE2 batch screen; all native execution belongs on GitHub."""
import re

from tools.portable_exact_cell_sharing import main as _main, run as _run

FLAG = '--diagnostic-batch-cell-update'
SCHEMA = 'm3_batch_cell_update_v1'
CELL_LINE = re.compile(
    r'^m3_replay: batch_cell_update enabled=([01]) supported=([01]) cells=(\d+) guards=(\d+)$',
    re.MULTILINE)


def cell_counts(stderr, enabled):
    matches = CELL_LINE.findall(stderr)
    if len(matches) != 1:
        raise ValueError('Exactly one batch-cell summary required')
    actual, supported, cells, guards = map(int, matches[0])
    if actual != int(enabled) or not supported or cells <= 0 or guards <= 0:
        raise ValueError('Wrong batch mode, unsupported build or no cells/guards exercised')
    return dict(cells=cells, guards=guards)


def run(binary, corpus, manifest_path, reference_path, companion_reference_path,
        output, *, timeout=900):
    return _run(binary, corpus, manifest_path, reference_path, companion_reference_path,
        output, timeout=timeout, diagnostic_flag=FLAG, report_schema=SCHEMA,
        parse_cell_counts=cell_counts)


if __name__ == '__main__':
    _main(runner=run)
