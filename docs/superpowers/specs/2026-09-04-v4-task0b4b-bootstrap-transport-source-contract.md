# V4 Task 0B4b-bootstrap-transport — fixed bootstrap and raw-helper contract

**Status:** locally implemented and verified; pending independent review before
it can be called sealed. It succeeds sealed Task 0B4b-evidence (`a276949`) and
permits only private fixed-literal loader and standard-stream helper
implementation. It does not authorize a session state machine, child, fixture,
namespace, REAPER, audio, or host operation. The current source SHA-256 is
`5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`.

## Scope

This gate may change `tools/reaper_v4_session.py`, the replacement pre-import
source contract, a controlled bootstrap/transport test module, recovery
records, and this contract/plan. It preserves Task 0A, Task 0B1, every sealed
Task 0B4b pure/admission/evidence behavior test, and both public signatures.
`load_session_config()` and `run_session()` remain immediate `SessionError`
stubs.

The implementation may import only `fcntl`, `select`, and `time` in addition
to the sealed evidence source imports. It may touch only fixed paths
`/run/m3-v4/session-config.sha256` and `/run/m3-v4/session-config.json`, and
only fixed descriptors 0, 1, and 2 for transport. Tests must patch the system
calls or use bounded controlled pipes; they must never open the real `/run`
paths, create a namespace/launcher, establish a barrier, invoke REAPER, or
launch a child.

## Private interfaces

The successor replaces the evidence static contract before source edits and
adds exactly these private interfaces:

```python
def _setup_diagnostic_fd() -> None: ...
def _emit_diagnostic_once(code: str) -> None: ...
def _read_fixed_regular(path: str, maximum: int) -> bytes: ...
def _load_fixed_session_config() -> SessionConfig: ...
def _wait_fixed_pipe(fd: int, event: int, deadline_ns: int) -> None: ...
def _write_frame_once(frame: bytes, deadline_ns: int) -> None: ...
def _read_ack_eof(deadline_ns: int) -> bytes: ...
```

They are module-private implementation edges, not alternate public APIs or
dependency-injection points. The only permitted fixed-fd callers are the later
single session root. Every ordinary `Exception` attributable to data, a
descriptor, poll, or syscall becomes `SessionError`; `BaseException` escapes.

## Required behavior

`_setup_diagnostic_fd()` acts on fd 2 only. It requires a FIFO/pipe and sets
nonblocking mode; failure produces no diagnostic and prevents the loader from
opening either bootstrap path. `_emit_diagnostic_once()` accepts only a
printable ASCII closed code no longer than 64 bytes and performs one
nonblocking fd-2 write attempt of at most the admitted 1024-byte limit. It
never writes stdout, retries, raises for a short write, or catches a
`BaseException`.

`_read_fixed_regular()` accepts only one of the two fixed literals. It opens
once with `O_RDONLY|O_NOFOLLOW|O_CLOEXEC`, requires a one-link regular file,
read-only descriptor/mount state, and bounded complete EOF read, then closes
once. It rejects a bad literal, nonregular/multilink/read-write mount, missing
close-on-exec/read-only flags, a value over its limit, short/error read, or
extra byte. Sidecar is read first with a 64-byte limit; config follows with
the existing 8192-byte bound.

`_load_fixed_session_config()` first prepares fd 2, then reads sidecar and
config in that exact order, calls the sealed parse/digest compatibility helper,
constructs a temporary private `SessionConfig`, and calls the sealed admission
helper before return. It never calls the public loader stub or accepts a path
argument. This proves only local fixed-literal operation under doubles, not
paired-substitution resistance or an actual `/run` mount.

`_wait_fixed_pipe()` validates a fixed pipe descriptor, sets its existing
status flags plus `O_NONBLOCK` before the deadline calculation or poll, uses a
bounded poll with `time.monotonic_ns()`, and refuses timeout, `POLLERR`, or
`POLLNVAL`. A flags-read or flags-write failure is `SessionError` before any
raw read or write.
For a requested `POLLIN`, a `POLLHUP` is admitted only as readiness for the
caller’s immediate bounded read: that read must still prove the ACK byte or
EOF. A hangup never makes a write successful. `_write_frame_once()` uses fd 1 only, requires a nonempty
exact bytes frame no larger than `protocol.MAX_FRAME_BYTES`, verifies pipe
type and `PIPE_BUF >= len(frame)`, waits for writable state, and calls
`os.write(1, frame)` exactly once. A short write, `EINTR`, `EPIPE`, `EAGAIN`,
or other write failure is `SessionError`; it never retries a frame.

`_read_ack_eof()` uses fd 0 only, requires pipe type, waits/reads at most two
bytes under its deadline, requires exactly `b"\x06"`, then an observed EOF on
the next bounded read. Missing, late, wrong, extra, or non-EOF data is
`SessionError`. It returns the single acknowledged byte only after both facts
hold. It does not construct a receipt or start a child.

## Static and behavioral proof

The replacement pre-import contract pins the public surface, exact imports,
helper inventory/signatures, fixed literal paths, no dynamic import/call,
per-helper imported attributes/calls, and forbids all child/barrier/evidence
capture/frame-construction edges. It permits `os.open` only in
`_read_fixed_regular` and requires its first argument to be the local `path`
after literal validation. It permits fd 0/1/2 only in their named helpers and
rejects arbitrary descriptor parameters at public boundaries.

Tests first record RED for missing helpers, then exercise only controlled
syscall/poll doubles or temporary pipes: diagnostic setup/one-write behavior;
sidecar-before-config ordering; descriptor shape/flag/EOF/bounds refusal;
valid parsed/admitted config; one complete stdout write and every refusal;
and ACK plus distinct EOF versus malformed alternatives. They assert observable
outcomes, never that a mock was merely called.

Completion requires the documented REDs, clean replacement static contract,
preserved prior suites, focused bootstrap suite, independent review,
`git diff --check`, a source hash, canonical-note readback, and a commit. It
does not prove real kernel pipe behavior, a live session, fixture safety,
REAPER compatibility, or live MIDI.

## Local implementation evidence

The replacement static contract first failed because the sealed evidence source
had neither the three permitted imports nor the seven helpers. After helper
stubs made that structural contract green, the five controlled bootstrap tests
failed against the stubs. A focused interruption regression then failed because
a close error masked `KeyboardInterrupt`; the final reader preserves that
interruption while still reporting a normal-path close error.

After a targeted RED showed that a closed Linux FIFO can report the second ACK
readiness event as `POLLHUP`, the helper was narrowed to accept that condition
only for a requested `POLLIN`; the immediate bounded read must still establish
EOF. A later targeted RED showed the raw standard streams remained blocking;
the common fixed-pipe waiter now sets `O_NONBLOCK` before polling, with an
explicit flags-failure refusal regression. The focused static/bootstrap command is green with nine checks. The
preserved Task 0B1 static, B4b pure, admission, evidence, bootstrap, and
mock-only state suite is green with 46 checks. These tests use only syscall/poll doubles and
canonical synthetic configuration bytes; no real `/run` path, child,
namespace, REAPER, audio device, or host scan was used.
