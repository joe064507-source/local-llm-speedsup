# Use the working engine as a design reference, not a universal patch set

These recipes were checked against the actual reference engine's source, not
inferred only from online advice. Module/function names below establish the
mechanism's lineage; they are NOT imports, a dependency on that checkout, or
instructions to look for the original owner's files. No runtime source,
personal configuration, machine identifiers or model weights are included.

For a new machine, map a recipe to its actual bottleneck and owning code, then
write, test and deploy a host-specific implementation. The original chip gates,
model aliases, memory caps, tile sizes and thresholds are not portable defaults.
Replace them with conditions supported by the new runtime and measured hardware.
Do not merely remove a compatibility check or apply all recipes indiscriminately.

## 1. Exact prompt-tail reuse with complete state

Reference mechanisms: `cache/exact_prefill.py` capture/restore;
`cache/prefix_cache.py` exact-prefix storage; scheduler prefill/insertion hooks;
`patches/mlx_lm_mtp/prompt_priming.py` paired head snapshots.

**Observed waste:** block-aligned prefix caching left a partial tail to recompute
on repeated system/tool prefixes and continuations. The improvement retained
the missing computation state, not a previous answer.

**Implementation shape:** find the actual next-token kickoff convention. Where
it consumes the final token, capture the state after N−1 prompt tokens. Reuse
compatible full blocks, retain the missing terminal and exact recurrent endpoint,
and pair the native drafter's state before publishing an entry. Restore the longest
compatible prefix that extends an ordinary cache hit. A missing component is a
normal-cache fallback, not a reason to damage the existing hit.

The drafter's retained suffix length is not its absolute backbone position.
Carry both, plus pending hidden input and any valid boundary candidate. Admit
memory BEFORE cloning state; account for retained snapshots coexisting with
the new copies. Clone immutable snapshots before the next request mutates them.
Validate actual serialized codec/layout markers, not just a cache class name.
Separate temporary block-table ownership from the active request. Protect paired
publication against an older asynchronous writer replacing the terminal.

**Port:** on a dense attention model, implement the equivalent exact KV boundary;
do not invent recurrent or MTP state that it does not have. On a hybrid/SSM model,
snapshot the real recurrent boundary rather than slicing it like attention KV.
On another native/external drafting implementation, inspect its actual verifier,
history, RNG and rejection state. Do not transplant an MTP snapshot format.

**Prove:** raw/restored tensors, offsets, codecs and continuation correctness;
all-or-nothing paired restore; writer races, misses, pressure and cancellation;
warm/novel-prefix latency with real schemas. See exact-prefix-contract.md. This
recipe produced the strongest repeatable end-to-end gain in the case study.

## 2. Shape-specific attention work reduction

Reference mechanisms: `patches/turboquant_pair_attention.py` and the dispatch
in `patches/turboquant_attention.py`.

The reference first-pass kernel handles two KV positions per online-softmax
update, reusing query data and combining normalization work. The normal second
pass remains. Every causally visible token is still attended to; cache precision
and the target sampling rule do not change. The extra registers can make narrow
verification shapes slower, so the dispatch keeps the ordinary path there.

**Port:** inspect the new backend's attention algorithm, cache packing, strides,
subgroup/warp width, register occupancy, head dimension and verification shape.
Implement in the supported kernel language or runtime extension only if that
work lies on its measured critical path. A CUDA/ROCm/Vulkan/CPU implementation
needs its own indexing and reduction design, not translated Metal constants.
If an existing kernel already removes this cost, move to another bottleneck.

**Prove:** causal-mask parity, awkward lengths/strides, empty or masked blocks,
supported/unsupported dispatch and complete request latency. Reordered floating
point reductions are not bit-exact: quantify errors and test output/tool quality.
The reference showed workload-specific gains, not a universal decode multiplier.

## 3. Read known continuation bytes during real tool waits

Reference mechanisms: `cache/continuation_read_ahead.py`, `cache/phase_runtime.py`
and `cache/phase_protocol.py`.

Observe a successfully completed structured tool-call stream without rewriting
events or retaining its text/arguments. During the tool gap, stage only known
cache files likely to be needed by that continuation. A single CPU-only worker
reads bounded raw bytes; the inference owner reconstructs tensors with the normal
loader/codec. Consume staged bytes once and release them or fall back normally.

Check file identity before/after reading and again at consumption. Cancel by
generation when the continuation changes. Stop scheduling on new inference or
memory pressure. Keep already-useful staged data instead of scanning and evicting
the entire candidate list. Account for mutable/immutable copies during a read,
then transfer the charge to the consumer until its bytes are released.

