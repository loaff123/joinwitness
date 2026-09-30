# JoinWitness

**See how a CSV join will multiply rows and amounts before you run it.**

JoinWitness is a local-first command-line preflight for developers and analysts. Give it two CSVs, the join keys, and the relationship you expect. It predicts the exact output size, checks duplicate and unmatched keys, and explains repeated left-side amounts in an offline HTML report and machine-readable JSON.

**Status:** version 0.1.0, released under the [MIT license](LICENSE). Install from this repository or a locally built wheel; no PyPI publication is claimed.

[简体中文](docs/README.zh-CN.md) · [Exact semantics](docs/SEMANTICS.md) · [Privacy](docs/PRIVACY.md) · [Alternatives](docs/COMPARISON.md)

## The mistake it catches

Four orders should still be four orders after adding customer information. If a customer appears three times in the lookup, their order appears three times after the join. Negative amounts can partly hide the damage.

For example, take these synthetic inputs:

**orders.csv**

```csv
order_id,customer_id,amount
O-1001,C001,100.00
O-1002,C002,90.00
O-1003,C003,-30.00
O-1004,C004,90.00
```

**customers.csv**

```csv
customer_id,segment
C001,Retail
C001,Wholesale
C001,Partner
C002,Retail
C002,Partner
C003,Retail
C003,Wholesale
C005,Prospect
```

A left join on `customer_id` produces:

| Check | Before | Predicted after |
| --- | ---: | ---: |
| Rows | 4 | 8 |
| Sum of left-side amount | 250 | 510 |

The four orders produce `3 + 2 + 2 + 1 = 8` rows. Repeated contributions add `260` to the total, while the absolute repeated amount is `320`: the duplicated negative amount masks part of the increase. C004 remains once without a match; C005 matches no order. A `many-to-one` expectation fails because the right key is not unique.

JoinWitness calculates this from per-key aggregates. It does not allocate the eight joined rows, or a billion-row cross-product for a larger mistake.

## Install

Requires Python 3.10 or newer. Clone the repository, then create a virtual environment:

```sh
git clone https://github.com/loaff123/joinwitness.git
cd joinwitness
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
joinwitness --help
```

Alternatively, install a wheel built from this repository:

```sh
python -m pip install /path/to/joinwitness-0.1.0-py3-none-any.whl
```

Auditing has no runtime network requirement. Installation may fetch Jinja2/MarkupSafe dependencies, and a source install may fetch build tooling. For a fully offline installation, obtain compatible dependency wheels first and use pip with `--no-index --find-links /path/to/wheelhouse`.

## Quickstart

Create a synthetic example and reports:

```sh
joinwitness demo --output demo
```

This creates `demo/orders.csv`, `demo/customers.csv`, `demo/audit.json`, `demo/report.html`, and `demo/report.json`. The directory must be new or empty. The command exits `0` on successful creation; its synthetic audit deliberately fails the `many-to-one` rule.

Audit your own files (this example uses `customer_id` on the left and `id` on the right):

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --right-key id \
  --expect many-to-one --how left \
  --amount amount \
  --html report.html --json report.json
```

Open `report.html` in your browser. It is self-contained and works offline. `report.json` is intended for automated checks and review tooling. A completed audit can return exit code `1` because it found a quality problem; that does not mean parsing failed.

### Save a repeatable policy

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --right-key id \
  --expect many-to-one --how left \
  --amount amount --fail-on-expansion \
  --html report.html --json report.json \
  --save-config audit.json

joinwitness run audit.json --force
```

**Keep configuration files private.** Unlike the default reports, a saved configuration contains source paths and column names. Review it before committing or sharing it. Saved input paths are relative to the configuration directory when possible, with absolute paths used across Windows drives. Reruns resolve inputs from that directory.

Report destinations are CLI options, not saved configuration fields. Both `audit` and `run` default to `report.html` and `report.json` in the current directory. Existing outputs require `--force`; even with it, input CSVs and the configuration being run cannot be overwritten. Output directories must already exist. Use new `--html`/`--json` paths instead when you want to preserve the earlier reports.

### Composite keys

Repeat the key flags in the same order on both sides:

```sh
joinwitness audit orders.csv customers.csv \
  --left-key customer_id --left-key region \
  --right-key id --right-key region \
  --expect many-to-one --how left \
  --html report.html
```

This compares `(customer_id, region)` with `(id, region)`. A NULL in either component makes the row unmatched.

