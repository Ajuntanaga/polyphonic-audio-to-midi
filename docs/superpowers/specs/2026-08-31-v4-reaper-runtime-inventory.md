# V4 REAPER Runtime-Manifest Inventory

Date: 2026-08-31
Status: static candidate only; **not safety-complete, launch-complete, or namespace-execution authority**
Scope: read-only inventory supporting the V4 scan-isolation design

## Decision

V4 stays blocked. This inventory identifies a small static starting set, but it
does not establish the exact GUI, dynamic-loader, Python-attester, X11, font,
configuration, or audio closure needed for a compatible REAPER launch. No
REAPER process was started to produce this document.

The required future host-runtime manifest is an immutable, individually
descriptor-pinned regular-file table plus explicit non-regular entry rules. It
may not replace that table with a broad `/usr`, `/lib`, `/lib64`, REAPER-install,
or home-directory bind. It covers both the Python attester closure and the
REAPER/libSwell/probe GUI closure; a non-REAPER fixture cannot prove a REAPER
dynamic dependency unnecessary.

An entry has one of these kinds:

| Kind | Required identity and mount rule |
| --- | --- |
| regular read-only | raw source/safe ancestors, mode, device/inode, SHA-256, `O_RDONLY|O_NOFOLLOW` FD snapshot, declared executable/read-only destination, and `--ro-bind-data` only |
| in-namespace symlink | literal destination/target, no host source, target resolves only within the namespace |
| X11 Unix socket | exact `DISPLAY`, raw path/safe ancestors, socket type, owner/mode, device/inode, `O_PATH|O_NOFOLLOW` anchor, FD-anchored Bubblewrap bind, pre-ACK in-namespace comparison, and post-run revalidation; no SHA-256 claim |
| writable staging/profile directory | fresh parent-dirfd creation, exact owner/mode/tree/no-symlink rules, retained anchored directory FD, FD-anchored Bubblewrap bind, pre-ACK identity comparison, and post-run revalidation; no SHA-256 claim |

The V4 RPP, ReaScript, and private Xauthority are regular inputs when they
exist. They are recorded in a separately sealed run-input manifest that links
to, but never modifies, the sealed host-runtime manifest.

## Static baseline candidates

These are current-host observations. Every entry would be a read-only
individual file mount. Symlink destinations require a separately listed target
and symlink topology; a directory mount is not implied.

Where a familiar system-library name is itself a host symlink, the table names
it only as an inventory alias. A completed manifest must instead name the
resolved one-link regular target as the FD source and recreate only the reviewed
in-namespace symlink topology. It must never open a host symlink with a
no-follow snapshot operation.

