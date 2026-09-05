# V4 Task 0B4b-payload-assembly — verified baseline to receipt values

**Status:** locally verified implementation checkpoint, pending independent
source review. This successor replaces only the two fail-closed
payload-assembly stubs in `tools/reaper_v4_session.py`. It neither creates a
namespace nor authorizes a fixture, REAPER, audio, X11 traffic, network,
Bubblewrap command, systemd scope, or host scan.

## Scope

The change preserves the public entrypoints, fixed bootstrap paths, raw
transport helpers, evidence collectors, and sealed Task 0A/0B1 interfaces. It
may add one private common-attestation helper:

```python
def _shared_receipt_attestation(
    config: SessionConfig, baseline: _EvidenceBaseline
) -> dict[str, object]: ...
```

It replaces only:

```python
def _assemble_pre_payload(
    config: SessionConfig, baseline: _EvidenceBaseline
) -> dict[str, object]: ...

def _assemble_post_payload(
    config: SessionConfig, baseline: _EvidenceBaseline,
    outcome: child_runner.ChildOutcome, pre_monotonic_ns: int,
    post_monotonic_ns: int,
) -> dict[str, object]: ...
```

The implementation consumes an already-owned `_EvidenceBaseline`; it does not
open a path, enumerate descriptors, poll a stream, call a child adapter,
establish a barrier, write a frame, or claim that a direct private call is a
session admission path. `run_session()` remains the only path that calls the
PRE helper after a successful barrier, and the only path that calls the POST
helper after a successful baseline recheck.

## Ownership and validation

Each helper first admits `config`, calls `_require_owned_evidence_baseline`,
and rejects a baseline whose locally owned configuration differs from the
freshly admitted snapshot. It materializes copied exact builtins from the
baseline before examining them. Ordinary data, comparison, or snapshot errors
become `SessionError`; `BaseException` is not caught.

The common helper must reject a baseline unless all of these concrete records
remain internally consistent with the admitted snapshot:

1. `cwd` and the exact canonical six-key environment are equal to
   `namespace_expectations`;
2. the measurement baseline has the configured root device/inode and a
   collector facts/evidence mapping;
3. the scan baseline has exactly the configured two relative entries, with
   matching mode, size, and SHA-256, and no other entry;
4. private-home mode is `0700` and its exact `.vst` and `.vst3` records are
   present;
5. authority mode, size, digest and X11 socket owner/mode/device/inode agree
   with `x11_identity`;
6. retained FD census and mount projection equal their admitted closed values;
   and
7. the stored certificate applicability projection equals a freshly derived
   closed projection.

The successful helper returns a fresh exact `dict` containing exactly the
shared Task 0B1 attestation keys. It maps each fact to a named evidence source:

| Receipt field | Source |
| --- | --- |
| `home`, `pwd`, `cwd`, environment list | admitted namespace expectations plus retained supplied observation |
| manifests and Bubblewrap values | admitted configuration |
| private/scan/read-only/FD facts | retained descriptor-rooted baseline and exact mount/census comparison |
| X11 identity | admitted fixed five-field projection plus retained authority/socket identity |
| dumpable/capabilities | the successful barrier structurally dominating the PRE helper in `run_session` |
| proc and control facts | retained, cross-checked parent certificate projection |

It returns the canonical environment key list and the full finite forbidden
environment list from the B3 design, not a shortened synthetic list. All
containment Booleans are emitted only after the corresponding retained records
have passed the checks above.

## PRE and POST payloads

`_assemble_pre_payload` creates a fresh exact-built-in mapping with exactly
the Task 0B1 PRE keys:

```python
{
    "schema": base_config["schema"],
    "namespace": base_config["namespace"],
    "nonce": base_config["nonce"],
    "config_sha256": base_config["config_sha256"],
    "inputs": copied_base_inputs,
    "row": copied_row,
    "phase": "pre",
    "no_child_started": True,
    "attestation": shared_attestation,
}
```

`_assemble_post_payload` first accepts only `_validate_child_outcome(outcome)`;
it requires exact non-Boolean positive clocks within the session integer range
and `post_monotonic_ns >= pre_monotonic_ns`. It creates a fresh mapping with
the Task 0B1 POST keys, byte-equal shared identity and attestation values, the
validated child PID/return code, `phase="post"`, `terminal=True`, and only the
additional `scan_root_unchanged=True` attestation key. It does not encode,
write, or independently recheck the baseline; the existing finalizer retains
the required `validate_post -> validate_exchange -> encode` order.

## Tests and sealing

The new payload test imports the source only after the replacement static
contract succeeds. With an `_EvidenceFixture` built solely from a temporary
directory, temporary descriptors, and a socket pair, it must prove:

1. actual PRE data validates with the sealed receipt validator and contains the
   complete named shared attestation;
2. actual POST data validates together with the PRE and exact ACK, preserves
   every shared value, and adds only `scan_root_unchanged`;
3. a config/baseline mismatch, consumed or forged baseline, mutated retained
   observation, timed-out/negative child, and invalid/regressing clock all
   refuse without an encoder, child, path, or transport edge; and
4. repeated calls return fresh unaliased exact builtin values.

The static contract replaces the two stub assertions with exact helper
signatures, known call edges, no forbidden capability addition, and source
SHA-256
`41f8d1fbaebb69c4aad2de50c16ff2fd48ad68b1d55e4fadf1e428889893d937`.
The test-first PRE vector first refused the prior stub. The completed focused
V4 suite then passed 51 checks, including the new controlled-descriptor PRE,
POST/exchange, fresh-value, and refusal vectors; `git diff --check` is clean.
No fixture, namespace, child process, REAPER, audio, X11 client traffic,
network, or host scan ran. Independent source review and the next executable
gap—runtime observation acquisition—remain pending; this result is
insufficient for fixture or host execution.
