# Choose work that actually lies on the critical path

## Cache and prompt processing

Stable system/tool prefixes often dominate short agent turns. Keep prompt bytes,
template, tool ordering and version identifiers stable for the conversation's
lifetime. Do not drop schemas, memory or thinking to manufacture a better score.
Idle prewarming can move startup work earlier, but is not faster cold computation;
it must yield to real requests and never replay actual user actions.

Full-block caching can leave a repeated partial tail. A bounded exact N−1
checkpoint can avoid that work, including on later tool continuations, when the
backbone and drafting state can be restored together. Read exact-prefix-contract.md.
This is not a response cache. An unrelated first question may still miss, and a
small endpoint index can churn across many agents. Unsupported state must fall
back to the normal runtime rather than truncate context or guess recurrent state.

## Memory, CPU, GPU and SSD

Verify the serving binary is native to the host before kernel work. Measure
page faults, swap, live tensor footprint, allocation peaks, cache reconstruction
and prefill separately. Free disk capacity helps available storage; it does not
turn SSD into bandwidth-equivalent GPU RAM. Do not indiscriminately delete models
or user files. Select exact authorized targets and protect the serving model.

Read-ahead can overlap known SSD cache reads with tool I/O. Bound total optional
memory, pending/in-flight copies, individual reads and lifetimes; cancel/pause for
real inference and pressure. Match cache identities and verify exact bytes.
Avoid loading the same chain twice during preload plus reconstruction. A faster
read that was not on the critical path may produce zero response-time gain.

## Decode and speculative generation

Profile per-token/verification time before changing kernels. Shared memory
bandwidth, cache layout, batching and drafting acceptance matter more than a
marketing TOPS number. Speculative decoding is appropriate only when target
verification preserves the target sampling distribution and drafting plus
verification cost is lower than the saved target work. Keep correct RNG/state
handling, rejection rollback and stop-token semantics. A fast drafter that is
rarely accepted can make the model slower. Native MTP requires its own exact
priming history; an external drafter may consume unacceptable extra RAM.

Fusion or paired attention needs shape/device/dtype gates and error checks.
Changing floating-point reduction order can change outputs even at the same
precision; measure numerical error and quality instead of calling it bit-exact.
Keep a generic path for unsupported shapes and package/driver versions.

## Apple Neural Engine

ANE is not a universal accelerator for every transformer operation. Probe
supported operations, compilation cost, tensor layouts, working sets and actual
end-to-end overlap in a separate experiment. GPU↔ANE transfers and retained
buffers can erase faster isolated MLP operations. Preserve memory-shedding guards.
Do not copy another machine's memory limits. Do not
assume unified address space means zero synchronization or zero-copy execution.

In the seed case study, tested ANE partitioning was essentially tied end to end;
an overlapped prototype was not deployed. Negative results are useful evidence,
not a reason to force every device to show activity.

## Agents versus model instances

Several agent conversations can share one loaded model. Their file/network tools
may overlap while GPU requests queue. More agents are not more GPUs: distinguish
single-stream response speed, aggregate useful-task throughput and worst-case
queue latency. Continuous batching may conflict with a singleton native-MTP path
and can require extra KV memory. Test, do not guess.

Start with the smallest useful fan-out; test larger counts only when permitted.
Keep a bounded batch and explicit wave/depth policy, isolated write ownership,
normal tool approvals and a budget for Python/tool processes. Do not start a
second model replica just to fill child slots. Flatten recursion when it creates
duplicate work. An agent-count ceiling is a local admission policy, not
an optimum or a benchmark result for other hosts. Local-only users must not be
silently escalated to cloud for a hard task or timeout.