| Source | Proposed destination | SHA-256 | Static reason |
| --- | --- | --- | --- |
| `/usr/bin/bwrap` | not mounted; trusted outer launcher only | `0abea81db798ebf6b4742ac0664802d97521547a353c2a0dbdc21d76cbbfd2c0` | namespace boundary; outer validator also requires root:root, 0755, regular, no caps/setid |
| `/home/ajuntanaga/opt/REAPER/reaper` | `/opt/reaper/reaper` | `cee99a74fdd9fc87974c96ea334a50afff4ca8d3121591aed218057bb38185e4` | REAPER main ELF |
| `/home/ajuntanaga/opt/REAPER/libSwell.so` | `/opt/reaper/libSwell.so` | `9b991d09df2fe359d47dc3f0b3d2e9aa358d806c702bb93c11d6b2fe61db011c` | REAPER static local reference |
| `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2` | same, plus exact `/lib64/ld-linux-x86-64.so.2` topology | `c5e80a563850d6ab5c2f2482e4202d9c1b71fbf44854b8c399e63527202c64e1` | ELF interpreter |
| `/usr/lib/x86_64-linux-gnu/libpthread.so.0` | same | `f93acb6e78dcf0213c8a85f922d21916249148e24de426079c40b6304c42085d` | direct `DT_NEEDED` candidate |
| `/usr/lib/x86_64-linux-gnu/libdl.so.2` | same | `7d293f8361fcead4f9691561adc0413f724f3607b959abe0d4fb243072956079` | direct `DT_NEEDED` candidate |
| `/usr/lib/x86_64-linux-gnu/libasound.so.2.0.0` | same, plus exact `libasound.so.2` topology | `40247a1edec481d7bbb229bbad85f3574448f689c3da7efc4768d4dcc7ef2dff` | direct `DT_NEEDED` candidate; does not authorize audio-device access |
| `/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.35` | same, plus exact `libstdc++.so.6` topology | `5bb0d21308f123b6ad46c6f35b42cedfcb8d6d439a53aa3dae04d880aaffdde3` | direct `DT_NEEDED` candidate |
| `/usr/lib/x86_64-linux-gnu/libm.so.6` | same | `beea4eeacfcfa2cd96011b959a826c97cf4a774017e214f6a34d7eea3d49cd88` | direct `DT_NEEDED` candidate |
| `/usr/lib/x86_64-linux-gnu/libgcc_s.so.1` | same | `9d339ecb409578d6a5d587e6c537a8f9589b8a13fefba30d167433a4b5758bee` | direct `DT_NEEDED` candidate |
| `/usr/lib/x86_64-linux-gnu/libc.so.6` | same | `a3947513a02831ec692ebf13053c07614882ab54a2101fb91a1b15724062ed0c` | direct `DT_NEEDED` candidate |
| `/usr/bin/python3.14` | exact private attester destination | `b8d8288faefdd300201f43fcf00f6f539a27218eeed3a3dff5ab10b9c4c99700` | attester entrypoint candidate only |
| `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so` | `/opt/m3-vst3-probe/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/x86_64-linux/M3_Polyphonic_Audio_to_MIDI_Probe.so` | `49c5b442e262394458be5d63e200ca26a62b8cc44b7e76c9160c52c654bd5521` | descriptor-pinned VST3 probe only |
| `build/vst3/release/VST3/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/Resources/moduleinfo.json` | `/opt/m3-vst3-probe/M3_Polyphonic_Audio_to_MIDI_Probe.vst3/Contents/Resources/moduleinfo.json` | `85b8bb18526e8f4ec4744e27069551741b01a8268efb3d97d8ab985e59fec24f` | descriptor-pinned VST3 metadata only |

The current full REAPER installation was observed to contain 2,645 files.
Aggregate table digests are inventory clues only and are intentionally not part
of this acceptance boundary. They do not authorize mounting that directory or
substitute for individual runtime entries.

## Explicit unresolved closure

Static inspection identifies dynamic loads that prevent a minimum-compatibility
claim today:

- `libSwell.so` names GUI libraries including `libX11.so.6`, `libXi.so.6`,
  `libGL.so.1`, `libfontconfig.so.1`, and `libgdk-3.so.0`; each needs its own
  recursive closure and configuration/font dependency evidence.
- REAPER names `libjack.so.0`, `libpulse-simple.so.0`, Lua modules, and
  install plug-in components through dynamic-load paths. Their actual need
  cannot be proved from the direct ELF list.
- Python 3.14 needs its interpreter closure, standard library, and perhaps
  extension modules. No exact minimal attester runtime manifest exists yet.
- The current non-GUI process has no `DISPLAY` or `XAUTHORITY`. At a future
  separately authorized inventory gate, validate only the active X socket and
  a copied private authority file. Never bind `$XDG_RUNTIME_DIR`, session
  D-Bus, or `/run` wholesale.
- The V4 design deliberately exposes no `/dev/snd`, JACK, Pulse, PipeWire, or
  ALSA configuration. Adding audio-device access requires a design amendment,
  not a runtime-manifest completion shortcut.

## Plug-in denial boundary

