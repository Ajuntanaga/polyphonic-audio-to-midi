# V4 Task 0B3 — Single Session-Owner Design

**Status:** design-only; Task 0B3a root shell, Task 0B3b pure receipt gate,
Task 0B3c descriptor gate, Task 0B3d child-adapter gate, Task 0B4a contract,
and Task 0B4b-pure compatibility-helper checkpoint are sealed. Task
0B4b-state-contract documentation checkpoint is sealed. The
remaining order is admission-pure, evidence, bootstrap-transport, and mock-
only state gates; then B4c-design, Task 0B5/closure/fixture-manifest review,
and B4c-execution.

**Authority:** This Task 0B3 record defines a future in-namespace session-owner
contract. By itself, it authorizes no module import, component invocation,
fixture, namespace, Bubblewrap/systemd/REAPER command, GUI/X11/audio/network
action, or host mutation. The separately scoped Task 0B3a source contract may
authorize source bytes and a pre-import static verifier only; it does not alter
immutable Task 0A or make a Task 0B1 library admissible.

## 1. Decision

One later, separately authorized source component—
`tools/reaper_v4_session.py`—is the sole in-namespace **runtime root**. Its
exact closure role is:

```text
kind = "session_entrypoint"
role = "same_namespace_pre_ack_child_post_owner"
```

It alone owns the state transition:

```text
validated configuration -> PRE -> parent ACK+EOF -> one child -> POST+EOF
```

It is not a fifth Task 0B1 artifact. It cannot be imported or executed until a
later scoped authority; Task 0B3a may author its source and static verifier
only. A later reviewed closure may include helper modules, but they are
reachable implementation details only: none may become a second runtime root,
coordinator, receipt writer, or child admission path. Until an independently
reviewed successor closure proves this one root reaches immutable Task 0A and
all three Task 0B1 runtime libraries, the only permitted closure state remains:

```text
BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)
```

Task 0B3a reserved this root identity and public API as a deliberately
**non-admissible skeleton**. Task 0B4b-pure retains the same two
immediate-failure public functions and adds only bounded in-memory
compatibility helpers; it performs no configuration I/O, clocks, diagnostics,
descriptor access, frame/ACK work, measurement, or child work. Its private
Task 0A base-config projection is not a public validation/admission entrypoint.
Those imports/helpers do not prove executable runtime reachability or
permit a successor Task 0B0 closure to become a fixture candidate. The detailed
execution rules in this record are reserved intact for the later Task 0B4
state-machine gate. That source and its mocked/in-process tests do not
themselves create the outer namespace harness required to prove raw-scope
recovery or host compatibility.

No second coordinator, fallback runner, alternate receipt writer, or
out-of-namespace control channel is permitted.

```mermaid
flowchart LR
  A["sealed SessionConfig"] --> B["barrier + provenance-backed preflight"]
  B --> C["validate and atomically emit PRE seq 0"]
  C --> D["parent validates then sends ACK + EOF"]
  D --> E["admit one exact ChildSpec"]
  E --> F["reap child and post-measure"]
  F --> G["validate and atomically emit POST seq 1 + EOF"]
  G --> H["outer controller confirms scope exit and writes artifacts"]
```

The outer controller remains the only owner of retained control-root dirfds,
markers, and durable receipts. The session owner receives none of them.

A later source-free execution-surface bootstrap may invoke the two public
session functions only. It exits nonzero and emits no text or traceback for a
`SessionError` or an escaping `BaseException`; it is not a second state-machine
root and cannot add a diagnostic, policy decision, receipt, or child path. Its
exact identity remains a separate policy-bound review item.

## 2. Existing component boundaries

The future session root composes these fixed boundaries; it must not duplicate
or weaken them.

| Component | Permitted future role | Must not do |
| --- | --- | --- |
| Task 0A protocol | Canonical bounded frame envelope and base-identity validation; process barrier primitive | Read/write a control stream, admit a child, or form a command |
| Task 0B1 receipt schema | In-memory PRE/POST/ACK value and relation validation | Read descriptors, consume ACK EOF, measure state, or emit a frame |
| Task 0B1 measurements | Explicit-plan, bounded metadata collection after its own authority | Walk ambient paths, frame I/O, or launch a child |
| Task 0B1 child runner | One exact child adapter after admission | Decide admission, consume ACK, emit PRE/POST, retry, or use a fallback |
| Outer controller | Scope lifetime, PID census, retained-dirfd artifacts, and final classification | Delegate control-root ownership into the namespace |

The session root owns only the missing composition: immutable configuration
admission, raw standard-stream exchange, evidence assembly, exact ChildSpec
binding, and conservative in-scope failure reporting.

### 2.1 Task 0B4 implementation boundary

The Task 0B4 source must compose the sealed components without changing their
APIs. It has four non-negotiable compatibility rules:

1. `validate_pre_payload` and `validate_post_payload` return immutable receipt
   snapshots. Task 0A's encoder accepts a top-level mapping but its JSON step
   cannot serialize the validator's nested mapping proxies. The session owns
   the exact-built-in requirement locally: it validates a bounded exact-built-
   in PRE or POST payload, retains that exact unaliased payload for the
   exchange relation, and passes that same payload to
   `protocol.encode_frame`. It must never loosen the Task 0A encoder or
   serialize a mutable replacement after validation.
2. A deeply frozen admitted `SessionConfig` cannot be passed directly to Task
   0A, whose base-config validator rejects the frozen top-level mapping. The
   session materializes one private, bounded exact-built-in base-config
   projection from the admitted snapshot, validates it immediately, and never
   exposes or reuses a mutable projection as authority.
3. Every ordinary `Exception` escaping a mandatory configuration, barrier,
   evidence, receipt, protocol, raw-transport, or child dependency is
   translated to `SessionError`. Before entering the PRE write it emits no
   bytes; a PRE-write failure may leave incomplete or complete-but-unconfirmed
   PRE bytes and starts no child; after a complete PRE but before the POST
   write it emits PRE-only uncertainty; and a POST-write failure may leave
   incomplete or complete-but-unconfirmed POST bytes but never an accepted
   terminal result. The one best-effort fd-2 diagnostic write is
   the explicit exception: its short write, interruption, or other failure is
   ignored exactly as the raw-transport contract requires. A `BaseException`
   before a PRE-write attempt escapes without a frame; one during either
   mandatory write attempt has that write's possibly incomplete or complete-
   but-unconfirmed byte state, and one after a recorded complete PRE but before
   a POST-write attempt is PRE-only. The silent bootstrap is the sole place
   that converts an escaping `BaseException` to a nonzero no-traceback process
   result. Outer acceptance always requires a clean process and scope result,
   never merely an observed absence of bytes. This does not prove direct-child
   reaping, scope exit, or a PID census; those remain outer-controller duties.
