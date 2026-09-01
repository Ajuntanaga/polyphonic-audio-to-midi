# V4 Task 0B0 Static Closure-Construction Method

Date: 2026-09-01
Status: independently re-reviewed documentation-only method; Task 0B1 source
authoring is authorized but module invocation remains separately prohibited
Scope: construct or refuse a conservative static closure record for the future
combined Task 0A/Task 0B1 Python, extension, and ELF inputs
Plan: docs/superpowers/plans/2026-08-31-v4-reaper-scan-isolation.md
Design: docs/superpowers/specs/2026-08-31-v4-reaper-scan-isolation-design.md
Inventory: docs/superpowers/specs/2026-08-31-v4-reaper-runtime-inventory.md

## 1. Decision and authority boundary

Task 0B0 defines a data-only method for constructing a conservative closure
record. It exists because the sealed Task 0A source hashes are known while its
Python/interpreter/extension/ELF closure is deliberately unresolved. The method
must either enumerate every statically feasible dependency permitted by one
sealed runtime policy, or emit a durable blocked record. It must never guess a
broad bind or silently select a host-dependent branch.

This is not a runtime analyzer and does not authorize source authoring,
namespace construction, a fixture, Bubblewrap, systemd, REAPER, GUI/X11,
audio, network, installation, MCP, or a host row. It does not alter the sealed
Task 0A component:

| Source | SHA-256 |
| --- | --- |
| `tools/reaper_v4_protocol.py` | `82afbe01cf11f083481db26cc10927965cd1341b4b75367ceda25de0d82b8331` |
| `tools/reaper_v4_attester.py` | `1b6cae926421615fb6f42fe1ee40d4a09d1dd862296a90c38b8371ee42377891` |
| `tests/test_reaper_v4_protocol.py` | `809a0b71c65e1e24e5c3f03a247408cec9dfec619d559acbddd1ad5ef0233192` |

Task 0B0 CLEAN review means only that this method is fit to govern the active
source-only Task 0B1. The user granted explicit offline Task 0B1 authority,
which may only author, never invoke, four sources: the build-time static closure
constructor plus the three runtime receipt-schema, measured-collector, and
child-adapter modules. Task 0B1 also covers authoring their schemas, synthetic
method-test fixtures, and catalog formats, but not constructing a record from
Task 0A data. A separate explicit offline Task 0B2 authority is required to
test or invoke the constructor against sealed static inputs. Task 0B2 excludes
target import/execution, target extension load, namespace/fixture creation,
Bubblewrap/systemd/REAPER command formation, GUI/X11/audio/network access, and
all host actions. A later bounded non-REAPER fixture and every host action
remain separately gated.

## 2. Artifact meanings

The following artifacts are deliberately distinct:

| Artifact | Meaning | Cannot establish |
| --- | --- | --- |
| Task 0A source component | Immutable source hashes and source-only behavior contract | Any runtime closure or launch authority |
| Static closure record | A provenance-backed conservative union of all statically feasible Task 0A/0B1 dependency edges under one sealed policy | Minimal actual loaded set or REAPER compatibility |
| `fixture-runtime-manifest` | A reviewed, budgeted allowlist for one non-REAPER fixture | A REAPER host runtime |
| `reaper-host-runtime-manifest` | A later compatibility artifact that references the fixture manifest and adds resolved REAPER/libSwell/GUI/X11/dynamic inputs | Permission to launch without fresh user authority |

The future `tools/reaper_v4_closure_constructor.py` is a build-time analysis
tool, not a V4 fixture runtime node. Its source and parser identities bind the
closure record's producer, but it is not mounted by a
`fixture-runtime-manifest`. Task 0A plus the Task 0B1 receipt-schema,
measured-collector, and child-adapter modules are initially **analysis roots**,
not runtime roots. This separation prevents a build tool from silently becoming
a sandbox dependency and prevents library source from silently becoming a
session entrypoint.

