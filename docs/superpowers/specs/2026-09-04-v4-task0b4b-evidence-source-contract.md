# V4 Task 0B4b-evidence — bounded evidence source contract

**Status:** sealed bounded-helper checkpoint under the user's project-wide
authorization. Its source SHA-256 is
`6049ec3096cf9a2fc50678884180fe4e0ef6072032418931f0d48afa14f83a1f`;
the 30-check regression suite and three independent reviews are clean. This
succeeds the sealed admission checkpoint `cf6384f`; it is not a session-run,
fixture, or host-execution authorization.

## 1. Scope

This gate may change only `tools/reaper_v4_session.py`, its replacement
pre-import static contract, a new evidence test module, the recovery records,
and this source contract/implementation plan. It preserves every Task 0A and
Task 0B1 source and every prior Task 0B4b pure/admission regression.

It adds no public API and leaves `load_session_config()` and `run_session()` as
one-statement `SessionError` stubs. It creates no runtime root, callback,
control channel, receipt payload, ACK, barrier, child, namespace, Bubblewrap,
systemd, REAPER, audio, X11 server, network, or host scan.

The source may use only descriptor integers supplied directly by the caller and
temporary controlled descriptors supplied by its tests. It may use `os` and
`stat` only in the named helpers below; it may not open an absolute path,
inspect `/proc`, enumerate ambient descriptors, form a launcher, write to a
descriptor, or read any raw control stream. The future bootstrap-transport and
outer-harness gates own fixed paths, mountinfo acquisition, inherited-FD
census acquisition, raw transport, and real namespace execution.

## 2. Private evidence interfaces

The successor replaces the admission static contract before source edits and
adds exactly these private interfaces. Their inputs are bounded and all ordinary
data/descriptor errors normalize to `SessionError`; `BaseException` is never
caught. Each consumes an admitted, locally owned `SessionConfig` snapshot or
calls `_admit_session_config()` before using configuration data.

```python
@dataclasses.dataclass(frozen=True)
class _EvidenceBaseline: ...

def _capture_environment_baseline(config: SessionConfig, cwd: str, environment: Mapping[str, object]) -> Mapping[str, object]: ...
def _capture_measurement_baseline(config: SessionConfig, root_fd: int) -> Mapping[str, object]: ...
def _capture_scan_baseline(config: SessionConfig, root_fd: int) -> Mapping[str, object]: ...
def _capture_private_tree_baseline(config: SessionConfig, home_fd: int) -> Mapping[str, object]: ...
def _capture_x11_baseline(config: SessionConfig, authority_fd: int, socket_fd: int) -> Mapping[str, object]: ...
def _validate_inherited_fd_census(config: SessionConfig, observed: tuple[Mapping[str, object], ...]) -> tuple[Mapping[str, object], ...]: ...
def _validate_mount_projection(config: SessionConfig, observed: tuple[Mapping[str, object], ...]) -> tuple[Mapping[str, object], ...]: ...
def _certificate_applicability_projection(config: SessionConfig) -> dict[str, object]: ...
def _require_owned_evidence_baseline(baseline: _EvidenceBaseline) -> tuple[int, int, int, int, int]: ...
def _capture_evidence_baseline(config: SessionConfig, measurement_root_fd: int, scan_root_fd: int, home_fd: int, authority_fd: int, socket_fd: int, cwd: str, environment: Mapping[str, object], inherited_fds: tuple[Mapping[str, object], ...], mounts: tuple[Mapping[str, object], ...]) -> _EvidenceBaseline: ...
def _recheck_evidence_baseline(baseline: _EvidenceBaseline, cwd: str, environment: Mapping[str, object], inherited_fds: tuple[Mapping[str, object], ...], mounts: tuple[Mapping[str, object], ...]) -> None: ...
def _release_evidence_baseline(baseline: _EvidenceBaseline) -> None: ...
```

`_EvidenceBaseline` is private, frozen, and directly non-constructible. It
contains the fresh admitted configuration, the five uniquely owned supplied
descriptors, immutable PRE observation snapshots (including cwd/environment),
and a private release flag. A module-private ownership registry retains only
baselines produced by successful capture together with their original
descriptor tuple; `_require_owned_evidence_baseline` rejects forged, missing,
unknown, consumed, or descriptor-mutated values before a recheck or close can
touch a descriptor, and release closes only that registered tuple. Ownership
of the five descriptors transfers only after the configuration has been
admitted. A capture failure after transfer attempts
every owned close once and raises `SessionError` if any close fails; release
marks the baseline consumed and removes its ownership registration before
attempting every close, then raises `SessionError` if any close fails. A
consumed baseline may not be rechecked or released again.

The capture/recheck functions return no receipt or Boolean attestation map.
Successful return is only an evidence precondition. The later state machine may
derive `scan_root_unchanged` only after a successful recheck, exchange
validation, and its own POST ordering.

## 3. Required observations and bounds

