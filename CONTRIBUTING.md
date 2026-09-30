# Contributing to JoinWitness

JoinWitness is an MIT-licensed open-source project. Open an issue for a bug or focused proposal, and submit a pull request with synthetic fixtures and reproducible checks.

## Development setup

Use Python 3.10 or newer in a virtual environment. From the project root:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. Read the actual checks configured in `pyproject.toml` and `.github/workflows` before changing them.

## Before proposing a change

1. Describe the input, intended relationship, join type, and expected outcome
2. Add a small, synthetic reproducer with hand-checkable counts
3. Add or update tests, then make the smallest change that addresses the behavior
4. Run the project's test, lint, type, and build checks
5. Update the English and Chinese guides when user-visible behavior changes
6. Include actual command results and platform details; do not infer a passed CI run from a workflow file

Typical local checks:

```sh
python -m pytest
python -m ruff check .
python -m mypy src
python -m build
```

Use only synthetic or explicitly approved fixtures. Do not commit private input files, sample-bearing reports, saved configurations with private paths, credentials, or local execution logs.

## Correctness contracts

Read [Semantics](docs/SEMANTICS.md) before changing the engine. Preserve:

- Exact text key equality and SQL-style NULL behavior, including composite keys
- Uniqueness checks over all non-NULL keys, not only matched keys
- Strict CSV errors rather than skipped or silently repaired records
- Separate counters for unmatched rows, repeated rows, and net output size
- Exact decimal arithmetic, signed and absolute repetition, and zero-sum cases
- Deterministic JSON and privacy-default exports
- No modification of input files or materialization of join cross-products
- Exit codes that distinguish quality failures from input/configuration/output failures

Property tests should compare small generated inputs with an independent explicit reference join. Include empty/header-only inputs, NULL components, repeated keys on either side, disjoint duplicate groups, Unicode, leading zeros, embedded CSV newlines, malformed rows, and zero/negative amounts.

For reports, test malicious-looking keys as text and inspect both wide and narrow layouts. Do not add remotely loaded fonts, scripts, styles, analytics, or assets to an offline report.

## Scope and dependencies

The initial scope is two UTF-8 CSVs and inner/left equality joins. Propose larger changes before implementing them. Any new normalization, coercion, NULL convention, report detail, or default quality policy can change results or disclosure risk and requires explicit documentation and regression tests.

Avoid dependencies without a concrete benefit. A performance change must preserve semantics and report both workload and measured resource use. Do not claim “large-file support” from a highly duplicated benchmark alone: distinct-key cardinality drives memory use.

## Reporting issues

Share the version, Python/platform details, command with private paths replaced, expected result, actual result, and a minimal synthetic fixture in a GitHub issue. A report's aggregate counts and amounts may themselves be sensitive. See [Security](SECURITY.md) for vulnerabilities.

## Release checklist

For each release, verify built wheel and source archive contents, clean installation, CLI examples, offline report behavior, and actual supported-platform checks. Package-registry publication is a separate maintainer action. Never publish real customer data or private configuration with a demo.