Exactly one separately reviewed same-namespace session entrypoint must later be
declared as a **runtime root**. It alone owns the PRE, ACK, child, and POST
sequence, and must reach Task 0A plus all three Task 0B1 runtime libraries. It
is not authorized in Task 0B1. Until that source and its manifest-root identity
exist, construction must emit the exact unresolved code
`runtime_session_entrypoint_unresolved` with expected role
`same_namespace_pre_ack_child_post_owner`; it may not produce
`COMPLETE_FIXTURE_CANDIDATE`.

"Complete combined closure" in this method means a closed conservative union,
not a claim that a particular execution loads the minimal listed files. It is
complete only when every statically feasible runtime Python, extension, ELF,
loader, and configuration edge under the sealed policy is enumerated,
provenance-linked, and budgeted, with no unresolved reachable edge and no
orphan entry.

## 3. Allowed mechanism

The future closure constructor may read only explicitly supplied regular files
and retained, safe directories as data. It parses source and ELF bytes; it does
not import, load, invoke, or evaluate target content. In particular, it must
not use target imports, `python -m`, `runpy`, `modulefinder` behavior that
imports, `exec`, `eval`, or `compile` to generate executable target code;
target bytecode execution; `ctypes`/`cffi`/`dlopen` of target artifacts; package
entry-point discovery that imports; target subprocess entrypoints; import hooks;
or any ambient analyzer package state. A parser pinned to the target grammar
and configured for AST-only output is allowed; generating or executing target
bytecode is not.

The Task 0B1 static-constructor skeleton is a named deliverable. Its source,
alongside the receipt-schema, measured-collector, and child-adapter sources,
is covered only by the explicit offline Task 0B1 authorization described in the
plan. This specification defines required behavior only. A documentation review
cannot be substituted for its implementation or test evidence. The current
author-only skeleton intentionally refuses all pathname loading and rejects
schema-invalid data. For the sole supplied schema-valid empty synthetic catalog vector,
it emits only a full
`BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)` record. It does not
yet parse a graph or implement a candidate-complete path; retained-dirfd input,
catalog records, and reachability construction require the later scoped Task
0B2/0B3 work.

## 4. Sealed input set

The method accepts only a versioned, canonical input bundle. Every supplied
path is validated through retained safe ancestors; regular files are opened
with `O_RDONLY|O_NOFOLLOW`, hashed from the file descriptor, and re-`fstat`ed
before and after reading. Device/inode, mode, uid/gid, `st_nlink`, size, and
mutation-relevant timestamps must remain stable; a final regular target with
`st_nlink != 1`, a changed identity, special file, alias ambiguity, or unsafe
path rejects the record.

### 4.1 Resolver policy

`resolver-policy.json` has an exact schema and supplies all runtime choices the
constructor may use:

- target interpreter raw path, SHA-256, build ID, ELF class/machine,
  `PT_INTERP`, Python version, cache tag, and extension suffixes;
- exact startup contract (`-I -S -B` semantics or a complete enumerated
  alternative), cwd, HOME/PWD, empty/import-safe environment, and ordered
  import roots plus the required startup-model catalog;
- explicit site, user-site, `.pth`, `sitecustomize`, `usercustomize`, zip,
  namespace-package, bytecode, importer-hook, and `sys.path` policy;
- grammar version, accepted AST forms, branch predicates, and prohibited
  dynamic-resolution constructs;
- loader policy: exact linker/loader identities, permitted search roots,
  dynamic-loader configuration inputs, and treatment of RPATH/RUNPATH,
  `$ORIGIN`, glibc-hwcaps, locale/gconv/NSS/configuration, and `dlopen`.

The constructor never reads ambient `sys.path`, `sys.modules`, cwd, shell
environment, HOME, loader cache, or analyzer-host configuration. If a required
startup or loader influence is not explicitly sealed in the policy, the result
is `BLOCKED_UNRESOLVED`.

### 4.1a Root declaration

