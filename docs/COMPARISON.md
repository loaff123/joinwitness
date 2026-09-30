# Choosing a join-checking workflow

Join validation is an established capability. JoinWitness's contribution is a focused, local CSV preflight packaged with an offline review report, repeatable configuration, and explicit policy outcomes. It does not claim a new join algorithm or a feature category that other projects lack.

The primary-source descriptions below were reviewed on 2026-09-30. They are documentation comparisons, not a head-to-head benchmark. Upstream projects may change.

## pandas

`pandas.merge` supports relationship checks through `validate`. Its merge indicator records whether an output row originated on the left, right, or both sides. If your workflow already lives in pandas, these are strong built-in controls and may be all you need. [pandas merging guide](https://pandas.pydata.org/docs/user_guide/merging.html#merge-key-uniqueness)

A meaningful semantic difference is NULL handling: pandas documents that NULL keys match each other. JoinWitness uses unmatchable NULL-key rows. Align both parsing and NULL behavior before expecting identical predictions. [pandas.merge reference](https://pandas.pydata.org/docs/reference/api/pandas.merge.html)

JoinWitness is useful when the desired deliverable is a standalone preflight report for someone outside the notebook. It predicts matched products from key aggregates and exposes amount repetition without writing the joined data. That workflow can also be implemented in pandas; this package supplies the reporting and policy conventions.

## qsv joinp

qsv's `joinp` is a general CSV join command using Polars. It documents validation before execution, a broad set of join types, filtering, key transformations, and options for memory-intensive jobs. It also documents support for files larger than RAM. Choose it when you need the joined output or those richer operations. [qsv joinp documentation](https://github.com/dathere/qsv/blob/master/docs/help/joinp.md)

JoinWitness is intentionally smaller: inner/left equality preflight, exact text keys, aggregate memory proportional to distinct keys, and human-readable impact reporting. It is not a replacement for qsv's execution engine and makes no general speed or capacity advantage claim. If you audit with JoinWitness and execute with qsv, align schema inference, NULL settings, and any key transformations first.

## getchatdata join audit

getchatdata's SQL-review workflow already includes a local CSV join-audit helper. Its documentation covers duplicate and NULL key counts, unmatched rows, exact inner/left output counts, composite exact-text keys, and decimal measure effects. This is substantial overlap and a useful alternative for a SQL-review workflow. [getchatdata SQL-review skill](https://github.com/parasdoshicom/getchatdata/blob/main/plugins/chatdata/skills/sql-review/SKILL.md)

Its documented failure policy blocks observed many-to-many matches or repeated supplied measures, even if a permissive relationship is declared. Its additional NULL tokens extend the blank default. JoinWitness exposes its own explicit quality flags, and supplied `--null-value` flags replace its default list. Check each tool's policy rather than treating successful exit codes or similarly named flags as equivalent.

JoinWitness's product emphasis is a self-contained HTML review artifact, configurable CI checks, reusable run configuration, and privacy-default exports with opt-in diagnostic samples. The underlying audit ideas are shared, not exclusive.

## Practical choice

- Stay with pandas when the data and review already live in Python and its built-in validation meets the need
- Use qsv when you want a broad CSV transformation and join execution toolkit
- Consider getchatdata's helper when the audit belongs inside that SQL-review workflow
- Use JoinWitness when you want a narrowly scoped CSV preflight with a report someone can open offline and a policy you can run again

For any choice, first state the intended row grain, verify key and NULL semantics, and distinguish lost rows from repeated measures. Passing a cardinality check alone does not make every metric additive after a join.
