# Join semantics and report fields

This document defines the 0.1 series' CSV equality-join model. A result applies to the two supplied files, the selected keys, and these rules. It does not validate a different database collation, cast, filter, predicate, or later version of the inputs.

## Inputs and parsing

Both files must be UTF-8 CSVs with a header row. An initial UTF-8 BOM is accepted. The same delimiter is used for both files; the default is comma. Supply an actual single character, such as `--delimiter ';'`; a two-character backslash escape such as `\t` is not a tab. Quote, NUL, CR, and LF are not valid delimiters.

The parser supports double-quoted fields, doubled quotes within quoted fields, CRLF/LF record endings, and quoted embedded newlines. All records must have the header's field count. Invalid UTF-8, NUL characters, malformed CSV, empty or duplicate headers, missing selected columns, and oversized fields fail as input errors. A quote inside an unquoted field, text or whitespace after a closing quote, and a blank record with the wrong field count are rejected. Fields are limited to 131,072 decoded characters. A header-only input represents zero data rows.

Headers and values are treated literally. No whitespace trimming, type inference, case folding, Unicode normalization, or deduplication occurs. CSV quoting is syntax: the parsed values `"abc"` and `abc` are equal. Leading zeros are preserved. A column name resembling SQL or a path has no executable meaning; the engine uses Python aggregation, not generated SQL.

Keys are ordered tuples of the selected columns. Both sides must select the same positive number of key columns, without selecting the same column twice on either side. Each `--left-key` pairs with the corresponding `--right-key`. A tuple is compared component by component; values are not concatenated with a separator.

## NULL values

The default NULL literal set is `['']`. Both an empty unquoted field and a quoted empty string parse to `''` and are NULL. `NULL`, `null`, `NA`, and a space are ordinary strings unless explicitly configured.

The first `--null-value` replaces the default list; repeated occurrences build the replacement list:

```sh
--null-value '' --null-value NULL
```

Matching is exact and case-sensitive. A row with a NULL in **any** key component is unmatchable. NULL-key rows never match each other. They contribute one row each to a left-join result when on the left, and zero to an inner-join result.

NULL-key rows are excluded from distinct-key and duplicate-key calculations. They are included in `null_key_rows` and `unmatched_rows`. `unmatched_keys` counts only distinct, non-NULL unmatched tuples, so it does not include NULL-key rows.

## Relationship expectations

The relationship describes uniqueness of the selected non-NULL keys across each entire input, not just the keys that find a match.

| Expected relationship | Required uniqueness |
| --- | --- |
| `one-to-one` | Both sides |
| `one-to-many` | Left side |
| `many-to-one` | Right side |
| `many-to-many` | Neither side |

For example, duplicate right-side keys violate `many-to-one` even if those keys do not appear on the left. A header-only or entirely NULL-key side has no duplicate non-NULL keys.

The observed relationship is the classification implied by whether each side has duplicate non-NULL keys. It is not proof that a many-to-many match actually occurred; duplicate groups on the two sides may be disjoint. Use the expansion metrics to see the actual matched multiplication.

A permissive relationship allows intentional repetition. It does not prove the amount is additive at the joined grain. Declare `--fail-on-expansion` when any repeated left row should block the workflow.

## Exact row-count formulas

Let `L[k]` and `R[k]` be the row counts of a non-NULL key tuple `k` on each side. Let `M` be the set of keys appearing on both sides, and `U_left` the number of unmatched left rows, including NULL-key rows.

```text
matched_output_rows = sum(L[k] * R[k] for k in M)
inner predicted_rows = matched_output_rows
left  predicted_rows = matched_output_rows + U_left

expansion_rows = sum(L[k] * (R[k] - 1) for k in M)
expanded_left_rows = sum(L[k] for k in M if R[k] > 1)
max_right_matches = max(R[k] for k in M), or 0 when M is empty
```

`expansion_rows` counts extra copies of matched left rows. It is not `predicted_rows - left.rows`: an inner join can drop some rows and repeat others at the same time. Likewise, right-side duplicates that match nothing do not contribute expansion.

At most ten expansion groups are shown, ordered by descending extra left copies and then lexicographically by key tuple to break ties. Each group reports its left and right counts, their product, and its extra left copies. Group identifiers are labels within a report, not durable identifiers across data revisions.

### Per-side counters

- `rows`: all data records
- `matchable_rows`: records with no NULL key components
- `null_key_rows`: records with at least one NULL key component
- `distinct_matchable_keys`: distinct non-NULL key tuples
- `duplicate_keys`: distinct non-NULL key tuples with more than one row
- `duplicate_excess_rows`: sum of `count - 1` across duplicate key groups
- `unmatched_rows`: non-NULL records with no matching tuple, plus NULL-key records
- `unmatched_keys`: distinct non-NULL tuples absent from the other input

## Exact amount arithmetic

`--amount COLUMN` selects one **left-side** amount column. Every data row must contain a valid amount, including unmatched and NULL-key rows. The setting does not convert currencies or infer units; the caller must ensure that summing this column is meaningful.

