# Implement for the machine in front of you

When the user asks to optimize, the deliverable is implemented and measured
improvement where feasible, not a list of suggestions. Use engine-porting-guide.md
as a reference for mechanisms that worked and experiments that did not. Do not
confuse its original backend or constants with the general problem being solved.

1. Inspect the actual hardware and loaded runtime, then measure the critical path.
   Map user requirements and the editable integration points before choosing code.
2. Research the installed version and applicable current upstream options. Apply
   a supported option if it solves the measured problem without weakening the
   contract; do not write a redundant patch merely to produce a diff.
3. If an uncovered bottleneck remains, inspect its owning module and implement a
   targeted candidate in an isolated copy of the real, possibly dirty baseline.
   An unfamiliar model/backend is a reason to investigate and adapt—not to stop
   automatically with generic advice or recommend changing the user's model.
4. Create missing adapters when feasible: request/stream and tool dialect, runtime
   status/admission, cache identity/state/codec, memory telemetry, compiler/device
   ownership, and activation. Test the adapter before trusting its measurements.
   Do not interpret an unknown measurement as zero or unsupported hardware as absent.
5. Test invariants, quality, memory, ordinary fallback and matched workload latency.
   Refine or reject a failed candidate. Keep changes attributable; after a new
   bottleneck is measured, another candidate may be justified. Do not iterate
   indefinitely without evidence or beyond the user's time/resource authority.
6. Apply a validated winner through the runtime's supported configuration/build
   mechanism or reviewed source changes. Verify the running code actually adopted
   it, then verify tools/children where relevant. Preserve rollback and report
   measured scope. If activation is blocked, say staged, not active.

Missing source, a closed accelerator interface, unavailable build tools, unproven
memory headroom, required permission or a lack of measurable benefit can be real
limits. Check relevant in-scope alternatives, name the specific limit and preserve
the working deployment. Do not bypass licensing/security, invent an API, blindly
patch a binary, or force a speed claim to satisfy "any machine".

## Guarded file application helper

`scripts/patch.py` provides real source-file check/apply/rollback operations for
agent-authored candidates. It is language-neutral for UTF-8 source text, not a
patch generator or universal optimizer. It does not execute payloads, install
dependencies, edit server configuration via an API, rebuild code or restart a
process. The agent still performs the engineering and authorized build/tests.

Keep candidates, manifests, identity contracts and backup state PRIVATE. A
manifest contains `version: 1`, `identity_sha256`, and a `files` array. Each entry:

- `path`: portable relative path beneath the explicitly selected source root;
- `before_sha256`: SHA-256 of exact existing bytes, or null for an added file;
- `after_sha256`: SHA-256 of the candidate bytes;
- `candidate`: relative path to a UTF-8 payload beside/below the manifest.

Hash the identity JSON with `patch.identity_digest`: sorted compact JSON encoded
as UTF-8 with non-ASCII characters preserved. The identity must describe fixed
hardware/model/runtime/precision/capability conditions, not changing free-memory
counters. The helper checks that declared hash; the agent must independently
verify it against the actual serving environment. Do not include the feature's
off/on state in the identity that is required to stay fixed during comparison.

Using the host's available Python 3.10+ launcher, run:

```sh
python3.11 scripts/patch.py check --root SOURCE --manifest PRIVATE/patch.json --identity PRIVATE/identity.json
python3.11 scripts/patch.py apply --root SOURCE --manifest PRIVATE/patch.json --identity PRIVATE/identity.json --state-dir PRIVATE/new-backup --confirm-idle
python3.11 scripts/patch.py rollback --root SOURCE --state-dir PRIVATE/new-backup --confirm-idle
```

`check` makes no writes. `apply` checks all source/candidate hashes and the declared
identity before backing up original bytes/modes outside the source root. It
rejects traversal, Git internals, case-aliased targets, linked/reparse paths and
binary payloads. Parent directories must already exist; at most 64 files, 8 MiB
per file and 32 MiB combined source/candidate bytes are admitted. Normal runtime
tooling must handle binaries, system packages and larger changes.

Every file replacement is atomic, but the whole multi-file batch is NOT atomic.
Use a trusted, exclusively owned source tree and stop its reload/watch/edit jobs
for the change. `--confirm-idle` is a user assertion, not a detected service lock
or protection against hostile concurrent filesystem changes. Prefer an isolated
build tree and the runtime's deployment switch for multi-file activation.

Backups and the prepared journal exist before the first source write. On a
partial failure/interruption, retain state and run rollback in the same exclusive
window. Rollback prechecks all backups/current hashes; it refuses to overwrite
later edits, restores exact original bytes/modes, and removes only still-matching
files that this patch added. Backups remain for inspection; there is no recursive
cleanup. On Windows, verify the private directory's ACLs: POSIX mode bits alone
do not guarantee privacy there. Nothing in the helper certifies a speedup.
