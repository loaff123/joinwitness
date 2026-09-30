# Verification

This document records local verification of version 0.1.0. Check the repository Actions page for hosted CI results on a specific commit. No PyPI publication is claimed.

## Verified here

Environment: Linux x86_64, Python 3.12.14.

- Full pytest suite, including generated small materialized-reference joins and an independent mixed-scale Decimal reference
- Ruff lint and strict mypy on every production module
- UTF-8/BOM, quoted delimiters/newlines, composite keys, exact Unicode and leading-zero behavior, NULL key components, strict malformed-input failures
- Signed/zero-sum and high-precision monetary arithmetic, global relationship rules, bounded samples, deterministic JSON
- Default omission of paths, headers, raw keys and hashes; hostile sample HTML escaping; script-free CSP and no remote report assets
- Input preservation, hardlink/symlink alias protection, safe config reruns, malformed/deep JSON errors, file-output collisions
- Wheel and source-distribution builds; wheel installation in a fresh virtual environment outside the source directory; installed CLI help and computed demo
- Scale checks reported separately in [benchmark results](../benchmarks/RESULTS.md), including a 10-billion-row prediction without constructing those rows

## Not verified here

- Windows/macOS execution. CI is configured for Ubuntu and Windows, Python 3.10/3.12/3.13, but no hosted CI runs have occurred
- Actual browser screenshots or visual layout inspection. Headless Chromium cannot create its singleton socket in this execution environment; the cloud browser rejects local file/loopback previews. Template behavior and privacy are tested, but desktop/mobile visual QA remains a release check
- External security audit, trademark clearance, public package-name reservation, performance on user datasets, or arbitrarily large distinct-key inputs

## Re-run

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m mypy src/joinwitness
python -m build
```

Open `examples/demo/report.html` in a desktop and mobile browser before public launch. Review default reports separately from opt-in sample reports. Reports are exact for the input state actually read; do not modify input files during an audit.
