# Exact prefill endpoint contract

This is an engineering recipe, NOT a drop-in patch for arbitrary runtimes.
The seed implementation was validated for a singleton Qwen hybrid-cache path.
Another architecture or checkpoint must establish its own compatibility and
parity; a model alias alone is not sufficient proof.

## State and position

For a prompt of N tokens, kickoff commonly needs the state after N−1 tokens plus
the final token as input. Confirm the actual runtime convention. Restoring N and
feeding the last token again is wrong. Recurrent/SSM/GDN state generally cannot
be trimmed like an attention KV array: preserve the exact boundary during prefill.

An entry's identity includes weight/tokenizer/template/adapter revision, rope and
position settings, exact token prefix, cache types and quantization codec/seed,
layer layout/dtypes, media/extra-input identity when supported, and draft model
state compatibility. Gate unsupported batched, sparse-prefill or multimodal inputs
out of the optimization while keeping their ordinary inference available.

Separate absolute prefix position from a draft head's physically retained suffix
history. If only five drafting tokens are folded at an absolute position of 19,
restoring it as though 18 drafting tokens existed invents state. Snapshot the
head's actual offset, pending hidden input, cached arrays and matching model host.
Publish a reusable entry only after backbone, recurrent endpoint and draft head
all exist. Restore all of them together or none; leave the prior ordinary path
untouched on a miss. Do not mix a matched backbone with an unmatched drafter.

## Storage, ownership and lifetime

Reuse already compatible full blocks; persist only the missing partial terminal
and exact recurrent sidecar when possible. A metadata cache-type name can lie
about old payload layout; validate actual format markers/codec identity too.
Avoid copying the entire dense KV just to retain small recurrent arrays.

An asynchronous writer can overwrite a newer terminal or clear its pending buffer
after a sidecar was replaced. Serialize or reject an in-flight terminal replacement
BEFORE committing paired state. Test the race with barriers, not sleeps. Keep
temporary request tables separate from the live request's ordinary block table;
clean up ownership on every failure. Optional capture/restore must fail closed
without discarding a valid normal-cache hit or mutating immutable snapshots.

Bound entry count, actual detached tensor bytes, staging/copy peaks and admission
under the existing memory ceiling. A RAM-index TTL is not an SSD deletion policy:
document private disk-cache retention/eviction separately. Tensor caches can encode
conversation state; do not export them as harmless benchmark data.

## Minimum tests before measuring

- Raw versus restored tensors/offsets for each supported cache representation.
- Exact N−1 one-token kickoff and ordinary-prefix fallback ownership.
- Full and suffix-only MTP priming, candidate/pending-state restoration.
- Wrong model host, token prefix, format, media and sparse inputs reject safely.
- Missing/corrupt/expired components and memory-pressure admission.
- Pending-writer replacement races, exceptions and cleanup without double free.
- Batch/stream isolation and ordinary scheduler/cache regression tests.
- Real full-schema inference, tool execution and returned delegated results.

Bound optional checkpoint capture independently of the model's configured
conversation context. Longer or unsupported requests must use ordinary inference;
an optimization coverage boundary is not permission to lower conversation context.
Do not claim that a fully populated native window fits without testing its memory
requirements on the actual host.