4. New private evidence helpers in the session must have named bounded inputs,
   outputs, and negative tests before use. They may not use `subprocess`, form
   a Bubblewrap/systemd/REAPER command, invent an all-true attestation, or
   turn a mocked observation into fixture evidence. The source contract must
   list each helper and its closure edge before it can claim an admissible
   PRE fact.

The original wording that treated one controlled fixture as sufficient for all
of the following has been corrected. A session module can be tested with
in-process transport and evidence doubles, but an actual fixed-path,
namespace/mount/X11/FD/proc fixture additionally needs the parent scope,
concurrent drains, outer teardown, and PID census. Those facilities are not
available to the session root or to the current Task 0B4 source/test scope.

## 3. Future SessionConfig admission contract

The future source accepts a descriptor-pinned read-only canonical JSON file and
its independent digest sidecar at exactly these two sandbox paths:

```text
/run/m3-v4/session-config.json
/run/m3-v4/session-config.sha256
```

The parent pins and retains the exact source bytes, source identities, and both
mount inputs before Bubblewrap creates the mounts. The sidecar contains exactly
64 lower-case hexadecimal bytes and no newline. The session command receives
only the two fixed paths as its configuration arguments; it accepts no ambient
configuration path, environment override, control descriptor, optional
argument, or digest-valued argv argument.

The configuration digest is SHA-256 over canonical UTF-8 JSON with
`session_config_sha256` omitted. The session opens the sidecar first, then the
configuration, each once with bounded no-follow, close-on-exec, regular,
one-link, read-only-mount checks and complete EOF reads. It requires:

```text
computed configuration digest == embedded session_config_sha256 == sidecar bytes
```

The sidecar is an outer-parent bootstrap trust anchor. It is deliberately not
included in `direct_input_digests`, `session_policy_sha256`, or any manifest
digest stored inside the SessionConfig: putting it in a config-derived digest
would make the configuration hash recursive. The parent records the pair in
its retained outer launch state and descriptor-pins both mount sources. A
same-byte host-path replacement or a paired substituted JSON/sidecar pair is
prevented by that retained parent identity, not by local hash equality. Inside
the namespace the sidecar detects disagreement and the session rejects a
changed content digest, symlink, nonregular file, link-count change, or
noncanonical replacement before PRE. Any malformed, duplicate, missing, extra,
stale, or digest-mismatched configuration fails before PRE and starts no child.

For this contract, canonical JSON means exact built-in `null`, Boolean,
integer, string, list, and object values only; no float, duplicate key,
whitespace variation, or non-ASCII path/identifier value; object keys sorted by
their printable-ASCII byte order; UTF-8; and `,`/`:` separators. The later
source/schema task must use identical canonical rules and cross-test its base
configuration/frame results against immutable Task 0A. It must not modify Task
0A or assume Task 0A's 2 KiB frame encoder can serialize the separately bounded
8 KiB SessionConfig/certificate records.

`schema` and `namespace` must exactly equal their `base_config` counterparts.
`namespace_policy_sha256` is SHA-256 of canonical JSON exactly over
`namespace_expectations`. `session_policy_sha256` is SHA-256 of the canonical
policy projection containing exactly `row`, `direct_input_digests`, the three
manifest digests, `namespace_policy_sha256`, `fixture_certificates`, `bwrap`,
`namespace_expectations`, `child`, and `limits`. `base_config.inputs` must be
exactly the canonical union of
`direct_input_digests` and `{"session_policy": session_policy_sha256}`; the
normal Task 0A `config_sha256` is then recomputed and validated over that
complete base configuration. This binds the full immutable policy and the
selected direct input hashes to the existing sealed PRE/POST identity without
changing the receipt grammar.

The parent retains the complete canonical SessionConfig bytes and digest and
compares all later PRE/POST values with them. `base_config.config_sha256` stays
the sealed Task 0A configuration identity; it is never the SessionConfig
digest and the two digests must not be conflated. A changed `child.argv`,
certificate, expectation, manifest, or limit necessarily changes
`session_policy_sha256` and therefore changes the Task 0A receipt identity.

Its future closed top-level shape is:

```text
{
  schema,
  namespace,
  session_config_sha256,
  base_config,
  session_policy_sha256,
  direct_input_digests,
  row,
  runtime_manifest_sha256,
  run_input_manifest_sha256,
  fixture_manifest_sha256,
  namespace_policy_sha256,
  fixture_certificates,
  bwrap,
  namespace_expectations,
  child,
  limits
}
```

All keys are exact; values are printable ASCII where a path or identifier is
needed, canonical lower-case hex where a digest is needed, and bounded exact
built-in containers only. Booleans never satisfy integer fields.

Every configuration-defined absolute path is either `/` or at most 512 ASCII
bytes, begins with one `/`, has one through 16 nonempty components of one
through 64 bytes drawn only from `[A-Za-z0-9._-]`, has no `.`/`..` component,
repeated slash, or trailing slash, and is compared byte-for-byte in that
normalized form. The future source opens such a path component-by-component
from a retained `/` anchor using `O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` for
`/` and every intermediate directory. It opens a final regular file readable as
`O_RDONLY|O_NOFOLLOW|O_CLOEXEC` relative to the retained parent dirfd, and a
final directory as `O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`. A final X11
socket is opened as `O_PATH|O_NOFOLLOW|O_CLOEXEC` relative to the retained
parent dirfd and must satisfy `stat.S_ISSOCK` before its owner/mode/device/inode
are used. It rejects any symlink or unexpected type before use. The two fixed
bootstrap paths are literals under this same grammar.

Parsed SessionConfig structural accounting is exact: charge one node for the
root and each scalar/list/object value; object keys are not nodes. The root has
depth zero, every contained value increments depth by one, and an object/list
at depth 15 may contain only scalars at depth 16; no value may exceed depth 16.
The total charged nodes must not exceed 256. This traversal occurs over the one
bounded exact-built-in snapshot before semantic validation.

