# Cloud processing

All new offloaded processing uses GitHub Actions. The laptop handles editing,
small report downloads and ntfy notifications. Modal is inaccessible; Oracle
signup is unavailable. No new Kaggle jobs should be submitted.

| Work | GitHub route | What success establishes |
| --- | --- | --- |
| Native C++ and VST3 | `.github/workflows/ci.yml` | Source checks, native tests and a packaged plugin |
| Offline synthetic replay | `.github/workflows/offline-replay.yml` | Comparison contracts and synthetic buffer parity |
| Linux configuration | `.github/workflows/linux-sandbox.yml` | Disposable runner configuration checks |
| Recorded corpus and assignment diagnosis | Private `Ajuntanaga/m3-offload` | New offline references and diagnostic reports |

See [the private worker setup](github/README.md) for pinned source dispatch,
input hashes, bounded jobs, artifact collection and ntfy monitoring. The source
repository is public; recordings, calibration and detailed recording results
must remain in the private worker repository. Standard CPU runners do not
provide GPU inference or prove behavior on this laptop's hardware.

The existing ntfy heartbeat follows recorded run IDs without launching jobs.
It preserves installed scores and distinguishes cloud compilation, offline
measurements and live-host verification. It sends inline summaries under
4,000 UTF-8 bytes through the workstation credential helper.

The already-running Kaggle corpus recovery version 2 is a legacy job. Collect
its final report and failure logs before deciding whether any recovery needs
to be repeated on GitHub. Version 1 is terminal ERROR; do not poll or rerun it.
[Historical Kaggle setup notes](kaggle/README-legacy.md) remain available to
interpret those artifacts, not as the route for new work.

Keep raw recordings, labels, calibration, current reports and source
provenance. After a verified upload and a pushed checkpoint, duplicate staging
copies can be removed while preserving their hash manifests. Detailed cloud
artifacts have finite retention; collect useful evidence before it expires.

A successful build or completed replay does not establish live readiness.
Acceptance still requires no lost labels or added false outputs, zero
processing allocations, buffer parity, native timing limits, host behavior
and MIDI lifecycle checks. Overall completion is not measured.
