# Matched local inference measurements

## Contract and inventory

Record hardware/memory, OS/architecture, runtime and dependency revisions, exact
weights/tokenizer/template/adapters, quantization, context, thinking/sampling,
tool schemas, cache representation and serving queue. Hash private fixtures;
never publish their raw contents. Freeze a private fixture within each comparison:
agent memories, tools and system instructions can change between sessions.

Track separate clocks: submission-to-first-activity, submission-to-first-content,
complete model request, generation-only time when server instrumentation exists,
tool execution and complete task including queueing. Do not infer decode speed
from output tokens divided by full request time. Missing token usage is unknown,
not permission to estimate it with character counts.

Warm-ups must be scheduled in advance and excluded consistently, not chosen
after observing a slow result. Include cold/novel-prefix cases when claiming
general chat gains. Cache state must be described; do not clear a user's cache
without approval. An optimization that reuses an exact tail does not accelerate
an unseen tail. Different stochastic output lengths are a confound, not evidence
of quality improvement. A test output ceiling must not truncate a valid trial.

## Portable streaming fixture

The helper uses standard-library Python 3.10+, no downloads or model libraries.
Create the fixture outside the public skill folder. Adapt every server-specific
request option to the installed runtime; do not silently disable thinking when
a server rejects the option. The illustrative arithmetic fixture below does NOT
represent a complete agent-quality benchmark or carry the user's real tools.

```json
{
  "version": 1,
  "cases": [
    {
      "id": "arithmetic",
      "request": {
        "messages": [{"role": "user", "content": "Compute (137 * 29) - (84 / 7). Check your work, then make the final answer only the integer. No tools needed."}],
        "temperature": 1.0,
        "top_p": 0.95,
        "max_tokens": 2048
      },
      "expect": {"text_exact": "3961"}
    }
  ]
}
```

`request` preserves all supplied tools, messages, sampling and thinking options.
The helper adds `model` and `stream: true`; an existing different model is rejected.
Set `stream_options: {"include_usage": true}` in the fixture if supported. If no
usage arrives, latency can be measured, but tokens/second remains null.

Expectations support exactly one of `text_exact`, `text_regex`, or
`tool_call: {"name": "...", "arguments": {...}}`. Text cases reject tool calls.
Tool cases require exactly one structured call with matching JSON arguments;
they DO NOT execute it. A permissive regex is only a smoke screen. Add real
tool round trips and domain/vision/long-context quality evaluation separately.
OpenAI-style `content`, `reasoning_content` and `reasoning` text deltas are
understood; other stream dialects require an adapter and tests.

```sh
python3.11 scripts/bench.py --base-url http://127.0.0.1:8082/v1 --model MY_MODEL --fixture /private/path/cases.json --label before
python3.11 scripts/bench.py --base-url http://127.0.0.1:8082/v1 --model MY_MODEL --fixture /private/path/cases.json --label before --run --confirm-idle --warmups 3 --repeats 5 --out /private/path/before.json
```

The default is preview-only. `--run` only sends normal inference requests and
can naturally populate existing caches; it is NOT a configuration toggle.
`--api-key-env LOCAL_LLM_API_KEY` reads an optional local-server credential from
that one environment variable, never prints it and never probes a cloud host.
Remote LAN/tailnet/cloud endpoints are intentionally rejected by this helper.

Supply `--identity /private/path/identity.json` to fingerprint a fixed hardware,
weights/tokenizer revision, precision and capability contract for both runs.
Only its hash is exported. Do not hash changing free-memory/disk counters as the
fixed identity. The agent must verify the declared identity against the serving
runtime: an identical alias alone does not prove identical weights. The comparison
rejects differing identity hashes and explicitly reports when identity was not
recorded; it does not independently inspect weights or hardware.

With oMLX, optionally add `--status-url http://127.0.0.1:8080/api/status`.
Recognized status fields are `active_requests`, `waiting_requests`,
`models_loading`, and optional `total_requests`. The helper checks idle state
before/after each request and requires a +1 counter delta when both counters are
present. It does not inspect arbitrary payload fields or retain model-status
details. Without counters, overlap is marked unknown. A submitted request that
finds subsequent contamination is invalid, never silently discarded as an outlier.
Busy preflight stops the run without submitting that request. Status is an
advisory observation, not an atomic reservation; use an exclusive test window.

## Comparison

Toggle a candidate only through an approved, idle-safe runtime operation outside
the benchmark. Preserve its prior state for rollback; no blind server restart.
Use identical fixture/model/seed/order/repetition counts within each pair.
If the engine only best-effort honors seeds, retain that caveat. Run the feature
off and on again to check repeatability rather than trusting one lucky sample.

```sh
python3.11 scripts/compare.py --pair before.json after.json --pair before2.json after2.json
python3.11 -m unittest discover -s scripts -p 'test_*.py'
```

Comparison reports paired medians and relative TIME reductions per case. Negative
values are regressions. It does not average unlike tasks into a universal score,
combine mismatched prompts silently, or pronounce reasoning quality unchanged.
Every measured case must pass its declared screen and be untruncated. Insufficient
repeats or overlap instrumentation remains visible even if the medians improved.
Every declared warm-up and measured trial must be present exactly once. Reusing
the same trial rows—even under another filename or label—is rejected; repeated
evidence needs fresh before AND after runs. The two-pair minimum is met only when
every reported case has at least two pairs with three measured repetitions.
These checks catch accidental reuse or incomplete reports, not fabricated data.
Inspect all raw rows, including warm-ups and failures. Use a larger, representative
workload before release; three repetitions are a screen, not statistical certainty.