The canonical input bundle—not `resolver-policy.json`—has two exact ordered
members: `analysis_roots` and `runtime_roots`. Every root is a closed object
with `id`, `module`, `kind`, `sha256`, and `role`. `id` is a unique stable
lowercase identifier; `module` is a cataloged dotted source module; `kind` is
either `analysis_source` or `session_entrypoint`; `sha256` is the exact source
identity; and `role` is a fixed semantic label. Both arrays are included in the
canonical `input_bundle_digest` and emitted as `analysis_root_identities` and
`runtime_root_identities` in the output record.

The constructor traverses every analysis root as evidence for the conservative
static graph. A Task 0B1 library listed in `analysis_roots` is never a runtime
root by implication. A complete candidate requires exactly one runtime root of
kind `session_entrypoint`, role `same_namespace_pre_ack_child_post_owner`, and
proven static reachability from that root to Task 0A plus every Task 0B1 runtime
library. Zero, multiple, malformed, or incomplete runtime roots emit the typed
unresolved output record `runtime_session_entrypoint_unresolved`; the analysis
graph remains recorded, but `closure_state` is `BLOCKED_UNRESOLVED`.

### 4.2 Startup model

`startup-model.json` supplies the target interpreter's pre-target import model
for the exact sealed startup contract. It names every bootstrap source,
built-in/frozen provider, extension, ELF, and virtual resource required before
the first Task 0A/Task 0B1 lexical import, including import machinery,
`_imp`/marshal/encoding/bootstrap providers where applicable. Each entry has a
typed `startup` edge, exact catalog key, and hash-bound target-interpreter
provenance. The model also records its independently reviewed static evidence
that no additional startup node is reachable under that policy.

`-I -S -B` is not evidence that the startup set is empty. An absent, incomplete,
or unverifiable startup model is `BLOCKED_UNRESOLVED`; the constructor may not
infer startup behavior by importing the target interpreter or observing the
analyzer process.

### 4.3 Module catalog

`module-catalog.json` maps every permitted dotted name to exactly one declared
provider in the ordered runtime model:

- source module or package with raw path, identity, source encoding, SHA-256,
  and declared in-namespace destination;
- extension module with its ELF catalog key; or
- built-in/frozen module with sealed interpreter-provisioning evidence.

Duplicate or shadowed names, non-finite namespace-package fan-out, unexplained
package initializers, bytecode/source disagreement, missing encodings, and a
claimed built-in/frozen module inferred only from an absent `.so` all refuse.
The catalog also contains exact relative-import and package-`__init__` rules.

A finite namespace-package segment is allowed only when the catalog records its
ordered sealed parent roots, exact participating child modules, and a synthetic
in-namespace directory topology. It creates an explicit `namespace` node and
edge, never a host repository-directory bind. No ambient import root, extra
namespace contributor, or unsealed child may participate. This rule is required
for the current `tools.reaper_v4_protocol` import because `tools/__init__.py`
is absent.

`interpreter-module-registry.json` is required for every built-in/frozen node.
Each exact registry entry names the module and kind (`builtin` or `frozen`),
the target interpreter SHA-256/build ID, and one sealed regular-file provenance
record. That record identifies the build-generated registry or independently
reviewed static-binary mapping that supports the entry. The constructor verifies
the registry's target identity and evidence hash before accepting a cataloged
built-in/frozen provider. It never infers `_json`, `_struct`, `_collections`,
`_sre`, or any other provider from the absence of a `lib-dynload` file. Missing
or unverifiable registry evidence is `BLOCKED_UNRESOLVED`.

Every frozen provider also needs `frozen-effect-catalog.json`: an exact frozen
payload hash plus a hash-bound, non-executing frozen-code or source-equivalence
effect certificate. The certificate enumerates its import, resource, native,
and startup edges using the same conservative rules as a source module. A
frozen provider with computed or unverifiable effects blocks. Every built-in
provider instead requires a logical-provider entry in the native-effect catalog
bound to the target interpreter artifact and module name. Startup frozen and
built-in providers obey the same rules; startup membership alone is not effect
evidence.

