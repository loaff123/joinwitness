# Architecture

JoinWitness preflights an equality join between two local CSV files. It computes cardinality and repeated left-side amounts without constructing the joined rows.

## Modules

- `models.py`: typed immutable configuration, statistics, rules and report contracts
- `csvio.py`: strict UTF-8 CSV validation, exact tuple keys and per-key aggregates; monetary cells become arbitrary-precision integer units of 10^-18
- `engine.py`: match counts, SQL NULL behavior, global relationship validation, bounded expansion explanations and exact monetary contribution accounting
- `config.py`: versioned, strictly validated private JSON configurations with relocatable input paths
- `output.py`: input-alias protection, preflight output validation and per-file staged writes
- `report.py` and `templates/report.html`: autoescaped, script-free, self-contained Jinja2 report
- `cli.py`: audit/run/demo commands, human summary and machine-readable exit status
- `demo.py`: synthetic input files passed through the same audit engine

## Data flow

1. Validate configuration and output destinations
2. Read each input completely, validate syntax/column selection, and aggregate exact non-NULL key tuples
3. Compare per-key counts; compute `left_count * right_count` using Python integers
4. Evaluate explicit quality rules and retain only aggregate diagnostics plus opted-in bounded key samples
5. Serialize deterministic JSON and autoescaped HTML; stage each complete file before publishing it

Memory scales with distinct input keys plus parsing buffers, not predicted output size. No external-memory spill is implemented. No SQL is assembled or executed, so source column names are dictionary lookups rather than SQL identifiers. There is no runtime network operation.

See [semantics](SEMANTICS.md) for formulas and [privacy](PRIVACY.md) for exported-data boundaries. Multiple output files are not an atomic transaction as a set; individual complete files are staged, while unexpected filesystem failures can leave a partial set of completed outputs.