Amounts must be finite, plain base-10 decimal text with an optional sign, at most 38 digits in total and at most 18 digits after the decimal point. Digits are ASCII `0`–`9`; leading and trailing zeros count toward the limits. Forms such as `+12.50`, `-.5`, and `1.` are accepted; a decimal point alone is not. No surrounding whitespace, exponent notation, thousands separators, currency symbols, `NaN`, or infinities are accepted. NULL tokens configured for keys do not make an invalid amount acceptable. Normalize such data deliberately before auditing.

The engine uses integer fixed-point arithmetic, without binary floating point or rounding. Report amounts are canonical decimal **strings**, avoiding JSON floating-point precision loss. Formatting is not currency display formatting: insignificant trailing fractional zeros may be removed.

For a matched left row of amount `a` with `r` matching right rows:

```text
output contribution = a * r
signed duplicated contribution = a * (r - 1)
absolute duplicated contribution = abs(a) * (r - 1)
```

| Field | Meaning |
| --- | --- |
| `input_total` | Sum of all left amounts |
| `matched_input_total` | Sum of left amounts whose non-NULL key matches |
| `unmatched_input_total` | Sum of all other left amounts, including NULL-key rows |
| `output_total` | Predicted total after the selected join |
| `duplicated_signed_amount` | Signed sum of extra matched contributions |
| `duplicated_absolute_amount` | Sum of the absolute value of each extra contribution |
| `duplicated_left_rows` | Left input rows that will appear more than once |
| `extra_copies` | Total additional copies of those rows |
| `dropped_amount` | Signed unmatched amount removed by an inner join; zero for a left join |
| `net_change` | `output_total - input_total` |

For a left join, `net_change` equals `duplicated_signed_amount`. For an inner join it equals `duplicated_signed_amount - dropped_amount`. A negative dropped amount can increase the resulting total. Positive and negative duplicated amounts can cancel, and a zero-valued row can repeat without changing either monetary sum. Inspect the row counters as well.

## Quality rules and exit status

The declared relationship is a quality rule. Optional rules constrain predicted row count, unmatched rows, and expansion. Amount statistics explain impact; they do not establish business correctness.

- `--max-output-rows N` passes when `predicted_rows <= N`
- `--fail-on-expansion` passes when `expansion_rows == 0`, even if an inner join's final row count is smaller than its input
- `--fail-on-unmatched` passes only when both inputs have zero unmatched rows, including NULL-key rows; unused right-side lookup entries can therefore fail a left-join audit

For `audit` and `run`, the CLI returns `0` when all selected rules pass, `1` when an audit finishes but a rule fails, and `2` for an input, configuration, or output failure. `demo` returns `0` when it successfully creates its intentionally failing demonstration; user interruption returns `130`. A result with no declared failure does not imply that a downstream metric is meaningful. Reports are useful evidence for a decision, not approval to ignore the source grain.

## Determinism and privacy

For the same input content and configuration, JSON serialization is deterministic. Default exports omit source paths, headers, raw keys, rows, and hashes. Opt-in samples expose raw key components; they are for diagnosis and can be sensitive. The total raw-key sample budget is 0–100 across expansion groups, then unmatched-left keys, then unmatched-right keys. NULL-key rows are not sampled. Samples are bounded selections, not random or statistically representative samples.

A saved configuration serves a different purpose: it contains private paths and column names needed to run the audit again. The versioned JSON object uses `schema_version: 1`; duplicate or unknown fields, wrong types, and configurations larger than 1 MiB are rejected. Saved input paths are relative to the configuration directory where possible, with an absolute-path fallback for different Windows drives. `run` resolves relative inputs from the configuration directory. Report destinations are supplied separately on the command line and default to the current directory. Existing outputs require `--force`; input CSVs and the configuration being run remain protected. Report files are staged individually; publication of the entire set is not a multi-file transaction. See [Privacy](PRIVACY.md).

## Capacity and scope

CSV records are scanned incrementally. The engine retains counts and optional amount aggregates for distinct non-NULL keys, then calculates products with exact Python integers. Its memory requirement grows with distinct keys and key lengths, not the predicted join size. It does not materialize the join and it does not spill those aggregates to disk.

A highly duplicated file can therefore be inexpensive to audit even when its join would be enormous. A file containing millions of long unique keys can still require substantial memory. The predicted-row threshold is a quality policy; it is not a cap on ingestion memory. See [measured benchmarks](../benchmarks/RESULTS.md).

Only inner and left equality joins are supported. A preflight on extracts cannot prove properties of unseen source rows, changed files, arbitrary SQL predicates, a different NULL policy, or a downstream tool's implicit coercions.

### JSON integer consumers

Row/key counts are JSON integer literals computed with Python arbitrary-precision integers. A JavaScript `Number` loses integer precision above 9,007,199,254,740,991; consumers handling predictions above that range need a bigint-capable JSON parser. All monetary fields are decimal strings and must not be converted to binary floating point when exact arithmetic matters.