The nested members are also closed. A later source/schema task must use these
exact member sets, not an extensible configuration map:

```text
fixture_certificates = {
  proc_ptrace_barrier,
  control_visibility
}

bwrap = {path, version, argv_sha256}

namespace_expectations = {
  home, pwd, cwd,
  environment,                 # exactly HOME, PWD, DISPLAY, XAUTHORITY, LANG, TZ
  user_namespace,
  x11_identity,
  measurement_root,            # exactly path, device, inode
  measurement_plan,            # exactly resources, expected
  private_tree,
  scan_root,
  descriptor_policy,
  control_visibility
}

child = {argv, cwd, environment, timeout_ms}

limits = {
  pre_deadline_ms, ack_deadline_ms, post_deadline_ms,
  diagnostic_max_bytes, max_frame_bytes, child_timeout_ms
}
```

Their exact nested shapes are:

```text
user_namespace = {
  policy_sha256, effective_uid, effective_gid, uid_map, gid_map, setgroups
}
uid_map/gid_map = [{inside_id, outside_id, length}]

x11_identity = {display, display_number, screen, protocol, authority, socket}
authority = {
  path, source_device, source_inode, destination_mode, destination_size, sha256
}
socket = {path, kind, uid, gid, mode, device, inode}

private_tree = {home_mount, empty_directories}
home_mount = {path, filesystem_type, mode, writable}

scan_root = {path, entries, mount_points}
entries = [{relative_path, input_name, mode, size, sha256}]
mount_points = [{relative_path, readonly}]

descriptor_policy = {fd_policy_sha256, inherited_fds}
inherited_fds = [{fd, kind, role}]

control_visibility = {mount_policy_sha256, namespace_root_kind, mounts}
mounts = [{path, filesystem_type, readonly}]
```

`uid_map` and `gid_map` are lists of one through eight exact non-Boolean
integer triples, sorted by `inside_id` and non-overlapping in both inside and
outside ranges; `setgroups` is exactly `"deny"`. `effective_uid` and
`effective_gid` are non-Boolean integers represented by a permitted mapping.
`socket.kind` is exactly `"unix_socket"`. `private_tree.empty_directories` is
exactly `[".vst", ".vst3"]`; `home_mount.filesystem_type` is exactly `"tmpfs"`,
`home_mount.mode` is `0o700`, and `home_mount.writable` is true. That mount
describes the private writable home used to prove those two directories are
bounded-empty.

`authority.source_device` and `authority.source_inode` are parent-only
descriptor-pinning provenance. Because a future `--ro-bind-data` mount may
copy a regular Xauthority file, the session must not compare those source
identities to the in-namespace destination. It instead requires the destination
to be a no-follow regular one-link file with `destination_mode`,
`destination_size`, and `sha256`, captures its destination device/inode before
PRE, and compares that retained destination baseline before POST.

The selected fixture vector has exactly two nested scan-root entries. Each
entry's `sha256` must equal
`direct_input_digests[entry.input_name]`; only directories implied by those two
relative paths may exist. `mount_points` is exactly `"."` plus the two file
mount paths, all read-only. The session derives the receipt's
`production_bundle_absent` claim only from that exact no-extra tree comparison.
Within `scan_root.mount_points`, `"."` denotes `scan_root.path` itself rather
than a string concatenation ending in `/.`; every other member is joined by one
slash only after its relative-path grammar has been validated.

Every `entries.relative_path` has one through eight printable-ASCII components
of one through 64 bytes drawn only from `[A-Za-z0-9._-]`; no component is `.`
or `..`, no path begins or ends with `/`, and the two paths are byte-sorted,
unique, and neither is a prefix of the other. Each entry is a no-follow regular
file, has a non-Boolean `mode`, a non-Boolean size no greater than 16 MiB, and
is hashed by a 64 KiB streaming buffer. The combined expected entry size is at
most 32 MiB. Every implied directory is opened no-follow and may contain only
its named descendants; any symlink, special file, unexpected directory, or
extra entry fails before PRE.

The session reads at most 64 KiB/128 records of `/proc/self/mountinfo`, at
most 16 inherited FD entries, at most eight 256-byte records from each of
`/proc/self/uid_map`, `/proc/self/gid_map`, and `/proc/self/setgroups`, and at
most 64 KiB of the Xauthority file (whose declared size must fit that limit).
These are hard byte/record caps independent of the five-second deadline. The
future source reads regular entries and authority data in 64 KiB bounded chunks
rather than allocating their contents as one object.

The initial FD census has one exact, bounded mechanism. Before opening any
component-path, scan-root, measurement, X11, or mountinfo descriptor, the
session performs exactly one non-recursive `os.listdir("/proc/self/fd")` scan.
It accepts at most 16 numeric ASCII names, and requires four entries: the
three declared inherited FDs plus exactly one transient iterator FD created
and closed by that single scan. It `fstat`s the declared three against
`descriptor_policy`. The sole other listed number must immediately fail
`fstat` with `EBADF`; it is the only permitted iterator artifact. A second
extra entry, a successful `fstat` of the extra number, no transient artifact,
or any other error suppresses PRE. The next descriptor open may occur only
after this census has completed. The two bootstrap descriptors are already
closed before it; fd-2 `fstat`/nonblocking setup itself opens no descriptor.
This deliberately fails closed if a future target Python has different
`os.listdir` iterator behavior; the later non-REAPER fixture gate must prove
the pinned interpreter behavior before this root can become admissible.

`descriptor_policy.inherited_fds` is exactly the ordered three-entry list:

```text
{fd: 0, kind: "pipe", role: "ack_input"}
{fd: 1, kind: "pipe", role: "receipt_output"}
{fd: 2, kind: "pipe", role: "diagnostic_output"}
```

`user_namespace.policy_sha256` is the SHA-256 of canonical JSON exactly over
`{effective_uid, effective_gid, uid_map, gid_map, setgroups}`.
`descriptor_policy.fd_policy_sha256` is the SHA-256 of canonical JSON exactly
over `{inherited_fds}`. `control_visibility.mount_policy_sha256` is the
SHA-256 of canonical JSON exactly over `{namespace_root_kind, mounts}`. The
session recomputes all three before PRE and requires them to match the relevant
certificate applicability values.