**Port:** map the actual cache index, lifecycle events, storage paths and normal
deserializer. A native callback may be better than SSE observation. Check file
identity using the target OS's reliable primitives; do not assume POSIX inode
semantics on every filesystem. Restrict reads to owned cache roots, never a home
directory or arbitrary model/user files. RAM-resident or already asynchronous
loaders may gain nothing from another reader.

**Prove:** exact byte/tensor/metadata parity, consume-once ownership, cancellation,
closed owners, changed files and failed streams. Measure both first activity and
full continuation latency. The reference consumed prefetched data but did NOT
establish a meaningful end-to-end gain. Successful I/O is not proof of speed.

## 4. One budget for competing optional work

Reference mechanisms: `cache/phase_budget.py` and `cache/phase_runtime.py`.

Use fresh measurements from the existing memory enforcer. Admit optional work
against its real ceiling and reserve transient copies conservatively. Request
or phase transitions revoke stale leases; revoked bytes remain charged until
their owners have actually released buffers. Expired/unknown telemetry admits
no new optional work. A cancellation request cannot free an in-flight syscall's
buffer by itself. Probe devices only on a thread allowed by the runtime.

**Port:** on unified memory, do not count accelerator allocations twice in the
process footprint. On discrete GPUs, maintain separate host RAM, each device's
VRAM, pinned/staging buffers and transfer obligations. Available RAM cannot pay
a VRAM reservation. Honor cgroup/affinity/runtime limits where applicable.
Choose phase admission based on this runtime's ownership and measured contention;
do not copy the reference's exact optional-byte limits or assume it supports
continuous batching just because several agents exist.

**Prove:** stale telemetry, concurrent reservations, epoch transitions, revocation,
delayed release and low-memory fallback, without raising the original guard.
This is an enabling resource mechanism, not an independently proven speed gain.

## 5. GPU/NPU partitioning: optimize the hand-off, not utilization

Reference mechanism: `patches/qwen35_ane_prefill.py`, especially prefill module
selection and preparation/compilation lifetimes; the separate tiled-overlap
prototype was not retained as a successful optimization.

The reference excludes draft-only modules from scarce prompt-offload slots:
traversal order can otherwise fill them with modules that never receive useful
prefill shapes. It adapts tile/chunk sizing to the available working set and
releases preparation buffers only after device users finish. Existing code may
already stage compilation one layer at a time; verify this before claiming it as
a new patch. Include compilation, retained programs, copies and synchronization
in the resource/latency accounting.

**Port:** identify genuinely supported NPU/ANE subgraphs and state interfaces.
Evaluate the entire boundary: producer → materialization/layout → device call →
consumer synchronization. On a machine without a suitable NPU path, optimize the
GPU/CPU path instead. Do not force conversion, reduce precision/thinking, or split
a recurrent layer into tiles without testing its changed numerical behavior.

**Prove:** operator/state parity, lifetime and peak-memory tests, then full-request
quality/latency with compilation and steady state reported separately. The
reference ANE split essentially tied GPU-only; the overlapped prototype changed
rounding and did not justify deployment. Retain these negative lessons.

## 6. Sampling, lifecycle and agents

Reference lessons: native-MTP sampler preparation was faster in isolation but
not reliably faster end to end; prompt warm-up and shared-model request admission
improved operational behavior without creating more model compute capacity.

Reuse immutable sampler preparation only with distribution/RNG and history-window
parity. Do not keep it solely because a microbenchmark improves. Stable tool/system
prefixes support computation reuse; do not remove tools or memories to shrink them.
Prewarming can move cold work earlier but must yield to user requests and cannot
be advertised as faster cold computation. Verify normal launch and serving-code
adoption after updates; a file edited on disk is not an activated engine patch.

Several agents can overlap tools while sharing one model. Match admission to the
backend: serial inference for a singleton path, tested batching/replicas only
where compatible and memory-safe. Recheck returned child results and actual tool
execution. Preserve the user's local-only policy; never silently use cloud LLMs.

## Required porting outcome

For each selected recipe, record privately: observed cost → owning source/API →
new implementation → compatibility/fallback → correctness tests → matched latency
→ deployment/rollback result. Investigate unlisted bottlenecks too. A recipe list
is not the deliverable when the user asked for an implementation.

This guide transfers the engineering reasoning, not universal compatibility.
Do not claim reference patches are installed when only this skill was installed,
or claim complete quality equivalence from a narrow screen.
