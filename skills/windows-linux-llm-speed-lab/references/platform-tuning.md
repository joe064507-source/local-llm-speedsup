# Windows/Linux specialization

## Establish topology and actual execution environment

Use inventory.py, then inspect the serving runtime's environment. Identify
Windows native versus WSL/Linux/container, x86-64 versus ARM64, CPU ISA/affinity,
host RAM and cgroup/container limits, visible GPUs, driver/runtime versions,
dedicated versus shared GPU memory, SSD placement and any interconnects.
An inventory collected outside WSL/container may not describe what the model
process can access. Never sum host RAM and VRAM as interchangeable fast capacity.
Windows display-adapter memory may be incomplete; verify with the runtime.

On Linux, check process affinity and cgroup limits before choosing thread counts
or memory ceilings. A multi-socket system needs NUMA locality checks. On Windows,
use read-only device/driver queries first; do not alter security, driver watchdogs,
pagefile settings or power/thermal protections to improve benchmark numbers.
On ARM PCs verify architecture-native binaries rather than assuming AVX support.

## Research by compatible backend

- NVIDIA/CUDA: inspect compute capability, installed driver/toolkit/runtime,
  supported attention/GEMM kernels and exact quantized model format. Test graph
  replay, fused kernels, allocation reuse and cache/batching changes only when
  shape/lifetime/RNG and runtime support are established. Driver-reported CUDA
  support is not the same as the model environment's toolkit or compiled kernels.
- AMD/ROCm/HIP: match the actual GPU architecture, OS and driver combination to
  upstream support. Do not fake hardware architecture identifiers or bypass
  unsupported-device checks. Consider the user's working Vulkan path when the
  supported ROCm combination is unavailable, not a forced driver migration.
- Intel/integrated GPU/APU: inspect supported SYCL/Vulkan/OpenVINO paths and
  shared-memory accounting. Presence of an NPU does not establish an executable
  graph for the user's model; test conversion, state, copies and numerical effects.
- CPU-only: measure memory bandwidth, native ISA, thread oversubscription,
  affinity/NUMA, batch shape and quantized kernels. More threads can be slower;
  do not advertise a prompt-processing BLAS gain as decode acceleration.
- Multiple GPUs: inspect tensor/pipeline parallel support, device placement,
  peer access and actual interconnect costs. Sharding can solve capacity while
  increasing latency. Compare aggregate throughput AND individual request wait.
  Multiple processes or model replicas require separate memory/admission budgets.

Research entrypoints, checked at skill creation; recheck installed-version support:

- [llama.cpp build/backend options](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
- [llama.cpp serving options](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
- [vLLM GPU installation and compatibility](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/)
- [NVIDIA-SMI documentation](https://docs.nvidia.com/deploy/nvidia-smi/index.html)

Use exact model/vendor/runtime primary sources for additional options. Do not
assume Linux backend support also means native Windows support. No package,
driver or system change is implied by discovering an option.

## Custom patch candidates and deployment

Choose from measured costs: wasted prefix work, duplicate host/device transfers,
allocation/synchronization, unsupported efficient kernel shapes, cache layout,
speculation overhead, scheduler admission or overlappable tool/disk I/O.
Adapt the mechanism, not the Apple Metal/ANE implementation. Recurrent models
still require exact state boundary/draft pairing; dense attention-only models
have a different state contract. Keep target sampling and user features intact.

Build in an isolated source/output environment, preserve the working runtime and
untracked custom changes, and verify ABI/driver compatibility. Do not replace
loaded DLLs/extensions, kill a service, or open a public model endpoint to test.
See custom-patch-workflow.md for acceptance and rollback. The bundled parser and
transport tests do not certify real CUDA/ROCm/NPU kernels on an untested machine.

For examples, use the available Python 3.10+ launcher (`py -3`, `python`,
`python3` or an explicit environment path) and the host shell's path syntax.
The measurement reference's python3.11 command is an example, not a Windows
requirement. Keep each release's patch and benchmark evidence hardware-specific.