`namespace_root_kind` is exactly `"private_tmpfs_root"`. `mounts` is an ordered
list of 1 through 64 unique absolute printable-ASCII mount paths, byte-sorted
under the absolute-path grammar, each with an exact printable-ASCII filesystem
type and Boolean read-only state. It is the complete expected in-namespace
mount projection: a later session parses at most 128 mountinfo records,
accepting only the kernel octal escapes `\040`, `\011`, `\012`, and `\134` in
a mount path, rejects any other escape or decoded noncanonical path, then
compares the decoded projection exactly. It rejects an unknown, duplicate,
missing, or mismatched mount. The host control-root path is never placed in
SessionConfig. For every `scan_root.mount_points` member, the absolute path
formed from `scan_root.path` plus that member's relative path must occur once
in `control_visibility.mounts` with the same read-only state; no other listed
mount may be strictly below `scan_root.path`.

Each complete mount projection is taken by exactly one no-follow,
close-on-exec open of `/proc/self/mountinfo`. It reads in bounded chunks through
byte 65,537 solely to detect overflow, rejects a 65,537th byte, rejects a 129th
record, demands EOF after an otherwise bounded 64 KiB/128-record stream, and
closes the descriptor before comparing the exact decoded projection. This is
performed once before PRE and once after the child; it never stops early at a
valid prefix that could omit a later mount.

`direct_input_digests` is a closed map of 1 through 15 lower-case direct input
names to 64-hex SHA-256 values. It exactly matches the parent-retained selected
row's manifest-declared receipt-input map and cannot use the reserved name
`session_policy`. The resulting Task 0A `inputs` map has 2 through 16 entries:
that map is the only receipt representation of the direct input hashes, and it
must be byte-identical in PRE and POST. The SessionConfig JSON and its digest
sidecar are bootstrap artifacts, not direct inputs: neither may appear in this
map or in a manifest digest that SessionConfig itself carries.

`environment` and `child.environment` are exact six-member maps with the
lexicographically ordered names shown above; they must compare byte-for-byte.
The following cross-field relations are mandatory before PRE:

```text
home == pwd == cwd == environment.HOME == environment.PWD
     == child.cwd == child.environment.HOME == child.environment.PWD
     == private_tree.home_mount.path

x11_identity.display == environment.DISPLAY == child.environment.DISPLAY
x11_identity.authority.path == environment.XAUTHORITY
                             == child.environment.XAUTHORITY
x11_identity.socket.path == "/tmp/.X11-unix/X" + decimal(x11_identity.display_number)
x11_identity.display == ":" + decimal(x11_identity.display_number)
                      or ":" + decimal(x11_identity.display_number)
                         + "." + decimal(x11_identity.screen)
x11_identity.protocol == "MIT-MAGIC-COOKIE-1"
```

`display_number` and `screen` are non-Boolean integers in `0..2147483647`; an
omitted display screen is therefore represented by the first permitted display
form with `screen == 0`. The receipt's fixed X11 projection is exactly
`{display, authority: authority.path, socket: socket.path, screen, protocol}`;
the source may not substitute a second path or inferred socket. The session
rejects any mismatch before it opens a child.

`measurement_root` is a positive non-Boolean device/inode pair with an absolute
manifest-declared sandbox path. The scan root deliberately has no predeclared
device/inode pair: its private tmpfs identity is created inside the namespace.
The session opens it before PRE, captures its device/inode, mount-table, exact
tree, and file hashes in a retained baseline, then compares that same baseline
after the child to derive `scan_root_unchanged`. `private_tree` and `scan_root`
facts are true only after the provenance requirements in Section 4 are met.

`measurement_plan.resources` is an ordered list of 1 through 16 unique,
single-component printable-ASCII relative names (at most 256 bytes each).
`measurement_plan.expected` has exactly the same names and each value is
exactly `{mode, size}`, where `mode` is a non-Boolean integer in `0..0o7777`
and `size` is a non-Boolean nonnegative integer. Before launching the scope,
the parent compares this one plan and its root identity with the manifest;
inside the namespace, the session converts the exact resource list to the
collector's tuple and accepts only descriptor-rooted facts matching it. There
is no second measurement-plan or ambient resource source.

The limits record is deliberately fixed for the future non-REAPER session
fixture, not caller-selectable:

```text
pre_deadline_ms=5000, ack_deadline_ms=5000, post_deadline_ms=5000,
diagnostic_max_bytes=1024, max_frame_bytes=2064, child_timeout_ms=30000
```

`child.timeout_ms` must equal `limits.child_timeout_ms`.
`max_frame_bytes` equals the current Task 0A maximum and must also fit the
queried `PIPE_BUF`. The canonical SessionConfig itself is at most 8,192 bytes,
has at most 256 structural nodes and depth 16, permits at most 16 argv members
of at most 512 printable-ASCII bytes each, and has no duplicate JSON key.
Any altered limit, Boolean integer, oversized byte/string/container count, or
additional nested key fails before PRE; a later reviewed schema may only change
these constants by explicit amendment.

| Member | Required binding |
| --- | --- |
| `schema`, `namespace`, `base_config`, `session_policy_sha256`, `direct_input_digests` | Task 0A identity. `base_config` is exactly `{schema, namespace, nonce, config_sha256, inputs}`; its inputs are the direct manifest input hashes plus `session_policy`, and Task 0A revalidates them. |
| `row` | Exactly `{sample_rate_hz: 44100, block_size: 32}`. No other V4 row is admitted by this design. |
| `runtime_manifest_sha256`, `run_input_manifest_sha256`, `fixture_manifest_sha256`, `namespace_policy_sha256` | Sealed identities supplied and independently retained by the parent. The session carries only the admitted values; the parent compares later receipt values to its retained state. The run-input manifest, not the receipt, binds the private scan-root entry list and hashes. `namespace_policy_sha256` binds the complete `namespace_expectations` object and must equal the certificate applicability field. The manifests exclude the self-referential SessionConfig bootstrap pair. |
| `fixture_certificates` | The two complete canonical parent-validated certificate records described below. The session rehashes and cross-binds their declared policy/manifests/results; a missing, unknown, or mismatched record suppresses PRE. |
| `bwrap` | Exact absolute path, version text, and complete-argv digest held and independently validated by the parent. The session does not claim it can observe the parent’s complete Bubblewrap argv. |
| `namespace_expectations` | Exact `HOME`, `PWD`, `cwd`, environment map, user-namespace mapping, descriptor-pinned X11 record, one `measurement_root` identity, bounded private-tree and scan-tree evidence, and mount/descriptor visibility policy. |
| `child` | One immutable `argv`, exact `cwd`, exact environment, and bounded timeout later used to construct one `ChildSpec`. |
| `limits` | Explicit bounded protocol, diagnostic, frame, measurement, and child-lifetime limits; no field may select a fallback or extend a deadline dynamically. |