### 4.4 ELF catalog

`elf-catalog.json` supplies one identity record for the interpreter, loader,
extensions, libraries, and any future literal `dlopen` target. Each record has
raw path, final regular source, approved in-namespace symlink topology, mode,
device/inode, byte size, SHA-256, build ID, ELF class/machine, `PT_INTERP`,
SONAME, RPATH/RUNPATH, and all `DT_NEEDED`/related dynamic tags. Every SONAME
resolution has one exact policy-backed target. A missing, ambiguous, escaping,
writable, relative, or unenumerated search result refuses.

### 4.5 Branch policy

`branch-policy.json` keys every permitted branch decision by source SHA-256 and
AST location. It may eliminate an edge only with sealed facts whose semantics
are explicit, such as the target `sys.platform`, `sys.version_info`, `os.name`,
`TYPE_CHECKING`, or a literal Boolean. It cannot use facts observed from the
analyzer machine.

### 4.6 Native-effect catalog

`native-effect-catalog.json` is required for every extension, executable, and
native library node. It is a hash-bound, independently reviewed static-analysis
certificate keyed by the exact artifact SHA-256, optional built-in logical
provider name, and analyzer identity. For each artifact/provider it records
every proven native `dlopen`/`dlsym` call site, native
configuration/resource access, and symbol-provider lookup, or records the
artifact as unresolved. A `none_proven` claim is allowed only with a sealed
certificate that proves the absence of those calls for the exact artifact; an
empty `DT_NEEDED` table, lack of a string, or an omitted catalog entry is never
such proof.

Every literal finite `dlopen` target has a call-site record and resolves through
the ELF catalog. A computed target, indirect/unanalyzable call, plugin scan,
unsealed resource access, or absent certificate is `BLOCKED_UNRESOLVED`. This
rule deliberately makes a synthetic native initializer containing either
`dlopen("libhidden.so")` or a computed name block even when neither target is in
`DT_NEEDED`.

`ctypes.CDLL(None)` is a native symbol-provider lookup, not an implicit libc
allowance. Its catalog record must bind the exact Python call site, target
interpreter ABI, requested symbol and version, provider ELF identity, and
resolution evidence. Task 0A's `prctl` lookup therefore blocks unless such a
record identifies its provider under the sealed process ABI.

### 4.7 Virtual-resource catalog

`virtual-resource-catalog.json` covers non-regular resources accessed by target
source or native code. A literal regular-file read records the pinned regular
input it consumes. A literal virtual resource records its type, normalized
in-namespace address, creation/mount rule, access mode, and reason. The only
example currently known from Task 0A is a `proc_self_status` virtual resource
for `/proc/self/status`; it is not a host file hash or a permission to mount an
arbitrary `/proc` tree.

The source parser recognizes only a fixed call-form allowlist, including direct
`open`, `os.open`, and literal `Path(...).read_text`/`read_bytes` forms after
name binding is resolved. A computed path, dynamic alias, unrecognized
resource-reading call, or native resource effect without a catalog record
blocks. A future resource record can never silently convert a host path into a
broad bind.

`source-effect-catalog.json` closes indirect pure-Python call effects. It is
keyed by exact source SHA-256 and AST call-site location, with the resolved
callee identity, transitive effect summary, and evidence. A call outside the
fixed pure-expression allowlist must either have such a finite summary or
block. A `none` summary is valid only when the sealed summary proves no import,
resource, native-bridge, process, or environment effect for that exact callee
graph. This prevents an unrecognized wrapper around `open` from being mistaken
for a pure computation.

### 4.8 Resource policy

