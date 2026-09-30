# Privacy and data handling

JoinWitness audits local CSV files. Its runtime does not call a hosted service, use an AI model, send telemetry, or fetch remote assets for reports. It reads the supplied inputs without changing them.

Local-first operation does not make every output safe to publish. Choose the output directory deliberately and review files before sharing them.

## What each output contains

| Artifact | Default content | Potentially sensitive content |
| --- | --- | --- |
| HTML report | Counts, relationships, rule results, anonymous expansion groups, optional amount totals | Aggregate business volumes and amounts |
| JSON report | Structured audit results and version fields | The same aggregates as HTML |
| Report with `--samples N` | Default content plus bounded raw key samples | Customer IDs, account numbers, emails, or any other data used as a key |
| Saved configuration | Input locations, selected column names, and audit settings | Paths, internal naming, and configured NULL literals |
| Local error output | Information needed to diagnose an input/configuration/output failure | Paths, column names, and filesystem details may appear |

Default HTML and JSON do **not** export source paths, source column names, raw keys, complete source rows, or hashes of keys or files. They still reveal the number of rows and distinct keys, matching patterns, join policy, and requested amount totals. These can be commercially or personally sensitive, particularly for small populations. No anonymity guarantee or formal privacy mechanism is provided.

## Samples are an explicit disclosure choice

No raw key samples are included unless `--samples` is greater than zero. Once enabled, raw components may appear in both report formats. Samples can identify people even when other columns are excluded. Review the entire report before sending it, and do not assume that limiting the sample count makes it anonymous.

Sampling limits report detail, not the data examined: the audit still processes all records. Samples are deterministic diagnostic selections rather than a representative sample.

## Configuration is private working material

`--save-config audit.json` creates a reusable run configuration. It is **not** a sanitized report. It needs file paths and column names to repeat the job and may contain absolute paths that reveal usernames or project names.

Before committing a configuration, replace private locations with intentional project-relative ones if appropriate, inspect every field, and confirm the referenced outputs are safe. Do not put credentials in file names, column names, command arguments, or configuration.

## Storage and cleanup

Reports and configurations are ordinary local files. JoinWitness does not encrypt them, choose a retention period, or manage permissions for other users of the machine. Your filesystem, backups, sync clients, shell history, CI logs, and browser extensions can have their own behavior.

- Save sensitive reports outside publicly served or automatically shared directories
- Restrict filesystem access using your normal local controls
- Avoid capturing private error messages or sample-bearing reports in public issue reports
- Remove files using your organization's retention rules when no longer needed
- Use synthetic fixtures when asking for help

Installers and developer tooling are separate from runtime auditing. Installing from source may contact package indexes for build dependencies; an offline wheel installation requires compatible wheels for JoinWitness and its dependencies, installed with `--no-index --find-links`.

## Trust boundary

JoinWitness does not execute spreadsheet formulas, SQL, or commands from CSV cells. The generated report treats displayed data as text. Even so, handle untrusted CSVs in an appropriate local environment: distinct-key memory usage is unbounded by a fixed data-size quota, and very large inputs can consume resources.

A saved configuration determines which local files are read; CLI output flags determine where artifacts are written. Review configurations from other people before running them. Local runtime behavior does not validate the trustworthiness of the distribution you installed or of unrelated software on the same machine.

See [Security](../SECURITY.md) for reporting concerns and [Semantics](SEMANTICS.md) for the precise parsing and output contracts.