`fixture_certificates` must include the two full distinct, digest-bound records
for:

1. the non-dumpable, capability-free proc/ptrace barrier and its negative
   `/proc/<session-pid>/fd/1` and `/proc/<session-pid>/mem` fixture proof; and
2. the exact mount/FD policy proving that no V4 control-root path or retained
   control descriptor crosses into the namespace.

These are certificates the parent validates against the reviewed fixture and
namespace policy. They are carried as admitted full records so the session can
rehash their canonical bytes and compare their applicable policy/manifests to
SessionConfig. The session may attest their result only after it also checks the
configuration binding and its own allowed descriptor/mount state. It must not
turn a local Boolean or a receipt self-assertion into proof.

Each future certificate is itself closed canonical JSON with these exact
members:

```text
{
  schema, kind, certificate_sha256, fixture_evidence_sha256,
  session_source_sha256, runtime_manifest_sha256, fixture_manifest_sha256,
  bwrap_path, bwrap_version, bwrap_argv_sha256,
  namespace_policy_sha256, mount_policy_sha256, fd_policy_sha256,
  kernel_release, boot_id, uid, user_namespace_policy_sha256, result
}
```

Every certificate has `schema` as exact non-Boolean integer `1`; every
`*_sha256` and `certificate_sha256` is 64 lower-case hexadecimal bytes;
`kernel_release` is printable ASCII of 1 through 128 bytes; `boot_id` is the
lower-case 36-byte UUID form `8-4-4-4-12`; and `uid` is a non-Boolean integer
in `0..2147483647`. `bwrap_path` follows the absolute-path grammar,
`bwrap_version` is printable ASCII of 1 through 128 bytes, and `kind` is one of
the two exact literals below. All device and inode identities throughout
SessionConfig are non-Boolean integers in `1..9223372036854775807`; all size
fields are non-Boolean integers in `0..16777216`; every `mode` field means
`stat.S_IMODE(st_mode)` and is a non-Boolean integer in `0..0o7777`.

For both admitted certificate records, these equality relations are mandatory:

```text
certificate.runtime_manifest_sha256 == runtime_manifest_sha256
certificate.fixture_manifest_sha256 == fixture_manifest_sha256
certificate.bwrap_{path,version,argv_sha256} == bwrap.{path,version,argv_sha256}
certificate.namespace_policy_sha256 == namespace_policy_sha256
certificate.mount_policy_sha256 == control_visibility.mount_policy_sha256
certificate.fd_policy_sha256 == descriptor_policy.fd_policy_sha256
certificate.user_namespace_policy_sha256 == user_namespace.policy_sha256
```

`certificate.uid` is the outer parent's effective host UID, not the
in-namespace effective UID. It must equal the mapping-derived host UID for
`user_namespace.effective_uid`: locate the unique `uid_map` record whose
inside range contains that effective UID and calculate
`outside_id + effective_uid - inside_id`. Any absent, ambiguous, or unequal
mapping suppresses PRE. The parent validates `kernel_release`, `boot_id`, and
the session-source identity before scope creation; the session only rehashes
their canonical certificate record and compares the listed in-namespace
applicability fields.

Its digest omits `certificate_sha256`. `kind` is exactly either
`proc_ptrace_barrier` or `control_visibility`. For `proc_ptrace_barrier`,
`result` is exactly `{proc_receipt_blocked: true, proc_mem_blocked: true}`;
for `control_visibility`, it is exactly
`{control_root_absent: true, mount_mutation_blocked: true}`. Before the scope
starts, the parent must match every applicability field with its current sealed
session source, manifests, Bubblewrap policy, mount/FD policy, kernel/boot/user
namespace policy, and fixture evidence. Any mismatch, missing record, stale
boot, unknown result member, or unverified fixture evidence suppresses PRE.
The session rehashes each admitted record and verifies its `kind`, fixed
result, matching runtime/fixture manifests, Bubblewrap record, user namespace,
mount policy, and FD policy before it copies the permitted parent-owned values
into receipt payloads. It does not claim to measure the parent's executable
path, Bubblewrap argv, or a certificate's external applicability.

`user_namespace_policy_sha256` is the sealed static `--unshare-user` topology
and mapping policy, which the parent can match before scope creation. The
future session must separately confirm the resulting in-namespace user
namespace/mapping against the explicit `user_namespace` map, effective IDs,
and policy digest in admitted SessionConfig before PRE. A future namespace inode
is never treated as a pre-scope certificate input.

## 4. Attestation provenance

Every required receipt assertion has a named evidence owner. The later source
must refuse instead of inventing a value when its evidence is unavailable.

| Receipt assertion class | Evidence required before PRE | Owner of evidence |
| --- | --- | --- |
| `home`, `pwd`, `cwd`, `environment_keys`, `forbidden_env_absent` | In-namespace direct measurement, exact comparison with `namespace_expectations`, and no unlisted environment key | Session owner |
| `runtime_manifest_sha256`, `run_input_manifest_sha256`, Bubblewrap path/version/argv digest, base identity, row | Session carries values from its admitted configuration; parent independently compares all PRE/POST values with its retained configuration, manifest, and Bubblewrap identities | Parent |
| private HOME and empty `.vst`/`.vst3`, production-bundle absence, scan root read-only/no later mount | Exact `private_tree`, two-entry `scan_root`, and mount-point projections; a bounded no-extra tree/mount comparison plus retained in-namespace baseline | Session owner + fixture/runtime manifest |
| X11 identity | `x11_identity.authority` no-follow destination regular mode/size/hash comparison plus a retained destination device/inode baseline; source device/inode remain parent-only provenance. Compare the socket type/owner/mode/device/inode and then project the fixed five receipt fields | Session owner + parent |
| `source_fds_absent` | Exact initial inherited-FD census equal to `descriptor_policy.inherited_fds`; all later internally opened descriptors are separately tracked | Session owner + fixture policy |
| `dumpable_disabled`, `capabilities_empty` | Task 0A barrier must succeed in the owner process before PRE | Session owner |
| `proc_receipt_blocked`, `proc_mem_blocked` | Session barrier plus matching sealed fixture certificate; a future fixture must prove the negative opens | Parent-validated fixture certificate + session owner |
| `control_root_absent` | Matching control-visibility certificate, matching mount/FD policy digests, the closed private-root discriminator, and exact inherited-FD census; neither `V4ControlPaths` nor a control-root path/FD may cross the boundary | Parent-validated fixture certificate + session owner |
| POST-only `scan_root_unchanged` | Same anchored root/mount identity and post-child bounded recheck | Session owner |