`resource-policy.json` supplies the numeric, non-ambient budgets used during
construction: maximum graph nodes/edges/depth and manifest bytes; maximum
regular-entry count, bytes read, copied bytes, and largest entry; a fixed
page-size assumption; the planned snapshot/anchor/directory/control/stdio/temp
FD equation and reserve; minimum soft `RLIMIT_NOFILE`; private-tmpfs and
writable-tree ceilings; process allowances; `MemoryHigh`, `MemoryMax`, and
kill-reserve values. The constructor compares derived values only to this
sealed policy. It does not inspect its own limits or any systemd scope.

A later fixture or host preflight independently observes the actual limits and
refuses if they are absent, differ from the sealed policy, or offer less than
the recorded requirement. The policy's copy model is a conservative planned
upper bound for `--ro-bind-data` destinations, not a claim about actual
Bubblewrap allocation.

## 5. Graph construction rules

### 5.1 Python edges

The graph begins with every `startup-model` root and the deterministic union of
declared analysis and runtime roots, then parses target source bytes with the
target grammar, recording each AST digest. The seed order is startup roots,
ordered analysis roots, then ordered runtime roots. Identical source roots
deduplicate only when their `module` and `sha256` both match; a duplicated module
with a different SHA-256 is unresolved. The output retains both root-role
identities even when their source traversal seed is shared. It traverses every
lexical literal `import` and `from … import` edge, including function-local
imports. Relative imports and required package initializers resolve only through
the module catalog. Runtime-root reachability is evaluated from the parsed
runtime-root node against this conservative graph; an analysis-only path does
not satisfy it.

For `from package import name`, the record always includes the package source.
It classifies `name` as a package attribute only when the package AST provides
a sealed static binding and has no unresolved dynamic attribute hook. If a
cataloged `package.name` submodule could be imported by Python's fallback
semantics, the conservative union includes that submodule edge as well. An
ambiguous attribute/submodule decision, a dynamic `__getattr__`, or an
unresolved re-export blocks rather than choosing the analyzer host's behavior.

For an unproven conditional, platform test, exception fallback, or
function-local branch, the conservative union includes every finite literal
edge. A `try`/`except ImportError` records the attempted dependency and every
fallback. Intentional absence is valid only as a negative-resolution record
against the constructed search model; ambient host absence is never evidence.

The following are unresolved unless a finite literal target set is explicitly
allowed by the resolver policy and every member is separately cataloged:

- `__import__`, `importlib` loaders, computed module names, mutable `sys.path`
  or `sys.meta_path`, and import hooks;
- package/entry-point/plugin discovery, `pkgutil`, `runpy`, zip imports, and
  namespace package fan-out;
- star imports with dynamic `__all__`, source/bytecode disagreement, and any
  dependency selected by file state, environment, or a call result.

The method treats `ctypes.CDLL(None)` exclusively as an explicit
native-effect/provider edge. It resolves only through the exact call-site,
symbol-version, target-process ABI, provider ELF identity, and interposition
evidence recorded in the native-effect catalog. It never assumes libc alone is
the provider or treats the call as evidence that any process-global symbol is
safely available.

### 5.2 Extension and ELF edges

For each extension or executable ELF node, recurse through `PT_INTERP`,
`DT_NEEDED`, SONAME, and policy-permitted RPATH/RUNPATH resolution. `$ORIGIN`
expansion is allowed only when its exact source and destination topology are
sealed; otherwise it refuses. `LD_LIBRARY_PATH`, `LD_PRELOAD`, `LD_AUDIT`,
loader caches, default library directories, glibc-hwcaps selection, provider
configuration, and other dynamic-loader inputs are either disabled by policy
or individually recorded and pinned.

The native-effect catalog must close every native dynamic-load, symbol-provider,
and native resource/configuration edge before this metadata closure can become
complete. Literal `dlopen` targets follow the same rules. Computed names,
plugin discovery, unresolved `dlsym` branches, optional GUI/audio loads, or an
unproven absence of native effects remain unresolved. String scans are only
leads for catalog review; they never prove a dependency necessary or
unnecessary.

### 5.3 Path and topology integrity

