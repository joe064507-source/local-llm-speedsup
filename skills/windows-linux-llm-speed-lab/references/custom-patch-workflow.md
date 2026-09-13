# Design, apply and validate custom inference patches

This skill is an implementation workflow, not just advice. When the user asks
for optimization and authorizes the scoped changes, create and test source
patches, then deploy a successful candidate. If they ask only for diagnosis or
expressly protect a running build, keep experiments separate and do not mutate
that deployment without new permission.

Use engine-porting-guide.md to derive candidate mechanisms from the actual
reference implementation. Use adaptive-implementation.md to create missing
runtime adapters and select the supported build/deployment path. For bounded
source changes, scripts/patch.py checks an authored manifest, applies exact
candidate bytes with private backups, and restores them without overwriting later
edits. This is application tooling, not a substitute for designing the right patch.

## 1. Capture the real baseline

Identify the runtime checkout/build, exact active entrypoints and source hashes.
Record dirty tracked files AND relevant untracked custom files. A worktree at
HEAD alone may omit the user's existing optimizations; do not mistake pristine
upstream for their real baseline. Snapshot only necessary source/build inputs to
a private scratch location, preserving ownership and licenses. Record the model,
tokenizer/template, adapters, precision, device and cache compatibility contract.
Do not clone private auth/config/cache state into a public project.

Keep the serving code, model alias, weights and settings untouched during design.
For a compile test use isolated output/cache directories and the right host
architecture. Do not overwrite a serving native extension with an experiment.
Only launch an additional model if independent memory headroom is proven and the
user authorized that workload; otherwise test small components and arrange an
idle, reversible trial. Never kill an active user session to obtain a benchmark.

## 2. Make an attributable patch

State the measured critical-path cost and the mechanism that should reduce it.
Examples: retain a missing exact endpoint, eliminate a duplicated reconstruction,
fuse compatible kernels, reuse immutable sampling preparation with RNG parity,
or overlap a known disk read with a tool wait. A speculative "use all processors"
goal is not yet a patch hypothesis.

Edit the narrow owning module, not a unrelated facade or an installed package
copy that the server never imports. Preserve user edits. Keep generic behavior
available for unsupported shapes/models/formats. Gate by architecture, runtime
revision/ABI, tensor/cache dtype/layout and state semantics; a reused alias alone
cannot certify a new checkpoint. Include exact temporary ownership and cleanup.
Do not catch errors by silently compressing context, skipping tools or disabling
thinking. Never weaken approvals or memory enforcement to make a patch pass.

Save a reviewable patch and a small manifest containing:

- hypothesis and intended workload;
- baseline runtime revision and required pre-existing local changes;
- changed file paths with baseline/candidate hashes;
- required hardware/model/cache/ABI conditions and ordinary fallback;
- numerical properties (bit-exact, tolerance-tested, or approximation);
- unit/integration/latency evidence and unsupported cases;
- deployment switch/reload needs and exact rollback targets.

Use safe relative paths in distributable patches. Avoid a generic auto-apply tool
that overwrites arbitrary checkouts. Check target hashes and patch applicability
before applying; stop on drift instead of force-applying. Upstream code retains
its license; do not relabel copied Apache/GPL/etc. code as this skill's MIT code.

## 3. Test before enabling

Exercise behavior, not source-text matches: state/tensor parity, offsets, RNG,
rejection and cancellation paths, races, corruption, pressure, unsupported inputs
and resource cleanup. Test both optimized and ordinary paths. For NPU/ANE splits,
measure boundary copies/synchronization and graph compilation/retained buffers.
Device activity is not the success criterion. Changed floating-point ordering
requires quantified error/quality checks, not a claim of exact equality.

Run the runtime's own targeted regression suite from the correct interpreter.
Use matched complete-response and relevant task benchmarks, with production
tools/thinking settings preserved, before describing an experiment as faster.
No speed claim from a truncated answer or disabled capability. Preserve all
trials, including regressions, cold starts and slow long-thinking outputs.

## 4. Deploy the winner and leave an escape route

Within the authorized scope, apply the validated patch to the intended source
only after baseline hashes still match. Activate it during an idle-safe window
if reloading is necessary; don't routinely restart an already-correct model.
Verify the newly running code/feature, exact model identity, one expected model
load, real tool execution, child result delivery and resource health. A disk file
or config toggle alone is not evidence that the running process adopted it.

If measured representative latency regresses, correctness fails or memory behavior
is unacceptable, restore only this candidate's backed-up changes/feature switch.
Never reset the repository, delete weights, remove aliases used by live clients,
or undo unrelated user work. Preserve unsuccessful results as negative evidence.
If no safe deployment window exists, deliver the tested patch and report it as
staged—not active. For protected known-good builds, that distinction is mandatory.