The Task 0B1 receipt schema fixes the fact names. This design neither adds a
fact nor permits an open all-true map. The future session source may only
construct a PRE/POST after its evidence satisfies the existing pure validators.
`environment_keys` is exactly the canonical list
`["DISPLAY", "HOME", "LANG", "PWD", "TZ", "XAUTHORITY"]` and proves the
in-namespace environment has no other key. `forbidden_env_absent` is exactly
the canonical high-risk subset
`["BASH_ENV", "CLAP_PATH", "DBUS_SESSION_BUS_ADDRESS", "ENV", "LD_AUDIT", "LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH", "SSH_AUTH_SOCK", "VST3_PATH", "VST_PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR"]`.
The finite forbidden list is an additional guard, not a claim that an open-ended
wildcard list itself proves absence of every undeclared key.

Because Task 0B1 requires shared PRE/POST attestation values to be identical,
the session rechecks every fact a child could mutate before it proposes POST:
the private home mount and both empty directories, the full scan-root
mount/tree/hash baseline, Xauthority and X11 socket identities, the complete
mount projection, and the inherited-FD policy. Environment/cwd/base identity,
the barrier result, and parent certificate/manifest values may be carried only
because the configuration and descriptor policy prove them immutable to the
child. Any changed or unreadable mutable fact suppresses POST; the session does
not reuse a stale PRE Boolean.

`no_later_scan_mount` is a present-tense sampled property, not a prediction:
at each PRE and POST sampling point, the exact complete mount projection has no
unknown mount strictly below the scan root. The parent-validated
`mount_mutation_blocked` certificate is additional fixture evidence, not a
substitute for the post-child comparison.

## 5. Exact raw transport

Only standard streams form the in-namespace control channel:

```text
trusted parent stdin  -> session fd 0: exact ACK byte then EOF
session fd 1          -> trusted parent stdout: framed PRE/POST only
session/bwrap fd 2    -> trusted parent stderr: bounded diagnostics only
```

No inherited descriptor beyond the exact three-entry descriptor policy is an
admission, receipt, configuration, or control channel. The two fixed
descriptor-pinned configuration paths in Section 3 are opened by path only,
then closed before the inherited-FD census and raw exchange; they never arrive
as passed descriptors. Opening either once is the unavoidable prerequisite to
its immediate `fstat` check: the session first requires a regular one-link file
and the configured hard bound, reads at most `limit + 1` bytes, demands EOF,
and closes it. `load_session_config` may then return only a structurally
validated, sidecar-bound snapshot; `run_session` may use it for PRE only after
the matching bounded mount projection has confirmed the expected read-only
mounts. The future session checks that fd 0 and fd 1 are pipes,
obtains the applicable `PIPE_BUF`, and refuses before PRE if the sealed maximum
frame does not fit. It uses a deadline-enforced nonblocking/poll loop before
each write or read. Once writable, it emits each frame in one write of the
complete byte sequence; a short write, `EINTR`, `EPIPE`, `EAGAIN` after the
sealed deadline, or other error is failure. It never retries an incomplete
frame, writes a diagnostic to stdout, or emits a second PRE/POST.

Before either bootstrap path is opened, `load_session_config` performs one
`fstat` of fd 2, requires a pipe/FIFO, and sets it nonblocking. If that setup
fails, it aborts silently before either bootstrap path is opened. Only after that setup, fd 2
permits at most one printable-ASCII closed-code diagnostic, at most
`diagnostic_max_bytes`, in one nonblocking `write` attempt. A short write,
`EAGAIN`, interruption, or other write error is ignored and never retried; it
never carries a receipt or admission value. `run_session` repeats that one
bounded fd-2 setup at its own entry rather than retaining mutable readiness
state from `load_session_config`; its setup failure is silent and disables
diagnostics only for that call, while its later mandatory descriptor-policy
preflight still decides admission. The parent begins concurrent bounded
draining of stdout and stderr when it creates the scope and continues until both
EOFs; stdout backpressure, stderr overflow, read error, or either deadline
expiry is raw-exchange uncertainty. Before ACK it starts no child; after ACK it
suppresses POST and requires outer teardown/census.

The one legal wire exchange is:

```text
stdout: PRE frame, type=PRE, sequence=0
stdin:  byte 0x06, then EOF
stdout: POST frame, type=POST, sequence=1, terminal=true, then EOF
```

The session must:

1. call exactly `attester.validate_config(attester.AttesterConfig(base_config))`
   and `attester.establish_protocol_barrier(base_config)`, then call exactly
   `receipt_schema.validate_pre_payload(pre_payload, 0)` and
   `protocol.encode_frame(protocol.FrameType.PRE, 0, pre_payload)` before the
   single stdout write. `pre_payload` is the bounded exact-built-in value just
   validated by the receipt schema; the immutable `pre_receipt.payload` is a
   validation snapshot, not an encoder input;
2. read at most two ACK bytes under the sealed deadline, require exactly one
   byte `0x06` followed by observable EOF, and reject missing, delayed,
   duplicate, extra, malformed, or non-EOF input;
3. construct and launch the child only after that ACK condition succeeds;
4. sample `pre_monotonic_ns` immediately before the successful PRE emission;
   after direct-child reaping and every post measurement, sample
   `post_monotonic_ns`;
