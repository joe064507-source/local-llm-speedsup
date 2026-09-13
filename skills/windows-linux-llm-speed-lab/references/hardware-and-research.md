# Hardware-aware research

## Detect before selecting a backend or kernel

`scripts/inventory.py` performs bounded, read-only OS queries and prints a
sanitized inventory. It does not load a model, benchmark a GPU, install packages,
contact the internet or change any service. It collects CPU/architecture, memory,
disk free space, and accessible GPU data on macOS/Linux/Windows. Missing probes
remain unknown. Its macOS path is tested on the seed machine; other OS adapters
have parser tests, not a claim of live testing on those hosts.

On Apple Silicon, compare Python/process architecture with hardware and report
Rosetta translation if detected. Query GPU names/cores from display records, not
hardware serial numbers. Unified RAM is not dedicated GPU VRAM. On CUDA hosts,
collect visible GPU count/name/memory/driver without UUIDs or running process
names. PCI topology, interconnect bandwidth, NUMA and multi-GPU placement need
additional scoped inspection before proposing sharding. On AMD/Intel hosts,
identify the actual driver/backend and verify supported kernels rather than
assuming CUDA-equivalent coverage. Windows display memory reporting may be
incomplete; verify it with the serving runtime before capacity decisions.

Disk free bytes are capacity, not measured SSD bandwidth. Probe hardware
capability separately from runtime support and from observed utilization. A
Neural Engine/NPU on the chip does not prove this model has an executable NPU
graph. Do not turn on unsupported acceleration merely to show utilization.

The helper's installed-package list describes its own Python environment only.
Find the actual serving process/interpreter, version and accelerator build using
scoped local checks. Do not dump process environments, credentials or all command
lines. Account for weights + KV/recurrent/draft state + transient buffers + tool
processes + OS reserve. Keep existing thermal/power/memory protections.

## Research pass

Use the installed source/configuration as the starting point, then browse current
PRIMARY sources: runtime docs/releases, exact model card/config/chat template,
hardware/vendor documentation and relevant upstream patches/issues. Confirm
publication/version dates and whether a proposed fix already exists in this
checkout. Record an option matrix: applicability, expected bottleneck, memory
cost, numerical risk, evidence and test needed. External performance claims are
hypotheses until reproduced on this machine with its real workload.

Useful starting points, verified when this skill was created (2026-09-12):

- [MLX unified memory](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html): CPU/GPU memory and execution model; do not infer that every operation benefits from a device hand-off.
- [MLX-LM source and usage](https://github.com/ml-explore/mlx-lm): inspect installed generation/cache/speculation implementation and compatible model support.
- [llama.cpp server documentation and source](https://github.com/ggml-org/llama.cpp/tree/master/tools/server): verify the installed build's serving, batching, cache and speculative options rather than transferring flags from another engine.
- [Core ML stateful models](https://apple.github.io/coremltools/docs-guides/source/stateful-models.html): state must be explicitly modeled and managed when evaluating a separate Core ML path.

These links are research entrypoints, not frozen recommendations or claims that
every backend can serve every model. Discover other hardware-specific official
sources when relevant. Do not install random acceleration scripts or pipe a web
response into a shell. If research is unavailable, state the evidence gap and
continue only with locally supported experiments.

## From research to original work

Prefer a supported option if it addresses the measured bottleneck and preserves
the contract. If it does not, inspect traces and identify repeated work, avoidable
copies, allocation/synchronization costs, unretained state or a scheduling gap.
Form a falsifiable custom-patch hypothesis with a predicted observable effect.
Use custom-patch-workflow.md; do not merely rename a model into another model's
compatibility gate or copy the seed machine's memory limits.
