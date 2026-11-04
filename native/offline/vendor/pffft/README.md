# PFFFT subset for the standalone cue experiment

Unmodified files from [marton78/pffft](https://github.com/marton78/pffft),
commit `7ae36e8c1d352cba66231de953cfa35f235b9e7a`.
`UPSTREAM.json` records the SHA-256 of each upstream file. The original
copyright notices and redistribution terms remain in `LICENSE.txt` and
the source files.

The optional `M3_FROZEN_CUE_PFFFT` backend builds the double-precision real
transform with AVX, without fast-math or fused contraction. It requires
`M3_BUILD_FROZEN_CUE_PROBE` and a Linux x86-64 CPU with AVX support. The Modal
harness checks that CPU feature before executing the probe. This subset is
linked only into the standalone probe and its tests; both options default off.

Preparation creates the library setup. Processing supplies aligned input,
output and scratch buffers. The test executable wraps the linked C allocation
functions as well as C++ allocation operators. The timing executable has no
allocation wrappers. Its reported workspace size excludes the opaque FFT
setup. Upstream setup allocation failure is not handled safely, so this
experiment does not establish production out-of-memory behavior.