5. retain the exact emitted PRE value and consumed ACK byte, call exactly
   `receipt_schema.validate_post_payload(post_payload, 1)`, then
   `receipt_schema.validate_exchange(pre_payload, exact_ack, post_payload)`,
   and only then call
   `protocol.encode_frame(protocol.FrameType.POST, 1, post_payload)` for its
   only stdout write. `post_payload` is likewise the exact-built-in value
   validated before encoding, never a mutable replacement or frozen receipt
   mapping;
   and
6. close stdout after POST, with no trailing byte or second frame.

The parent independently reads PRE under its own bounded frame/diagnostic
limit, validates it against retained configuration and manifest state, writes
the one ACK byte, and closes its write end. It rejects any unexpected raw
output. A valid in-memory `validate_ack_bytes(b"\x06")` result is not evidence
of stream EOF; the session and parent must prove the raw condition separately.

## 6. Child admission and environment

After valid ACK+EOF, the session may create exactly one `ChildSpec`. It must
derive every field from the single admitted configuration snapshot and must not
look up `PATH`, inherit an environment, add a descriptor, or choose a fallback.

The child environment is the closed six-key map:

```text
HOME, PWD, DISPLAY, XAUTHORITY, LANG, TZ
```

It must contain exactly those six keys and the byte-identical values in
`namespace_expectations`. In particular `PWD == HOME`, the working directory
equals that same `HOME`, and `XAUTHORITY` is the private in-namespace path.
The session constructs `ChildSpec.environment` only as the lexicographic tuple
`(("DISPLAY", value), ("HOME", value), ("LANG", value), ("PWD", value),
("TZ", value), ("XAUTHORITY", value))`; it must not pass the JSON map or an
ambient mapping through unchanged.
The exact six-key environment proves every undeclared key is absent. The
finite high-risk guard list in Section 4 is additionally attested but does not
stand in for a wildcard assertion. If a later compatibility manifest proves a
truly necessary extra key, it requires a reviewed configuration/schema
amendment; there is no runtime exception.

The child adapter remains the sole `subprocess` user. Its future invocation
must retain its sealed boundaries: absolute executable and cwd, `shell=False`,
`DEVNULL` on descriptors 0/1/2, `close_fds=True`, `pass_fds=()`, one bounded
launch, and bounded kill/reap once Python has bound the returned process
object. It reserves at most two direct-child cleanup slots; within an entered
slot, a `kill()` error still reaches the bounded `wait()`, and reaping is
confirmed only when that wait returns. The outer session/scope—not the
adapter—owns recovery and evidence sealing for every unconfirmed cleanup and
for a partial launch interrupted before binding, including before `Popen`
returns or after OS child creation but before Python retains the returned
object.

After a returned `ChildOutcome`, the session treats `timed_out == true` or a
negative `returncode` as uncertainty. Either condition suppresses POST and
requires outer teardown/census; only a non-timeout, nonnegative return code may
enter the post-child evidence branch.

## 7. State and failure table

No uncertain path can emit terminal success evidence.

| Stage or condition | Child started? | Session stdout | Required outer action |
| --- | ---: | --- | --- |
| Configuration, barrier, provenance, PRE payload, or frame-size failure | No | No PRE | Mark namespace uncertainty; no ACK/child |
| PRE write error, short write, or interruption during its attempt | No | Possibly incomplete or complete-but-unconfirmed PRE bytes, never a retry | Treat raw exchange as invalid; no child |
| Missing/bad/extra/non-EOF ACK | No | PRE only | No POST; close/terminate scope and seal uncertainty |
| Child adapter interruption before its returned process object is bound (including before `Popen` returns) | Unknown | PRE only | Outer scope-wide teardown and PID census; no POST |
| Child timeout, kill/reap uncertainty, signal, or interruption after launch | Yes or unknown | PRE only | Outer scope-wide teardown and PID census; no POST |
| Child exits but post measurement, root identity, or POST validation fails | Yes | PRE only | No POST; outer controller rejects the row |
| POST write error, short write, or interruption during its attempt | Yes | PRE plus possibly incomplete or complete-but-unconfirmed POST, never a retry | Treat raw exchange as invalid; outer teardown/census uncertainty |
| Child exits, reaps, post checks and POST write all succeed | Yes | PRE then terminal POST then EOF | Still require scope-exit confirmation, zero-REAPER census, and outer receipt validation |

Terminal POST establishes only that this session observed and reaped its direct
child within the declared contract. It is not row acceptance, a scope-exit
proof, a zero-PID census, a cache/profile validation, or permission to scan.

## 8. Measurement-root rules

The existing Task 0B1 measurement API proves bounded mode/size facts for
explicit one-component regular-file resources. It is not a general mount or
tree attester. The future session owner must therefore:

1. use the one `namespace_expectations.measurement_root` identity with expected
   device/inode and its finite resource plan; no second or ambient root source
   is permitted;
2. retain the root descriptor for the entire PRE-to-POST interval and recheck
   it before PRE and after the child;
3. separately open the in-namespace `scan_root` once before PRE, retain its
   descriptor and observed device/inode/mount/tree/hash baseline through the
   child, then make the same bounded no-follow, no-extra comparison after the
   child; and
4. use only bounded, no-follow, non-recursive measurement calls under either
   admitted root; and
5. assign every fact outside that API to a separately reviewed, bounded
   evidence function or to a sealed fixture certificate.

The later source closure must include every new measurement/evidence function.
No session code may treat an ambient pathname, an arbitrary `/proc` walk, or a
single mode/size result as proof of an unrelated receipt assertion.

## 9. Required later gates

This record intentionally creates no implementation authority. The smallest
safe sequence is:

1. **Task 0B3a — non-admissible session skeleton:** author only the named
   session-root API shell and its pre-import source-byte/AST verifier. Both
   public functions fail closed before any runtime work; no component invocation
   or fixture.
2. **Task 0B3b — pure receipt gate (sealed):** executed adversarial in-memory
   receipt PRE/POST/ACK vectors only and proved value/exchange relations. It
   did not test raw ACK EOF/order or any session behavior.
3. **Task 0B3c — measurement gate:** test only a temporary, synthetic
   directory/descriptor boundary and bounded identity failures; no namespace.
4. **Task 0B3d — child-adapter gate:** use a non-REAPER sentinel child to test
   one-launch, environment, timeout, and reaping behavior.
