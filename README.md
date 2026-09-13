# Local LLM Speed Labs

Experimental, implementation-oriented skills for improving local LLM performance
with measured results and checks for answer, reasoning and tool-use regressions.

The working reference engine is the engineering guide—not a fixed patch to force
onto every machine. These skills direct an agent to inspect the recipient's
hardware and runtime, research compatible options, develop appropriate custom
patches, test them, and deploy successful changes with rollback.

## Choose an edition

- [Apple Silicon](skills/apple-silicon-llm-speed-lab/SKILL.md): Metal/MLX, Neural
  Engine tradeoffs, unified memory and SSD caching.
- [Windows/Linux](skills/windows-linux-llm-speed-lab/SKILL.md): CPU, discrete or
  integrated GPUs, CUDA/ROCm/Vulkan, WSL/containers and multi-GPU considerations.

Install one named skill folder in your agent's skill directory. Hermes supports
the selected profile's `skills/` directory; compatible SKILL.md-based agents can
use their own discovery mechanism. Reopen the agent session if necessary;
installing a skill does not require restarting the model server.

Ready-to-install ZIPs are in [releases](releases/). They contain only public
skill files, with normalized archive metadata. No model weights are included.

Example request:

> Use this skill to optimize my local model. Use the reference engine lessons as
> a guide, inspect my actual bottlenecks, and implement and test appropriate
> machine-specific changes. Preserve my model, thinking, tools and context.

## What the agent learns from the reference engine

The [engine porting guide](skills/apple-silicon-llm-speed-lab/references/engine-porting-guide.md)
captures source-checked mechanisms and their adaptation requirements:

- Exact partial-prefix computation reuse with paired recurrent/native-drafter state.
- Shape-specific attention work reduction with numerical and dispatch checks.
- Known-continuation SSD read-ahead with consume-once ownership and cancellation.
- Shared optional-memory admission that respects existing memory guards.
- GPU/Neural Engine partitioning, compilation lifetimes and hand-off costs.
- Sampling, cold-start and shared-model agent scheduling lessons.

An unfamiliar backend is a reason to investigate and build an adapter where
feasible, not automatically stop at advice. The agent should also address newly
measured bottlenecks that are not in this list. Unsupported interfaces, lack of
permissions or lack of a measurable benefit remain legitimate limits.

## Included executable helpers

Python 3.10+, standard library only; use your platform's available interpreter.

- `inventory.py`: read-only hardware inventory; missing measurements remain unknown.
- `bench.py`: preview-first, loopback-only streaming benchmark; never executes tools.
- `compare.py`: matched latency comparisons that reject failed, missing or reused trials.
- `patch.py`: check/apply/rollback for reviewed, agent-authored UTF-8 source files,
  with hash checks, private backups and protection against overwriting later edits.

The patch helper is not a patch generator, a service manager or a substitute for
an agent that can inspect and edit code. It cannot establish quality or speed by
itself. Multi-file changes require an exclusive workspace and are not batch-atomic.
Read the [implementation contract](skills/apple-silicon-llm-speed-lab/references/adaptive-implementation.md)
before applying changes. Configuration and compiled binaries use the runtime's
supported mechanisms, not blind file replacement.

## Evidence and limitations

Version 1.1.0: 54 helper tests per edition passed on an Apple Silicon host,
including a temporary fake HTTP server and real isolated source apply/rollback.
Windows/Linux adapters have parser tests; physical Windows/Linux accelerator
and kernel validation remains pending. These checks do not certify every device,
model, driver, runtime or generated patch.

The [anonymized Qwen case study](skills/apple-silicon-llm-speed-lab/references/qwen-case-study.md)
records 37–63% lower warm complete-response medians in four tested workloads.
That is not a universal decode-speed improvement or a promise for novel prompts.
The ANE and read-ahead experiments did not establish meaningful end-to-end gains;
those negative findings are retained. Quality screens are not proof of unchanged
reasoning on every task. Exact host/revision details and private raw inputs are
withheld, so this is not a fully reproducible benchmark release.

Run helper tests from the repository root, for each edition:

```sh
python3.11 -B -m unittest discover -s skills/apple-silicon-llm-speed-lab/scripts -p 'test_*.py'
python3.11 -B -m unittest discover -s skills/windows-linux-llm-speed-lab/scripts -p 'test_*.py'
```

Substitute your available Python 3.10+ launcher. Tests need permission to bind a
temporary loopback port, but never contact a live inference server or download a model.

## Privacy and license

Do not commit generated hardware reports, private identity/patch manifests,
backup state, prompts, model output, credentials or tensor caches. They can
identify a machine or contain private source even without a person's name.
Examples use synthetic data and generic loopback/rejection-test addresses.

Original skill instructions and helpers are [MIT licensed](LICENSE). Runtime
source and weights are not bundled; their original licenses still apply to any
implementation you adapt or distribute. No guarantees of universal compatibility,
speed gains or unchanged quality are made.
