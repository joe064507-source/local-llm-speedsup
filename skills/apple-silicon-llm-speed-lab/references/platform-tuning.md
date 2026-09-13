# Apple Silicon specialization: GPU, Neural Engine, RAM and SSD

## Identify the actual Mac and process

Run inventory.py. Distinguish Intel versus Apple Silicon, SoC family, GPU core
count, total unified memory, probe architecture and actual serving process
architecture. The helper reads Rosetta status in its own Python process; invoking
a separate universal binary can report THAT binary's translation instead. Missing
sysctl data in a sandbox requires a read-only permission grant, not guessed specs.
Do not assume that every Mac with the same chip name has the same RAM or GPU.

Inspect the real server's interpreter/build, libraries, model revision and launch
service. Keep launchd recovery and the stable model alias intact. A healthy HTTP
endpoint does not prove the right model or newly edited code is serving. Do not
touch a user's working oMLX/MLX/llama.cpp configuration during skill installation.

## Select applicable paths

- Apple Silicon MLX/oMLX: inspect native arm64 kernels, prompt reconstruction,
  exact hybrid/recurrent state, native MTP, KV format and stream ownership. Keep
  CPU/GPU synchronization on the owning stream; avoid materializing tensors on
  reader threads just to hide I/O. Match installed source and compiled ABI.
- llama.cpp Metal: inspect actual GGUF metadata/template, GPU layer placement,
  cache type, batch/microbatch and server-slot context. Do not transfer oMLX
  internal cache patches or flags without adapting them to the runtime.
- Intel Macs: verify CPU ISA, Metal GPU support and separate/integrated VRAM.
  Apple Silicon MLX/ANE assumptions do not apply. Preserve the functioning
  backend and investigate a native CPU/Metal implementation of the relevant
  mechanism. Do not stop at the chip mismatch or choose an incompatible build;
  that new port still needs its own correctness and latency evidence.
- Core ML/ANE experiments: verify conversion, supported shapes/state, compilation,
  memory residence, numerical parity and GPU↔ANE hand-offs first. Do not promise
  that every transformer operation or every quantized checkpoint maps to ANE.

Research current upstream choices using hardware-and-research.md. Model-specific
state reuse, copy elimination, kernel fusion and bounded prefetch are candidates
when profiling identifies them as real costs—not mandatory patches for every Mac.

Coordinate the whole critical path: GPU prefill/decode, any compatible ANE
subgraphs, unified-memory ownership/copy peaks and SSD cache reads/writes.
An operation moved to ANE only helps if execution plus hand-off and memory costs
beat its GPU path in the full request. SSD read-ahead only helps if useful bytes
arrive before they are needed without evicting more valuable resident state.
Optimize useful overlap; do not require all devices to be busy at once. The
largest demonstrated seed gain was exact prompt-tail reuse, not an ANE speedup.

## Memory and lifecycle

Unified RAM is shared by weights, caches, ANE programs, staging buffers, tools,
WindowServer and the OS. Keep existing safety margins and pressure shedding;
do not inflate limits to force apparent GPU/ANE utilization. Respect thermal and
power protections. SSD swap is not equivalent to resident unified RAM.

For native extensions, build into a separate output directory and preserve the
serving binary. A Rosetta compiler cache can poison an otherwise arm64 Python
test; verify compiler target and isolate build caches when needed. Do not delete
the user's whole cache or restart launchd just to retest a helper script.

Measure complete warm, cold and novel-prefix responses with thinking/tool schemas
unchanged. The anonymized Qwen case is evidence for that workload only. Increasing
children on a singleton model means queued inference plus overlapping tools, not
independent full-speed model copies. Verify real child results before claiming
multi-agent integration, and do not advertise an untested fan-out as optimal.
