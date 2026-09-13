# Seed case study: measured warm-prefix gains, not a universal promise

An anonymized Apple Silicon example used oMLX and a 27B Qwen-family abliterated
MLX checkpoint with native MTP. Exact host specifications, deployment revision
fingerprints and collection dates are withheld to protect the source environment.
The aggregate measurements illustrate the method; they are not a fully
reproducible benchmark release or a hardware recommendation. This skill does not
download or distribute a checkpoint or claim support based on its name alone.

An exact N−1 partial-prefill checkpoint paired backbone/recurrent and native-MTP
state. Previously unretained partial tails caused repeated computation beyond
full 2,048-token cache blocks. Warm hits reused roughly 479–550 extra tokens in
the first-request workload. Representative restore overhead was about 11–19 ms.

Two matched off/on comparisons, each with 25 Hermes tool schemas, three warm-ups
and three measured repetitions per case per state, produced these pooled medians:

| Complete model-request workload | Off | On | Time reduction |
|---|---:|---:|---:|
| Greeting | 6.03 s | 2.87 s | 52.4% |
| Arithmetic check | 5.64 s | 2.07 s | 63.3% |
| Short explanation | 12.79 s | 7.99 s | 37.5% |
| Tool selection + simulated result processing | 12.24 s | 5.73 s | 53.2% |

First pair medians, off→on: 5.84→3.25, 5.65→2.04, 12.79→7.45,
12.33→5.58 seconds. Second pair: 6.22→2.50, 5.46→2.10, 12.78→8.54,
12.14→5.87 seconds, in the same case order. Each pair used matching prompt/tool
and initial-request hashes; the two pairs had different saved prefix snapshots.

All 96 case trials, including warm-ups (120 model requests because tools used
two), passed narrow correctness screens and a request-counter overlap audit.
No response was truncated. Thinking, medium effort, preserved reasoning,
temperature 1/top-p .95/top-k 20, 8-bit TurboQuant KV, final dense attention cache,
vision, tools and configured 262,144 context were retained. This does NOT prove
equal quality on every task. A cache-on explanation warm-up generated 939 tokens
and took 40.14 s: longer thinking still takes time.

341 selected tests passed (328 cache/MTP/scheduler tests and 13 harness checks).
Separately, two real Hermes children each executed a terminal check and returned
their results to the parent. That cold/shared-queue integration session took
8m 36s including waiting and shutdown; it was not counted as a speed result.

Limits: exact repeated prefixes, eligible text state, bounded optional checkpoint
capture, RAM-index/head-array caps, RAM TTL and private SSD eviction budgets.
Optimization coverage was narrower than the configured conversation context;
full native-context memory fit remains untested.
These results do not promise faster novel questions, cold starts or raw decode.

Other experiments were not relabeled as this gain: ANE partitioning measured
34.04 versus 34.08 seconds (essentially tied); speculative-sampling reuse and a
new overlapped ANE pipeline were not retained as deployed speed improvements.
Keep those negative findings when describing the work publicly.
