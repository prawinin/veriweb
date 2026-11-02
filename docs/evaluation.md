# Evaluation

The evaluation harness runs actual model planning, extraction, synthesis, citation resolution, and numeric comparison over controlled source documents. Only search and page collection are replaced by fixture inputs. Answer keys remain outside model prompts and production logic.

Two sets are included:

- `controlled-fixtures.json`: 20 cases covering numeric retrieval, comparisons, conflicts, scope/date differences, partial answers, and abstention.
- `frozen-probes.json`: 20 additional synthetic probes. These were authored during development; they are not an independently sealed external benchmark.

## Run both sets

Start the configured model with `scripts/dev.py --with-model`. The `.env` model URL must point to that server. In a second terminal:

```sh
run_dir="evals/runs/$(date +%Y%m%d-%H%M%S)"

.venv/bin/python scripts/evaluate.py   --mode fixture --fixtures evals/controlled-fixtures.json   --deadline 120 --output "$run_dir/controlled"

.venv/bin/python scripts/evaluate.py   --mode fixture --fixtures evals/frozen-probes.json   --deadline 120 --output "$run_dir/frozen"
```

Cases run sequentially. Avoid simultaneous dashboard investigations on the same model while measuring performance. No weights are downloaded by the evaluation runner. Fixture retrieval uses BM25; optional embedding loading is deliberately excluded from this small regression harness.

Each run writes `summary.json`, `report.md`, and the actual `artifacts/CASE_ID.json`. Exit status 0 means every selected case passed. Status 1 means an execution or rubric failure; status 2 indicates invalid configuration or selection.

Run a subset with `--cases scope-population,scope-cost` or a category with `--category conflict`. To rescore saved outputs without model calls:

```sh
.venv/bin/python scripts/evaluate.py --mode score   --results "$run_dir/controlled/artifacts"   --output "$run_dir/rescored"
```

## Recorded results

The complete local run on 1 November 2026 passed both sets:

| Set | Strict case passes | Mean wall time per case |
| --- | --- | --- |
| [Controlled](../evals/results/controlled.json) | 20/20 | 11.66s |
| [Additional probes](../evals/results/frozen.json) | 20/20 | 8.64s |

These are recorded model runs, not deterministic guarantees. Earlier development runs had scope and conflict failures; the retained regression tests cover those corrections. The latest automated code checks passed 102 backend and 15 frontend tests.

## What a pass means

The scorer checks exact expected coverage values, requested subjects and dimensions, required abstention, source-pair/conflict kinds, and quote provenance. A strict case pass requires all applicable checks. Timing includes model calls and evaluation orchestration.

It does not automatically verify semantic entailment of arbitrary prose, publisher reliability, or general live-web accuracy. An exact quote can be authentic while a claim misinterprets it. These are visible development fixtures, so passing them is regression evidence rather than an unseen benchmark result.

Live web testing needs real questions and independently reviewed sources. The optional `--mode live --base-url` runner saves service results unscored; invented fixture entities have no valid real-web answer key. Check years, currencies, units, geographic scope, negative claims, blocked-source handling, and whether missing evidence remains explicit.

The recorded AMD hardware measurements are in [hardware.json](../evals/results/hardware.json). Vulkan LLM throughput, ROCm kernel execution, CPU extraction, and full-report wall time are separate measurements.
