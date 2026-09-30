"""Terminal entry point; quality failures still produce reviewable reports."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from . import __version__
from .config import dump_config, load_config
from .demo import prepare_demo
from .models import AuditConfig, InputError, JoinType, Relationship
from .output import validate_outputs, write_outputs

RELATIONSHIPS = ('one-to-one', 'one-to-many', 'many-to-one', 'many-to-many')


def _outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--html', type=Path, default=Path('report.html'), help='offline report path (default: report.html)')
    parser.add_argument('--json', default='report.json', help='deterministic JSON path, or - for stdout (default: report.json)')
    parser.add_argument('--force', action='store_true', help='replace existing output files, never input CSVs/config')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='joinwitness', description='See CSV join cardinality and monetary duplication before you join.')
    parser.add_argument('--version', action='version', version=f'JoinWitness {__version__}')
    commands = parser.add_subparsers(dest='command', required=True)
    audit = commands.add_parser('audit', help='preflight two CSV inputs without materializing a join')
    audit.add_argument('left', type=Path)
    audit.add_argument('right', type=Path)
    audit.add_argument('--left-key', action='append', required=True, help='left key column; repeat for a composite key')
    audit.add_argument('--right-key', action='append', required=True, help='right key column; repeat in matching order')
    audit.add_argument('--expect', choices=RELATIONSHIPS, default='many-to-one', help='required relationship (default: many-to-one)')
    audit.add_argument('--how', choices=('inner', 'left'), default='left', help='join type (default: left)')
    audit.add_argument('--amount', help='left monetary column, using exact plain decimal amounts')
    audit.add_argument('--delimiter', default=',', help='one literal delimiter character (default: comma)')
    audit.add_argument('--null-value', action='append', help='literal null token; repeat to replace the default empty-string token')
    audit.add_argument('--samples', type=int, default=0, help='opt in to up to N raw key samples (0–100; default: 0)')
    audit.add_argument('--max-output-rows', type=int, help='fail a quality rule above this predicted row count')
    audit.add_argument('--fail-on-unmatched', action='store_true', help='fail if either input has unmatched rows, including NULL keys')
    audit.add_argument('--fail-on-expansion', action='store_true', help='fail if any left row is repeated by multiple right matches')
    audit.add_argument('--save-config', type=Path, help='save private paths, column names and rules for reruns')
    _outputs(audit)
    run = commands.add_parser('run', help='rerun a versioned JSON configuration')
    run.add_argument('config', type=Path)
    _outputs(run)
    demo = commands.add_parser('demo', help='create and analyze a synthetic four-order example')
    demo.add_argument('--output', type=Path, default=Path('joinwitness-demo'), help='new or empty output directory')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        # Delay imports so --help/version work independently of report execution.
        from .engine import audit
        from .report import render_report

        save_config: Path | None = None
        protected: list[Path] = []
        demo = args.command == 'demo'
        if demo:
            config = prepare_demo(args.output)
            html_path = args.output / 'report.html'
            json_destination = str(args.output / 'report.json')
            force = False
        elif args.command == 'run':
            config = load_config(args.config)
            protected.append(args.config)
            html_path, json_destination, force = args.html, args.json, args.force
        else:
            config = AuditConfig(
                left=args.left, right=args.right,
                left_keys=tuple(args.left_key), right_keys=tuple(args.right_key),
                relationship=cast(Relationship, args.expect), join_type=cast(JoinType, args.how),
                amount_column=args.amount, delimiter=args.delimiter,
                null_values=tuple(args.null_value) if args.null_value is not None else ('',),
                sample_limit=args.samples, max_output_rows=args.max_output_rows,
                fail_on_unmatched=args.fail_on_unmatched, fail_on_expansion=args.fail_on_expansion,
            )
            save_config = args.save_config
            html_path, json_destination, force = args.html, args.json, args.force
        protected.extend((config.left, config.right))
        paths = [html_path]
        if json_destination != '-':
            paths.append(Path(json_destination))
        if save_config:
            paths.append(save_config)
        validate_outputs(paths, protected, force)
        result = audit(config)
        json_text = json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n'
        files = [(html_path, render_report(result))]
        if json_destination != '-':
            files.append((Path(json_destination), json_text))
        if save_config:
            files.append((save_config, dump_config(config, save_config)))
        write_outputs(files, protected, force)
        stream = sys.stderr if json_destination == '-' else sys.stdout
        if json_destination == '-':
            print(json_text, end='')
        verdict = 'PASS' if result.passed else 'NEEDS REVIEW'
        print(f'{verdict} | Predicted {result.predicted_rows:,} rows from {result.left.rows:,} left rows', file=stream)
        print(f'HTML report: {html_path}', file=stream)
        if save_config:
            print('Saved rerun configuration contains source paths and column names. Keep it private.', file=stream)
        if demo:
            print('Synthetic demo created. Its many-to-one rule intentionally fails; run the saved audit to get exit 1.', file=stream)
            return 0
        return 0 if result.passed else 1
    except (InputError, OSError, UnicodeError) as exc:
        print(f'joinwitness: {exc}', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('joinwitness: interrupted', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