The manifest must contain no VST2, VST3, CLAP, or LV2 tree. The private root
plus exact mount allowlist is the primary boundary. Offline fixtures also use
these canaries:

| Format | Default-root canaries |
| --- | --- |
| VST2 | `/usr/lib/vst`, `/usr/local/lib/vst`, `/usr/lib/x86_64-linux-gnu/vst`, `$HOME/.vst`, `$HOME/.local/lib/vst` |
| VST3 | `/usr/lib/vst3`, `/usr/local/lib/vst3`, multiarch and share variants, `$HOME/.vst3`, `$HOME/.local/lib/vst3` |
| CLAP | `/usr/local/lib/clap`, `/usr/lib/clap`, multiarch/share variants, `~/.clap`, `$HOME/.local/lib/clap`, and any `CLAP_PATH` input |
| LV2 | `/usr/local/lib/lv2`, `/usr/lib/lv2`, multiarch/share variants, `$HOME/.lv2`, `$HOME/.local/lib/lv2` |

The only discovered live canary is
`$HOME/.vst3/yabridge/ATONE.vst3`, with a member symlinked into the Wine plug-in
tree. It must be absent from the namespace and is never altered.

## Task 0A source-component seal

Commit `fac3b5e` seals the non-admissible source component, not an executable
attester or a runtime manifest:

| Source | SHA-256 | Role |
| --- | --- | --- |
| `tools/reaper_v4_protocol.py` | `82afbe01cf11f083481db26cc10927965cd1341b4b75367ceda25de0d82b8331` | In-memory canonical frame envelope and base configuration grammar |
| `tools/reaper_v4_attester.py` | `1b6cae926421615fb6f42fe1ee40d4a09d1dd862296a90c38b8371ee42377891` | Non-admissible configuration and mocked-testable barrier primitive |
| `tests/test_reaper_v4_protocol.py` | `809a0b71c65e1e24e5c3f03a247408cec9dfec619d559acbddd1ad5ef0233192` | Pre-import source-shape and focused behavior gate |

Declared runtime imports are `dataclasses`, `enum`, `hashlib`, `json`, `struct`,
`collections.abc`, `ctypes`, and `pathlib`. The static candidate closure includes
`_ctypes`/libffi, `_hashlib`/libcrypto, interpreter built-ins such as `_json` and
`_struct`, plus transitive pure-Python standard-library modules. The actual
recursive import, extension, loader, `sys.path`, and conditional-import closure
remains **unresolved-static-overapprox**. No target code was imported for this
inventory, and this component cannot emit a receipt, consume an ACK, start a
child, create a namespace, or support a host command.

## Completion gate

The gate has two deliberate meanings:

1. A **safety-complete** reviewed allowlist can support a bounded non-REAPER
   fixture. It may cleanly refuse because its regular-file set is incompatible
   with REAPER; it must never imply compatibility.
2. A **compatibility-complete** reviewed allowlist resolves every REAPER,
   libSwell, probe, GUI, Python, X11, configuration, and dynamic-load input
   needed for the single V4 row. Only that stronger state can satisfy a future
   host-launch precondition.

Phase A contains only a sealed, non-admissible frame-envelope/base-identity and
barrier skeleton. It has no PRE/POST schema, measured collector, standard-stream
control, or child-launch module, and its tests never create a namespace or
process. Task 0B must separately author, without invoking, the exact receipt
schema/exchange module, measured collectors, and child-runner adapter. Before
any fixture, the reviewed manifest successor must seal all three source hashes
and every newly imported Python source, extension, and ELF dependency, while
referencing the immutable Phase A skeleton manifest. The later Bubblewrap
fixture validates only the safety-complete table. Neither activity proves the
compatibility-complete REAPER closure. Until the applicable manifest state is
complete:

1. do not form or execute a V4 REAPER command, launch REAPER, or broaden a
   runtime bind;
2. do not pass pathname-mounted regular sources to Bubblewrap; and
3. do not treat an incomplete runtime closure as retry or host authority.