`_capture_environment_baseline` receives only an explicitly supplied cwd and
exact built-in environment map; it does not read ambient cwd or `os.environ`.
It deep-snapshots and compares them with the admitted `home`, `pwd`, `cwd`,
and exact six-key environment mapping. The keys must be in the canonical order
`DISPLAY`, `HOME`, `LANG`, `PWD`, `TZ`, `XAUTHORITY`, with no extra key. It
also rejects each forbidden-name presence from the B3 finite list
(`BASH_ENV`, `CLAP_PATH`, `DBUS_SESSION_BUS_ADDRESS`, `ENV`, `LD_AUDIT`,
`LD_LIBRARY_PATH`, `LD_PRELOAD`, `PYTHONHOME`, `PYTHONPATH`,
`SSH_AUTH_SOCK`, `VST3_PATH`, `VST_PATH`, `XDG_CONFIG_HOME`,
`XDG_DATA_HOME`, `XDG_RUNTIME_DIR`). Its immutable result is retained and
must compare unchanged at recheck; it proves only supplied-observation
composition, never a live namespace measurement.

`_capture_measurement_baseline` must require a directory whose `st_dev` and
`st_ino` exactly equal `namespace_expectations.measurement_root`; it converts
the admitted plan to the sealed `MeasurementPlan` and calls the sealed
collector once. Its immutable result contains exactly the root identity and
collector facts/evidence.

`_capture_scan_baseline` must require one supplied directory descriptor, retain
its device/inode identity, and compare the complete descriptor-rooted tree to
the admitted two-entry plan. It opens each implied directory and final file
relative to that supplied descriptor with `O_NOFOLLOW|O_CLOEXEC`; it rejects a
symlink, special file, absent/extra name, wrong mode/size, changed identity, or
digest mismatch. It reads each regular file in chunks no larger than 64 KiB,
rejects more than 32 MiB total, and returns only immutable device/inode/entry
facts. It never receives or opens an absolute scan path.

`_capture_private_tree_baseline` requires an owned directory descriptor with
mode `0700`; it requires the exact named `.vst` and `.vst3` directories to be
directories and empty. `_capture_x11_baseline` requires an owned readable
regular authority descriptor with one link, the configured mode/size/SHA-256,
and a retained destination device/inode; it also requires the supplied socket
descriptor to be a socket with the configured owner/mode/device/inode.

The FD-census and mount-projection helpers are comparison/retention helpers in
this gate: they deep-snapshot exact supplied observations and compare them
byte-for-byte to the admitted descriptor/mount policy. They do not enumerate
`/proc` or claim a live namespace. The mount helper also proves that the mount
covering private home has the admitted filesystem/read-only state and that the
scan-root mount relation is present. `_certificate_applicability_projection`
returns a fresh, closed, non-authoritative projection of the configuration and
both certificate records needed by the later state gate; it neither measures
nor asserts external certificate applicability.

The recheck repeats every descriptor-rooted measurement, scan tree, private
tree, authority/socket identity, supplied cwd/environment, mount projection,
and supplied FD census from the retained baseline. Any change, unreadability,
malformed observation, or ordinary descriptor error raises `SessionError` and
leaves the later state gate without terminal POST authority.

## 4. Source restrictions and static contract

The replacement pre-import test must pin the exact public surface, imports,
private helper inventory, dataclass fields/signatures, and fail-closed public
stubs. It must forbid dynamic imports/calls, raw transport, callbacks,
subprocesses, path APIs, `/proc`, `os.write`, `os.pipe`, `os.dup`, `os.listdir`
outside scan/private-tree helpers, and every `os` attribute outside the named
descriptor evidence helpers. It must require `O_NOFOLLOW` and `O_CLOEXEC` on
every relative `os.open`, the 64 KiB/32 MiB bounds, one collector call per
measurement capture/recheck, exact release-state checks, and no receipt,
barrier, frame encoder, child-runner, or mountinfo edge.

After implementation it also pins the exact session-source SHA-256. The hash
is an additional source seal, not an authority expansion.

## 5. Tests and completion

Tests import the session source only after the new static gate passes. They use
only `TemporaryDirectory`, temporary regular files/directories, a temporary
Unix-domain socket, supplied descriptor integers, and supplied immutable FD/
mount observation tuples. They must cover:

1. successful capture, deterministic post recheck, and single release;
2. supplied cwd/environment mismatch, missing/extra key, and every forbidden
   name refusal without reading ambient process state;
3. measurement-root identity/resource refusal;
4. scan extra-tree, symlink, mode/size/hash, and post-change refusal;
5. private-home nonempty/wrong-mode refusal;
6. authority link/mode/size/hash and socket identity refusal;
7. malformed/mismatched FD and mount observation refusal;
8. certificate projection freshness and absence of an attestation map;
9. forged-baseline rejection before any descriptor operation, capture-failure
   cleanup uncertainty, release-close error handling, and legitimate-baseline
   descriptor-tuple mutation rejection.

Completion recorded REDs before the production repairs, a clean replacement
static gate, preserved Task 0B4b helper/admission tests, 30 passing focused
checks, three independent source reviews, `git diff --check`, this source
hash, canonical-note readback, and the checkpoint commit. It proves bounded
helper behavior only; it does not prove a real namespace, private mount,
parent certificate, REAPER compatibility, or live MIDI operation. The next
implementation gate is Task 0B4b-bootstrap-transport.
