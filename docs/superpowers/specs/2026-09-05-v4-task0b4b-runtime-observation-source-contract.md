# V4 Task 0B4b-runtime-observation — fixture-ready evidence acquisition

**Status:** locally verified implementation checkpoint, pending source review.
This bounded successor replaces the three runtime-observation stubs only. It consumes the already-admitted
configuration and feeds the existing descriptor-rooted evidence helpers; it
does not change Task 0A, Task 0B1, receipt assembly, raw framing, barrier,
child adapter, namespace launcher, REAPER, audio, X11 client traffic, network,
or host fixture authority.

## Exact surface

The successor implements:

```python
def _open_runtime_evidence_descriptors(
    config: SessionConfig,
) -> tuple[int, int, int, int, int]: ...

def _observe_runtime_descriptor_census(
    config: SessionConfig, retained: tuple[int, int, int, int, int],
) -> tuple[Mapping[str, object], ...]: ...

def _read_runtime_mountinfo() -> bytes: ...

def _observe_runtime_mount_projection(
    config: SessionConfig,
) -> tuple[Mapping[str, object], ...]: ...
```

and replaces only:

```python
_capture_runtime_evidence(config)
_recheck_runtime_evidence(baseline)
_release_runtime_evidence(baseline)
```

No public API or alternate coordinator is added.

## Observation rules

`_capture_runtime_evidence` first re-admits the supplied configuration and
samples the inherited FD census, supplied process cwd/environment, and bounded
mount projection before it opens evidence paths. It then opens exactly the
five admitted paths once: measurement root, scan root, private home,
Xauthority, and X11 socket. Directory paths use directory/no-follow/close-on-
exec flags; Xauthority is a no-follow regular-file candidate; the socket uses
`O_PATH|O_NOFOLLOW|O_CLOEXEC`. Any partial open is closed exactly once. On
success it transfers exactly those five descriptors to
`_capture_evidence_baseline`; on failure it leaves no new owned descriptor.

The FD census is bounded by a fixed 64-descriptor ceiling and a compatible
soft `RLIMIT_NOFILE`; it probes descriptors without opening `/proc`, requires
that the only descriptors before capture are the configured pipe records
0/1/2, and permits exactly the retained five descriptors during recheck.
All other live descriptor numbers refuse. The return value is the existing
three-record descriptor-policy projection.

The mount reader opens only `/proc/self/mountinfo`, requires a bounded regular
EOF-delimited byte stream, and closes its reader once. The parser accepts only
well-formed printable ASCII records, projects exactly the admitted mount paths
in configuration order, derives a bind classification only from a non-root
mount root, and refuses an unknown mount below the scan root. It never returns
or exposes raw mountinfo bytes.

`_recheck_runtime_evidence` obtains the registry-owned descriptor tuple,
resamples cwd/environment, the descriptor census (allowing only that tuple),
and mount projection, then delegates exactly once to the existing retained
baseline recheck. `_release_runtime_evidence` delegates exactly once to the
existing registry-backed release. Ordinary observation and cleanup errors
become `SessionError`; `BaseException` is never swallowed.

## Test boundary

Tests use only the existing temporary controlled evidence fixture, duplicated
fixture descriptors, monkeypatched syscall/resource/mountinfo observations,
and a socket pair. They must prove capture/recheck/release, partial-open
cleanup, bounded FD census refusal, exact mount projection/no-extra-scan-mount
refusal, and no runtime observation on invalid admission. No test may create a
namespace or mount, run a child, read the host mount table, access real `/run`,
or form a REAPER/Bubblewrap/systemd command.

## Local result

Source SHA-256:
6a2bbdfee29c26253ffb4a8f05c62feeab207ea21942aa40368a9ac9e8fcdc1c.

The focused V4 suite completed 57 tests: the immutable Task 0B1 static
contract, the pre-import session source contract, pure/admission/evidence/
bootstrap/state/payload regressions, and six controlled runtime-observation
vectors. Those vectors exercised fixture-descriptor handoff, retained
recheck/release, bounded descriptor-census closure, mount projection, partial
open cleanup, invalid-admission non-observation, and bounded mountinfo read
closure. This is not a namespace, Bubblewrap, REAPER, X11-client, audio,
network, or host-fixture result.
