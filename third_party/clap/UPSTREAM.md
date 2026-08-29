# CLAP Header Provenance

- Upstream: `https://github.com/free-audio/clap`
- Tag: `1.2.10`
- Commit: `195b42a004144fab0b3cf95e9c067187d15365b7`
- Retrieved UTC: `2026-08-29T05:59:30Z`
- Copied subtree: `include/clap`
- Copied license: `LICENSE`

Verification and retrieval commands:

```text
git ls-remote https://github.com/free-audio/clap.git 'refs/tags/1.2.10*'
git clone --filter=blob:none --no-checkout https://github.com/free-audio/clap.git build/vendor/clap-src
git -C build/vendor/clap-src fetch --depth 1 origin 195b42a004144fab0b3cf95e9c067187d15365b7
git -C build/vendor/clap-src checkout --detach 195b42a004144fab0b3cf95e9c067187d15365b7
```

Only the official `include/clap` header tree and `LICENSE` were vendored.
Upstream examples, helpers, CMake files, and source implementations were not
copied.
