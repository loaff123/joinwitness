# Measured benchmarks — 0.1.0

Measured on 2026-09-30, using this repository's `benchmark.py`.

Environment: CPython 3.12.14, Linux 6.18.44 x86_64, glibc 2.41, 9 logical CPUs visible to the shared cloud container. CPU model could not be obtained from this restricted container (lscpu cannot read the system CPU inventory). Other jobs were active; scheduling contention and warm filesystem cache can affect timing. This is a small reproducible engineering check, not a comparative performance study.

## Results

Both scenarios use 100,000 rows in each input, totaling 3,200,020 CSV bytes. Data is synthetic. Timings include CSV parsing, validation, aggregation, prediction and rule evaluation; exclude fixture generation, interpreter/import startup, and HTML/JSON rendering.

| Scenario | Distinct keys per input | Predicted rows, checked analytically | Audit seconds across 3 fresh processes | Peak whole-process RSS MiB |
| --- | ---: | ---: | --- | --- |
| Duplicate-heavy, amount analysis off | 1 | 10,000,000,000 | 1.203 / 3.168 / 0.939 | 12.750 / 12.750 / 12.750 |
| Distinct-heavy, amount analysis on | 100,000 | 100,000 | 1.891 / 3.560 / 1.855 | 70.168 / 69.832 / 70.355 |

The duplicate-heavy run demonstrates counting a 10-billion-row result without constructing it. The distinct-heavy run illustrates the memory cost of retaining unique keys. The scenarios have different amount settings and are not a controlled comparison of key cardinality alone.

RSS is `resource.getrusage(RUSAGE_SELF).ru_maxrss`, a process high-water mark including Python and imports, not an incremental engine allocation. Fresh worker processes avoid carry-over peaks, but OS cache is not cleared. No full join was attempted at scale. No pandas/qsv comparison or speed advantage is claimed. Results depend on input width, length, key cardinality, quoting, amounts, filesystem, machine and load; do not extrapolate linear timings or guaranteed capacity.

## Reproduce

From an installed development environment in the repository root:

```sh
python benchmarks/benchmark.py --rows 100000 --keys 1 --repeats 3
python benchmarks/benchmark.py --rows 100000 --keys 100000 --money --repeats 3
```

Raw output: [duplicate-heavy.json](duplicate-heavy.json), [distinct-heavy.json](distinct-heavy.json).

The generator repeats key `index % keys`. If `q, r = divmod(rows, keys)`, expected output is `r*(q+1)^2 + (keys-r)*q^2`. The script asserts that prediction on every run. Small randomized tests independently compare against materialized joins, including SQL NULL semantics and signed amounts.

## Practical limit

JoinWitness stores per-key aggregates in memory. It is designed for bounded local CSV checks, not arbitrarily large distinct-key workloads. Memory also includes CSV parsing buffers and one current record. There is no external-memory spill engine or enforced total memory budget. See [semantics](../docs/SEMANTICS.md) and [security](../SECURITY.md).
