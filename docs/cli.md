# CLI reference

Run `python3 /app/app.py` inside a package installed at `/app`, or `.venv/bin/python app.py` from a local checkout.

| Argument | Meaning |
| --- | --- |
| `--query`, `--question` | Research question; required |
| `--url` | Starting public page or domain |
| `--corpus` | Optional folder of saved HTML pages |
| `--query-id` | Identifier returned in the result |
| `--output` | Override the output JSON path |
| `--deadline` | Exact-answer budget in seconds; default and maximum 25 |
| `--report` | Generate the richer dashboard report instead of the bounded exact-answer result |

Without a URL or corpus, the exact-answer path attempts a bounded search. URL reads use public-address validation, redirect checks, robots rules, and size limits. Corpus reads reject symlinks and oversized files.

```sh
.venv/bin/python app.py   --query "What is Mercury orbital period in Earth days?"   --url https://science.nasa.gov/mercury/facts/   --query-id mercury

cat output/_output.json
```

Default output fields:

| Field | Meaning |
| --- | --- |
| `query_id` | Supplied query identifier |
| `answer` | Concise grounded answer, or an empty string |
| `citations` | Supporting public URLs or corpus file paths |
| `source_url` | Primary citation, or an empty string |
| `confidence` | Evidence heuristic between 0 and 1 |
| `conflict_detected` | Competing retained values were found |
| `telemetry.runtime` | Execution path actually used |
| `telemetry.latency_ms` | Worker duration in milliseconds |
| `telemetry.device` | Device information available to the worker |

The parent writes a current-query abstention before starting a supervised worker. The default output is atomically replaced at `output/_output.json`, or `/app/output/_output.json` in the AMD candidate image. A timed-out worker is stopped, leaving an abstention rather than a stale previous answer.

Numeric answers preserve the extracted units and requested years or qualifiers. Missing evidence or ambiguous values produce an empty answer. Equivalent day notation is handled conservatively; this is not a general unit-conversion engine. Confidence 0.75 is a fixed heuristic for validated evidence, not a calibrated probability.

CPU extraction is reported as CPU execution. A configured remote inference backend does not establish independently verified hardware. The conflict flag is an ambiguity signal, not a source-truth verdict.

The dashboard and `--report` perform a longer research workflow; their latency and output format differ from the 25-second exact-answer path. The CLI implements the project submission target; it is not a claim of acceptance by an organizer's external grader.