The constructor probes only declared candidate paths in catalog order. It never
recursively scans broad `/usr`, `/lib*`, a REAPER installation, HOME, a runtime
directory, the repository, or any archived Windows tree. Host symlinks are
recorded as each raw hop and final regular target, rejecting loops, escapes,
case/Unicode ambiguity, destination traversal, and replacement. It recreates
only declared in-namespace symlink topology.

Every manifest node must have a root-to-node provenance path. An extra valid
file or library is an orphan and causes refusal rather than silently broadening
the allowlist.

## 6. Canonical output record

The method emits canonical UTF-8 JSON with exact keys/types, sorted arrays and
maps, no duplicate keys, floats, timestamps, temporary paths, FD numbers,
locale-dependent text, or hash-table-order dependence in the content digest.
An optional non-digested observation envelope may carry a timestamp.

Canonical JSON means UTF-8, object keys sorted by Unicode code point, no
insignificant whitespace, integers only, and arrays sorted by their documented
stable key. A digest is the lowercase SHA-256 of those exact bytes. The
`task0a_source_component_digest` is the digest of this exact object, whose
`files` array is sorted by `path` and contains only the three table entries in
Section 1:

```json
{"schema":1,"files":[{"path":"tests/test_reaper_v4_protocol.py","sha256":"809a0b71c65e1e24e5c3f03a247408cec9dfec619d559acbddd1ad5ef0233192"},{"path":"tools/reaper_v4_attester.py","sha256":"1b6cae926421615fb6f42fe1ee40d4a09d1dd862296a90c38b8371ee42377891"},{"path":"tools/reaper_v4_protocol.py","sha256":"82afbe01cf11f083481db26cc10927965cd1341b4b75367ceda25de0d82b8331"}]}
```

`closure_digest` is the digest of the complete digest-bearing record with its
own `closure_digest` member omitted; no null, empty, or placeholder value is
encoded in its preimage. Every other listed member, including
`method_spec_sha256`, is included. Catalog and policy digests follow the same
canonical-JSON rule over their respective exact documents.

`constructor_identity` and `parser_identity` are exact raw-path, mode,
device/inode, byte-size, SHA-256, and version records for the future static
constructor and its AST/ELF parsers. `input_bundle_digest` is the canonical
digest of the ordered input-root identities plus all catalog/policy digests.
Changing one source byte, constructor/parser byte, policy byte, or sealed input
must change the applicable identity and the closure digest. Two independent
encoders of unchanged sealed inputs must produce identical digest-bearing bytes.
Constructor/parser identities are provenance only; they are not runtime nodes
or fixture mounts.

The digest-bearing record contains:

```text
schema, method_version, method_spec_sha256, constructor_identity,
parser_identity, resolver_policy_digest, resource_policy_digest,
interpreter_module_registry_digest, native_effect_catalog_digest,
frozen_effect_catalog_digest, virtual_resource_catalog_digest,
source_effect_catalog_digest,
startup_model_digest, input_bundle_digest, target_platform,
task0a_source_component_digest, analysis_root_identities,
runtime_root_identities,
module_catalog_digest, elf_catalog_digest, branch_policy_digest,
nodes, edges, branch_records, unresolved, budgets, closure_digest,
closure_state
```

Every regular-file or ELF node records its kind, logical name, raw source,
resolved source, sandbox destination, identity/hash/size/mode, discovery
reason, and parent edge. A synthetic namespace node instead records sealed
parent roots, synthetic topology, and exact child set. A virtual-resource node
records its resource rule and normalized in-namespace address. A built-in,
frozen, or startup node records the interpreter/startup registry provenance
that supplies it. Every node type still has a root-to-node provenance path.
Every edge is typed: `import`, `conditional`, `package_init`, `builtin`,
`frozen`, `namespace`, `startup`, `extension`, `pt_interp`, `dt_needed`, `rpath_runpath`,
`literal_dlopen`, `native_effect`, `resource`, or `config`. Each branch record
includes the source location, expression, sealed inputs, verdict (`included`,
`excluded`, or `unresolved`), and evidence. An exclusion without sealed
evidence refuses. Every `unresolved` member is a closed object with `code`,
`role`, `analysis_root_ids`, and `evidence`. The missing-session case uses only
`code: "runtime_session_entrypoint_unresolved"` and
`role: "same_namespace_pre_ack_child_post_owner"`; its
`analysis_root_ids` are the ordered declared analysis-root identifiers and its
evidence identifies the empty/malformed/incomplete runtime-root declaration.

