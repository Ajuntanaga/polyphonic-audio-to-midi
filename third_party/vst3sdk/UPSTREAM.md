# Pinned Steinberg VST3 SDK

Retrieved UTC: `2026-08-29T12:08:18Z`

Tag: `v3.8.1_build_84`

Only the official root build/license/readme files and the four required
submodule worktrees are retained. The copied tree is source-only and contains
no Git metadata.

## Locked revisions

| Path | Repository | Revision |
| --- | --- | --- |
| `.` | `https://github.com/steinbergmedia/vst3sdk.git` | `3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96` |
| `base` | `https://github.com/steinbergmedia/vst3_base` | `fcf9da0bd27a16f7f03773a3a39822f28f5c8477` |
| `cmake` | `https://github.com/steinbergmedia/vst3_cmake` | `054c9143cbb8d47fc4694e473f2ee3b4d951a8f5` |
| `pluginterfaces` | `https://github.com/steinbergmedia/vst3_pluginterfaces` | `4f547e8e102b47de4a8b8aaf343c73b700786372` |
| `public.sdk` | `https://github.com/steinbergmedia/vst3_public_sdk` | `586dc5e6c8012c3e4b01c79389375cbe96bdb1da` |

The root gitlinks and each checked-out submodule HEAD were verified against
these five revisions before any source was copied.

## Retrieval commands

The acquisition ran once under low CPU and idle I/O priority in ignored build
storage. The source-changing commands were:

```sh
git ls-remote https://github.com/steinbergmedia/vst3sdk.git refs/tags/v3.8.1_build_84
git clone --filter=blob:none --no-checkout https://github.com/steinbergmedia/vst3sdk.git build/vendor/vst3sdk-src
git -C build/vendor/vst3sdk-src checkout --detach 3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96
git -C build/vendor/vst3sdk-src submodule update --init --depth 1 base cmake pluginterfaces public.sdk
```

The network commands were bounded with `timeout`, run at `nice -n 15`, and
assigned idle I/O priority with `ionice -c3`. The retained copy used:

```sh
install -m 0644 build/vendor/vst3sdk-src/CMakeLists.txt third_party/vst3sdk/CMakeLists.txt
install -m 0644 build/vendor/vst3sdk-src/LICENSE.txt third_party/vst3sdk/LICENSE.txt
install -m 0644 build/vendor/vst3sdk-src/README.md third_party/vst3sdk/README.md
rsync -a --exclude=.git build/vendor/vst3sdk-src/base/ third_party/vst3sdk/base/
rsync -a --exclude=.git build/vendor/vst3sdk-src/cmake/ third_party/vst3sdk/cmake/
rsync -a --exclude=.git build/vendor/vst3sdk-src/pluginterfaces/ third_party/vst3sdk/pluginterfaces/
rsync -a --exclude=.git build/vendor/vst3sdk-src/public.sdk/ third_party/vst3sdk/public.sdk/
```

`SHA256SUMS` is generated lexically from the repository root and covers every
retained file except the manifest itself.

## Retained and excluded scope

Retained roots: root `CMakeLists.txt`, `LICENSE.txt`, `README.md`, `base`,
`cmake`, `pluginterfaces`, and `public.sdk`.

Excluded roots: `doc`, `tutorials`, and `vstgui4`. Archives, generated build
files, and all `.git` metadata are also excluded. Project CMake configuration
disables VSTGUI, VST3 plug-in examples, hosting examples, automatic plug-in
links, and default validator execution; only the separately requested official
validator and module-info utility may be built.