### Controls worth knowing

| Option | Purpose |
| --- | --- |
| `--expect` | Declare `one-to-one`, `one-to-many`, `many-to-one`, or `many-to-many` |
| `--how` | Predict an `inner` or `left` equality join |
| `--amount` | Track an exact numeric amount from the left input |
| `--max-output-rows N` | Fail if predicted rows exceed the allowed maximum |
| `--fail-on-unmatched` | Fail on unmatched rows in either input, including NULL-key rows |
| `--fail-on-expansion` | Fail if a matched left row would be repeated |
| `--delimiter ';'` | Use a literal single-character delimiter for both inputs |
| `--null-value VALUE` | Set an exact NULL token; repeat for multiple tokens |
| `--samples N` | Opt in to at most N raw key samples across the report, from 0 to 100 |

The default NULL list is only the empty string, including quoted empty CSV fields. Supplying any `--null-value` replaces that list. To treat both blank and `NULL` as missing, use `--null-value '' --null-value NULL`. The literal `NA` remains a normal key unless you configure it otherwise.

### Exit codes for scripts and CI

- `0`: all declared quality rules passed
- `1`: audit completed, but at least one quality rule failed
- `2`: invalid input or configuration, or an output error

The `demo` command is the deliberate exception above; interruption returns `130`. Use the audit/run exit code to stop downstream work, and retain the report to explain the failure. An audit checks the files you supplied; it cannot guarantee that a later join on changed inputs will behave the same way.

## What the report tells you

- The declared relationship and observed key uniqueness
- Predicted output rows, unmatched rows, and extra copies of matched left rows
- Duplicate-key counts on both inputs, including keys that never match
- The largest expansion groups, without raw keys by default
- With `--amount`: input and output totals, signed and absolute duplicated contributions, and amounts dropped by an inner join
- Pass/fail results for the selected rules

A zero net amount change does not prove safety. Positive and negative values can cancel. JoinWitness reports repeated-row counts and absolute duplicated contributions as well as signed totals.

## Where it fits

Use JoinWitness before enriching orders with customers, attaching categories to transactions, reviewing a supplier extract, or promoting a CSV-based data workflow. It is useful when someone needs to review the join's consequences without opening a notebook or receiving the source data.

Existing tools already validate joins well. pandas provides relationship validation and merge indicators; qsv provides a broad CSV join CLI; getchatdata includes a local join-audit helper. JoinWitness packages a narrower preflight into a report-and-policy workflow. See the [source-backed comparison](docs/COMPARISON.md) to choose the right tool.

## Deliberate boundaries

- **Exact text keys.** No automatic number/date conversion, trimming, case folding, or Unicode normalization. `001`, `1`, and `1 ` are different keys.
- **SQL-style NULL matching.** A key with any configured NULL component never matches another row, including another NULL row.
- **Two UTF-8 CSVs.** Optional UTF-8 BOM, quoted fields/newlines, and a chosen delimiter are supported. Malformed input is rejected instead of silently repaired.
- **Inner and left equality joins only.** No right/full/as-of/fuzzy joins, expressions, Excel inputs, or database connections.
- **No join execution or automatic fixes.** Resolve the source grain or key choice in your own pipeline and rerun.
- **Memory grows with distinct keys.** Inputs are scanned incrementally, but per-key aggregates stay in memory. This is not an out-of-core engine. [Benchmark results](benchmarks/RESULTS.md) describe measured workloads, not a universal capacity promise.

See [semantics](docs/SEMANTICS.md) for counting formulas, monetary limits, and strict CSV rules.

## Privacy and review

Runtime auditing is local, with no telemetry, hosted backend, or network calls. Inputs are read without modification. Default HTML and JSON omit source paths, column names, raw keys, rows, and hashes. Counts, relationships, and monetary totals can still be sensitive.

`--samples` deliberately adds raw keys. Saved configuration files and local error messages can reveal paths or headers. Review what you share and where you save it. See [Privacy](docs/PRIVACY.md) and [Security](SECURITY.md).

## Development and release status

See [Contributing](CONTRIBUTING.md) for checks and fixtures, and [Changelog](CHANGELOG.md) for release scope. See [verification evidence](docs/VERIFICATION.md) and [GitHub Actions](https://github.com/loaff123/joinwitness/actions) for actual platform checks.

JoinWitness is licensed under [MIT](LICENSE).