Only two terminal states exist:

| `closure_state` | Meaning | May become a fixture manifest? |
| --- | --- | --- |
| `COMPLETE_FIXTURE_CANDIDATE` | One reviewed session-entrypoint runtime root reaches Task 0A plus every Task 0B1 runtime library, and the conservative graph is closed, provenance-backed, and budgeted | Only after separate fixture-manifest review and authority |
| `BLOCKED_UNRESOLVED` | A reachable edge, input identity, policy condition, budget, or topology is incomplete or ambiguous | No |

No current Task 0A-only record can be `COMPLETE_FIXTURE_CANDIDATE`: the future
Task 0B1 runtime-source identities, their graph, and the separately reviewed
session-entrypoint runtime root do not yet exist. Even after Task 0B1 source
authoring, the absence of that root produces
`BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)`. The current honest
result is therefore `BLOCKED_UNRESOLVED`.

Neither state claims an actual loaded set, a successful fixture, REAPER
compatibility, or authority to form a Bubblewrap/REAPER command.

## 7. Resource and stability accounting

The record contains both per-mount and aggregate accounting. It counts
`--ro-bind-data` copies by destination, not merely unique source inode:

- regular-entry count, graph edge/depth count, manifest bytes, largest regular
  entry, bytes read, and total copied bytes;
- maximum simultaneous regular snapshot, nonregular anchor, directory anchor,
  control, stdio/pipe, and temporary FDs;
- explicit FD equation: required FDs plus fixed reserve must be strictly below
  the sealed resource-policy minimum soft `RLIMIT_NOFILE`; no limit raise is
  permitted;
- conservative memory equation: page-rounded copy bytes plus private tmpfs,
  writable-tree, interpreter/launcher/Bubblewrap/child allowances and a fixed
  reserve must fit the sealed `MemoryHigh`; its worst case must fit the sealed
  `MemoryMax` with a kill reserve.

The future constructor has declared exact-root scan, total-read, manifest-size,
graph-depth, and time limits, uses low CPU/I/O priority, and refuses
deterministically before it produces a complete candidate when any limit is
exceeded.

## 8. Required future falsification evidence

When separately authorized to implement this method, all method tests remain
source/data-only and never import a target module. The test set must prove:

1. Startup roots, direct, relative, package-initializer,
   package-attribute/submodule, finite namespace-package, function-local,
   cycle, built-in/frozen, and extension/ELF edges are recorded with provenance.
   A frozen `a` that imports hidden `b` blocks if `b` is omitted from its
   frozen-effect certificate.
2. Sealed literal and platform/version branches behave as declared; environment,
   file, call-result, computed-import, namespace, and dynamic-`__all__` cases
   block unless every finite candidate and policy proof is supplied.
3. Recursive `DT_NEEDED`/`PT_INTERP` resolution works, while an escaping RPATH,
   ambient loader variable, unresolved SONAME, hwcaps ambiguity, or computed
   `dlopen` blocks. A synthetic native initializer containing either literal
   `dlopen("libhidden.so")` or a computed name, without a corresponding
   `DT_NEEDED`, blocks unless the hash-bound native-effect record closes it.
   `CDLL(None)` with an absent, wrong-version, ambiguous, or interposed provider
   also blocks.
4. Literal `open`, `os.open`, `Path(...).read_text`/`read_bytes`, and
   `/proc/self/status` accesses are cataloged as pinned regular or virtual
   resources; computed paths, dynamic aliases, and unmodeled native resource
   effects block. An unrecognized pure-Python wrapper around any resource or
   import effect blocks unless its source-effect summary closes the exact call
   graph.