5. **Task 0B4a — session-source contract correction:** under the current
   source-and-test authority, replace the incompatible skeleton-only contract
   with an exact source contract for configuration parsing, private
   exact-built-in projections, receipt/encoder compatibility, bounded evidence
   helpers, and silent PRE-only uncertainty. This stage is documentation and
   test-first source-shape work; it creates no namespace, raw scope, fixture,
   or host proof.
6. **Task 0B4b-pure — compatibility-helper checkpoint (sealed):** the later
   pure in-memory source/test gate implements only bounded data conversion,
   canonical/digest handling, Task 0A base-config projection, and PRE/POST
   value-to-encoder compatibility. Public session entrypoints remain
   immediate-failure stubs; it does not implement the session state machine,
   transport, barrier, evidence, or child path.
7. **Task 0B4b-state-contract (sealed documentation-only checkpoint):** this
   record resolves the B4c name collision and documents why the current
   B4b-pure parser, collector, and POST helper cannot directly admit or run
   the coordinator. It creates no source/test/runtime authority.
8. **Task 0B4b-admission-pure:** a fresh source/test authority must first
   validate every closed SessionConfig nested relation and cross-digest in
   memory, revalidate any supplied frozen object at the trust boundary, and
   make a fresh private base/child projection. It must replace the B4b-pure
   static contract before source change while preserving all seven pure-helper
   regressions. It may not open a path, claim provenance, establish a barrier,
   or emit a frame.
9. **Task 0B4b-evidence:** a separate source/test gate must author and seal
   each bounded private evidence and retained-baseline helper required by the
   provenance table, with synthetic/mock/temporary-resource negative tests.
   It must not add a runtime root, callback, raw channel, or all-true
   attestation. Actual namespace/path/FD proof remains later.
10. **Task 0B4b-bootstrap-transport:** a separate source/test gate must
   author and seal the fixed-literal bootstrap loader and fixed standard-stream
   helper logic against syscall/poll doubles or temporary controlled pipes. It
   must cover sidecar-first loading, descriptor/EOF bounds, ACK+EOF, write
   failure, deadline, and the one fd-2 diagnostic attempt without executing a
   real fixture or child.
11. **Task 0B4b-state:** only after the preceding gates are sealed may a
   further fresh explicit user authority and reviewed source contract implement
   and test the one session root against bounded in-process transport and
   evidence doubles. It must cover every failure-table row as a local
   state-machine outcome: no child before ACK+EOF and no terminal POST for an
   uncertain path. It uses a mocked `ChildOutcome`, mocked barrier, and mocked
   measurement/evidence boundaries; it does not launch a sentinel or invoke
   the real `PR_SET_DUMPABLE` barrier. The sealed Task 0B3d sentinel evidence
   remains the only direct-child launch evidence. These tests prove local
   composition only; they cannot claim fixed-path provenance, namespace
   measurements, X11, scope exit, descendant containment, PID census, or host
   compatibility.
12. **Task 0B4c-design — controlled-fixture definition gate:** a separate,
   source-free design authority must define the bounded non-REAPER fixture,
   outer ownership, standard-stream topology, expected mounts, and resource
   budgets. It creates no namespace, process, mount, or executed fixture.
13. **Task 0B5 — graph-construction implementation gate:** under a separate
   data-only authority, implement and review the currently unavailable closed
   schema/catalog/graph-construction method. It may parse only supplied static
   data through retained directory descriptors; it must not import, execute, or
   load a target or create a fixture.
14. **Successor Task 0B0 closure review and fixture-runtime-manifest review:**
   only after a reviewed executable session root, fixture definition, and graph
   constructor exist, rebuild the graph from this one session-entrypoint root
   through Task 0A and every runtime library. It must remain blocked on any
   unresolved edge or budget excess. A bounded fixture-runtime manifest must be
   independently reviewed before any fixture-execution authority.
15. **Task 0B4c-execution — outer-harness controlled-fixture gate:** only
   after the preceding closure and fixture-manifest review may a separately
   scoped authority execute an actual fixed-path/standard-stream,
   namespace/mount/FD/proc fixture, concurrent parent drains, or an
   uncertain-child teardown/census scenario. Its own future authority must
   name exactly one independently reviewed non-REAPER scope mechanism and its
   fixed policy; it must not substitute an unreviewed launcher. It provides the
   outer scope owner that this session intentionally lacks. It never authorizes
   REAPER, X11, audio, host scanning, or a host launch.
16. **Separate host-manifest and host-request gates:** a bounded non-REAPER
   fixture manifest may prove only a safety property. REAPER compatibility and
   a host request remain separate, later decisions.

Each gate needs its own explicit scope, tests, independent review, and user
authorization. Passing one does not authorize the next.

## 10. Rejected alternatives

| Alternative | Rejection reason |
| --- | --- |
| Add sequencing to immutable Task 0A | Violates its sealed non-admissible, process-incapable boundary. |
| Let receipt, measurement, or child-runner library choose admission | Splits responsibility and creates an implicit runtime root. |
| Use an arbitrary inherited descriptor or control-root path | Weakens the standard-stream/outer-controller ownership boundary. |
| Let stdin carry configuration as well as ACK | Makes ACK EOF and configuration provenance ambiguous. |
| Accept self-asserted all-true receipt facts | Provides no evidence for parent-owned, proc/ptrace, or control-visibility claims. |
| Emit POST after a timeout or teardown uncertainty | Can falsely turn partial launch information into terminal evidence. |
| Permit a child environment exception at runtime | Reopens loader, plugin, and session-variable injection paths without review. |

## 11. Non-claims and references

This design does not create a session file, validate a runtime closure, prove a
fixture works, establish REAPER compatibility, scan a VST3 bundle, open REAPER,
or change the real-time Audio-to-MIDI implementation. It does not authorize a
retry of the sealed v1/v2/v3 work.

It refines the design boundary recorded in:

- `docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md` (Task 0B3);
- `docs/superpowers/specs/2026-08-31-v4-reaper-scan-isolation-design.md`
  (§4.3–§4.4);
- `docs/superpowers/specs/2026-09-01-v4-task0b-closure-construction-method.md`;
- `docs/superpowers/specs/2026-09-01-v4-task0b1-author-only-source-contract.md`.

Any conflict with those sealed documents is a block requiring a reviewed
amendment, not a runtime interpretation.
