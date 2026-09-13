# Release and installation

The release is an implementation-oriented optimization skill with hardware,
benchmark/comparison and guarded source-patching helpers. It is not a model,
inference engine, universal automatic optimizer or guarantee of a particular speed.
Its engine-derived recipes guide the agent to author and test new host-specific
patches; patch.py applies reviewed payloads, not prepackaged universal engine fixes.
Instructions and original helper code in this
package are MIT-licensed; upstream models/runtimes keep their own licenses. No
third-party runtime source or weights are bundled.

For Hermes, copy this edition's named skill folder to the selected profile's
`skills/` directory (a category subdirectory such as `skills/mlops/` is also
supported by the tested setup). For Codex, copy it to the selected Codex home's
`skills/` directory. Restart/reopen the AGENT session if its discovery cache
requires it; do not restart the model server. Other SKILL.md-based agents can read
the instructions and use the Python helpers. Confirm their own discovery rules.

The included `agents/openai.yaml` is optional Codex UI metadata; it is not a
cloud inference requirement. The scripts run locally without an OpenAI SDK or API
account. Requests use the user's existing local server, only with explicit run
flags. The benchmark executes no tools. The patch helper writes only explicitly
manifested source files and private backup state after a check/apply request;
rollback removes only its own unchanged additions or restores its originals.
No dependency installation, model loading, service restart, config API mutation
or benchmark upload is performed automatically by these helpers.

Run the bundled standard-library tests, inspect archive contents, and validate
the SKILL.md frontmatter before release. Exclude `__pycache__`, private fixtures,
credentials, raw outputs/reasoning, model tensors and runtime/session state.
Performance claims must identify workload, non-identifying hardware class, cache
state and sample counts. If hardware/revision details are withheld for privacy,
say so; do not present the release as independently reproducible evidence.
Generated inventories and identity documents can fingerprint a host even without
names or addresses: keep them private. Use synthetic test data, strip original
file timestamps/owner attributes from archives, and inspect all archive members.
Before publishing, review the public account and Git author/email metadata too;
sanitized files do not anonymize the publisher.
Preparing a ZIP does not publish a GitHub repository or submit to a skill hub.
Choose the user's destination, owner, license approval if needed, and visibility
before any public upload. A private download link is not a public release.
