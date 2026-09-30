# Security policy

JoinWitness is an early-stage local tool. No dedicated private vulnerability-reporting channel or response-time guarantee is currently offered. For a suspected vulnerability, open an issue requesting a private reporting channel without including exploit details or sensitive data; wait for maintainer guidance before sharing them.

## What to include

- JoinWitness version, Python version, and operating system
- The affected command or behavior
- A minimal synthetic reproducer
- Expected and actual behavior, including whether data could be exposed or files damaged
- Any suggested mitigation

Remove source paths, column names, raw key samples, private amount totals, and credentials unless they are essential and the recipient is authorized to receive them. Avoid sending actual input data.

## Security boundaries

The CLI reads local files and writes requested reports/configuration. It has no runtime network service, telemetry, remote model call, SQL execution, or spreadsheet formula evaluation. Default reports omit source identifiers, but aggregate information can still be sensitive. Opt-in samples expose raw keys, and saved configurations contain private paths and headers. See [Privacy](docs/PRIVACY.md).

Treat untrusted CSVs and configurations as untrusted input. A malformed input should produce a controlled error, not silent data repair. Very large or high-cardinality inputs can exhaust memory or disk resources. The field-size limit reduces one risk; it does not impose an overall resource budget. Run the tool with normal least-privilege filesystem access and appropriate resource limits.

Generated HTML must display data as escaped text and remain self-contained. Vulnerabilities that execute input content, disclose excluded fields, overwrite inputs unexpectedly, or compromise exact results are important to report.

## Supported versions and disclosure

The latest 0.1.x source version is the current evaluation target. No production support or patch window is promised. Do not post exploit details or private data in public issues.
