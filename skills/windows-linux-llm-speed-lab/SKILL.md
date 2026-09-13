---
name: windows-linux-llm-speed-lab
description: "Detect Windows/Linux CPU, GPU and memory topology, research compatible inference backends, and implement custom local-LLM speed patches with matched quality checks. Use for CUDA, ROCm, Vulkan, CPU, WSL or multi-GPU agent performance."
---

# Windows/Linux LLM Speed Lab

Deliver a measured reduction in the user's actual waiting time, without silently
changing their chosen model or capabilities. This is a portable experimental
workflow, not a universal acceleration switch. A successful result can also be
an honestly rejected prototype and an intact working setup.

When asked to optimize, implement and test machine-specific changes where
feasible; a suggestion list is not the deliverable. The working reference engine
is the engineering guide, not a fixed patch set. Read
[engine-porting-guide.md](references/engine-porting-guide.md) to transfer its actual
mechanisms and negative findings, then
[adaptive-implementation.md](references/adaptive-implementation.md) for the
implementation loop and guarded source check/apply/rollback helper.

This edition targets Windows/Linux machines: native/WSL/container environments,
discrete GPUs, integrated GPUs/APUs, CPU-only and multi-GPU hosts. Read
[platform-tuning.md](references/platform-tuning.md) after hardware detection.
For macOS on Apple Silicon use `apple-silicon-llm-speed-lab`. The seed Apple
benchmark is an example of the method, not a validated Windows/Linux patch.
For an unlisted OS/runtime, investigate and port the generic workflow where
feasible; its presence here is not a claim of prevalidated driver/kernel support.

## Establish the contract

Run the read-only `scripts/inventory.py` with an available Python 3.10+ interpreter.
Read [hardware-and-research.md](references/hardware-and-research.md), then inspect
the user's installed runtime and local operating instructions. Identify
the real serving model/revision, tokenizer/template, quantization, architecture,
accelerator, available memory, inference admission, context and cache formats.
Distinguish a model alias from the actual weights. Inspect configuration without
printing credentials. Prefer installed source over assumptions about versions.

Record what must not change: answer/reasoning quality, model provenance (including
an abliterated checkpoint when the user requires it), thinking budget, sampling,
tools, vision, context, approvals and cloud policy. Do not generalize one owner's
preferences to all users. Local-only inference means no cloud delegation, fallback
or auth probes; ordinary authorized internet tools are a separate capability.

Keep a known-good deployment intact. Develop new code and its unit tests separately.
Do not restart, clear caches, replace weights, alter a working model's settings or
run a load test merely to install this skill. For implementation, use the runtime's
supported configuration mechanism, preserve unrelated edits and prepare rollback.
An additional model process is not safe if its weights/cache do not fit alongside
the serving process. Stop before a destructive, externally publishing, or
out-of-scope step that needs new approval.

## Measure before choosing a change

Read [measurement.md](references/measurement.md). Distinguish prompt processing,
first reasoning activity, first visible text, full response, actual tool execution,
queue wait and generation-only tokens/second. The user's status-bar rate may include
more than decode; inspect its calculation instead of comparing unrelated numbers.

Use representative short answers, longer reasoning, unseen questions, growing
conversations, tool selection/result handling and relevant media/context cases.
Keep full real schemas and prompts privately when they matter. Separate cold,
warm identical-prefix, and novel-prefix workloads. Do not repeatedly benchmark
only "Hi" and claim all conversations became faster.

`scripts/bench.py` previews a user-supplied OpenAI-compatible fixture by default.
It sends requests only with `--run --confirm-idle`, only to numeric loopback (or
localhost mapped to loopback), never follows redirects/proxies, never executes
tools, and never edits or restarts services. Use a supported Python 3.10+ binary;
do not assume a command named `python3` exists. See the fixture example in
[measurement.md](references/measurement.md). Other transports need a small
runtime-specific adapter; this script does not pretend they are compatible.

## Choose the bottleneck-specific experiment

Research current upstream documentation, release notes, source and existing
solutions for the detected hardware/model/runtime; record primary-source links
and applicable versions. Do not stop at searching for a setting: where evidence
shows an unaddressed bottleneck, design and implement a targeted custom patch.
Read [custom-patch-workflow.md](references/custom-patch-workflow.md) for source
isolation, compatibility manifests, correctness tests, deployment and rollback.
Apply accepted patches within the user's authorization, not just recommend them.
Keep the known-good production model intact while experiments are unproven.
An unlisted model/backend calls for source inspection and an appropriate adapter
or new implementation—not blind reuse of the reference's constants. Use
`scripts/patch.py check` before its explicit `apply` operation for suitable
agent-authored source files; it preserves private rollback state. The helper
does not design kernels, certify quality, compile code or activate a service.

Read only the relevant parts of [optimization-patterns.md](references/optimization-patterns.md):

- Repeated prompt-tail work: exact prefill endpoint reuse and paired draft state.
- Slow cold start/prefill: lifecycle, native architecture and memory pressure.
- Slow decode: verified drafting, memory bandwidth and compatible kernels.
- Tool gaps: bounded read-ahead and overlapping independent tool work.
- Multi-agent work: shared model versus actual inference concurrency.

For hybrid recurrent models or native MTP, also read
[exact-prefix-contract.md](references/exact-prefix-contract.md) before touching
cache code. Eligibility must reflect actual state/layout, not just a model name.
Do not remove a compatibility gate because another checkpoint looks similar.
Treat custom ANE/GPU partitioning and changed reduction orders as numerical
experiments, not inherently lossless or faster operations.

## Accept or reject with evidence

Change one attributable feature at a time. Test correctness/fallback/resource
behavior first, then repeat matched off/on measurements. Prefer at least two
paired comparisons with three or more measured repetitions per case per state.
Report every failed or truncated trial, warm-up policy, uncertainty and output
lengths. Preserve runtime counters where available to detect overlapping work.
`scripts/compare.py --pair off.json on.json --pair off2.json on2.json` refuses
mismatched fixtures/settings and invalid warm trials; it reports all cases,
including regressions. Its narrow screens are not a proof of unchanged quality.

Verify actual tools and returned child results through the intended agent harness;
synthetic tool JSON is not an executed tool. Keep a session alive when background
children need a later-result consumer. Check memory under realistic load without
weakening its guards. Retain a candidate only when its representative latency
and quality results justify it; otherwise roll back just that candidate.

Hand off: what is enabled, exact before/after metrics and their scope, unchanged
capabilities, tests actually run, limits, normal launch behavior and rollback.
Never promise the same percentage on another model or present an isolated kernel
gain as a complete-response gain. The measured seed example is in
[qwen-case-study.md](references/qwen-case-study.md), not a performance guarantee.

## Sharing

This folder is a self-contained skill for compatible SKILL.md-based agents. Read
[sharing.md](references/sharing.md) when preparing a release. Export only an explicit
allowlist: instructions, original helpers/tests and sanitized measurements. Never
include private fixtures, prompts, thinking, cache tensors, auth, configuration,
session databases or a copied home directory. Preparing a release is not permission
to publish to a public account; confirm the destination and visibility first.