5. Malformed source/ELF/catalog data, source encoding ambiguity, duplicate
   destination, symlink loop, path replacement, in-place mutation, final
   regular `st_nlink != 1`, missing root, and extra orphan node all block.
6. The same sealed inputs produce byte-identical graph and record digests;
   a source, policy, interpreter, loader, constructor, parser, or resource
   catalog change changes the relevant digest. Timestamp, FD, `PYTHONPATH`,
   cwd, HOME, `sys.modules`, import-hook, loader-variable, locale, and analyzer
   limit variation must neither change nor refuse an otherwise valid static
   result. Any ambient-induced completion, output change, or refusal is an
   implementation failure.
7. Each FD/byte/memory limit passes at its exact allowed boundary and blocks at
   boundary plus one before producing a complete candidate.

The future implementation must additionally prove that it parses data only:
no target import/execution, target extension load, target symbol call,
subprocess target entrypoint, import hook, or namespace/process creation.

## 9. Independent review and promotion rules

An independent reviewer reconstructs at least one Python path, one
extension-to-loader path, one native-effect decision, and one virtual-resource
decision from raw data and matches their edges/hashes without target import or
execution. The reviewer verifies every unresolved reachable edge blocks, every
entry has root provenance, every exclusion has sealed evidence, registry/native
effect evidence binds the exact target identity, resource equations recompute,
and the result contains no host-compatibility wording.

The original Task 0B0 method review and its Task 0B1 source-component amendment
are independently CLEAN. This does not grant Task 0B2
constructor-invocation authority, fixture authority, or host authority. A
future separately authorized graph-construction successor must show the same
method applies to the combined Task 0A/Task 0B1 analysis graph and reports the
missing runtime root before a reviewed
`fixture-runtime-manifest` can exist. The
`reaper-host-runtime-manifest` still needs separately authorized resolution of
REAPER, libSwell, GUI, X11, and all dynamic runtime behavior.

**Task 0B2 narrow correction amendment.** Under the current user `Proceed`
authorization, and only after the demonstrated sealed-synthetic-data RED,
Task 0B2 may correct only the private normalization in
`tools/reaper_v4_closure_constructor.py` required for its own constructed
synthetic record to validate. It must reseal the static constructor source
hash, rerun the static contract and Task 0B2 tests, and receive independent
review; all other Task 0B1 source expansion or correction, target
import/execution/loading, fixture or namespace action, and host action remain
forbidden.

**Task 0B2 static result.** The sole sealed synthetic input was exercised only
through the closure constructor. Its initial RED exposed an internal
immutable-snapshot normalization mismatch; the narrow correction was confined
to that private constructed record and the source resealed at
`2f8b1f02f5a730c70e38b6ebe06a99ec8abbd3c70a05851f66d6be6c5e2a97f7`.
The constructor-only test and the seven-check source contract pass, and an
independent review is CLEAN. The output is exactly
`BLOCKED_UNRESOLVED(runtime_session_entrypoint_unresolved)`, canonical digest
`0fdb65aa2467554f85fb21e2e570850921cb1615bfe56ebb4b1a0b5d5fb185bf`.
The vector's identities are synthetic placeholders: this is no fixture-runtime
manifest, host-runtime manifest, compatibility claim, or host authority.

## 10. Rejected alternatives

- **Import the target modules to inspect `sys.modules`:** rejected because it
  evaluates the very source whose closure is being justified.
- **Bind whole Python/system/library directories:** rejected because a broad
  bind conceals unresolved dependencies and defeats descriptor-pinned scope.
- **Call the conservative union the minimal loaded set:** rejected because the
  no-execution boundary cannot prove per-run minimality.
- **Replace the Python attester with a native helper now:** potentially reduces
  future closure size, but changes the architecture and needs a separate user-
  approved design; it is outside Task 0B0.
